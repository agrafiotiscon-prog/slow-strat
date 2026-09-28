"""Summarise an EA-simulator run: per-period CAGR / max drawdown, yearly returns, per-module stats."""
import sys
import numpy as np, pandas as pd

def load(d):
    eq = pd.read_csv(d + "/equity.csv")
    eq["time"] = pd.to_datetime(eq.time, unit="s")
    eq = eq.set_index("time")
    tr = pd.read_csv(d + "/trades.csv")
    tr["t_open"] = pd.to_datetime(tr.t_open, unit="s"); tr["t_close"] = pd.to_datetime(tr.t_close, unit="s")
    tr["mod"] = (tr.magic - 7102600).map({1: "Gold trend", 2: "Gold Asia", 3: "Index dip"})
    tr["r"] = tr.pnl / (tr.sl_dist * tr.volume * np.where(tr.symbol == "XAUUSD", 100, 1))
    return eq, tr

PER = {"2008-2011": ("2008-01-01", "2011-12-31"), "2012-2015": ("2012-01-01", "2015-12-31"),
       "2016-2019": ("2016-01-01", "2019-12-31"), "2020-2023": ("2020-01-01", "2023-12-31"),
       "2024-2026*": ("2024-01-01", "2026-09-30"), "2025": ("2025-01-01", "2025-12-31"), "2026 YTD": ("2026-01-01", "2026-09-30"),
       "FULL": ("2007-06-01", "2026-09-30")}

def period_stats(eq, a, z):
    e = eq.loc[a:z]
    if len(e) < 20: return None
    c0 = e.equity.iloc[0]; yrs = (e.index[-1] - e.index[0]).days / 365.25
    cagr = (e.equity.iloc[-1] / c0) ** (1 / yrs) - 1
    pk = np.maximum.accumulate(np.r_[c0, e.equity.values])[1:]
    dd = ((pk - e.worst.values) / pk).max()
    m = e.equity.resample("ME").last().pct_change().dropna()
    return dict(cagr=cagr, maxdd=dd, ret_to_dd=cagr / dd if dd > 0 else np.nan, pos_months=(m > 0).mean(), worst_month=m.min())

if __name__ == "__main__":
    eq, tr = load(sys.argv[1])
    rows = [{"period": k, **s} for k, (a, z) in PER.items() if (s := period_stats(eq, a, z))]
    print(pd.DataFrame(rows).set_index("period").round(3).to_string())
    y = eq.equity.resample("YE").last()
    y0 = pd.concat([pd.Series([eq.equity.iloc[0]], index=[eq.index[0]]), y])
    yr = y0.pct_change().dropna()
    dd_y = eq.groupby(eq.index.year).apply(lambda e: ((np.maximum.accumulate(e.equity.values) - e.worst.values) / np.maximum.accumulate(e.equity.values)).max())
    print("\nYear   return   maxDD")
    for t, v in yr.items():
        print(f"{t.year}  {v*100:7.1f}%  {dd_y.get(t.year, np.nan)*100:6.1f}%")
    g = tr.groupby("mod")
    print("\n", pd.DataFrame({"trades": g.size(), "per_year": g.size() / 19.3, "win_rate": g.apply(lambda x: (x.pnl > 0).mean()),
                              "avg_R": g.r.mean(), "profit": g.pnl.sum()}).round(3).to_string())
    print(f"\nall trades: {len(tr)}  win rate {(tr.pnl>0).mean():.3f}")
