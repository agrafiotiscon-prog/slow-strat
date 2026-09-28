import sys, time
import pandas as pd
import strategies as S, sweep as W, engine as E

which = sys.argv[1]
if which == "donch":
    grid = dict(tf=["H1", "H4", "D1"], n_entry=[10, 20, 40, 55], sl_atr=[1.5, 2.5, 4.0],
                p_trail_r=[1.0, 2.0, 3.0], p_trail_start=[0.0, 1.0], sides=["long", "both"])
    def build(b, params, **kw):
        return S.donchian_bo(b, params=params, **kw)
elif which == "asia":
    grid = dict(rng_end=[5, 6, 7], trade_end=[10, 12, 15], sl_mode=["range", "atr"], sl_k=[0.5, 1.0],
                tp_k=[0.5, 1.0, 2.0], trend_filter=[0, 20, 50], flat_h=[None, 20])
    def build(b, params, **kw):
        return S.asian_breakout(b, params=params, **kw)
elif which == "trendpb":
    grid = dict(tf=["H1", "H4"], fast=[10, 20], slow=[50, 100], htf=["H4", "D1"], sl_atr=[1.0, 2.0, 3.0],
                tp_r=[1.0, 2.0, 3.0], touch_atr=[0.0, 0.5])
    def build(b, params, **kw):
        return S.trend_pullback(b, params=params, **kw)
elif which == "sweepr":
    grid = dict(tf=["M15", "H1"], sl_buf_atr=[0.2, 0.5, 1.0], tp_r=[0.7, 1.0, 1.5, 2.5], sess=[(7, 17), (0, 24), (12, 20)],
                min_sweep_atr=[0.05, 0.3], max_sweep_atr=[1.0, 2.0])
    def build(b, params, **kw):
        return S.pdhl_sweep(b, params=params, **kw)
elif which == "bbfade":
    grid = dict(tf=["H1", "H4"], n=[20, 50], k=[2.0, 2.5, 3.0], adx_max=[20, 25, 100], sl_atr=[1.5, 3.0], max_hold=[12, 48])
    def build(b, params, **kw):
        return S.bb_fade(b, params=params, **kw)
t = time.time()
df = W.sweep(build, grid)
df.to_csv(f"../results/sweeps/{which}.csv", index=False)
print(f"{which}: {len(df)} runs in {time.time()-t:.0f}s")
keys = list(grid)
cols = keys + ["dev_trades_per_year","dev_winrate","dev_pf","dev_avg_r","dev_sharpe","dev_maxdd","r_12-15","r_16-19","r_20-23","hold_trades_per_year","hold_winrate","hold_pf","hold_avg_r","hold_sharpe"]
cols = [c for c in cols if c in df.columns]
df["robust"] = df[["r_12-15","r_16-19","r_20-23"]].min(axis=1)
print("--- top by dev sharpe"); print(W.show(df, "dev_sharpe", 15)[cols].to_string())
print("--- top by worst-era avgR (dev only)"); print(W.show(df, "robust", 15)[cols + ["robust"]].to_string())
