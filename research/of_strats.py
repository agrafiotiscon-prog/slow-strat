"""Classic order-flow / volume strategies on gold (M5 execution, same cost model as everything else)."""
import itertools, sys, time
import numpy as np, pandas as pd
import engine as E, gold, indicators as I, orderflow as OF, strategies as S

pd.set_option("display.width", 260)
b = gold.m5("2006-06-01")
F = OF.m5_flow(b)
PROF = pd.read_parquet("/tmp/of_profile.parquet")
n = len(b)
st = S.server_time(b.index)
sday = st.normalize()
utc_h = b.index.hour + b.index.minute / 60.0
d1 = S.bars_tf(b, "D1")
atrD = I.atr(d1, 14)
atrD_k = pd.Series(atrD.values, index=d1.index + pd.Timedelta("1D"))
ATRD = atrD_k.reindex(b.index, method="ffill").values
c = b.close.values; h = b.high.values; l = b.low.values; o = b.open.values
P = PROF.reindex(sday)  # prior-day profile for each bar's server day
POC, VAH, VAL = P.poc.values, P.vah.values, P.val.values
spread = S.spread_model(b, floor=0.25)
costs = E.Costs(slip=0.08, lot_step=1e-6, min_lot=0, max_lot=1e12)


def run(sd, sl, tp, sx=None, max_hold=0, name="x"):
    sig = E.Signals(name, sd, sl, tp, sx, E.StratParams(risk=0.01, max_hold=max_hold))
    r = E.run(b, [sig], costs, spread=spread, equity0=1e8, compounding=False)
    return r.trades


def summarize(t, label):
    t = t.copy()
    t["era"] = pd.cut(t.entry_time.dt.year, [2006, 2011, 2015, 2019, 2023, 2027], labels=["07-11", "12-15", "16-19", "20-23", "24-26"])
    row = {"strategy": label, "n/yr": len(t) / 20.3, "win": (t.r > 0).mean(), "avgR": t.r.mean()}
    for e, g in t.groupby("era", observed=True):
        row[e] = g.r.mean()
    return row


def one_per_day(mask):
    """keep only the first True per server day"""
    s = pd.Series(mask, index=b.index)
    first = s & ~s.groupby(sday).cumsum().shift(1, fill_value=0).astype(bool)
    return first.values & mask


rows = []
# ---- A. VWAP deviation fade (London+NY), exit at VWAP or time
vw = F.vwap_day.values
dev = (c - vw) / ATRD
sess = (utc_h >= 8) & (utc_h < 17)
for k, slk, hold in itertools.product([0.8, 1.2], [0.5, 1.0], [24, 72]):
    lng = sess & (dev < -k) & (c > o)          # stretched below VWAP + bullish bar (buyers stepping in)
    sht = sess & (dev > k) & (c < o)
    sig_l, sig_s = one_per_day(lng), one_per_day(sht)
    sd = np.zeros(n, np.int64); sd[1:][sig_l[:-1]] = 1; sd[1:][sig_s[:-1]] = -1
    sl = np.where(sd != 0, np.roll(ATRD, 1) * slk, 0)
    tp = np.where(sd != 0, np.abs(np.roll(c - vw, 1)), 0)     # target = back to VWAP
    rows.append(summarize(run(sd, sl, tp, max_hold=hold), f"VWAP fade k={k} sl={slk} hold={hold}"))

# ---- B. Value-area '80% rule': open outside prior VA, two consecutive M30 closes back inside -> target opposite edge
m30 = D30 = S.bars_tf(b, "M30") if False else None
first_bar = np.r_[True, sday[1:] != sday[:-1]]
day_open = pd.Series(np.where(first_bar, o, np.nan), index=b.index).groupby(sday).transform("first").values
inside = (c > VAL) & (c < VAH)
# M30 closes: bar whose minute%30==25 (last M5 of a 30-min block)
m30_close = (b.index.minute % 30) == 25
ins30 = pd.Series(np.where(m30_close, inside, np.nan), index=b.index).ffill()
prev_ins30 = pd.Series(np.where(m30_close, inside, np.nan), index=b.index).dropna().shift(1).reindex(b.index).ffill()
two_inside = m30_close & (ins30.values == 1) & (prev_ins30.values == 1)
for slk in [0.5, 1.0]:
    lng = two_inside & (day_open < VAL) & (utc_h >= 6) & (utc_h < 18)     # opened below VA, accepted back in -> long to VAH
    sht = two_inside & (day_open > VAH) & (utc_h >= 6) & (utc_h < 18)
    sig_l, sig_s = one_per_day(lng), one_per_day(sht)
    sd = np.zeros(n, np.int64); sd[1:][sig_l[:-1]] = 1; sd[1:][sig_s[:-1]] = -1
    sl = np.where(sd != 0, np.roll(ATRD, 1) * slk, 0)
    tp = np.where(sd == 1, np.roll(VAH - c, 1), np.where(sd == -1, np.roll(c - VAL, 1), 0))
    tp = np.where(tp > 0, tp, 0)
    rows.append(summarize(run(sd, sl, tp, max_hold=288), f"80% rule sl={slk}"))

