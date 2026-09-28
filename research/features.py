"""Entry-time features for trade-level analysis (all computed on completed bars)."""
from __future__ import annotations

import numpy as np
import pandas as pd

import indicators as I
import strategies as S


def d1_features(m5: pd.DataFrame) -> pd.DataFrame:
    d = S.bars_tf(m5, "D1")
    c = d.close
    f = pd.DataFrame(index=d.index)
    a14 = I.atr(d, 14)
    f["d_atr_pct"] = a14 / c
    f["d_atr_rank"] = a14.rolling(250, min_periods=60).rank(pct=True)
    ch = (c - c.shift(20)).abs()
    vol = c.diff().abs().rolling(20).sum()
    f["d_er20"] = ch / vol
    f["d_adx"] = I.adx(d, 14)
    f["d_ma50_dist"] = (c - I.sma(c, 50)) / a14
    f["d_ma200_dist"] = (c - I.sma(c, 200)) / a14
    f["d_ret5"] = (c / c.shift(5) - 1) / f["d_atr_pct"]
    f["d_ret20"] = (c / c.shift(20) - 1) / f["d_atr_pct"]
    f["d_ret60"] = (c / c.shift(60) - 1) / f["d_atr_pct"]
    f["d_rsi14"] = I.rsi(c, 14)
    f["d_ema_slope"] = (I.ema(c, 20) - I.ema(c, 20).shift(5)) / a14
    # known once the bar closes -> index by close time
    f.index = f.index + pd.Timedelta("1D")
    return f


def h4_features(m5: pd.DataFrame) -> pd.DataFrame:
    h = S.bars_tf(m5, "H4")
    c = h.close
    f = pd.DataFrame(index=h.index)
    a = I.atr(h, 14)
    f["h4_er12"] = (c - c.shift(12)).abs() / c.diff().abs().rolling(12).sum()
    f["h4_adx"] = I.adx(h, 14)
    f["h4_ma50_dist"] = (c - I.ema(c, 50)) / a
    f["h4_rsi14"] = I.rsi(c, 14)
    f["h4_atr_rank"] = a.rolling(500, min_periods=100).rank(pct=True)
    f.index = f.index + pd.Timedelta("4h")
    return f


def attach(trades: pd.DataFrame, m5: pd.DataFrame) -> pd.DataFrame:
    t = trades.sort_values("entry_time").copy()
    for f in (d1_features(m5), h4_features(m5)):
        f = f.sort_index()
        t = pd.merge_asof(t, f, left_on="entry_time", right_index=True, direction="backward")
    ny = S.ny_time(pd.DatetimeIndex(t.entry_time))
    t["ny_hour"] = ny.hour
    t["dow"] = ny.dayofweek
    # direction-aligned versions
    for c in ["d_ma50_dist", "d_ma200_dist", "d_ret5", "d_ret20", "d_ret60", "d_ema_slope", "h4_ma50_dist"]:
        t[c + "_dir"] = t[c] * t["dir"]
    t["d_rsi14_dir"] = (t["d_rsi14"] - 50) * t["dir"]
    t["h4_rsi14_dir"] = (t["h4_rsi14"] - 50) * t["dir"]
    t["era"] = pd.cut(pd.DatetimeIndex(t.entry_time).year, [2003, 2011, 2015, 2019, 2023, 2027],
                      labels=["04-11", "12-15", "16-19", "20-23", "24-26"])
    return t


def bucket_table(t: pd.DataFrame, col: str, q: int = 4) -> pd.DataFrame:
    x = t.dropna(subset=[col]).copy()
    dev = x[x.era.isin(["12-15", "16-19", "20-23"])]
    edges = np.unique(np.nanquantile(dev[col], np.linspace(0, 1, q + 1)))
    if len(edges) < 3:
        return pd.DataFrame()
    edges[0], edges[-1] = -np.inf, np.inf
    x["b"] = pd.cut(x[col], edges)
    tab = x.pivot_table(index="b", columns="era", values="r", aggfunc="mean", observed=False)
    tab["n_dev"] = x[x.era.isin(["12-15", "16-19", "20-23"])].groupby("b", observed=False).size()
    return tab
