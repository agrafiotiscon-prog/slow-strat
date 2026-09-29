"""Gold H4 breakout with a GLD-ETF-flow confirmation filter: full-engine test by era (0.6% risk, compounded)."""
import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np, pandas as pd, book as B, gold, strategies as S, engine as E
b = gold.m5(B.GOLD_START)
rows = []
for lab, filt, ch, sl in [("base", "sma200", 80, 1.0), ("gld vs SMA50", "sma200_gld50", 80, 1.0), ("gld 20d chg", "sma200_gld20", 80, 1.0),
                          ("gld 60d chg", "sma200_gld60", 80, 1.0), ("base ch60", "sma200", 60, 1.0), ("gld50 ch60", "sma200_gld50", 60, 1.0),
                          ("base sl1.25", "sma200", 80, 1.25), ("gld50 sl1.25", "sma200_gld50", 80, 1.25), ("gld60 ch60", "sma200_gld60", 60, 1.0)]:
    sig = S.trend_bo(b, tf="H4", n_entry=ch, filt=filt, sl_atr=sl, atr_n=20, params=E.StratParams(risk=0.01, trail_r=3.0), name="g")
    t, rc, rl = B.gold_r([sig], bars=b)
    x = rc.resample("1D").last().dropna(); eq = (1 + 0.006 * x.diff().fillna(0)).cumprod()
    xl = rl.resample("1D").min().dropna().reindex(x.index).fillna(x)
    r = {"cfg": lab, "trades": len(t), "win": round((t.r > 0).mean(), 3), "avgR": round(t.r.mean(), 3)}
    for e, (a, z) in {"07-11": ("2007", "2011"), "12-15": ("2012", "2015"), "16-19": ("2016", "2019"), "20-23": ("2020", "2023"),
                      "24-26": ("2024", "2026"), "ALL": ("2007", "2026")}.items():
        q = eq.loc[a:z]; yrs = (q.index[-1] - q.index[0]).days / 365.25
        cg = (q.iloc[-1] / q.iloc[0]) ** (1 / yrs) - 1; dd = (1 - q / q.cummax()).max()
        r[e] = f"{cg*100:.1f}/{dd*100:.1f}"
    rows.append(r)
pd.set_option("display.width", 250); print(pd.DataFrame(rows).to_string(index=False))
pd.DataFrame(rows).to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "results", "gld_filter_gold_trend.csv"), index=False)
