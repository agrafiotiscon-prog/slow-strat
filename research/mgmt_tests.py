"""Trade-management / timing checks for the gold trend module (full engine)."""
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
for be in [0.0, 1.0, 1.5, 2.0]:
    for boff in ([0.0] if be == 0 else [0.0, 0.25]):
        sig = S.trend_bo(b, tf="H4", n_entry=80, filt="sma200", sl_atr=1.0, atr_n=20,
                         params=E.StratParams(risk=0.01, trail_r=3.0, be_trigger=be, be_offset=boff), name="g")
        t, rc, rl = B.gold_r([sig], bars=b)
        rows.append({"cfg": f"BE at {be}R (+{boff}R)" if be else "base (no BE)", "win": round((t.r > 0).mean(), 3), "avgR": round(t.r.mean(), 3), **era_stats(rc)})
print(pd.DataFrame(rows).to_string(index=False))
# time-of-day and NFP-day breakdown of base trades
sig = S.trend_bo(b, tf="H4", n_entry=80, filt="sma200", sl_atr=1.0, atr_n=20, params=E.StratParams(risk=0.01, trail_r=3.0), name="g")
t, rc, rl = B.gold_r([sig], bars=b)
ny = S.ny_time(pd.DatetimeIndex(t.entry_time))
t["ny_slot"] = ny.hour
t["era"] = pd.cut(t.entry_time.dt.year, [2006, 2011, 2015, 2019, 2023, 2027], labels=["07-11", "12-15", "16-19", "20-23", "24-26"])
print("\navg R by New York entry hour (H4 slot) and era"); print(t.pivot_table(index="ny_slot", columns="era", values="r", aggfunc=["mean", "count"], observed=True).round(2).to_string())
d = pd.DatetimeIndex(t.entry_time)
first_fri = (ny.dayofweek == 4) & (ny.day <= 7)
t["nfp_day"] = first_fri
print("\nNFP-day (first Friday) entries vs others:"); print(t.groupby("nfp_day").r.agg(["mean", "count"]).round(3))
