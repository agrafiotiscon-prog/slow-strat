"""Limit-order (pullback) entries for the gold H4 breakout: buy a little below the breakout
price, SL anchored where the market entry would have put it. Full engine, era split."""
import numpy as np, pandas as pd
import book as B, engine as E, gold, strategies as S
pd.set_option("display.width", 250)
b = gold.m5(B.GOLD_START)


def era_stats(rc, risk=0.006):
    x = rc.resample("1D").last().dropna(); eq = (1 + risk * x.diff().fillna(0)).cumprod(); out = {}
    for e, (a, z) in {"07-11": ("2007", "2011"), "12-15": ("2012", "2015"), "16-19": ("2016", "2019"), "20-23": ("2020", "2023"),
                      "24-26": ("2024", "2026"), "ALL": ("2007", "2026")}.items():
        q = eq.loc[a:z]; yrs = (q.index[-1] - q.index[0]).days / 365.25
        out[e] = f"{((q.iloc[-1]/q.iloc[0])**(1/yrs)-1)*100:.1f}/{(1-q/q.cummax()).max()*100:.1f}"
    return out


rows = []
for frac, exp in [(0.0, 0), (0.1, 48), (0.25, 48), (0.25, 96), (0.5, 48), (0.5, 96), (0.5, 144), (0.75, 96)]:
    sig = S.trend_bo(b, tf="H4", n_entry=80, filt="sma200", sl_atr=1.0, atr_n=20,
                     params=E.StratParams(risk=0.01, trail_r=3.0, lim_expiry=exp), name="g")
    if frac:
        sig.lim = np.where(sig.direction != 0, sig.sl * frac, 0.0)
    t, rc, rl = B.gold_r([sig], bars=b)
    rows.append({"cfg": "market (base)" if not frac else f"limit {frac}xATR exp {exp // 48}xH4", "n": len(t),
                 "win": round((t.r > 0).mean(), 3), "avgR": round(t.r.mean(), 3), "sumR": round(t.r.sum(), 1), **era_stats(rc)})
    print(rows[-1], flush=True)
df = pd.DataFrame(rows)
print(df.to_string(index=False))
df.to_csv("../results/limit_entry_tests.csv", index=False)
