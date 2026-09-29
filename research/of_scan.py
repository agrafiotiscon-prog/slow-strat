"""Order-flow proxies vs outcome of the existing gold trades (entry-time features), by era."""
import pickle, time
import numpy as np, pandas as pd
import gold, orderflow as OF, strategies as S

pd.set_option("display.width", 250)
t0 = time.time()
b = gold.m5("2006-06-01")
prof = OF.daily_profile(b); print("profile", len(prof), f"{time.time()-t0:.0f}s")
h4f = OF.h4_flow(b); print("h4 flow", len(h4f), f"{time.time()-t0:.0f}s")
m5f = OF.m5_flow(b)[["cvd_day", "vol_day", "vwap_day", "vwap_week", "rvol", "close"]]
prof.to_parquet("/tmp/of_profile.parquet"); h4f.to_parquet("/tmp/of_h4.parquet")
cur, trades = pickle.load(open("/tmp/final_curves_v2.pkl", "rb"))
a_d = S.bars_tf(b, "D1")
import indicators as I
atr_d = I.atr(a_d, 14); atr_d.index = atr_d.index + pd.Timedelta("1D")
for mod in ["GOLD_BO", "GOLD_ASIA"]:
    t = trades[mod].sort_values("entry_time").reset_index(drop=True)
    t = pd.merge_asof(t, h4f.sort_index(), left_on="entry_time", right_index=True, direction="backward")
    # latest completed M5 bar before entry
    m = m5f.copy(); m.index = m.index + pd.Timedelta("5min")
    t = pd.merge_asof(t, m.sort_index(), left_on="entry_time", right_index=True, direction="backward")
    ps = prof.copy(); ps.index = S.server_time(ps.index) if False else ps.index
    # profile index is server-day date; entry server day:
    t["sday"] = S.server_time(pd.DatetimeIndex(t.entry_time)).normalize()
    t = t.merge(prof, left_on="sday", right_index=True, how="left")
    t = pd.merge_asof(t.sort_values("entry_time"), atr_d.rename("atrD").sort_index(), left_on="entry_time", right_index=True, direction="backward")
    d = t["dir"]
    t["of_h4_delta_dir"] = t.h4_delta_ratio * d
    t["of_cvd_div"] = np.sign(t.h4_px20) * d - np.sign(t.h4_cvd20) * d        # >0: price moved our way but CVD didn't
    t["of_cvd20_dir"] = t.h4_cvd20 * d
    t["of_day_cvd_dir"] = (t.cvd_day / t.vol_day) * d
    t["of_vs_vwap_day"] = (t.close - t.vwap_day) / t.atrD * d
    t["of_vs_vwap_week"] = (t.close - t.vwap_week) / t.atrD * d
    t["of_vs_poc"] = (t.close - t.poc) / t.atrD * d
    t["of_outside_va"] = np.where(d > 0, t.close > t.vah, t.close < t.val).astype(float)
    t["of_prev_day_delta_dir"] = t.day_delta_ratio * d
    t["of_prev_close_vs_vwap"] = (t.day_close - t.day_vwap) / t.atrD * d
    t["of_rvol_m5"] = t.rvol
    t["of_h4_rvol"] = t.h4_rvol
    t["of_h4_vol_ratio"] = t.h4_vol_ratio
    t["of_h4_climax"] = t.h4_climax
    t["of_day_vol_ratio"] = t.day_vol_ratio
    t["era"] = pd.cut(t.entry_time.dt.year, [2006, 2011, 2015, 2019, 2023, 2027], labels=["07-11", "12-15", "16-19", "20-23", "24-26"])
    t.to_parquet(f"/tmp/of_trades_{mod}.parquet")
    rows = []
    for c in [c for c in t.columns if c.startswith("of_")]:
        x = t.dropna(subset=[c]).reset_index(drop=True)
        dev = x[x.era.isin(["12-15", "16-19", "20-23"])]
        if x[c].nunique() < 2 or len(dev) < 50:
            continue
        med = dev[c].median() if x[c].nunique() > 2 else 0.5
        hi = (x[c] > med).values
        row = {"feature": c, "split": med}
        signs = []
        for e in ["07-11", "12-15", "16-19", "20-23", "24-26"]:
            me = (x.era == e).values
            dd = x.r[me & hi].mean() - x.r[me & ~hi].mean()
            row[e] = dd
            if e in ("12-15", "16-19", "20-23"):
                signs.append(np.sign(dd))
        row["consistent_dev"] = abs(sum(signs)) == 3
        row["holdout_same_sign"] = np.sign(row["24-26"]) == signs[0] if row["consistent_dev"] else False
        rows.append(row)
    df = pd.DataFrame(rows)
    print(f"\n===== {mod}: R(high half) - R(low half) by era")
    print(df.round(3).to_string(index=False))
    df.to_csv(f"../results/orderflow_filters_{mod}.csv", index=False)
