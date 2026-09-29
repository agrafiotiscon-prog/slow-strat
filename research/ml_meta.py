"""Walk-forward meta-labeling: for each test year Y, train a gradient-boosted classifier on all
trades that CLOSED before Y (features known at entry), predict P(win) for year-Y trades, and
measure whether taking only high-probability trades improves results out of sample."""
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score
pd.set_option("display.width", 250)
DROP = {"strat", "dir", "entry_time", "exit_time", "entry", "exit", "lots", "pnl", "r", "reason", "bars", "era", "sym"}

def walk(mod, model="gbm", first_test=2014, thr_q=0.5):
    t = pd.read_parquet(f"/tmp/feat_{mod}.parquet").sort_values("entry_time").reset_index(drop=True)
    feats = [c for c in t.columns if c not in DROP and t[c].dtype != object]
    t["y"] = (t.r > 0).astype(int)
    t["year"] = t.entry_time.dt.year
    out = []
    for Y in range(first_test, 2027):
        tr = t[t.exit_time < pd.Timestamp(f"{Y}-01-01")]
        te = t[t.year == Y]
        if len(te) == 0 or len(tr) < 80:
            continue
        use = [c for c in feats if tr[c].nunique(dropna=True) > 2]
        X, Xt = tr[use].astype(float), te[use].astype(float)
        if model == "gbm":
            m = HistGradientBoostingClassifier(max_depth=3, max_iter=150, learning_rate=0.05, min_samples_leaf=20, l2_regularization=1.0)
        else:
            m = make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=2000))
            X = X.fillna(X.median()); Xt = Xt.fillna(X.median())
        m.fit(X, tr.y)
        p_tr = m.predict_proba(X)[:, 1]
        thr = np.quantile(p_tr, thr_q)          # threshold from TRAINING predictions only
        p = m.predict_proba(Xt)[:, 1]
        te = te.assign(p=p, tk=p >= thr)
        out.append(te)
    o = pd.concat(out)
    o["era"] = pd.cut(o.year, [2013, 2015, 2019, 2023, 2026], labels=["14-15", "16-19", "20-23", "24-26"])
    rows = []
    for e, g in o.groupby("era", observed=True):
        yrs = g.year.nunique() if e != "24-26" else 2.73
        auc = roc_auc_score(g.y, g.p) if g.y.nunique() > 1 else np.nan
        rows.append({"era": e, "n": len(g), "AUC": auc, "base avgR": g.r.mean(), "taken%": 100 * g.tk.mean(),
                     "taken avgR": g.r[g.tk].mean(), "skipped avgR": g.r[~g.tk].mean(),
                     "base R/yr": g.r.sum() / yrs, "taken R/yr": g.r[g.tk].sum() / yrs})
    return pd.DataFrame(rows)

for mod in ["GOLD_BO", "GOLD_ASIA", "IDX_DIP"]:
    for model in ["gbm", "logit"]:
        print(f"\n=== {mod} / {model}")
        print(walk(mod, model).round(3).to_string(index=False))
