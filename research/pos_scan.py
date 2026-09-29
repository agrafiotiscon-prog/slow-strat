"""COT positioning + GLD flows vs outcome of gold trades, and as standalone weekly strategies."""
import numpy as np, pandas as pd
import positioning as P
pd.set_option("display.width", 250)
W = P.weekly_features(); G = P.daily_flow_features()
ERAS = ["07-11", "12-15", "16-19", "20-23", "24-26"]
for mod in ["GOLD_BO", "GOLD_ASIA"]:
    t = pd.read_parquet(f"/tmp/of_trades_{mod}.parquet").sort_values("entry_time").reset_index(drop=True)
    t = t[[c for c in t.columns if not c.startswith(("mm_", "pm_", "nc_", "oi_", "gld_"))]]
    t = pd.merge_asof(t, W, left_on="entry_time", right_index=True, direction="backward")
    t = pd.merge_asof(t, G, left_on="entry_time", right_index=True, direction="backward")
    d = t["dir"]
    for c in ["mm_net", "mm_net_chg4", "pm_net", "oi_chg4", "gld_chg5", "gld_chg20", "gld_vs_sma50", "gld_chg60"]:
        t[c + "_dir"] = t[c] * d
    for c in ["mm_rank156", "mm_rank52", "pm_rank156", "nc_rank156"]:
        t[c + "_dir"] = (t[c] - 0.5) * d
    rows = []
    for c in [c for c in t.columns if c.endswith("_dir") and c.split("_")[0] in ("mm", "pm", "nc", "oi", "gld")]:
        x = t.dropna(subset=[c]).reset_index(drop=True)
        dev = x[x.era.isin(["12-15", "16-19", "20-23"])]
        med = dev[c].median(); hi = (x[c] > med).values
        row = {"feature": c, "split": med}; s = []
        for e in ERAS:
            me = (x.era == e).values
            if me.sum() < 8: row[e] = np.nan; continue
            row[e] = x.r[me & hi].mean() - x.r[me & ~hi].mean()
            if e in ("12-15", "16-19", "20-23"): s.append(np.sign(row[e]))
        row["consistent_dev"] = len(s) == 3 and abs(sum(s)) == 3
        row["holdout_agrees"] = row["consistent_dev"] and np.sign(row["24-26"]) == s[0]
        rows.append(row)
    print(f"\n===== {mod}: R(high half) - R(low half)")
    print(pd.DataFrame(rows).round(3).to_string(index=False))
    pd.DataFrame(rows).to_csv(f"../results/positioning_filters_{mod}.csv", index=False)
