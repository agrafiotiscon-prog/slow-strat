import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import pickle, numpy as np, pandas as pd, book as B, gold, strategies as S, engine as E, final_portfolio as F, stress as ST
cur, trades = pickle.load(open('/tmp/final_curves_v2.pkl','rb'))
b = gold.m5(B.GOLD_START)
sig = S.trend_bo(b, tf='H4', n_entry=80, filt='sma200_xaueur', sl_atr=1.0, atr_n=20, params=E.StratParams(risk=0.01, trail_r=3.0), name='GOLD_BO2')
t, rc, rl = B.gold_r([sig], bars=b)
cur['GOLD_BO2'] = (rc, rl); trades['GOLD_BO2'] = t
t['era']=pd.cut(t.entry_time.dt.year,[2006,2011,2015,2019,2023,2026],labels=['07-11','12-15','16-19','20-23','24-26'])
print('GOLD_BO2 trades', len(t), 'win', round((t.r>0).mean(),3), 'avgR', round(t.r.mean(),3)); print(t.groupby('era',observed=True).r.agg(['count','mean','sum']).round(3).T)
pickle.dump((cur,trades), open('/tmp/final_curves_v2.pkl','wb'))
idx, C, L = F.hourly(cur)
rows=[]
cfgs = {
 'v1 Balanced': {'GOLD_BO':0.6,'GOLD_ASIA':0.5,'IDX_US500':1.0,'IDX_NAS100':1.0,'IDX_US30':1.0},
 'v2: XAUEUR gold + DXY idx 1.5': {'GOLD_BO2':0.6,'GOLD_ASIA':0.5,'IDXF_US500':1.5,'IDXF_NAS100':1.5,'IDXF_US30':1.5},
 'v2 gold 0.75, idx 1.5': {'GOLD_BO2':0.75,'GOLD_ASIA':0.5,'IDXF_US500':1.5,'IDXF_NAS100':1.5,'IDXF_US30':1.5},
 'v2 gold 0.75, idx 2.0': {'GOLD_BO2':0.75,'GOLD_ASIA':0.5,'IDXF_US500':2.0,'IDXF_NAS100':2.0,'IDXF_US30':2.0},
 'v2 gold 0.6, asia 0.4, idx 2.0': {'GOLD_BO2':0.6,'GOLD_ASIA':0.4,'IDXF_US500':2.0,'IDXF_NAS100':2.0,'IDXF_US30':2.0},
}
for lab, W in cfgs.items():
    r={'config':lab}
    for p in ['FULL 2007-2026','2007-2011','2012-2015','2016-2019','2020-2023','2024-2026 (holdout)']:
        c,d = ST.brake_sim(idx,C,L,W,*F.PER[p],0.03,0.08,0.5); r[p[:9]]=f"{c*100:.1f}/{d*100:.1f}"
    rows.append(r)
pd.set_option('display.width',250); print(pd.DataFrame(rows).to_string(index=False))
