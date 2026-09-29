"""Position-sizing overlays on the actual module trade lists (closed-trade equity, per-trade risk):
   (1) volatility targeting, (2) equity-curve filter, (3) gold month-of-year seasonality check."""
import pickle, numpy as np, pandas as pd
import gold, strategies as S, indicators as I
pd.set_option("display.width", 250)
cur, trades = pickle.load(open("/tmp/final_curves_v2.pkl", "rb"))
b = gold.m5("2006-06-01"); d1 = S.bars_tf(b, "D1")
ret = np.log(d1.close).diff()
rv = ret.rolling(60).std() * np.sqrt(252)
rv_ratio = (rv / rv.rolling(504, min_periods=250).median()); rv_ratio.index = rv_ratio.index + pd.Timedelta("1D")
ERAS = {"07-11": ("2007", "2012"), "12-15": ("2012", "2016"), "16-19": ("2016", "2020"), "20-23": ("2020", "2024"), "24-26": ("2024", "2027")}

def stats(t, mult, risk):
    """closed-trade compounded equity with per-trade multipliers; returns CAGR/maxDD per era"""
    t = t.assign(m=mult).sort_values("exit_time")
    out = {}
    for e, (a, z) in ERAS.items():
        x = t[(t.exit_time >= a) & (t.exit_time < z)]
        eq = np.cumprod(1 + risk * x.m.values * x.r.values)
        if len(eq) == 0: out[e] = "n/a"; continue
        yrs = (pd.Timestamp(z) - pd.Timestamp(a)).days / 365.25 if e != "24-26" else 2.73
        pk = np.maximum.accumulate(np.r_[1, eq]); dd = (1 - np.r_[1, eq] / pk).max()
        out[e] = f"{((eq[-1]) ** (1 / yrs) - 1) * 100:.1f}/{dd * 100:.1f}"
    return out

for mod, risk in [("GOLD_BO", 0.006), ("GOLD_ASIA", 0.005)]:
    t = trades[mod].sort_values("entry_time").reset_index(drop=True)
    vr = rv_ratio.reindex(pd.DatetimeIndex(t.entry_time), method="ffill").values
    rows = [{"overlay": "base", **stats(t, np.ones(len(t)), risk)}]
    for lo, hi in [(0.5, 1.5), (0.67, 1.25)]:
        m = np.clip(1 / np.nan_to_num(vr, nan=1.0), lo, hi)
        rows.append({"overlay": f"vol-target clip[{lo},{hi}]", **stats(t, m, risk)})
    # equity-curve filter: half size when the module's own R-equity is below its N-trade SMA
    for N, lowm in [(20, 0.5), (50, 0.5), (20, 0.0)]:
        cumr = t.sort_values("exit_time").r.cumsum()
        # decision for trade i uses trades closed before its entry
        closed = t.sort_values("exit_time")
        m = []
        for i, row in t.iterrows():
            past = closed[closed.exit_time < row.entry_time].r
            if len(past) < N: m.append(1.0); continue
            c = past.cumsum().values
            m.append(1.0 if c[-1] >= c[-N:].mean() else lowm)
        rows.append({"overlay": f"equity filter N={N} low={lowm}", **stats(t, np.array(m), risk)})
    print(f"\n==== {mod} (CAGR/maxDD by era, closed-trade)")
    print(pd.DataFrame(rows).to_string(index=False))

# seasonality: mean daily gold return by calendar month, by era
r = pd.DataFrame({"r": ret * 1e4, "m": ret.index.month, "era": pd.cut(ret.index.year, [2005, 2011, 2015, 2019, 2023, 2026], labels=list(ERAS))})
print("\ngold mean daily return (bp) by month and era")
print(r.pivot_table(index="m", columns="era", values="r", aggfunc="mean", observed=True).round(1).T.to_string())
