"""Market data loading and normalisation.

All loaders return a DataFrame indexed by bar-open time in UTC (tz-naive),
columns: open, high, low, close, volume.  Raw sources are fetched by
research/fetch_data.sh into $DATA_REPOS (default /home/user/data_repos).
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

REPOS = Path(os.environ.get("DATA_REPOS", "/home/user/data_repos"))
CACHE = Path(__file__).resolve().parent.parent / "data"
CACHE.mkdir(exist_ok=True)

SNOW = REPOS / "TheSnowGuru_Stocks-Futures-Financial-Time-series-Tick-Bar-Data"
GDF = REPOS / "gdf"
CASIO = REPOS / "farshoffs_casio" / "data"


def _std(df: pd.DataFrame) -> pd.DataFrame:
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = df[["open", "high", "low", "close", "volume"]].astype("float64")
    bad = (df.high < df[["open", "close"]].max(axis=1)) | (df.low > df[["open", "close"]].min(axis=1))
    df.loc[bad, "high"] = df.loc[bad, ["open", "high", "close"]].max(axis=1)
    df.loc[bad, "low"] = df.loc[bad, ["open", "low", "close"]].min(axis=1)
    return df.dropna()


def _cached(name: str, builder):
    p = CACHE / f"{name}.parquet"
    if p.exists():
        return pd.read_parquet(p)
    df = builder()
    df.to_parquet(p)
    return df


def _read_iso(path: Path, time_col: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    t = pd.to_datetime(df[time_col], utc=True).dt.tz_localize(None)
    df = df.drop(columns=[time_col])
    df.index = t
    df.columns = [c.lower() for c in df.columns]
    if "volume" not in df:
        df["volume"] = 0.0
    return _std(df)


def gold_m5_duka() -> pd.DataFrame:
    """XAUUSD bid M5, Dukascopy, UTC, 2020-01-09 .. 2026-09-27."""
    return _cached("XAUUSD_M5_duka", lambda: _read_iso(CASIO / "xauusd_m5.csv", "timestamp"))


def gold_m5_octa_raw() -> pd.DataFrame:
    """XAUUSD M5 from an OctaFX MT4 export (broker server time), 2004 .. 2026-01."""
    return _cached("XAUUSD_M5_octa_raw",
                   lambda: _read_iso(CASIO / "xauusd_m5_secondary_octafx_mt4.csv", "timestamp"))


def gdf_m1(symbol: str) -> pd.DataFrame:
    """Last ~6 months of M1 bars (UTC) from getdata-finance samples."""
    s = symbol.lower()
    f = GDF / f"{s}-1m" / f"{symbol.upper()}_1m.csv"
    return _cached(f"{symbol.upper()}_M1_gdf", lambda: _read_iso(f, "datetime"))


def snow_h1_raw(symbol: str) -> pd.DataFrame:
    """MT5-exported H1 bars (broker server time) 2007 .. 2023-09."""
    sym = symbol.upper()
    folder = {"XAUUSD": "commodities/gold", "XAGUSD": "commodities/silver",
              "US30": "indices/dow30", "NAS100": "indices/nasdaq100", "US500": "indices/s&p500",
              "GER40": "indices/dax30", "UK100": "indices/ftse100"}.get(sym, f"forex/{sym.lower()}")
    fname = {"US30": "USA30IDXUSD_H1.csv", "NAS100": "USATECHIDXUSD_H1.csv", "US500": "USA500IDXUSD_H1.csv",
             "GER40": "DEUIDXEUR_H1.csv", "UK100": "GBRIDXGBP_H1.csv", "AUDCAD": "AUDCAD60.csv"}.get(sym, f"{sym}_H1.csv")
    path = SNOW / folder / fname

    def build():
        first = open(path).readline()
        sep = "\t" if "\t" in first else ","
        has_header = not first[:1].isdigit()
        df = pd.read_csv(path, sep=sep, header=0 if has_header else None)
        if not has_header:
            df.columns = ["Time", "Open", "High", "Low", "Close", "Volume"][:df.shape[1]]
        df.columns = [c.lower() for c in df.columns]
        df.index = pd.to_datetime(df.pop("time"))
        return _std(df)
    return _cached(f"{sym}_H1_snow_raw", build)


def resample(df: pd.DataFrame, rule: str, offset: str | None = None) -> pd.DataFrame:
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    out = df.resample(rule, label="left", closed="left", offset=offset).agg(agg)
    return out.dropna(subset=["open"])


def estimate_tz_shift(raw: pd.DataFrame, ref: pd.DataFrame, rule: str = "1h",
                      candidates=range(-4, 5)) -> dict:
    """Find the whole-hour shift that best aligns `raw` (unknown tz) to UTC `ref`.

    Returns {hours: correlation of hourly returns}.  Evaluated separately by
    season so DST-following brokers show up as a 1h difference between
    summer and winter.
    """
    r = resample(ref, rule).close.pct_change()
    out = {}
    for h in candidates:
        x = raw.copy()
        x.index = x.index - pd.Timedelta(hours=h)
        xr = resample(x, rule).close.pct_change()
        j = pd.concat([r, xr], axis=1, join="inner").dropna()
        out[h] = float(j.corr().iloc[0, 1]) if len(j) > 100 else np.nan
    return out


def us_dst(ts: pd.DatetimeIndex) -> np.ndarray:
    """True where US daylight saving is in force (2nd Sun Mar .. 1st Sun Nov)."""
    years = ts.year
    out = np.zeros(len(ts), dtype=bool)
    for y in np.unique(years):
        mar = pd.Timestamp(year=y, month=3, day=1)
        start = mar + pd.Timedelta(days=(6 - mar.weekday()) % 7 + 7, hours=7)  # 2am EST = 7 UTC
        nov = pd.Timestamp(year=y, month=11, day=1)
        end = nov + pd.Timedelta(days=(6 - nov.weekday()) % 7, hours=6)  # 2am EDT = 6 UTC
        m = years == y
        out[m] = (ts[m] >= start) & (ts[m] < end)
    return out


def nyclose_to_utc(df: pd.DataFrame) -> pd.DataFrame:
    """Convert broker 'New York close' server time (GMT+2 winter / GMT+3 summer) to UTC."""
    approx_utc = df.index - pd.Timedelta(hours=2)
    dst = us_dst(approx_utc)
    out = df.copy()
    out.index = df.index - pd.to_timedelta(np.where(dst, 3, 2), unit="h")
    return _std(out)


def fixed_to_utc(df: pd.DataFrame, hours: int) -> pd.DataFrame:
    out = df.copy()
    out.index = df.index - pd.Timedelta(hours=hours)
    return out
