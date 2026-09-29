"""Index dip-buying on broker-style daily bars (server day = NY 17:00 close), execution on H1 bars."""
import itertools
import numpy as np, pandas as pd
import multi as M, strategies as S, engine as E, indicators as I

def dip(bars, params, rule="rsi2ibs", lo=10, ibs_lo=0.2, trend_n=200, exit_ma=5, sl_atr=2.0, max_hold_d=10, atr_n=10,
        dxy_max=None, dxy_n=200):
    d = S.bars_tf(bars, "D1")
    c = d.close
    ibs = (c - d.low) / (d.high - d.low).replace(0, np.nan)
    r2 = I.rsi(c, 2)
    cond = {"rsi2": r2 < lo, "ibs": ibs < ibs_lo, "rsi2ibs": (r2 < lo) & (ibs < ibs_lo)}[rule]
    long_ = cond & (c > I.sma(c, trend_n))
    if dxy_max is not None:
        import ext
        dx = ext.daily_features()[f"dxy_vs_sma{dxy_n}"]
        # value known at this D1 bar's close (FRED noon rate of that day or earlier)
        known = dx.reindex(d.index + pd.Timedelta("1D"), method="ffill").values
        long_ &= pd.Series(known, d.index).fillna(0).values <= dxy_max
    a = I.atr(d, atr_n)
    ex = (c > I.sma(c, exit_ma)).astype(int)
    n = len(bars)
    pos = S.exec_pos(d.index, "D1", bars.index)
    sd = S.place(n, pos, long_.astype(float).values).astype(np.int64)
    sl = S.place(n, pos, (a * sl_atr).values)
    sx = S.place(n, pos, ex.astype(float).values).astype(np.int64)
    sx = np.where(sd == 1, 0, sx)
    params.max_hold = max_hold_d * 24  # H1 bars
    return E.Signals("dip", sd, sl, np.zeros(n), sx, params)

if __name__ == "__main__":
    rows = []
    for sym in ["US500", "NAS100", "US30", "GER40", "UK100"]:
        for rule, lo, trend_n, exit_ma, sl_atr in itertools.product(["rsi2", "rsi2ibs"], [5, 10, 20], [100, 200], [3, 5, 10], [2.0, 3.0]):
            tr, rc, rl = M.r_curve(sym, dip, rule=rule, lo=lo, ibs_lo=0.25, trend_n=trend_n, exit_ma=exit_ma, sl_atr=sl_atr)
            t = tr[tr.exit_time < "2023-09-12"]
            t26 = tr[tr.exit_time > "2026-01-01"]
            rows.append(dict(sym=sym, rule=rule, lo=lo, trend_n=trend_n, exit_ma=exit_ma, sl_atr=sl_atr, n=len(t), win=(t.r > 0).mean(),
                             avg_r=t.r.mean(), r_1317=t[t.exit_time < "2018"].r.mean(), r_1823=t[t.exit_time >= "2018"].r.mean(),
                             n26=len(t26), r26=t26.r.mean()))
    df = pd.DataFrame(rows)
    df.to_csv("../results/sweeps/idx_server.csv", index=False)
    key = ["rule", "lo", "trend_n", "exit_ma", "sl_atr"]
    g = df.groupby(key).agg(min_r=("avg_r", "min"), mean_r=("avg_r", "mean"), win=("win", "mean"), n=("n", "sum"),
                            r_1317=("r_1317", "mean"), r_1823=("r_1823", "mean"), n26=("n26", "sum"), r26=("r26", "mean"))
    pd.set_option("display.width", 250)
    print(g.sort_values("min_r", ascending=False).head(20).round(3).to_string())
    print(df[(df.rule == "rsi2ibs") & (df.lo == 10) & (df.trend_n == 200) & (df.exit_ma == 5) & (df.sl_atr == 2.0)].round(3).to_string())