# ---- C. Prior-day POC rejection: price tags prior POC from above/below and closes back away with delta support
delta = F.delta.values
for slk, tpk in [(0.3, 0.6), (0.5, 1.0)]:
    tag_from_above = (l <= POC) & (c > POC) & (o > POC) & (delta > 0)
    tag_from_below = (h >= POC) & (c < POC) & (o < POC) & (delta < 0)
    ok = (utc_h >= 7) & (utc_h < 17)
    sig_l, sig_s = one_per_day(tag_from_above & ok), one_per_day(tag_from_below & ok)
    sd = np.zeros(n, np.int64); sd[1:][sig_l[:-1]] = 1; sd[1:][sig_s[:-1]] = -1
    sl = np.where(sd != 0, np.roll(ATRD, 1) * slk, 0); tp = np.where(sd != 0, np.roll(ATRD, 1) * tpk, 0)
    rows.append(summarize(run(sd, sl, tp, max_hold=288), f"POC rejection sl={slk} tp={tpk}"))

# ---- D. Volume-climax reversal at a 3-hour extreme
hh36 = pd.Series(h).rolling(36).max().values; ll36 = pd.Series(l).rolling(36).min().values
clim = F.climax.values
for slk, tpk in [(0.3, 0.6), (0.5, 1.0)]:
    top = clim & (h >= hh36) & (c < (h + l) / 2)
    bot = clim & (l <= ll36) & (c > (h + l) / 2)
    sd = np.zeros(n, np.int64); sd[1:][bot[:-1]] = 1; sd[1:][top[:-1]] = -1
    sl = np.where(sd != 0, np.roll(ATRD, 1) * slk, 0); tp = np.where(sd != 0, np.roll(ATRD, 1) * tpk, 0)
    rows.append(summarize(run(sd, sl, tp, max_hold=144), f"Climax reversal sl={slk} tp={tpk}"))

# ---- E. London / NY opening-range breakout confirmed by relative volume
rvol = F.rvol.values
for start_h, k_rvol, tpk in itertools.product([7, 13.5], [0.0, 1.5], [1.0, 2.0]):
    in_or = (utc_h >= start_h) & (utc_h < start_h + 0.5)
    or_hi = pd.Series(np.where(in_or, h, np.nan), index=b.index).groupby(sday).transform("max").values
    or_lo = pd.Series(np.where(in_or, l, np.nan), index=b.index).groupby(sday).transform("min").values
    win = (utc_h >= start_h + 0.5) & (utc_h < start_h + 3)
    vol_ok = rvol > k_rvol if k_rvol else np.ones(n, bool)
    up = win & (c > or_hi) & vol_ok; dn = win & (c < or_lo) & vol_ok
    first = one_per_day(up | dn)
    sd = np.zeros(n, np.int64); sd[1:][(first & up)[:-1]] = 1; sd[1:][(first & dn)[:-1]] = -1
    rngv = np.roll(or_hi - or_lo, 1)
    sl = np.where(sd != 0, rngv, 0); tp = np.where(sd != 0, rngv * tpk, 0)
    rows.append(summarize(run(sd, sl, tp, max_hold=288), f"ORB {start_h}h rvol>{k_rvol} tp={tpk}xOR"))

df = pd.DataFrame(rows)
df["min_dev"] = df[["12-15", "16-19", "20-23"]].min(axis=1)
print(df.sort_values("min_dev", ascending=False).round(3).to_string(index=False))
df.to_csv("../results/orderflow_strategies.csv", index=False)
