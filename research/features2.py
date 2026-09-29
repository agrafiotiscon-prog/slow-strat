"""Extended entry features: classic indicators beyond the ones already used, tick volume,
and intermarket context (USD index, VIX, oil, S&P 500 trend).  Everything is computed
from COMPLETED bars/days known at entry time."""
from __future__ import annotations

import numpy as np
import pandas as pd

import assets as A
import ext
import indicators as I
import strategies as S


def _supertrend(b: pd.DataFrame, n=10, k=3.0) -> pd.Series:
    a = I.atr(b, n).values
    hl2 = ((b.high + b.low) / 2).values
    c = b.close.values
    up = hl2 - k * a
    dn = hl2 + k * a
    trend = np.ones(len(b))
    fu, fd = up.copy(), dn.copy()
    for i in range(1, len(b)):
        if np.isnan(a[i]):
            continue
        fu[i] = max(up[i], fu[i - 1]) if c[i - 1] > fu[i - 1] else up[i]
        fd[i] = min(dn[i], fd[i - 1]) if c[i - 1] < fd[i - 1] else dn[i]
        if c[i] > fd[i - 1]:
            trend[i] = 1
        elif c[i] < fu[i - 1]:
            trend[i] = -1
        else:
            trend[i] = trend[i - 1]
    return pd.Series(trend, b.index)


def _psar(b: pd.DataFrame, step=0.02, mx=0.2) -> pd.Series:
    h, l = b.high.values, b.low.values
    n = len(b)
    d = np.ones(n)
    sar = l[0]
    ep = h[0]
    af = step
    up = True
    for i in range(1, n):
        sar = sar + af * (ep - sar)
        if up:
            sar = min(sar, l[i - 1], l[i - 2] if i > 1 else l[i - 1])
            if l[i] < sar:
                up, sar, ep, af = False, ep, l[i], step
            elif h[i] > ep:
                ep, af = h[i], min(mx, af + step)
        else:
            sar = max(sar, h[i - 1], h[i - 2] if i > 1 else h[i - 1])
            if h[i] > sar:
                up, sar, ep, af = True, ep, h[i], step
            elif l[i] < ep:
                ep, af = l[i], min(mx, af + step)
        d[i] = 1 if up else -1
    return pd.Series(d, b.index)


def indicator_block(b: pd.DataFrame, prefix: str) -> pd.DataFrame:
    c = b.close
    f = pd.DataFrame(index=b.index)
    a14 = I.atr(b, 14)
    macd = I.ema(c, 12) - I.ema(c, 26)
    sig = I.ema(macd, 9)
    f[f"{prefix}_macd_hist"] = (macd - sig) / a14
    f[f"{prefix}_macd_line"] = macd / a14
    f[f"{prefix}_supertrend"] = _supertrend(b)
    f[f"{prefix}_psar"] = _psar(b)
    tenkan = (b.high.rolling(9).max() + b.low.rolling(9).min()) / 2
    kijun = (b.high.rolling(26).max() + b.low.rolling(26).min()) / 2
    span_a = ((tenkan + kijun) / 2).shift(26)
    span_b = ((b.high.rolling(52).max() + b.low.rolling(52).min()) / 2).shift(26)
    top = np.maximum(span_a, span_b)
    bot = np.minimum(span_a, span_b)
    f[f"{prefix}_ichi_cloud"] = np.where(c > top, 1, np.where(c < bot, -1, 0))
    f[f"{prefix}_ichi_tk"] = np.sign(tenkan - kijun)
    kc_mid = I.ema(c, 20)
    f[f"{prefix}_keltner_pos"] = (c - kc_mid) / (2 * a14)
    lo14, hi14 = b.low.rolling(14).min(), b.high.rolling(14).max()
    f[f"{prefix}_stoch"] = 100 * (c - lo14) / (hi14 - lo14)
    tp = (b.high + b.low + c) / 3
    md = tp.rolling(20).apply(lambda x: np.mean(np.abs(x - x.mean())), raw=True)
    f[f"{prefix}_cci"] = (tp - tp.rolling(20).mean()) / (0.015 * md)
    lo, mid, hi = I.bands(c, 20, 2.0)
    f[f"{prefix}_bb_pctb"] = (c - lo) / (hi - lo)
    f[f"{prefix}_bb_width_rank"] = ((hi - lo) / mid).rolling(250, min_periods=60).rank(pct=True)
    f[f"{prefix}_rsi14"] = I.rsi(c, 14)
    f[f"{prefix}_adx"] = I.adx(b, 14)
    if "volume" in b:
        v = b.volume.replace(0, np.nan)
        f[f"{prefix}_vol_ratio"] = v / v.rolling(20).mean()
        f[f"{prefix}_vol_ratio_bar"] = v / v.rolling(100).median()
    return f


def known_at_close(f: pd.DataFrame, tf: str) -> pd.DataFrame:
    g = f.copy()
    g.index = g.index + pd.Timedelta(S.TF[tf])
    return g[~g.index.duplicated(keep="last")].sort_index()


def spx_daily() -> pd.DataFrame:
    d = A.daily("US500")
    c = d.close
    f = pd.DataFrame(index=d.index)
    f["spx_vs_sma200"] = c / I.sma(c, 200) - 1
    f["spx_ret20"] = c.pct_change(20)
    f["spx_rvol20"] = np.log(c).diff().rolling(20).std() * np.sqrt(252)
    f.index = f.index + pd.Timedelta("1D")
    return f


def attach(trades: pd.DataFrame, bars: pd.DataFrame, tf_list=("H4", "D1")) -> pd.DataFrame:
    """Attach indicator blocks (for each timeframe) + intermarket daily features to trades."""
    t = trades.sort_values("entry_time").copy()
    blocks = [known_at_close(indicator_block(S.bars_tf(bars, tf), tf.lower()), tf) for tf in tf_list]
    blocks += [ext.daily_features(), spx_daily()]
    for f in blocks:
        t = pd.merge_asof(t, f.sort_index(), left_on="entry_time", right_index=True, direction="backward")
    d = t["dir"]
    # direction-aligned versions (positive = supports the trade direction)
    for c in list(t.columns):
        if any(c.endswith(s) for s in ("_macd_hist", "_macd_line", "_supertrend", "_psar", "_ichi_cloud", "_ichi_tk",
                                      "_keltner_pos", "dxy_ret5", "dxy_ret20", "dxy_vs_sma50", "dxy_vs_sma200",
                                      "wti_ret20", "wti_vs_sma100", "spx_vs_sma200", "spx_ret20")):
            t[c + "_dir"] = t[c] * d
        if c.endswith(("_stoch", "_rsi14", "_bb_pctb")):
            mid = 0.5 if c.endswith("_bb_pctb") else 50
            t[c + "_dir"] = (t[c] - mid) * d
        if c.endswith("_cci"):
            t[c + "_dir"] = t[c] * d
    t["era"] = pd.cut(pd.DatetimeIndex(t.entry_time).year, [2003, 2011, 2015, 2019, 2023, 2027],
                      labels=["04-11", "12-15", "16-19", "20-23", "24-26"])
    return t
