import numpy as np, pandas as pd
pd.set_option("display.width", 250)
ERAS = ["12-15", "16-19", "20-23", "24-26"]
def show(t, mask, label):
    row = {"filter": label, "kept%": 100 * mask.mean()}
    for e in ERAS:
        me = (t.era == e).values
        base = t.r[me].sum(); kept = t.r[me & mask].sum()
        row[f"{e} R/yr kept"] = kept / {"12-15": 4, "16-19": 4, "20-23": 4, "24-26": 2.73}[e]
        row[f"{e} avgR"] = t.r[me & mask].mean()
    return row
for mod, rules in {
    "GOLD_BO": [("base", lambda t: np.ones(len(t), bool)),
                ("d1 vol ratio <= 1.3", lambda t: (t.d1_vol_ratio_bar.fillna(1) <= 1.3).values),
                ("d1 vol ratio <= 1.6", lambda t: (t.d1_vol_ratio_bar.fillna(1) <= 1.6).values),
                ("d1 keltner stretch <= 1.0", lambda t: (t.d1_keltner_pos_dir.fillna(0) <= 1.0).values),
                ("d1 keltner stretch <= 1.5", lambda t: (t.d1_keltner_pos_dir.fillna(0) <= 1.5).values),
                ("d1 BB width rank <= 0.8", lambda t: (t.d1_bb_width_rank.fillna(0.5) <= 0.8).values),
                ("USD 5d against gold dir", lambda t: (t.dxy_ret5_dir.fillna(0) <= 0).values),
                ("USD 5d not strongly with", lambda t: (t.dxy_ret5_dir.fillna(0) <= 0.005).values),
                ("vol<=1.6 & keltner<=1.5", lambda t: ((t.d1_vol_ratio_bar.fillna(1) <= 1.6) & (t.d1_keltner_pos_dir.fillna(0) <= 1.5)).values),
                ],
    "IDX_DIP": [("base", lambda t: np.ones(len(t), bool)),
                ("DXY below SMA200", lambda t: (t.dxy_vs_sma200.fillna(0) <= 0).values),
                ("DXY <= SMA200 +1%", lambda t: (t.dxy_vs_sma200.fillna(0) <= 0.01).values),
                ("DXY <= SMA200 +2%", lambda t: (t.dxy_vs_sma200.fillna(0) <= 0.02).values),
                ("VIX 5d rise <= 25%", lambda t: (t.vix_ret5.fillna(0) <= 0.25).values),
                ("VIX >= 15", lambda t: (t.vix.fillna(20) >= 15).values),
                ],
    "GOLD_ASIA": [("base", lambda t: np.ones(len(t), bool)),
                  ("DXY 5d >= 0 (odd)", lambda t: (t.dxy_ret5.fillna(0) >= 0).values),
                  ("d1 BB width rank <= 0.8", lambda t: (t.d1_bb_width_rank.fillna(0.5) <= 0.8).values),
                  ("h4 bbwidth <= 0.8", lambda t: (t.h4_bb_width_rank.fillna(0.5) <= 0.8).values),
                  ]}.items():
    t = pd.read_parquet(f"/tmp/feat_{mod}.parquet")
    t = t[t.entry_time >= "2012-01-01"].reset_index(drop=True)
    print(f"\n==== {mod}  (R per year from kept trades; base = no filter)")
    print(pd.DataFrame([show(t, f(t), l) for l, f in rules]).round(3).to_string(index=False))
