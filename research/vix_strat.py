"""VIX-stretch dip buying on US indices (daily), with real VIX and a broker-available proxy."""
import itertools
import numpy as np, pandas as pd
import assets as A, engine as E, ext, indicators as I, multi as M, strategies as S
pd.set_option("display.width", 250)
VIX = ext.vix().close

def vix_dip(bars, params, k=0.10, trend_n=200, exit_mode="vix", sl_atr=2.5, max_hold_d=10, src="vix", atr_n=10,
            dxy_max=None, rsi_lo=None):
    d = S.bars_tf(bars, "D1")
    c = d.close
    # VIX value known at this D1 bar's close: VIX dated <= the bar's UTC date (closes 16:15 NY, before 17:00 NY)
    day = (d.index + pd.Timedelta("1D")).normalize() - pd.Timedelta("1D")
    if src == "vix":
        v = VIX.reindex(pd.DatetimeIndex(day), method="ffill").values
        v = pd.Series(v, d.index)
    else:  # proxy: 5-day realized vol of the index itself, annualised
        v = np.log(c).diff().rolling(5).std() * np.sqrt(252) * 100
    stretch = v / v.rolling(10).mean() - 1
    cond = (stretch > k) & (c > I.sma(c, trend_n))
    if rsi_lo is not None:
        cond &= I.rsi(c, 2) < rsi_lo
    if dxy_max is not None:
        dx = ext.daily_features()["dxy_vs_sma200"]
        dxv = dx.reindex(d.index + pd.Timedelta("1D"), method="ffill").values
        cond &= pd.Series(dxv, d.index).fillna(0) <= dxy_max
    a = I.atr(d, atr_n)
    if exit_mode == "vix":
        ex = (v < v.rolling(10).mean())
    else:
        ex = c > I.sma(c, 5)
    n = len(bars)
    pos = S.exec_pos(d.index, "D1", bars.index)
    sd = S.place(n, pos, cond.astype(float).values).astype(np.int64)
    sl = S.place(n, pos, (a * sl_atr).values)
    sx = S.place(n, pos, ex.astype(int).astype(float).values).astype(np.int64)
    sx = np.where(sd == 1, 0, sx)
    params.max_hold = max_hold_d * 24
    return E.Signals("vixdip", sd, sl, np.zeros(n), sx, params)

ERA = {"13-15": ("2013", "2016"), "16-19": ("2016", "2020"), "20-23": ("2020", "2024"), "24-26": ("2024", "2027")}
rows = []
for src, k, exit_mode, sl_atr, trend_n in itertools.product(["vix", "proxy"], [0.05, 0.10, 0.20], ["vix", "sma5"], [2.0, 3.0], [0, 200]):
    allt = []
    for s in ["US500", "NAS100", "US30"]:
        tr, rc, rl = M.r_curve(s, vix_dip, bars=A.exec_bars(s), k=k, exit_mode=exit_mode, sl_atr=sl_atr, src=src,
                               trend_n=trend_n if trend_n else 1)
        allt.append(tr)
    t = pd.concat(allt)
    row = dict(src=src, k=k, exit=exit_mode, sl=sl_atr, trend=trend_n, n=len(t), win=(t.r > 0).mean(), avgR=t.r.mean())
    for e, (a, z) in ERA.items():
        x = t[(t.entry_time >= a) & (t.entry_time < z)]
        row[e] = x.r.mean(); row[e + "_n"] = len(x)
    rows.append(row)
df = pd.DataFrame(rows)
df["min_dev"] = df[["13-15", "16-19", "20-23"]].min(axis=1)
print(df.sort_values("min_dev", ascending=False).round(3).to_string(index=False))
