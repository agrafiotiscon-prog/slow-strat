"""Portfolio-level effect of the contrarian managed-money COT filter on the gold trend module
(v2 Balanced weights, drawdown brake 3->8 %, compounded, intraday-low drawdown)."""
import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import pickle, numpy as np, pandas as pd
import book as B, engine as E, gold, positioning as P, strategies as S, final_portfolio as F, stress as ST
cur, trades = pickle.load(open("/tmp/final_curves_v2.pkl", "rb"))
b = gold.m5(B.GOLD_START)
c = P.cot_disagg()
mmn = (c.m_money_positions_long_all - c.m_money_positions_short_all) / c.open_interest_all
for wk, th in [(2, 0.04), (4, 0.02)]:
    ch = mmn - mmn.shift(wk); ch.index = ch.index + pd.Timedelta(days=6)
    ch = ch[~ch.index.duplicated(keep="last")].sort_index()
    v = ch.reindex(b.index, method="ffill").values
    sig = S.trend_bo(b, tf="H4", n_entry=80, filt="sma200", sl_atr=1.0, atr_n=20, params=E.StratParams(risk=0.01, trail_r=3.0), name="GOLD_BO")
    d = sig.direction
    sig.direction = np.where(np.nan_to_num(v * d, nan=-1.0) < th, d, 0)
    t, rc, rl = B.gold_r([sig], bars=b)
    cur[f"GOLD_BO_COT{wk}"] = (rc, rl); trades[f"GOLD_BO_COT{wk}"] = t
idx, C, L = F.hourly(cur)
IDX = {"IDXF_US500": 1.2, "IDXF_NAS100": 1.2, "IDXF_US30": 1.2}
cfgs = {
    "v2 Balanced (EA today)": {"GOLD_BO": 0.48, "GOLD_ASIA": 0.40, **IDX},
    "+ COT 2w filter, same risk": {"GOLD_BO_COT2": 0.48, "GOLD_ASIA": 0.40, **IDX},
    "+ COT 2w filter, gold risk 0.60": {"GOLD_BO_COT2": 0.60, "GOLD_ASIA": 0.40, **IDX},
    "+ COT 4w filter, same risk": {"GOLD_BO_COT4": 0.48, "GOLD_ASIA": 0.40, **IDX},
}
rows = []
for lab, W in cfgs.items():
    r = {"config": lab}
    for p in ["FULL 2007-2026", "2007-2011", "2012-2015", "2016-2019", "2020-2023", "2024-2026 (holdout)"]:
        cg, dd = ST.brake_sim(idx, C, L, W, *F.PER[p], 0.03, 0.08, 0.5)
        r[p[:9]] = f"{cg*100:.1f}/{dd*100:.1f}"
    rows.append(r)
pd.set_option("display.width", 250)
df = pd.DataFrame(rows); print(df.to_string(index=False))
df.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "results", "cot_filter_portfolio.csv"), index=False)
