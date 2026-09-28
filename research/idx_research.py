"""Daily dip-buying on equity indices (executed at next day's open)."""
import itertools, sys
import numpy as np, pandas as pd
import assets as A, engine as E, indicators as I

pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)

def segments(d):
    """split at data gaps > 30 days so indicators never straddle a gap"""
    gap = d.index.to_series().diff() > pd.Timedelta(days=30)
    seg = gap.cumsum().values
    return [d[seg == s] for s in np.unique(seg)]

def signals(d, rule="rsi2", lo=10, trend_n=200, exit_ma=5, sl_atr=0.0, max_hold=10, ibs_lo=0.2, atr_n=10):
    c = d.close
    tr = I.sma(c, trend_n) if trend_n else c * 0 - 1e18
    a = I.atr(d, atr_n)
    if rule == "rsi2":
        cond = I.rsi(c, 2) < lo
    elif rule == "ibs":
        ibs = (c - d.low) / (d.high - d.low).replace(0, np.nan)
        cond = ibs < ibs_lo
    elif rule == "rsi2ibs":
        ibs = (c - d.low) / (d.high - d.low).replace(0, np.nan)
        cond = (I.rsi(c, 2) < lo) & (ibs < ibs_lo)
    elif rule == "down3":
        cond = (c < c.shift(1)) & (c.shift(1) < c.shift(2)) & (c.shift(2) < c.shift(3))
    elif rule == "lowest5":
        cond = c <= c.rolling(5).min()
    long_ = (c > tr) & cond
    ex = (c > I.sma(c, exit_ma)).astype(int)  # close longs
    n = len(d)
    sd = np.zeros(n, np.int64); sl = np.zeros(n); tp = np.zeros(n); sx = np.zeros(n, np.int64)
    L = long_.values; X = ex.values; AA = a.values
    for i in range(n - 1):
        if L[i]:
            sd[i + 1] = 1
            sl[i + 1] = AA[i] * sl_atr if sl_atr > 0 else AA[i] * 50  # "no stop" = catastrophic stop far away
        if X[i]:
            sx[i + 1] = 1
    sx = np.where(sd == 1, 0, sx)
    return sd, sl, tp, sx

def run(symbol, risk=0.01, **kw):
    d = A.daily(symbol)
    cst = A.COST[symbol]
    trades = []; eqs = []
    for seg in segments(d):
        if len(seg) < 260:
            continue
        sd, sl, tp, sx = signals(seg, **kw)
        p = E.StratParams(risk=risk, max_hold=kw.get("max_hold", 10))
        s = E.Signals(symbol, sd, sl, tp, sx, p)
        sp = seg.close.values * cst["spread_bp"] * 1e-4
        costs = E.Costs(contract=cst["contract"], commission=cst["commission"], slip=0.0, lot_step=0.01, min_lot=0.01,
                        max_lot=1e6, swap_long=cst["swap_long"], swap_short=cst["swap_short"], triple_dow=4)
        # slippage as 0.5bp of price
        costs.slip = float(np.median(seg.close.values) * 0.5e-4)
        r = E.run(seg, [s], costs, spread=sp, equity0=100_000, compounding=False)
        trades.append(r.trades)
    t = pd.concat(trades)
    return t

def summarize(t, label):
    t = t.copy(); t["y"] = t.exit_time.dt.year
    dev = t[t.exit_time < "2024-01-01"]; hold = t[t.exit_time >= "2024-01-01"]
    f = lambda x: pd.Series({"n": len(x), "win": (x.pnl > 0).mean(), "avg_r": x.r.mean(), "pf": x.pnl[x.pnl>0].sum()/max(1e-9,-x.pnl[x.pnl<0].sum())})
    return {"label": label, **{f"dev_{k}": v for k, v in f(dev).items()}, **{f"hold_{k}": v for k, v in f(hold).items()},
            "worst_year_r": t.groupby("y").r.sum().min()}

if __name__ == "__main__":
    rows = []
    for sym in ["US500", "NAS100", "US30"]:
        for rule, lo, trend_n, exit_ma, sl_atr, mh in itertools.product(["rsi2", "ibs", "rsi2ibs", "down3", "lowest5"], [5, 10, 20], [0, 100, 200], [3, 5, 10], [0.0, 2.0, 3.0], [5, 10]):
            if rule in ("down3", "lowest5") and lo != 10:
                continue
            kw = dict(rule=rule, lo=lo, trend_n=trend_n, exit_ma=exit_ma, sl_atr=sl_atr, max_hold=mh, ibs_lo=lo / 50)
            t = run(sym, **kw)
            rows.append({"sym": sym, **kw, **summarize(t, "")})
    df = pd.DataFrame(rows).drop(columns="label")
    df.to_csv("../results/sweeps/idx_daily.csv", index=False)
    # robust: positive in dev for all 3 indices with same params
    key = ["rule", "lo", "trend_n", "exit_ma", "sl_atr", "max_hold"]
    g = df.groupby(key).agg(dev_r_min=("dev_avg_r", "min"), dev_r_mean=("dev_avg_r", "mean"), dev_win=("dev_win", "mean"),
                           dev_n=("dev_n", "sum"), hold_r_mean=("hold_avg_r", "mean"), hold_win=("hold_win", "mean"), hold_n=("hold_n", "sum"))
    print(g.sort_values("dev_r_min", ascending=False).head(30).round(3).to_string())
