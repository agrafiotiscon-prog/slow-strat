"""Multi-asset daily / hourly data for diversification research.

Index and FX H1 history (2007/2013 .. 2023-09) comes from MT5 exports (UTC,
verified against Dukascopy gold), recent data (2024-05 .. 2026-09 daily,
2026-03 .. 2026-09 intraday) from getdata-finance samples.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import data as D

GDF_NAME = {"US500": "spx500", "NAS100": "nas100", "US30": "us30", "JPN225": "jpn225",
            "EURUSD": "eurusd", "GBPUSD": "gbpusd", "USDJPY": "usdjpy", "XAUUSD": "xauusd",
            "AUDUSD": "audusd", "USDCAD": "usdcad", "USDCHF": "usdchf", "EURJPY": "eurjpy",
            "EURGBP": "eurgbp", "XAGUSD": "xagusd", "USOIL": "usoil"}

# price-based cost model: (spread in price units at a reference price, ref price) -> scales with price
COST = {
    "US500": dict(spread_bp=1.0, contract=1.0, commission=0.0, swap_long=-0.07, swap_short=-0.02),
    "NAS100": dict(spread_bp=1.0, contract=1.0, commission=0.0, swap_long=-0.07, swap_short=-0.02),
    "US30": dict(spread_bp=1.0, contract=1.0, commission=0.0, swap_long=-0.07, swap_short=-0.02),
    "JPN225": dict(spread_bp=2.0, contract=1.0, commission=0.0, swap_long=-0.04, swap_short=-0.02),
    "GER40": dict(spread_bp=1.0, contract=1.0, commission=0.0, swap_long=-0.05, swap_short=-0.02),
    "XAUUSD": dict(spread_bp=0.8, contract=100.0, commission=3.5, swap_long=-0.055, swap_short=-0.01),
}
FX_COST = dict(spread_bp=0.8, contract=100000.0, commission=3.5, swap_long=-0.01, swap_short=-0.01)


def gdf_file(symbol: str, tf: str) -> pd.DataFrame:
    s = GDF_NAME[symbol]
    f = D.GDF / f"{s}-{tf}" / f"{s.upper()}_{tf}.csv"
    return D._cached(f"{symbol}_{tf}_gdf", lambda: D._read_iso(f, "datetime"))


def daily(symbol: str) -> pd.DataFrame:
    """UTC daily bars: MT5 H1 history resampled (to 2023-09) + recent daily sample (2024-05 ..)."""
    h1 = D.snow_h1_raw(symbol)
    d_old = D.resample(h1, "1D")
    d_old = d_old[d_old.index.dayofweek < 5]
    try:
        d_new = gdf_file(symbol, "1d")
        d_new = d_new[d_new.index.dayofweek < 5]
    except (FileNotFoundError, KeyError):
        d_new = d_old.iloc[:0]
    d = pd.concat([d_old, d_new[d_new.index > d_old.index[-1]]])
    return d


def hourly(symbol: str) -> pd.DataFrame:
    h1 = D.snow_h1_raw(symbol)
    try:
        new = D.resample(gdf_file(symbol, "1m"), "1h")
        h1 = pd.concat([h1, new[new.index > h1.index[-1]]])
    except (FileNotFoundError, KeyError):
        pass
    return h1


def exec_bars(symbol: str) -> pd.DataFrame:
    """Best-resolution execution bars: H1 where available, daily bars to fill the
    2023-09 .. 2026-03 hole (daily-signal strategies only)."""
    h1 = hourly(symbol)
    try:
        d = gdf_file(symbol, "1d")
    except (FileNotFoundError, KeyError):
        return h1
    d = d[d.index.dayofweek < 5]
    old_end = D.snow_h1_raw(symbol).index[-1]
    new = h1[h1.index > old_end]
    new_start = new.index[0] if len(new) else pd.Timestamp.max
    fill = d[(d.index > old_end) & (d.index < new_start.normalize())]
    return pd.concat([h1[h1.index <= old_end], fill, new]).sort_index()
