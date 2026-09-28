"""Compare EA-simulator trades with the Python research trades (module by module)."""
import pickle, sys
import numpy as np, pandas as pd
sys.path.insert(0, "../../research")
import strategies as S

ea = pd.read_csv(sys.argv[1] + "/trades.csv")
def srv_to_utc(ts):
    t = pd.to_datetime(ts, unit="s")
    ny = t - pd.Timedelta(hours=7)
    return ny.dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="shift_forward").dt.tz_convert("UTC").dt.tz_localize(None)
ea["entry_utc"] = srv_to_utc(ea.t_open); ea["exit_utc"] = srv_to_utc(ea.t_close)
ea["mod"] = ea.magic - 7102600
ea["r"] = ea.pnl / (ea.sl_dist * ea.volume * np.where(ea.symbol == "XAUUSD", 100, 1))
cur, trades = pickle.load(open("/tmp/final_curves.pkl", "rb"))
start = pd.Timestamp("2007-06-01")
pairs = [("GOLD_BO", 1, "XAUUSD"), ("GOLD_ASIA", 2, "XAUUSD"), ("IDX_US500", 3, "US500"), ("IDX_NAS100", 3, "NAS100"), ("IDX_US30", 3, "US30")]
rows = []
for name, mod, sym in pairs:
    rt = trades[name]; rt = rt[rt.entry_time >= start + pd.Timedelta(days=3)].copy()
    et = ea[(ea["mod"] == mod) & (ea.symbol == sym) & (ea.entry_utc >= start + pd.Timedelta(days=3))].copy()
    tol = pd.Timedelta("65min") if mod == 3 else pd.Timedelta("6min")
    rt = rt.sort_values("entry_time"); et = et.sort_values("entry_utc")
    m = pd.merge_asof(rt, et[["entry_utc", "exit_utc", "dir", "r", "reason"]].rename(columns={"dir": "ea_dir", "r": "ea_r", "reason": "ea_reason"}),
                      left_on="entry_time", right_on="entry_utc", direction="nearest", tolerance=tol)
    matched = m.dropna(subset=["entry_utc"])
    same_dir = (matched.dir == matched.ea_dir).mean() if len(matched) else np.nan
    exit_close = (abs(matched.exit_utc - matched.exit_time) <= pd.Timedelta("65min")).mean() if len(matched) else np.nan
    rows.append(dict(module=name, research_trades=len(rt), ea_trades=len(et), matched=len(matched),
                     match_pct=len(matched) / max(1, len(rt)), same_dir=same_dir, same_exit_time=exit_close,
                     research_avgR=rt.r.mean(), ea_avgR=et.r.mean(), research_win=(rt.r > 0).mean(), ea_win=(et.r > 0).mean(),
                     r_corr=np.corrcoef(matched.r, matched.ea_r)[0, 1] if len(matched) > 2 else np.nan))
    unmatched = m[m.entry_utc.isna()]
    if len(unmatched):
        print(f"{name}: {len(unmatched)} research trades without EA match, e.g.", unmatched.entry_time.head(5).tolist())
    extra = et[~et.entry_utc.isin(matched.entry_utc)]
    if len(extra):
        print(f"{name}: {len(extra)} EA trades without research match, e.g.", extra.entry_utc.head(5).tolist())
pd.set_option("display.width", 250)
print(pd.DataFrame(rows).round(3).to_string())
