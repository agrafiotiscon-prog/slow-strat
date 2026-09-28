"""Candidate strategies.  Every function takes M5 execution bars (UTC, bid)
and returns engine.Signals aligned to those bars.

Signals are evaluated on COMPLETED bars of the signal timeframe and executed
at the open of the first execution bar after that bar closes, exactly like an
EA that evaluates on the first tick of a new bar.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import data as D
import indicators as I
from engine import Signals, StratParams

TF = {"M5": "5min", "M15": "15min", "M30": "30min", "H1": "1h", "H4": "4h", "D1": "1D"}


_TFC = {}


def server_time(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Typical MT5 broker server clock: New York + 7h (GMT+2 winter, GMT+3 summer)."""
    return ny_time(idx) + pd.Timedelta(hours=7)


def bars_tf(m5: pd.DataFrame, tf: str) -> pd.DataFrame:
    """Higher-timeframe bars as an MT5 broker on NY-close server time builds them.
    Returned index is the bar OPEN time in UTC."""
    if tf == "M5":
        return m5
    key = (id(m5), len(m5), m5.index[0], tf)
    if key in _TFC:
        return _TFC[key]
    if tf in ("H4", "D1"):
        st = server_time(m5.index)
        x = m5.copy()
        x["utc"] = m5.index
        x.index = st
        agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum", "utc": "first"}
        b = x.resample(TF[tf]).agg(agg).dropna(subset=["open"])
        # scheduled open time of the server bar, converted back to UTC
        nyo = (b.index - pd.Timedelta(hours=7)).tz_localize("America/New_York", ambiguous="NaT",
                                                            nonexistent="shift_forward")
        utc_open = nyo.tz_convert("UTC").tz_localize(None)
        utc_open = pd.DatetimeIndex(np.where(pd.isna(utc_open), b.utc.values, utc_open))
        b.index = utc_open
        b = b.drop(columns="utc")
        b = b[~b.index.duplicated(keep="last")].sort_index()
    else:
        b = D.resample(m5, TF[tf])
    _TFC[key] = b
    return b


def exec_pos(sig_index: pd.DatetimeIndex, tf: str, exec_index: pd.DatetimeIndex) -> np.ndarray:
    """Execution bar position for each signal bar: the first execution bar that opens
    at/after the signal bar's scheduled close (EA acts on the first tick of the next bar)."""
    close_t = sig_index + pd.Timedelta(TF[tf])
    # never enter inside the rollover window (16:30-18:30 NY): wait until 18:30 NY
    ny = ny_time(close_t)
    mins = ny.hour * 60 + ny.minute
    inside = (mins >= 16 * 60 + 30) & (mins < 18 * 60 + 30)
    if inside.any():
        target = ny.normalize() + pd.Timedelta(hours=18, minutes=30)
        tu = target.tz_localize("America/New_York", ambiguous="NaT", nonexistent="shift_forward") \
                   .tz_convert("UTC").tz_localize(None)
        close_t = pd.DatetimeIndex(np.where(inside, tu, close_t))
    pos = np.searchsorted(exec_index.values, close_t.values, side="left")
    # if that lands on a blocked bar (e.g. Sunday re-open), roll forward to the next open bar
    nxt = _next_unblocked(exec_index)
    ok = pos < len(exec_index)
    pos[ok] = nxt[pos[ok]]
    return pos


_NXT = {}


def _next_unblocked(idx: pd.DatetimeIndex) -> np.ndarray:
    key = (len(idx), idx[0], idx[-1])
    if key not in _NXT:
        ny = ny_time(idx)
        mins = ny.hour * 60 + ny.minute
        blocked = (mins >= 16 * 60 + 30) & (mins < 18 * 60 + 30)
        n = len(idx)
        nxt = np.arange(n)
        j = n
        for i in range(n - 1, -1, -1):
            if not blocked[i]:
                j = i
            nxt[i] = j
        _NXT[key] = nxt
    return _NXT[key]


def place(n: int, pos: np.ndarray, values: np.ndarray, dtype=np.float64) -> np.ndarray:
    out = np.zeros(n, dtype)
    ok = (pos < n) & (values != 0) & ~pd.isna(values)
    out[pos[ok]] = values[ok]
    return out


def _empty(n):
    return np.zeros(n, np.int64), np.zeros(n), np.zeros(n), np.zeros(n, np.int64)


