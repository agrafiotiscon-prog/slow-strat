import sys, time
import pandas as pd
import strategies as S, sweep as W
grid = dict(tf=["H1", "H4", "D1"], rsi_n=[2, 3], lo=[5.0, 10.0, 20.0], trend_n=[50, 100, 200],
            exit_ma=[5, 10], sl_atr=[2.0, 3.0, 5.0], sides=["long", "both"])
def build(b, params, lo, **kw):
    return S.rsi_pullback(b, hi=100 - lo, lo=lo, params=params, **kw)
t = time.time()
df = W.sweep(build, grid)
df.to_csv("../results/sweeps/rsi_pullback.csv", index=False)
print(f"{len(df)} runs in {time.time()-t:.0f}s")
cols = ["tf","rsi_n","lo","trend_n","exit_ma","sl_atr","sides","dev_trades_per_year","dev_winrate","dev_pf","dev_avg_r","dev_sharpe","dev_maxdd","r_12-15","r_16-19","r_20-23","hold_trades_per_year","hold_winrate","hold_pf","hold_avg_r","hold_sharpe"]
print(W.show(df, "dev_sharpe", 30)[cols].to_string())
