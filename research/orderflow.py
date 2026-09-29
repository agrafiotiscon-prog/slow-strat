"""Order-flow proxies that an MT5 EA can compute from broker bars (spot gold has no
exchange tape, so true bid/ask aggressor volume is not available):

  * bar delta      = volume * (2*CLV - 1),  CLV = (close - low) / (high - low)
                     ("money-flow multiplier"; + when the bar closes near its high)
  * cumulative delta (CVD) per server day and rolling
  * VWAP anchored at the server-day and server-week open
  * prior-day volume profile: POC (busiest price bin) and 70 % value area (VAH/VAL)
  * relative volume (RVOL): volume vs the average of the same time-of-day slot
  * climax / absorption bars: very high volume with a small body

Everything is computed from COMPLETED M5 bars; daily/profile values are only used
from the next server day on.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import indicators as I
import strategies as S


def m5_flow(m5: pd.DataFrame) -> pd.DataFrame:
    """Per-M5-bar order-flow proxies (indexed by bar open, UTC)."""
    o, h, l, c, v = (m5[k].values for k in ("open", "high", "low", "close", "volume"))
    rng = np.where(h > l, h - l, np.nan)
    clv = np.where(np.isnan(rng), 0.5, (c - l) / np.where(np.isnan(rng), 1, rng))
    f = pd.DataFrame(index=m5.index)
    f["vol"] = v
    f["delta"] = v * (2 * clv - 1)
    st = S.server_time(m5.index)
    f["sday"] = st.normalize()
    f["sweek"] = (st - pd.to_timedelta(st.dayofweek, unit="D")).normalize()
    tp = (h + l + c) / 3.0
    f["pv"] = tp * v
    g = f.groupby("sday")
    f["cvd_day"] = g.delta.cumsum()
    f["vol_day"] = g.vol.cumsum()
    f["vwap_day"] = g.pv.cumsum() / f.vol_day
    gw = f.groupby("sweek")
    f["vwap_week"] = gw.pv.cumsum() / gw.vol.cumsum()
    # RVOL: bar volume vs mean volume of the same 5-minute slot over the previous 20 server days
    slot = (st.hour * 12 + st.minute // 5).values
    f["slot"] = slot
    vs = pd.Series(v, m5.index)
    f["rvol"] = vs / vs.groupby(slot).transform(lambda x: x.shift(1).rolling(20, min_periods=5).mean())
    body = np.abs(c - o) / np.where(np.isnan(rng), 1, rng)
    vmed = vs.rolling(288 * 5, min_periods=288).median().values
    f["climax"] = (v > 3 * vmed) & (body < 0.3)
    f["close"] = c
    return f


def daily_profile(m5: pd.DataFrame, bin_bp: float = 5.0) -> pd.DataFrame:
    """Prior-server-day volume profile: POC, VAH, VAL (70 %), plus day VWAP/CVD summary.
    Indexed by the server day the values become USABLE (i.e. the next day)."""
    f = m5_flow(m5)
    tp = ((m5.high + m5.low + m5.close) / 3).values
    rows = []
    for day, idx in f.groupby("sday").indices.items():
        p = tp[idx]
        vv = f.vol.values[idx]
        if len(p) < 24 or vv.sum() <= 0:
            continue
        step = np.median(p) * bin_bp * 1e-4
        b = np.floor(p / step).astype(np.int64)
        lo = b.min()
        hist = np.bincount(b - lo, weights=vv)
        poc_i = int(hist.argmax())
        tot = hist.sum()
        a, z, acc = poc_i, poc_i, hist[poc_i]
        while acc < 0.7 * tot:
            up = hist[z + 1] if z + 1 < len(hist) else -1
            dn = hist[a - 1] if a - 1 >= 0 else -1
            if up >= dn:
                z += 1; acc += up
            else:
                a -= 1; acc += dn
        rows.append({"sday": day, "poc": (lo + poc_i + 0.5) * step, "vah": (lo + z + 1) * step, "val": (lo + a) * step,
                     "day_delta_ratio": f.delta.values[idx].sum() / vv.sum(), "day_vwap": (p * vv).sum() / vv.sum(),
                     "day_close": m5.close.values[idx[-1]], "day_vol": vv.sum()})
    d = pd.DataFrame(rows).set_index("sday").sort_index()
    d["day_vol_ratio"] = d.day_vol / d.day_vol.rolling(20, min_periods=5).mean().shift(1)
    d.index = d.index + pd.Timedelta("1D")    # usable from the next server day
    return d


def h4_flow(m5: pd.DataFrame) -> pd.DataFrame:
    """Order-flow features of each completed H4 bar (server-time bars), known at the bar close."""
    f = m5_flow(m5)
    h4 = S.bars_tf(m5, "H4")
    pos = np.searchsorted(h4.index.values, m5.index.values, side="right") - 1
    g = pd.DataFrame({"k": pos, "delta": f.delta.values, "vol": f.vol.values, "rvol": f.rvol.values,
                      "climax": f.climax.values.astype(float)}).groupby("k")
    out = pd.DataFrame(index=h4.index)
    agg = pd.DataFrame({"delta": g.delta.sum(), "vol": g.vol.sum(), "rvol": g.rvol.mean(), "climax": g.climax.max()})
    agg = agg[agg.index >= 0]
    out.loc[h4.index[agg.index], ["h4_delta", "h4_vol", "h4_rvol", "h4_climax"]] = agg.values
    out["h4_delta_ratio"] = out.h4_delta / out.h4_vol
    out["h4_vol_ratio"] = out.h4_vol / out.h4_vol.rolling(30, min_periods=10).mean().shift(1)
    cvd = out.h4_delta.cumsum()
    a = I.atr(h4, 20)
    # 20-bar CVD change (normalised by 20-bar volume) vs 20-bar price change (in ATR): divergence measure
    out["h4_cvd20"] = (cvd - cvd.shift(20)) / out.h4_vol.rolling(20).sum()
    out["h4_px20"] = (h4.close - h4.close.shift(20)) / a
    out.index = out.index + pd.Timedelta("4h")   # known at bar close
    return out
