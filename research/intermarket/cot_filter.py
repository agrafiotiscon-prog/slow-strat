"""COT positioning as a filter on the gold H4 breakout, full engine (the two per-trade candidates
from pos_scan.py): non-commercial 3-year COT index in the trade direction, and contrarian
4-week managed-money change. COT is used from the Monday after the as-of Tuesday."""
import sys; sys.path.insert(0, ".")
import numpy as np, pandas as pd
import book as B, engine as E, gold, positioning as P, strategies as S
pd.set_option("display.width", 250)
b = gold.m5(B.GOLD_START)
W = P.weekly_features()


def era_stats(rc, risk=0.006):
    x = rc.resample("1D").last().dropna(); eq = (1 + risk * x.diff().fillna(0)).cumprod(); out = {}
    for e, (a, z) in {"07-11": ("2007", "2011"), "12-15": ("2012", "2015"), "16-19": ("2016", "2019"), "20-23": ("2020", "2023"),
                      "24-26": ("2024", "2026"), "ALL": ("2007", "2026")}.items():
        q = eq.loc[a:z]; yrs = (q.index[-1] - q.index[0]).days / 365.25
        out[e] = f"{((q.iloc[-1]/q.iloc[0])**(1/yrs)-1)*100:.1f}/{(1-q/q.cummax()).max()*100:.1f}"
    return out


def feat_at_bars(col):
    f = W[col].dropna()
    f = f[~f.index.duplicated(keep="last")].sort_index()
    return f.reindex(b.index, method="ffill").values


nc = feat_at_bars("nc_rank156") - 0.5
mm = feat_at_bars("mm_net_chg4")
rows = []
cfgs = [("base", None)]
for th in [0.0, 0.06, 0.12]:
    cfgs.append((f"COT index (non-comm) in trade dir > {th}", ("nc", th)))
for th in [0.0, 0.01, 0.02]:
    cfgs.append((f"managed-money 4w change against trade < {th}", ("mm", th)))
for name, cfg in cfgs:
    sig = S.trend_bo(b, tf="H4", n_entry=80, filt="sma200", sl_atr=1.0, atr_n=20,
                     params=E.StratParams(risk=0.01, trail_r=3.0), name="g")
    if cfg:
        kind, th = cfg
        d = sig.direction
        if kind == "nc":
            ok = np.nan_to_num(nc * d, nan=1.0) > th
        else:
            ok = np.nan_to_num(mm * d, nan=-1.0) < th
        sig.direction = np.where(ok, d, 0)
    t, rc, rl = B.gold_r([sig], bars=b)
    rows.append({"filter": name, "n": len(t), "win": round((t.r > 0).mean(), 3), "avgR": round(t.r.mean(), 3), **era_stats(rc)})
    print(rows[-1], flush=True)
df = pd.DataFrame(rows)
print(df.to_string(index=False))
df.to_csv("../results/cot_filter_gold_trend.csv", index=False)

# ---- plateau check for the contrarian managed-money rule: look-back (weeks) x threshold
c = P.cot_disagg()
mmn = (c.m_money_positions_long_all - c.m_money_positions_short_all) / c.open_interest_all
rows2 = []
for wk in [2, 4, 8, 13]:
    ch = (mmn - mmn.shift(wk)); ch.index = ch.index + pd.Timedelta(days=6)
    ch = ch[~ch.index.duplicated(keep="last")].sort_index()
    v = ch.reindex(b.index, method="ffill").values
    for th in [0.0, 0.02, 0.04]:
        sig = S.trend_bo(b, tf="H4", n_entry=80, filt="sma200", sl_atr=1.0, atr_n=20,
                         params=E.StratParams(risk=0.01, trail_r=3.0), name="g")
        d = sig.direction
        sig.direction = np.where(np.nan_to_num(v * d, nan=-1.0) < th, d, 0)
        t, rc, rl = B.gold_r([sig], bars=b)
        rows2.append({"weeks": wk, "thresh": th, "n": len(t), "avgR": round(t.r.mean(), 3), **era_stats(rc)})
        print(rows2[-1], flush=True)
df2 = pd.DataFrame(rows2)
print(df2.to_string(index=False))
df2.to_csv("../results/cot_mm_contrarian_plateau.csv", index=False)
