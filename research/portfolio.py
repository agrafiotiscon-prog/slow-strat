"""Run several strategies on one shared account and report per-era results."""
from __future__ import annotations

import numpy as np
import pandas as pd

import engine as E
import gold
import strategies as S
import sweep as W

pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 40)


def run_portfolio(sigs, start="2012-01-01", end=None, bars=None, spread_mult=1.0, slip=0.08,
                  commission=3.5, equity0=10_000, compounding=True):
    b = bars if bars is not None else gold.m5(start, end)
    sp = S.spread_model(b, floor=0.25) * spread_mult
    costs = E.Costs(slip=slip, commission=commission)
    return E.run(b, sigs, costs, spread=sp, equity0=equity0, compounding=compounding)


def report(res: E.Result, periods=None):
    periods = periods or {"12-15": ("2012", "2015"), "16-19": ("2016", "2019"), "20-23": ("2020", "2023"),
                          "DEV": ("2012", "2023"), "HOLD 24-26": ("2024", "2026-09-30"),
                          "2025": ("2025", "2025"), "2026": ("2026", "2026")}
    rows = []
    for k, (a, b) in periods.items():
        st = res.stats(a, b)
        if st:
            rows.append({"period": k, **{x: st[x] for x in ("trades", "trades_per_year", "winrate", "pf", "avg_r",
                                                               "cagr", "maxdd", "mar", "sharpe", "worst_month",
                                                               "pct_pos_months")}})
    df = pd.DataFrame(rows).set_index("period")
    return df.astype(float).round(3)


def per_strategy(res: E.Result):
    t = res.trades
    g = t.groupby("strat")
    return pd.DataFrame({"n": g.size(), "win": g.apply(lambda x: (x.pnl > 0).mean()),
                         "avg_r": g.r.mean(), "sum_r": g.r.sum()}).round(3)


def monthly_corr(res: E.Result):
    t = res.trades.copy()
    t["m"] = t.exit_time.dt.to_period("M")
    p = t.pivot_table(index="m", columns="strat", values="r", aggfunc="sum").fillna(0)
    return p.corr().round(2)
