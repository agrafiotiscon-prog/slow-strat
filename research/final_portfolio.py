"""Final portfolio evaluation (compounded, shared equity) for the EA presets."""
import itertools, pickle, sys
import numpy as np, pandas as pd
import assets as A, book as B, engine as E, gold, idx_server, multi as M, strategies as S

OUT = "../results"
PER = {"2007-2011": ("2007-01-01", "2012-01-01"), "2012-2015": ("2012-01-01", "2016-01-01"),
       "2016-2019": ("2016-01-01", "2020-01-01"), "2020-2023": ("2020-01-01", "2024-01-01"),
       "2024-2026 (holdout)": ("2024-01-01", "2026-09-30"), "2025": ("2025-01-01", "2026-01-01"),
       "2026 YTD": ("2026-01-01", "2026-09-30"), "FULL 2007-2026": ("2007-01-01", "2026-09-30")}

GOLD_BO = dict(tf="H4", n_entry=80, filt="sma200", sl_atr=1.0, atr_n=20, trail_r=3.0)
IDX_DIP = dict(rule="rsi2ibs", lo=10, ibs_lo=0.25, trend_n=200, exit_ma=5, sl_atr=2.0, atr_n=10, max_hold_d=10)
ASIA = dict(rng_end=7, trade_end=12, sl_mode="atr", sl_k=1.0, tp_k=1.0, trend_filter=50)


def build_curves(spread_mult=1.0, slip_mult=1.0):
    b = gold.m5(B.GOLD_START)
    cur, trades = {}, {}
    g = dict(GOLD_BO)
    tr_r = g.pop("trail_r")
    sig = S.trend_bo(b, params=E.StratParams(risk=0.01, trail_r=tr_r), name="GOLD_BO", **g)
    t, rc, rl = B.gold_r([sig], bars=b, spread_mult=spread_mult, slip=0.08 * slip_mult)
    cur["GOLD_BO"], trades["GOLD_BO"] = (rc, rl), t
    sig = S.asian_breakout(b, params=E.StratParams(risk=0.01), name="GOLD_ASIA", **ASIA)
    t, rc, rl = B.gold_r([sig], bars=b, spread_mult=spread_mult, slip=0.08 * slip_mult)
    cur["GOLD_ASIA"], trades["GOLD_ASIA"] = (rc, rl), t
    for s in ["US500", "NAS100", "US30"]:
        old = dict(M.SPREAD_BP)
        M.SPREAD_BP[s] = old[s] * spread_mult
        t, rc, rl = M.r_curve(s, idx_server.dip, bars=A.exec_bars(s), **IDX_DIP)
        M.SPREAD_BP.update(old)
        cur["IDX_" + s], trades["IDX_" + s] = (rc, rl), t
    return cur, trades


def hourly(cur):
    idx = pd.date_range("2007-01-01", "2026-09-30", freq="1h")
    C, L = {}, {}
    for k, (rc, rl) in cur.items():
        c = rc.resample("1h").last()
        l = rl.resample("1h").min()
        C[k] = c.reindex(idx).ffill().fillna(0).values
        L[k] = l.reindex(idx).fillna(pd.Series(C[k], idx)).values
    return idx, C, L


def simulate(idx, C, L, W, a, z):
    """Compounded equity: each module's R increments scaled by risk% * current equity."""
    m = (idx >= a) & (idx < z)
    keys = [k for k in W if W[k] > 0]
    inc = sum(W[k] * np.diff(C[k][m], prepend=C[k][m][0]) for k in keys) / 100.0
    exc = sum(W[k] * (L[k][m] - C[k][m]) for k in keys) / 100.0
    eq = np.cumprod(1 + inc)                     # multiplicative per-hour growth
    lo = eq * (1 + exc)
    t = idx[m]
    yrs = (t[-1] - t[0]).days / 365.25
    cagr = eq[-1] ** (1 / yrs) - 1
    pk = np.maximum.accumulate(eq)
    dd = ((pk - lo) / pk).max()
    d = pd.Series(eq, t).resample("1D").last().dropna()
    r = d.pct_change().dropna()
    sh = r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else np.nan
    mo = pd.Series(eq, t).resample("ME").last().pct_change().dropna()
    return dict(cagr=cagr, maxdd=dd, mar=cagr / dd if dd > 0 else np.nan, sharpe=sh,
                pos_months=(mo > 0).mean(), worst_month=mo.min()), pd.Series(eq, t)


PRESETS = {  # identical to the EA's presets (risk % per trade)
    "Conservative": {"GOLD_BO": 0.30, "GOLD_ASIA": 0.25, "IDX_US500": 0.50, "IDX_NAS100": 0.50, "IDX_US30": 0.50},
    "Balanced": {"GOLD_BO": 0.60, "GOLD_ASIA": 0.50, "IDX_US500": 1.00, "IDX_NAS100": 1.00, "IDX_US30": 1.00},
    "Aggressive": {"GOLD_BO": 0.90, "GOLD_ASIA": 0.75, "IDX_US500": 1.50, "IDX_NAS100": 1.50, "IDX_US30": 1.50},
}

if __name__ == "__main__":
    cur, trades = build_curves()
    pickle.dump((cur, trades), open("/tmp/final_curves.pkl", "wb"))
    idx, C, L = hourly(cur)
    rows = []
    for name, W in PRESETS.items():
        for p, (a, z) in PER.items():
            st, _ = simulate(idx, C, L, W, a, z)
            rows.append({"preset": name, "period": p, **st})
    df = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    print(df.round(3).to_string())
    # per-module trade stats
    for k, t in trades.items():
        tt = t[t.entry_time >= "2007-01-01"]
        h = tt[tt.entry_time >= "2024-01-01"]
        print(f"{k:12s} trades {len(tt):5d} ({len(tt)/19.7:5.1f}/yr) win {100*(tt.r>0).mean():5.1f}% avgR {tt.r.mean():.3f} | 2024+: {len(h)} trades, win {100*(h.r>0).mean():5.1f}% avgR {h.r.mean():.3f}")
