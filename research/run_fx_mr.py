import itertools, time, multiprocessing as mp
import numpy as np, pandas as pd
import multi as M, strategies as S, engine as E, indicators as I

ASSETS = M.FX + ["XAGUSD"] + M.IDX

def mr(b, params, tf="D1", lo=10, trend_n=0, exit_ma=5, sl_atr=2.0, max_hold=10, atr_n=14, sides="both"):
    d = S.bars_tf(b, tf)
    c = d.close
    r2 = I.rsi(c, 2)
    ok_l = np.ones(len(d), bool); ok_s = np.ones(len(d), bool)
    if trend_n:
        m = I.sma(c, trend_n); ok_l = (c > m).values; ok_s = (c < m).values
    L = (r2 < lo).values & ok_l
    Sh = (r2 > 100 - lo).values & ok_s
    if sides == "long": Sh[:] = False
    dd = np.where(L, 1, np.where(Sh, -1, 0))
    a = I.atr(d, atr_n)
    ma = I.sma(c, exit_ma)
    ex = np.where((c > ma).values & (c < ma).values, 2, np.where((c > ma).values, 1, np.where((c < ma).values, -1, 0)))
    n = len(b); pos = S.exec_pos(d.index, tf, b.index)
    sd = S.place(n, pos, dd.astype(float)).astype(np.int64)
    sl = S.place(n, pos, (a * sl_atr).values)
    sx = S.place(n, pos, ex.astype(float)).astype(np.int64)
    sx = np.where((sd != 0) & (sx == sd), 0, sx)
    params.max_hold = int(max_hold * pd.Timedelta(S.TF[tf]) / pd.Timedelta("1h"))
    return E.Signals("mr", sd, sl, np.zeros(n), sx, params)

ERAS = {"08-11": ("2008", "2011-12-31"), "12-15": ("2012", "2015-12-31"), "16-19": ("2016", "2019-12-31"), "20-23": ("2020", "2023-09-12"), "26": ("2026", "2026-12-31")}

def one(kw):
    out = dict(kw)
    for a in ASSETS:
        tr, rc, rl = M.r_curve(a, mr, **kw)
        for e, (s, z) in ERAS.items():
            x = tr[(tr.exit_time >= s) & (tr.exit_time <= z)]
            out[f"{a}|{e}"] = x.r.mean() if len(x) else np.nan
            out[f"{a}|{e}|n"] = len(x)
            out[f"{a}|{e}|w"] = (x.r > 0).mean() if len(x) else np.nan
    return out

if __name__ == "__main__":
    grid = dict(tf=["H4", "D1"], lo=[5, 15], trend_n=[0, 200], exit_ma=[5], sl_atr=[2.0, 4.0], max_hold=[10], sides=["both"])
    combos = [dict(zip(grid, v)) for v in itertools.product(*grid.values())]
    for a in ASSETS: M.h1(a)
    t = time.time()
    with mp.get_context("fork").Pool(4) as p:
        rows = p.map(one, combos, chunksize=1)
    pd.DataFrame(rows).to_pickle("../results/sweeps/fx_mr.pkl")
    print(f"{len(rows)} in {time.time()-t:.0f}s")
