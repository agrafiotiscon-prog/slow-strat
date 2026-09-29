"""Institutional positioning / flow data for gold:
  * CFTC disaggregated COT (COMEX gold, code 088691): managed money, producers, swap dealers
  * CFTC legacy COT (non-commercial net), 1986-2026
  * SPDR Gold Trust (GLD) holdings in tonnes, daily 2004-2026
Release lags are respected: COT 'as of' Tuesday is published Friday afternoon -> used from
the following Monday 00:00 UTC; GLD holdings for day D are used from D+1.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

import data as D

R = D.REPOS


def cot_disagg() -> pd.DataFrame:
    def build():
        d = json.load(open(R / "Jim-Lohse_investment-lab" / "data" / "cftc" / "raw" /
                           "disagg_fut_088691_2006-06-13_2026-09-24.json"))
        x = pd.DataFrame(d)
        x["date"] = pd.to_datetime(x["report_date_as_yyyy_mm_dd"].str[:10])
        num = ["open_interest_all", "m_money_positions_long_all", "m_money_positions_short_all",
               "prod_merc_positions_long", "prod_merc_positions_short", "swap_positions_long_all",
               "swap__positions_short_all"]
        num = [c for c in num if c in x.columns]
        for c in num:
            x[c] = pd.to_numeric(x[c], errors="coerce")
        return x.set_index("date")[num].sort_index()
    return D._cached("COT_disagg_gold", build)


def cot_legacy() -> pd.DataFrame:
    def build():
        x = pd.read_csv(R / "ngohamah_cot_analysis" / "data" / "GOLD.csv")
        x.index = pd.to_datetime(x["As of Date in Form YYYY-MM-DD"])
        return pd.DataFrame({"nc_net": x["Net Positions"].astype(float), "oi": x["Open Interest (All)"].astype(float)}).sort_index()
    return D._cached("COT_legacy_gold", build)


def gld() -> pd.Series:
    def build():
        x = pd.read_csv(R / "Jim-Lohse_investment-lab" / "data" / "flows" / "gld_holdings.csv")
        x.index = pd.to_datetime(x.date)
        return pd.DataFrame({"tonnes": x.tonnes.astype(float)}).sort_index()
    return D._cached("GLD_holdings", build)["tonnes"]


def weekly_features() -> pd.DataFrame:
    """COT features indexed by the time they are usable (Monday after the as-of Tuesday)."""
    c = cot_disagg()
    f = pd.DataFrame(index=c.index)
    oi = c.open_interest_all
    mm = (c.m_money_positions_long_all - c.m_money_positions_short_all) / oi
    pm = (c.prod_merc_positions_long - c.prod_merc_positions_short) / oi
    f["mm_net"] = mm
    f["mm_net_chg4"] = mm - mm.shift(4)
    f["mm_rank156"] = mm.rolling(156, min_periods=52).rank(pct=True)     # 3-year COT index
    f["mm_rank52"] = mm.rolling(52, min_periods=26).rank(pct=True)
    f["pm_net"] = pm
    f["pm_rank156"] = pm.rolling(156, min_periods=52).rank(pct=True)
    f["oi_chg4"] = oi / oi.shift(4) - 1
    leg = cot_legacy()
    nc = leg.nc_net / leg.oi
    f = f.join(pd.DataFrame({"nc_rank156": nc.rolling(156, min_periods=52).rank(pct=True)}), how="outer")
    f.index = f.index + pd.Timedelta(days=6)        # Tuesday as-of -> usable Monday
    return f.sort_index()


def daily_flow_features() -> pd.DataFrame:
    t = gld()
    f = pd.DataFrame(index=t.index)
    f["gld_chg5"] = t.pct_change(5)
    f["gld_chg20"] = t.pct_change(20)
    f["gld_vs_sma50"] = t / t.rolling(50).mean() - 1
    f["gld_chg60"] = t.pct_change(60)
    f.index = f.index + pd.Timedelta("1D")
    return f
