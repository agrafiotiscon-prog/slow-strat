"""Parallel parameter sweeps.  Selection uses the DEV period only; the
HOLDOUT period (2024-01 .. 2026-09) is reported but never used to choose."""
from __future__ import annotations

import itertools
import multiprocessing as mp
import os
import sys

import numpy as np
import pandas as pd

import engine as E
import gold
import strategies as S

DEV = ("2012-01-01", "2023-12-31")
HOLD = ("2024-01-01", "2026-09-30")
ERA = {"12-15": ("2012-01-01", "2015-12-31"), "16-19": ("2016-01-01", "2019-12-31"),
       "20-23": ("2020-01-01", "2023-12-31"), "24-26": HOLD}

_G = {}


def _init(start):
    b = gold.m5(start)
    _G["bars"] = b
    _G["spread"] = S.spread_model(b, floor=0.25)
    _G["costs"] = E.Costs(slip=0.08)


def _one(args):
    builder, kw = args
    b = _G["bars"]
    try:
        risk = kw.pop("_risk", 0.005)
        pk = {k[2:]: kw.pop(k) for k in list(kw) if k.startswith("p_")}
        params = E.StratParams(risk=risk, **pk)
        sig = builder(b, params=params, **kw)
        r = E.run(b, [sig], _G["costs"], spread=_G["spread"], equity0=100_000, compounding=False)
    except Exception as ex:  # pragma: no cover
        return {"error": repr(ex), **kw}
    row = dict(kw)
    row.update({f"p_{k}": v for k, v in pk.items()})
    tr = r.trades
    for tag, (a, z) in [("dev", DEV), ("hold", HOLD)] + list(ERA.items()):
        st = r.stats(a, z)
        if not st:
            continue
        if tag in ("dev", "hold"):
            for k in ("trades_per_year", "winrate", "pf", "avg_r", "cagr", "maxdd", "mar", "sharpe"):
                row[f"{tag}_{k}"] = st[k]
        else:
            row[f"r_{tag}"] = st["avg_r"]
    return row


def sweep(builder, grid: dict, start="2012-01-01", procs=None, fixed: dict | None = None) -> pd.DataFrame:
    keys = list(grid)
    combos = [dict(zip(keys, v)) for v in itertools.product(*[grid[k] for k in keys])]
    if fixed:
        for c in combos:
            c.update(fixed)
    ctx = mp.get_context("fork")
    _init(start)
    with ctx.Pool(procs or os.cpu_count(), initializer=_init, initargs=(start,)) as pool:
        rows = pool.map(_one, [(builder, dict(c)) for c in combos], chunksize=1)
    df = pd.DataFrame(rows)
    return df


def show(df: pd.DataFrame, sort="dev_sharpe", n=25, min_tpy=5):
    pd.set_option("display.width", 300)
    pd.set_option("display.max_columns", 60)
    d = df[df.get("dev_trades_per_year", 0) >= min_tpy].sort_values(sort, ascending=False).head(n)
    return d.round(3)
