"""Multi-asset research in risk units (R).

Each asset is simulated separately with a fixed risk budget (non-compounded,
large notional so lot rounding is irrelevant).  The bar-level equity curve is
converted to R units: R_curve = (equity - E0) / (E0 * risk).  Quote-currency
effects cancel because position size is computed in the same currency.
A portfolio risking `f` of equity per trade on each asset then has equity
~= 1 + f * sum(R_curves)  (non-compounded).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import assets as A
import data as D
import engine as E
import gold
import strategies as S

FX = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "EURJPY", "GBPJPY",
      "EURGBP", "EURCHF", "AUDCHF", "EURAUD", "EURCAD", "EURNZD", "GBPAUD", "GBPCAD", "GBPCHF"]
IDX = ["US500", "NAS100", "US30", "GER40", "UK100"]
METALS = ["XAUUSD", "XAGUSD"]

SPREAD_BP = {"XAUUSD": 0.8, "XAGUSD": 8.0, "US500": 1.0, "NAS100": 0.8, "US30": 0.7, "GER40": 0.8, "UK100": 1.3,
             "EURUSD": 0.3, "GBPUSD": 0.5, "USDJPY": 0.4, "AUDUSD": 0.5, "USDCAD": 0.6, "USDCHF": 0.6,
             "NZDUSD": 0.8, "EURJPY": 0.6, "GBPJPY": 1.0, "EURGBP": 0.8, "EURCHF": 0.8, "AUDCHF": 1.5,
             "EURAUD": 1.2, "EURCAD": 1.2, "EURNZD": 2.0, "GBPAUD": 1.5, "GBPCAD": 1.5, "GBPCHF": 1.5}
# commission as bp of notional per side (ECN $3.5 per 100k side = 0.35bp on EURUSD-ish notionals)
COMM_BP = {k: (0.35 if k in FX else 0.0) for k in SPREAD_BP}
COMM_BP["XAUUSD"] = 0.35 * 100 * 3.5 / 350  # $3.5 per 100oz side ~ 0.1-0.3bp
SWAP = {k: ((-0.07, -0.02) if k in IDX else (-0.055, -0.01) if k in METALS else (-0.01, -0.01)) for k in SPREAD_BP}

_H1 = {}


def h1(symbol: str) -> pd.DataFrame:
    if symbol not in _H1:
        if symbol == "XAUUSD":
            _H1[symbol] = D.resample(gold.m5("2007-01-01"), "1h")
        else:
            _H1[symbol] = A.hourly(symbol)
    return _H1[symbol]


def r_curve(symbol: str, builder, bars: pd.DataFrame | None = None, risk=0.01, **kw):
    """Simulate per contiguous data segment (gaps > 7 days split the data so no
    position or indicator straddles a hole in the history)."""
    b = bars if bars is not None else h1(symbol)
    gap = b.index.to_series().diff() > pd.Timedelta(days=7)
    seg = gap.cumsum().values
    trades, rcs, rls = [], [], []
    off = 0.0
    for s in np.unique(seg):
        bs = b[seg == s]
        if (bs.index[-1] - bs.index[0]).days < 365:   # need ~1y of data for indicator warm-up
            continue
        t, rc, rl = _r_curve_seg(symbol, builder, bs, risk, **kw)
        trades.append(t)
        rcs.append(rc + off)
        rls.append(rl + off)
        off = float(rcs[-1].iloc[-1])
    return pd.concat(trades), pd.concat(rcs), pd.concat(rls)


def _r_curve_seg(symbol, builder, b, risk, **kw):
    px = float(np.median(b.close.values))
    sp = S.spread_model(b, bps=SPREAD_BP[symbol], floor=0.0, roll_mult=4.0)
    # commission: convert bp of notional to "per lot per side" with contract=1
    costs = E.Costs(contract=1.0, commission=0.0, slip=px * 0.3e-4, lot_step=1e-9, min_lot=0.0,
                    max_lot=1e18, swap_long=SWAP[symbol][0], swap_short=SWAP[symbol][1])
    # fold commission into the spread (round trip = 2 sides) -- equivalent in expectation
    sp = sp + 2 * COMM_BP[symbol] * 1e-4 * b.close.values
    p = E.StratParams(risk=risk)
    sig = builder(b, params=p, **kw)
    sig.name = symbol
    e0 = 1e8
    res = E.run(b, [sig], costs, spread=sp, equity0=e0, compounding=False)
    rc = (res.equity - e0) / (e0 * risk)
    rl = (res.equity_low - e0) / (e0 * risk)
    return res.trades, rc, rl


def combine(curves: dict, f: float):
    """curves: {name: (rc, rl)} -> portfolio equity (close, worst) with risk f per trade per asset."""
    idx = sorted(set().union(*[c[0].index for c in curves.values()]))
    idx = pd.DatetimeIndex(idx)
    tot_c = pd.Series(0.0, idx)
    tot_l = pd.Series(0.0, idx)
    for rc, rl in curves.values():
        rc2 = rc.reindex(idx).ffill().fillna(0.0)
        # worst: at bars where the asset has no bar, use its last close
        rl2 = rl.reindex(idx)
        rl2 = rl2.fillna(rc2)
        tot_c += rc2
        tot_l += rl2
    return 1 + f * tot_c, 1 + f * tot_l


def curve_stats(eq_c: pd.Series, eq_l: pd.Series, start=None, end=None) -> dict:
    c = eq_c.loc[start:end]
    l = eq_l.loc[start:end]
    if len(c) < 10:
        return {}
    c0 = c.iloc[0]
    years = (c.index[-1] - c.index[0]).days / 365.25
    ret = (c.iloc[-1] - c0) / c0 / years          # simple (non-compounded) annual return
    peak = np.maximum.accumulate(c.values)
    dd = ((peak - l.values) / peak).max()
    d = c.resample("1D").last().dropna()
    dr = d.diff().dropna() / d.shift(1).dropna().reindex(d.diff().dropna().index)
    sh = dr.mean() / dr.std() * np.sqrt(252) if dr.std() > 0 else np.nan
    m = c.resample("ME").last().diff().dropna()
    return dict(ann=ret, maxdd=dd, mar=ret / dd if dd > 0 else np.nan, sharpe=sh, pos_months=(m > 0).mean(), years=years)
