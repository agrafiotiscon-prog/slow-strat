"""The candidate strategy book and a portfolio evaluator in risk units.

Every module produces a bar-level R curve (MTM close and worst intrabar) at a
nominal 1R = 1% risk; the portfolio equity for per-module risk weights w is
1 + sum_k w_k * R_k(t).  Compounding is ignored here (the EA compounds, which
only scales results up in good years and down after losses).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import engine as E
import gold
import idx_server
import multi as M
import strategies as S

GOLD_START = "2007-01-01"


def gold_r(sigs: list[E.Signals], bars=None, spread_mult=1.0, slip=0.08, commission=3.5):
    """Run gold signals (M5 execution); return trades and R curves (close, worst)."""
    b = bars if bars is not None else gold.m5(GOLD_START)
    sp = S.spread_model(b, floor=0.25) * spread_mult
    costs = E.Costs(slip=slip, commission=commission, lot_step=1e-6, min_lot=0.0, max_lot=1e12)
    e0 = 1e8
    for s in sigs:
        s.params.risk = 0.01 * (s.params.risk / 0.01 if s.params.risk else 1.0)
    res = E.run(b, sigs, costs, spread=sp, equity0=e0, compounding=False)
    rc = (res.equity - e0) / (e0 * 0.01)
    rl = (res.equity_low - e0) / (e0 * 0.01)
    return res.trades, rc, rl


# ----------------------------------------------------------------------------
# module definitions
# ----------------------------------------------------------------------------
def gold_breakout(b, split=False, n_entry=80, sl_atr=1.0, trail_r=3.0, filt="sma200", tp1_r=1.0, name="G_BO"):
    P = E.StratParams
    if not split:
        return [S.trend_bo(b, tf="H4", n_entry=n_entry, filt=filt, sl_atr=sl_atr,
                           params=P(risk=0.01, trail_r=trail_r), name=name)]
    a = S.trend_bo(b, tf="H4", n_entry=n_entry, filt=filt, sl_atr=sl_atr, params=P(risk=0.005), name=name + "_tp")
    a.tp = np.where(a.direction != 0, a.sl * tp1_r, 0.0)
    r = S.trend_bo(b, tf="H4", n_entry=n_entry, filt=filt, sl_atr=sl_atr,
                   params=P(risk=0.005, trail_r=trail_r, be_trigger=tp1_r, be_offset=0.0), name=name + "_run")
    return [a, r]


def gold_pullback(b, name="G_PB"):
    return [S.trend_pullback(b, tf="H4", fast=20, slow=100, htf="D1", sl_atr=3.0, tp_r=1.0, touch_atr=0.0,
                             params=E.StratParams(risk=0.01), name=name)]


def gold_asia(b, name="G_ASIA"):
    return [S.asian_breakout(b, rng_end=7, trade_end=12, sl_mode="atr", sl_k=1.0, tp_k=1.0, trend_filter=50,
                             params=E.StratParams(risk=0.01), name=name)]


def index_dip(symbols=("US500", "NAS100", "US30"), **kw):
    kw = {**dict(rule="rsi2ibs", lo=10, ibs_lo=0.25, trend_n=200, exit_ma=5, sl_atr=2.0), **kw}
    out = {}
    for s in symbols:
        tr, rc, rl = M.r_curve(s, idx_server.dip, **kw)
        out[s] = (tr, rc, rl)
    return out


def combine(curves: dict[str, tuple[pd.Series, pd.Series]], weights: dict[str, float]):
    """weights: risk per trade as a fraction (e.g. 0.005) per curve key."""
    idx = pd.DatetimeIndex(sorted(set().union(*[c[0].index for c in curves.values()])))
    tc = pd.Series(0.0, idx)
    tl = pd.Series(0.0, idx)
    for k, (rc, rl) in curves.items():
        w = weights.get(k, 0.0) / 0.01
        if w == 0:
            continue
        c2 = rc.reindex(idx).ffill().fillna(0.0)
        l2 = rl.reindex(idx).fillna(c2)
        tc += w * c2 / 100.0
        tl += w * l2 / 100.0
    return 1 + tc, 1 + tl


def stats(ec, el, start=None, end=None):
    return M.curve_stats(ec, el, start, end)


PERIODS = {"07-11": ("2007", "2011-12-31"), "12-15": ("2012", "2015-12-31"), "16-19": ("2016", "2019-12-31"),
           "20-23": ("2020", "2023-12-31"), "24-26": ("2024", "2026-09-30"), "2025": ("2025", "2025-12-31"),
           "2026": ("2026", "2026-09-30"), "ALL": ("2007", "2026-09-30")}


def table(ec, el, periods=PERIODS):
    rows = []
    for k, (a, z) in periods.items():
        st = stats(ec, el, a, z)
        if st:
            rows.append({"period": k, **st})
    return pd.DataFrame(rows).set_index("period").astype(float).round(3)
