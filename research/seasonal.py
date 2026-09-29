"""January gold seasonal module: long XAUUSD at the first session of January (after rollover),
exit after N trading days or at the SL. Year-by-year, full engine."""
import numpy as np, pandas as pd
import engine as E, gold, indicators as I, strategies as S
pd.set_option("display.width", 250)
b = gold.m5("2004-06-15")
d1 = S.bars_tf(b, "D1")
atr = I.atr(d1, 20)
spread = S.spread_model(b, floor=0.25)
costs = E.Costs(slip=0.08, lot_step=1e-6, min_lot=0, max_lot=1e12)

def jan(start_day=1, hold_days=20, sl_atr=2.5, month=1, end_offset=0):
    n = len(b)
    # signal on the last D1 bar of December (or of the chosen month-1) -> executes first session of the month
    sd_d = np.zeros(len(d1)); ex_d = np.zeros(len(d1))
    idx = d1.index
    st = idx + pd.Timedelta(hours=26)       # a server-day label (NY+7h) of the bar; D1 open ~21-22 UTC prev day
    months = st.month; years = st.year
    for y in np.unique(years):
        m = np.flatnonzero((years == y) & (months == month))
        if len(m) < 5:
            continue
        first = m[0] + (start_day - 1)
        if first - 1 < 0:
            continue
        sd_d[first - 1] = 1                   # decision at close of the bar before the first bar of the month
        ex_d[min(first - 1 + hold_days, len(d1) - 1)] = 1
    pos = S.exec_pos(d1.index, "D1", b.index)
    sd = S.place(n, pos, sd_d).astype(np.int64)
    sl = S.place(n, pos, (atr * sl_atr).values * (sd_d > 0))
    sx = S.place(n, pos, ex_d).astype(np.int64)
    sig = E.Signals("jan", sd, sl, np.zeros(n), sx, E.StratParams(risk=0.01))
    r = E.run(b, [sig], costs, spread=spread, equity0=1e8, compounding=False)
    return r.trades

rows = []
for hold, sl in [(20, 2.5), (15, 2.5), (20, 4.0), (10, 2.5)]:
    t = jan(hold_days=hold, sl_atr=sl)
    t["year"] = t.entry_time.dt.year
    rows.append({"cfg": f"hold {hold}d sl {sl}ATR", "n": len(t), "win": (t.r > 0).mean(), "avgR": t.r.mean(),
                 "avgR 05-11": t[t.year <= 2011].r.mean(), "avgR 12-19": t[(t.year >= 2012) & (t.year <= 2019)].r.mean(),
                 "avgR 20-23": t[(t.year >= 2020) & (t.year <= 2023)].r.mean(), "avgR 24-26": t[t.year >= 2024].r.mean()})
    if hold == 20 and sl == 2.5:
        print(t[["entry_time", "exit_time", "r", "reason"]].assign(r=lambda x: x.r.round(2)).to_string(index=False))
print(pd.DataFrame(rows).round(3).to_string(index=False))
# placebo: same rule in every other month (is January special?)
pl = []
for mo in range(1, 13):
    t = jan(month=mo)
    pl.append({"month": mo, "avgR": round(t.r.mean(), 3), "win": round((t.r > 0).mean(), 2), "n": len(t)})
print(pd.DataFrame(pl).T.to_string())
