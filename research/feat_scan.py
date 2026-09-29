"""Scan every extended feature: does it separate winners from losers CONSISTENTLY in every development era?"""
import pickle, sys
import numpy as np, pandas as pd
import assets as A, features2 as F2, gold

pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
cur, trades = pickle.load(open("/tmp/final_curves.pkl", "rb"))
g = gold.m5("2007-01-01")
out = {}
mods = {"GOLD_BO": (trades["GOLD_BO"], g, ("H4", "D1")), "GOLD_ASIA": (trades["GOLD_ASIA"], g, ("H4", "D1"))}
idx = pd.concat([trades[f"IDX_{s}"].assign(sym=s) for s in ["US500", "NAS100", "US30"]])
mods["IDX_DIP"] = (idx, None, ("D1",))
rows = []
for name, (tr, bars, tfs) in mods.items():
    if bars is None:   # indices: attach per symbol with its own bars
        parts = [F2.attach(tr[tr.sym == s], A.exec_bars(s), tfs) for s in ["US500", "NAS100", "US30"]]
        t = pd.concat(parts)
    else:
        t = F2.attach(tr, bars, tfs)
    t = t.reset_index(drop=True)
    t.to_parquet(f"/tmp/feat_{name}.parquet")
    feats = [c for c in t.columns if c not in ("strat", "dir", "entry_time", "exit_time", "entry", "exit", "lots", "pnl", "r",
                                               "reason", "bars", "era", "sym")]
    dev_eras = ["12-15", "16-19", "20-23"]
    for c in feats:
        x = t.dropna(subset=[c]).reset_index(drop=True)
        if x[c].nunique() < 2:
            continue
        dev = x[x.era.isin(dev_eras)]
        if len(dev) < 60:
            continue
        # top-half vs bottom-half split on the development median
        med = dev[c].median()
        hi = x[c] > med
        row = {"module": name, "feature": c, "median": med}
        ok = []
        for e in dev_eras + ["24-26"]:
            me = (x.era == e).values
            if me.sum() < 10:
                row[e] = np.nan; continue
            diff = x.r[me & hi.values].mean() - x.r[me & ~hi.values].mean()
            row[e] = diff
            if e in dev_eras:
                ok.append(np.sign(diff))
        row["consistent"] = abs(sum(ok)) == 3
        row["dev_diff"] = dev[dev[c] > med].r.mean() - dev[dev[c] <= med].r.mean()
        rows.append(row)
df = pd.DataFrame(rows)
df.to_csv("../results/feature_scan.csv", index=False)
for m in df.module.unique():
    x = df[(df.module == m) & df.consistent].copy()
    x["abs"] = x.dev_diff.abs()
    print(f"\n===== {m}: features whose high/low split has the same sign in all 3 dev eras (R difference high-minus-low)")
    print(x.sort_values("abs", ascending=False).head(18)[["feature", "median", "12-15", "16-19", "20-23", "24-26", "dev_diff"]].round(3).to_string(index=False))
