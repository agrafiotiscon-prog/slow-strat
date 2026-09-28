import time, pandas as pd
import strategies as S, sweep as W
grid = dict(tf=["H1", "H4", "D1"], n_entry=[20, 40, 55, 80], filt=["none", "sma200", "sma50", "mom60"], sl_atr=[1.0, 1.5, 2.5],
            p_trail_r=[1.0, 2.0, 3.0], p_trail_start=[0.0, 1.0])
def build(b, params, **kw):
    return S.trend_bo(b, params=params, **kw)
t = time.time()
df = W.sweep(build, grid)
df.to_csv("../results/sweeps/gold_trend.csv", index=False)
print(f"{len(df)} runs in {time.time()-t:.0f}s")
