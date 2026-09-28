"""First-pass survey of all strategy families on gold (default parameters)."""
import sys
import time

import numpy as np
import pandas as pd

import data as D
import engine as E
import strategies as S

pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 30)

m5 = D.gold_m5_duka()
spread = S.spread_model(m5)
costs = E.Costs(slip=0.08)
IS = ("2020-01-01", "2023-12-31")
OOS = ("2024-01-01", "2026-09-30")


def evaluate(sig, label=None):
    r = E.run(m5, [sig], costs, spread=spread, equity0=10_000, compounding=False)
    row = {"name": label or sig.name}
    for tag, (a, b) in (("IS", IS), ("OOS", OOS)):
        st = r.stats(a, b)
        for k in ("trades_per_year", "winrate", "pf", "avg_r", "cagr", "maxdd", "mar"):
            row[f"{tag}_{k}"] = st.get(k, np.nan)
    return row, r


def fmt(df):
    f = df.copy()
    for c in f.columns:
        if c == "name":
            continue
        f[c] = f[c].astype(float).round(3)
    return f


if __name__ == "__main__":
    P = E.StratParams
    cands = [
        S.rsi_pullback(m5, "H1", params=P(risk=0.005)),
        S.rsi_pullback(m5, "H4", params=P(risk=0.005), name="rsi_pb_h4"),
        S.rsi_pullback(m5, "M15", params=P(risk=0.005), name="rsi_pb_m15"),
        S.asian_breakout(m5, params=P(risk=0.005)),
        S.asian_breakout(m5, sl_mode="atr", sl_k=0.5, tp_k=1.0, flat_h=20, params=P(risk=0.005), name="asia_bo_atr"),
        S.trend_pullback(m5, params=P(risk=0.005)),
        S.trend_pullback(m5, tf="M15", htf="H1", params=P(risk=0.005), name="trend_pb_m15"),
        S.donchian_bo(m5, params=P(risk=0.005, trail_r=1.0, trail_start=1.0)),
        S.donchian_bo(m5, tf="D1", n_entry=20, params=P(risk=0.005, trail_r=1.5, trail_start=1.0), name="donch_d1"),
        S.pdhl_sweep(m5, params=P(risk=0.005)),
        S.bb_fade(m5, params=P(risk=0.005)),
    ]
    rows = []
    for s in cands:
        t = time.time()
        row, r = evaluate(s)
        rows.append(row)
        print(f"{s.name} done in {time.time()-t:.1f}s", file=sys.stderr)
    print(fmt(pd.DataFrame(rows)).to_string())
