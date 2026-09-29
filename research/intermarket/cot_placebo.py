"""Placebo test for the contrarian managed-money COT filter on the gold breakout: drop the same share of
signal weeks at random (200 draws) and compare with the real filter (full engine, 0.6 % risk)."""
import sys, time; sys.path.insert(0, ".")
import numpy as np, pandas as pd
import book as B, engine as E, gold, positioning as P, strategies as S
b = gold.m5(B.GOLD_START)
ERAS = {"07-11": ("2007", "2011"), "12-15": ("2012", "2015"), "16-19": ("2016", "2019"), "20-23": ("2020", "2023"),
        "24-26": ("2024", "2026"), "ALL": ("2007", "2026")}


def stats(rc, risk=0.006):
    x = rc.resample("1D").last().dropna(); eq = (1 + risk * x.diff().fillna(0)).cumprod(); out = {}
    for e, (a, z) in ERAS.items():
        q = eq.loc[a:z]; yrs = (q.index[-1] - q.index[0]).days / 365.25
        cg = (q.iloc[-1] / q.iloc[0]) ** (1 / yrs) - 1; dd = (1 - q / q.cummax()).max()
        out[e + "_cagr"], out[e + "_dd"], out[e + "_mar"] = cg, dd, cg / dd
    return out


base = S.trend_bo(b, tf="H4", n_entry=80, filt="sma200", sl_atr=1.0, atr_n=20, params=E.StratParams(risk=0.01, trail_r=3.0), name="g")
d0 = base.direction.copy()


def run_mask(keep):
    s = E.Signals("g", np.where(keep, d0, 0), base.sl, base.tp, None, E.StratParams(risk=0.01, trail_r=3.0))
    t, rc, rl = B.gold_r([s], bars=b)
    return len(t), stats(rc)


c = P.cot_disagg()
mmn = (c.m_money_positions_long_all - c.m_money_positions_short_all) / c.open_interest_all
week = (b.index - pd.to_timedelta(b.index.dayofweek, unit="D")).normalize()
wk_codes, wk_idx = np.unique(week.values, return_inverse=True)
rng = np.random.default_rng(7)
rows = []
for wk, th in [(2, 0.04), (4, 0.02)]:
    ch = mmn - mmn.shift(wk); ch.index = ch.index + pd.Timedelta(days=6)
    ch = ch[~ch.index.duplicated(keep="last")].sort_index()
    v = ch.reindex(b.index, method="ffill").values
    keep = np.nan_to_num(v * d0, nan=-1.0) < th
    sigbars = d0 != 0
    frac = keep[sigbars].mean()
    n_real, real = run_mask(keep)
    t0 = time.time(); plc = []
    for i in range(200):
        kw = rng.random(len(wk_codes)) < frac
        n_p, st = run_mask(kw[wk_idx])
        plc.append(st)
    plc = pd.DataFrame(plc)
    row = {"rule": f"mm chg {wk}w < {th}", "keep_frac": round(frac, 3), "trades": n_real}
    for e in ERAS:
        for m in ("cagr", "dd", "mar"):
            k = f"{e}_{m}"
            pct = (plc[k] < real[k]).mean() if m != "dd" else (plc[k] > real[k]).mean()
            row[k] = round(real[k], 4)
            row[k + "_pctile"] = round(pct, 3)       # share of placebos the real rule beats
    rows.append(row)
    print(f"{row['rule']}: keep {frac:.2f}, {time.time()-t0:.0f}s", flush=True)
    for e in ERAS:
        print(f"  {e}: CAGR {real[e+'_cagr']*100:5.1f}% (beats {row[e+'_cagr_pctile']*100:3.0f}% of placebos)  "
              f"DD {real[e+'_dd']*100:5.1f}% (beats {row[e+'_dd_pctile']*100:3.0f}%)  MAR beats {row[e+'_mar_pctile']*100:3.0f}%", flush=True)
pd.DataFrame(rows).to_csv("../results/cot_mm_contrarian_placebo.csv", index=False)
