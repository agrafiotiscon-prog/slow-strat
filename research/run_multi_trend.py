import itertools, os, sys, time, multiprocessing as mp
import numpy as np, pandas as pd
import multi as M, strategies as S, engine as E

ASSETS = ["XAUUSD", "XAGUSD"] + M.IDX + M.FX
ERAS = {"08-11": ("2008", "2011"), "12-15": ("2012", "2015"), "16-19": ("2016", "2019"), "20-23": ("2020", "2023-09-10"),
        "26": ("2026-03-27", "2026-09-30")}

def build(b, params, trail_r, trail_start, **kw):
    params.trail_r = trail_r; params.trail_start = trail_start
    return S.trend_bo(b, params=params, **kw)

def one(kw):
    out = {**kw}
    curves = {}
    for a in ASSETS:
        tr, rc, rl = M.r_curve(a, build, **dict(kw))
        curves[a] = (rc, rl)
        t = tr.copy(); t["y"] = t.exit_time.dt.year
        for e, (s, z) in ERAS.items():
            x = t[(t.exit_time >= s) & (t.exit_time <= pd.Timestamp(z) + pd.Timedelta(days=366 if len(z) == 4 else 1))]
            out[f"{a}|{e}"] = x.r.mean() if len(x) else np.nan
            out[f"{a}|{e}|n"] = len(x)
    # equal-risk portfolio in R per year by era
    ec, el = M.combine(curves, 0.001)
    for e, (s, z) in ERAS.items():
        st = M.curve_stats(ec, el, s, z)
        out[f"pf|{e}|sharpe"] = st.get("sharpe", np.nan)
    return out

if __name__ == "__main__":
    grid = dict(tf=["H4", "D1"], n_entry=[20, 55], filt=["none", "sma200", "rsi14"], sl_atr=[1.5, 3.0],
                trail_r=[1.5, 3.0], trail_start=[0.0], exit_n=[0], sides=["both"])
    combos = [dict(zip(grid, v)) for v in itertools.product(*grid.values())]
    for a in ASSETS: M.h1(a)  # load before fork
    t = time.time()
    with mp.get_context("fork").Pool(4) as p:
        rows = p.map(one, combos, chunksize=1)
    df = pd.DataFrame(rows)
    df.to_pickle("../results/sweeps/multi_trend.pkl")
    print(f"{len(df)} configs in {time.time()-t:.0f}s")
