"""External / intermarket daily data: US Dollar Index (rebuilt from FRED H.10 rates),
VIX (CBOE), WTI crude, plus the S&P 500 CFD trend from our own index data.

All values dated D are treated as known from D+1 00:00 UTC (conservative: the
live EA sees them in real time, the research uses them a few hours late).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import data as D

REPOS = D.REPOS
DXY_W = {"Euro": 0.576, "Japan": 0.136, "United Kingdom": 0.119, "Canada": 0.091, "Sweden": 0.042, "Switzerland": 0.036}


def dxy() -> pd.Series:
    """ICE Dollar Index formula on FRED noon rates (all quoted as foreign currency per USD)."""
    def build():
        d = pd.read_csv(REPOS / "datasets_exchange-rates" / "data" / "daily.csv")
        d = d[d.Country.isin(DXY_W)]
        p = d.pivot_table(index="Date", columns="Country", values="Exchange rate")
        p.index = pd.to_datetime(p.index)
        p = p.dropna()
        val = 50.14348112 * np.prod(np.vstack([(p[c] ** w).values for c, w in DXY_W.items()]), axis=0)
        return pd.DataFrame({"dxy": val}, index=p.index)
    return D._cached("DXY_daily", build)["dxy"]


def vix() -> pd.DataFrame:
    def build():
        v = pd.read_csv(REPOS / "datasets_finance-vix" / "data" / "vix-daily.csv")
        v.index = pd.to_datetime(v.pop("DATE"))
        v.columns = [c.lower() for c in v.columns]
        return v
    return D._cached("VIX_daily", build)


def wti() -> pd.Series:
    def build():
        w = pd.read_csv(REPOS / "datasets_oil-prices" / "data" / "wti-daily.csv")
        w.index = pd.to_datetime(w.iloc[:, 0])
        return pd.DataFrame({"wti": pd.to_numeric(w.iloc[:, 1], errors="coerce")}).dropna()
    return D._cached("WTI_daily", build)["wti"]


def daily_features() -> pd.DataFrame:
    """Daily intermarket features, indexed by the time they become known (UTC)."""
    x = pd.DataFrame({"dxy": dxy()})
    v = vix()
    x = x.join(v.close.rename("vix"), how="outer").join(wti().rename("wti"), how="outer")
    x = x.sort_index().ffill()
    f = pd.DataFrame(index=x.index)
    f["dxy_ret5"] = x.dxy.pct_change(5)
    f["dxy_ret20"] = x.dxy.pct_change(20)
    f["dxy_vs_sma50"] = x.dxy / x.dxy.rolling(50).mean() - 1
    f["dxy_vs_sma200"] = x.dxy / x.dxy.rolling(200).mean() - 1
    f["dxy_vs_sma150"] = x.dxy / x.dxy.rolling(150).mean() - 1
    f["dxy_vs_sma250"] = x.dxy / x.dxy.rolling(250).mean() - 1
    f["dxy_vs_sma100"] = x.dxy / x.dxy.rolling(100).mean() - 1
    f["vix"] = x.vix
    f["vix_vs_sma10"] = x.vix / x.vix.rolling(10).mean() - 1
    f["vix_ret5"] = x.vix.pct_change(5)
    f["vix_rank250"] = x.vix.rolling(250, min_periods=60).rank(pct=True)
    f["wti_ret20"] = x.wti.pct_change(20)
    f["wti_vs_sma100"] = x.wti / x.wti.rolling(100).mean() - 1
    f.index = f.index + pd.Timedelta("1D")
    return f


def fx_close(country: str) -> pd.Series:
    """FRED noon rate (foreign currency per USD) for one currency, daily."""
    def build():
        d = pd.read_csv(REPOS / "datasets_exchange-rates" / "data" / "daily.csv")
        d = d[d.Country.isin(list(DXY_W) + ["Euro"])]
        p = d.pivot_table(index="Date", columns="Country", values="Exchange rate")
        p.index = pd.to_datetime(p.index)
        return p
    return D._cached("FX_daily", build)[country].dropna()