def ny_time(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    return idx.tz_localize("UTC").tz_convert("America/New_York").tz_localize(None)


def spread_model(bars: pd.DataFrame, bps: float = 0.8, floor: float = 0.20, roll_mult: float = 5.0) -> np.ndarray:
    """Gold spread: ~0.8bp of price (0.32 at $4000), 5x from 16:45 to 18:30 New York
    (the daily break / rollover, when broker spreads blow out)."""
    sp = np.maximum(bars.close.values * bps * 1e-4, floor)
    ny = ny_time(bars.index)
    mins = ny.hour * 60 + ny.minute
    roll = (mins >= 16 * 60 + 45) & (mins < 18 * 60 + 30)
    return np.where(roll, sp * roll_mult, sp)


def rollover_block(idx: pd.DatetimeIndex, before_min: int = 30, after_min: int = 90) -> np.ndarray:
    """True for bars inside the no-entry window around the 17:00 NY rollover."""
    ny = ny_time(idx)
    mins = ny.hour * 60 + ny.minute
    return (mins >= 17 * 60 - before_min) & (mins < 17 * 60 + after_min)


def session_ok(idx: pd.DatetimeIndex, start_h: float, end_h: float) -> np.ndarray:
    h = idx.hour + idx.minute / 60.0
    if start_h <= end_h:
        return (h >= start_h) & (h < end_h)
    return (h >= start_h) | (h < end_h)


# ---------------------------------------------------------------------------
# A. RSI(2)-style pullback in the direction of the trend (mean reversion)
# ---------------------------------------------------------------------------
def rsi_pullback(m5, tf="H1", rsi_n=2, lo=10.0, hi=90.0, trend_n=200, exit_rsi=None,
                 exit_ma=5, sl_atr=3.0, tp_atr=0.0, atr_n=14, max_hold=0, sides="both",
                 sess=None, params=None, name="rsi_pb"):
    b = bars_tf(m5, tf)
    c = b.close
    r = I.rsi(c, rsi_n)
    tr = I.sma(c, trend_n)
    a = I.atr(b, atr_n)
    long_ = (c > tr) & (r < lo)
    short = (c < tr) & (r > hi)
    if sides == "long":
        short[:] = False
    elif sides == "short":
        long_[:] = False
    if sess is not None:
        ok = session_ok(b.index + pd.Timedelta(TF[tf]), *sess)
        long_ &= ok
        short &= ok
    d = np.where(long_, 1, np.where(short, -1, 0))
    # exits: long exits when close > MA(exit_ma) (or RSI > exit_rsi)
    if exit_rsi is not None:
        xl = r > exit_rsi
        xs = r < 100 - exit_rsi
    else:
        m = I.sma(c, exit_ma)
        xl = c > m
        xs = c < m
    ex = np.where(xl & xs, 2, np.where(xl, 1, np.where(xs, -1, 0)))
    n = len(m5)
    pos = exec_pos(b.index, tf, m5.index)
    sd = place(n, pos, d.astype(np.float64)).astype(np.int64)
    sl = place(n, pos, (a * sl_atr).values)
    tp = place(n, pos, (a * tp_atr).values) if tp_atr > 0 else np.zeros(n)
    sx = place(n, pos, ex.astype(np.float64)).astype(np.int64)
    # never exit on the same bar we enter in the same direction
    sx = np.where((sd != 0) & (sx == sd), 0, sx)
    p = params or StratParams()
    if max_hold:
        p.max_hold = int(max_hold * pd.Timedelta(TF[tf]) / pd.Timedelta("5min"))
    return Signals(name, sd, sl, tp, sx, p)


# ---------------------------------------------------------------------------
# B. Asian-range breakout during London / NY
# ---------------------------------------------------------------------------
def asian_breakout(m5, rng_start=0, rng_end=6, trade_end=12, sl_mode="range", sl_k=1.0,
                   tp_k=1.0, min_rng_atr=0.3, max_rng_atr=2.0, atr_n=14, one_per_day=True,
                   trend_filter=0, flat_h=None, d1_mode="utc", params=None, name="asia_bo"):
    n = len(m5)
    idx = m5.index
    day = idx.normalize()
    h = idx.hour + idx.minute / 60.0
    in_rng = (h >= rng_start) & (h < rng_end)
    df = pd.DataFrame({"day": day, "h": m5.high.values, "l": m5.low.values}, index=idx)
    rh = df[in_rng].groupby("day").h.max()
    rl = df[in_rng].groupby("day").l.min()
    RH = rh.reindex(day).values
    RL = rl.reindex(day).values
    if d1_mode == "utc":
        d1 = D.resample(m5, "1D")
        a = I.atr(d1, atr_n).shift(1)  # yesterday's daily ATR
        A = a.reindex(day).values
        if trend_filter:
            ma = I.ema(d1.close, trend_filter).shift(1).reindex(day).values
            pc = d1.close.shift(1).reindex(day).values
    else:
        # broker (server-time) daily bars: use the last D1 bar completed before this UTC day starts
        d1 = bars_tf(m5, "D1")
        known_t = d1.index + pd.Timedelta("1D")
        def asof(series):
            sr = pd.Series(series.values, index=known_t)
            sr = sr[~sr.index.duplicated(keep="last")].sort_index()
            return sr.reindex(day.unique(), method="ffill").reindex(day).values
        A = asof(I.atr(d1, atr_n))
        if trend_filter:
            ma = asof(I.ema(d1.close, trend_filter))
            pc = asof(d1.close)
    tr_ok_l = np.ones(n, bool)
    tr_ok_s = np.ones(n, bool)
    if trend_filter:
        tr_ok_l = pc > ma
        tr_ok_s = pc < ma
    rng = RH - RL
    ok = (rng >= min_rng_atr * A) & (rng <= max_rng_atr * A)
    window = (h >= rng_end) & (h < trade_end)
    c = m5.close.values
    # signal on bar close -> enter next bar open
    up = window & ok & (c > RH) & tr_ok_l
    dn = window & ok & (c < RL) & tr_ok_s
    sd = np.zeros(n, np.int64)
    sl = np.zeros(n)
    tp = np.zeros(n)
    taken = set()
    for i in np.flatnonzero(up | dn):
        if i + 1 >= n:
            break
        dkey = day[i]
        if one_per_day and dkey in taken:
            continue
        taken.add(dkey)
        dirn = 1 if up[i] else -1
        if sl_mode == "range":
            sld = rng[i] * sl_k
        else:
            sld = A[i] * sl_k
        sd[i + 1] = dirn
        sl[i + 1] = sld
        tp[i + 1] = rng[i] * tp_k if tp_k > 0 else 0
    sx = np.zeros(n, np.int64)
    if flat_h is not None:
        fl = (h >= flat_h) & (np.r_[0, h[:-1]] < flat_h)
        sx[fl] = 2
    return Signals(name, sd, sl, tp, sx, params or StratParams())


# ---------------------------------------------------------------------------
# C. Trend pullback to EMA (continuation)
# ---------------------------------------------------------------------------
def trend_pullback(m5, tf="H1", fast=20, slow=50, htf="H4", htf_n=50, atr_n=14,
                   touch_atr=0.25, sl_atr=1.5, tp_r=2.0, sess=None, params=None, name="trend_pb"):
    b = bars_tf(m5, tf)
    hb = bars_tf(m5, htf)
    c = b.close
    ef = I.ema(c, fast)
    es = I.ema(c, slow)
    a = I.atr(b, atr_n)
    hma = I.ema(hb.close, htf_n)
    # htf trend known at close of htf bar -> ffill onto tf bars that close after it
    hclose_t = hb.index + pd.Timedelta(TF[htf])
    htrend = pd.Series(np.sign(hb.close - hma).values, index=hclose_t)
    tclose_t = b.index + pd.Timedelta(TF[tf])
    ht = htrend.reindex(tclose_t, method="ffill").values
    up = (ef > es).values & (ht > 0)
    dn = (ef < es).values & (ht < 0)
    touched_l = (b.low <= ef + touch_atr * a).values & (c > ef).values & (c > b.open).values
    touched_s = (b.high >= ef - touch_atr * a).values & (c < ef).values & (c < b.open).values
    d = np.where(up & touched_l, 1, np.where(dn & touched_s, -1, 0))
    if sess is not None:
        d = np.where(session_ok(tclose_t, *sess), d, 0)
    n = len(m5)
    pos = exec_pos(b.index, tf, m5.index)
    sd = place(n, pos, d.astype(np.float64)).astype(np.int64)
    sl = place(n, pos, (a * sl_atr).values)
    tp = place(n, pos, (a * sl_atr * tp_r).values) if tp_r > 0 else np.zeros(n)
    return Signals(name, sd, sl, tp, None, params or StratParams())


# ---------------------------------------------------------------------------
# D. Donchian breakout with ATR trailing (trend following)
# ---------------------------------------------------------------------------
def donchian_bo(m5, tf="H4", n_entry=20, atr_n=20, sl_atr=2.0, trail_r=1.0, trail_start=1.0,
                tp_atr=0.0, sides="both", params=None, name="donch"):
    b = bars_tf(m5, tf)
    hi, lo = I.donchian(b, n_entry)
    hi = hi.shift(1)
    lo = lo.shift(1)
    a = I.atr(b, atr_n)
    c = b.close
    d = np.where(c > hi, 1, np.where(c < lo, -1, 0))
    if sides == "long":
        d = np.where(d > 0, d, 0)
    n = len(m5)
    pos = exec_pos(b.index, tf, m5.index)
    sd = place(n, pos, d.astype(np.float64)).astype(np.int64)
    sl = place(n, pos, (a * sl_atr).values)
    tp = place(n, pos, (a * tp_atr).values) if tp_atr > 0 else np.zeros(n)
    p = params or StratParams(trail_r=trail_r, trail_start=trail_start)
    return Signals(name, sd, sl, tp, None, p)


# ---------------------------------------------------------------------------
# E. Previous-day high/low sweep and reclaim (failed breakout reversal)
# ---------------------------------------------------------------------------
def pdhl_sweep(m5, tf="M15", atr_n=14, sl_buf_atr=0.3, tp_r=1.5, sess=(7, 17), min_sweep_atr=0.05,
               max_sweep_atr=1.0, params=None, name="sweep"):
    b = bars_tf(m5, tf)
    d1 = D.resample(m5, "1D")
    pdh = d1.high.shift(1)
    pdl = d1.low.shift(1)
    day = b.index.normalize()
    PDH = pdh.reindex(day).values
    PDL = pdl.reindex(day).values
    a = I.atr(b, atr_n).values
    hi = b.high.values
    lo = b.low.values
    c = b.close.values
    o = b.open.values
    short = (hi > PDH + min_sweep_atr * a) & (hi < PDH + max_sweep_atr * a) & (c < PDH) & (c < o)
    long_ = (lo < PDL - min_sweep_atr * a) & (lo > PDL - max_sweep_atr * a) & (c > PDL) & (c > o)
    tclose = b.index + pd.Timedelta(TF[tf])
    ok = session_ok(tclose, *sess)
    d = np.where(long_ & ok, 1, np.where(short & ok, -1, 0))
    # SL beyond the sweep extreme
    sld = np.where(d == 1, c - lo + sl_buf_atr * a, np.where(d == -1, hi - c + sl_buf_atr * a, 0))
    n = len(m5)
    pos = exec_pos(b.index, tf, m5.index)
    sd = place(n, pos, d.astype(np.float64)).astype(np.int64)
    sl = place(n, pos, sld)
    tp = place(n, pos, sld * tp_r)
    return Signals(name, sd, sl, tp, None, params or StratParams())


# ---------------------------------------------------------------------------
# F. Bollinger fade in low-trend regime
# ---------------------------------------------------------------------------
def bb_fade(m5, tf="H1", n=20, k=2.0, adx_n=14, adx_max=20, sl_atr=1.5, atr_n=14, tp_mid=True,
            max_hold=24, params=None, name="bbfade"):
    b = bars_tf(m5, tf)
    lo, mid, hi = I.bands(b.close, n, k)
    ax = I.adx(b, adx_n)
    a = I.atr(b, atr_n)
    c = b.close
    rng_ok = ax < adx_max
    d = np.where(rng_ok & (c < lo), 1, np.where(rng_ok & (c > hi), -1, 0))
    xl = c > mid
    xs = c < mid
    ex = np.where(xl, 1, np.where(xs, -1, 0))
    N = len(m5)
    pos = exec_pos(b.index, tf, m5.index)
    sd = place(N, pos, d.astype(np.float64)).astype(np.int64)
    sl = place(N, pos, (a * sl_atr).values)
    sx = place(N, pos, ex.astype(np.float64)).astype(np.int64) if tp_mid else None
    if sx is not None:
        sx = np.where((sd != 0) & (sx == sd), 0, sx)
    p = params or StratParams()
    p.max_hold = int(max_hold * pd.Timedelta(TF[tf]) / pd.Timedelta("5min"))
    return Signals(name, sd, sl, np.zeros(N), sx, p)


# ---------------------------------------------------------------------------
# G. Generic trend breakout with daily trend filter (multi-asset)
# ---------------------------------------------------------------------------
def _d1_on(b_sig: pd.DataFrame, bars: pd.DataFrame, tf: str, series: pd.Series) -> np.ndarray:
    """Map a D1 series (indexed by D1 bar open) onto signal bars, using only completed D1 bars."""
    d1 = bars_tf(bars, "D1")
    known = pd.Series(series.values, index=d1.index + pd.Timedelta("1D"))
    known = known[~known.index.duplicated(keep="last")].sort_index()
    t = b_sig.index + pd.Timedelta(TF[tf])
    return known.reindex(t, method="ffill").values


def trend_bo(bars, tf="H4", n_entry=20, filt="none", sl_atr=2.0, atr_n=20, exit_n=0, sides="both",
             tp_atr=0.0, params=None, name="trend_bo"):
    b = bars_tf(bars, tf)
    hi, lo = I.donchian(b, n_entry)
    hi, lo = hi.shift(1), lo.shift(1)
    a = I.atr(b, atr_n)
    c = b.close
    up = (c > hi).values.copy()
    dn = (c < lo).values.copy()
    if filt != "none":
        d1 = bars_tf(bars, "D1")
        if filt == "sma200":
            fs = np.sign(d1.close - I.sma(d1.close, 200))
        elif filt == "sma100":
            fs = np.sign(d1.close - I.sma(d1.close, 100))
        elif filt == "sma50":
            fs = np.sign(d1.close - I.sma(d1.close, 50))
        elif filt == "rsi14":
            fs = np.sign(I.rsi(d1.close, 14) - 50)
        elif filt == "mom60":
            fs = np.sign(d1.close - d1.close.shift(60))
        elif filt == "both":
            fs = np.sign(d1.close - I.sma(d1.close, 200)) * ((np.sign(d1.close - I.sma(d1.close, 200)) ==
                                                                np.sign(I.rsi(d1.close, 14) - 50)))
        f = _d1_on(b, bars, tf, fs)
        up &= f > 0
        dn &= f < 0
    if sides == "long":
        dn[:] = False
    d = np.where(up, 1, np.where(dn, -1, 0))
    n = len(bars)
    pos = exec_pos(b.index, tf, bars.index)
    sd = place(n, pos, d.astype(np.float64)).astype(np.int64)
    sl = place(n, pos, (a * sl_atr).values)
    tp = place(n, pos, (a * tp_atr).values) if tp_atr > 0 else np.zeros(n)
    sx = None
    if exit_n:
        xh, xl = I.donchian(b, exit_n)
        xh, xl = xh.shift(1), xl.shift(1)
        ex = np.where((c < xl).values, 1, np.where((c > xh).values, -1, 0))  # close longs / shorts
        sx = place(n, pos, ex.astype(np.float64)).astype(np.int64)
        sx = np.where((sd != 0) & (sx == sd), 0, sx)
    return Signals(name, sd, sl, tp, sx, params or StratParams())


def trend_bo2(bars, tf="H4", n_entry=80, sl_atr=1.0, atr_n=20, filt="sma200", comp=0.0, adx_min=0.0,
              er_min=0.0, exit_n=0, params=None, name="trend_bo2"):
    """trend_bo + optional volatility-compression / trend-strength entry filters."""
    s = trend_bo(bars, tf=tf, n_entry=n_entry, filt=filt, sl_atr=sl_atr, atr_n=atr_n, exit_n=exit_n,
                 params=params, name=name)
    if not (comp or adx_min or er_min):
        return s
    b = bars_tf(bars, tf)
    ok = np.ones(len(b), bool)
    if comp:
        a_s = I.atr(b, atr_n)
        a_l = I.atr(b, atr_n * 5)
        ok &= (a_s / a_l).shift(1).values < comp          # compression measured before the breakout bar
    if adx_min:
        d1 = bars_tf(bars, "D1")
        ok &= _d1_on(b, bars, tf, I.adx(d1, 14)) > adx_min
    if er_min:
        d1 = bars_tf(bars, "D1")
        c = d1.close
        er = (c - c.shift(20)).abs() / c.diff().abs().rolling(20).sum()
        ok &= _d1_on(b, bars, tf, er) > er_min
    n = len(bars)
    pos = exec_pos(b.index, tf, bars.index)
    okm = place(n, pos, ok.astype(np.float64)) > 0
    s.direction = np.where(okm, s.direction, 0)
    return s
