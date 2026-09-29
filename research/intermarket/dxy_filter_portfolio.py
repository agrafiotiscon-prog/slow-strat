import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import pickle, numpy as np, pandas as pd, multi as M, assets as A, idx_server, final_portfolio as F, stress as ST
cur, trades = pickle.load(open('/tmp/final_curves.pkl','rb'))
kw = dict(F.IDX_DIP)
for s in ["US500","NAS100","US30"]:
    tr, rc, rl = M.r_curve(s, idx_server.dip, bars=A.exec_bars(s), dxy_max=0.01, **kw)
    cur['IDXF_'+s] = (rc, rl); trades['IDXF_'+s] = tr
    print(s, 'filtered trades', len(tr), 'win', round((tr.r>0).mean(),3), 'avgR', round(tr.r.mean(),3))
pickle.dump((cur,trades), open('/tmp/final_curves_v2.pkl','wb'))
idx, C, L = F.hourly(cur)
rows=[]
for lab, W in {
  'v1 Balanced (idx 1.0 unfiltered)': {'GOLD_BO':0.6,'GOLD_ASIA':0.5,'IDX_US500':1.0,'IDX_NAS100':1.0,'IDX_US30':1.0},
  'DXY-filtered idx 1.0': {'GOLD_BO':0.6,'GOLD_ASIA':0.5,'IDXF_US500':1.0,'IDXF_NAS100':1.0,'IDXF_US30':1.0},
  'DXY-filtered idx 1.5': {'GOLD_BO':0.6,'GOLD_ASIA':0.5,'IDXF_US500':1.5,'IDXF_NAS100':1.5,'IDXF_US30':1.5},
  'DXY-filtered idx 2.0': {'GOLD_BO':0.6,'GOLD_ASIA':0.5,'IDXF_US500':2.0,'IDXF_NAS100':2.0,'IDXF_US30':2.0},
  'unfiltered idx 1.5': {'GOLD_BO':0.6,'GOLD_ASIA':0.5,'IDX_US500':1.5,'IDX_NAS100':1.5,'IDX_US30':1.5},
}.items():
    r={'config':lab}
    for p in ['FULL 2007-2026','2012-2015','2016-2019','2020-2023','2024-2026 (holdout)']:
        c,d = ST.brake_sim(idx,C,L,W,*F.PER[p],0.03,0.08,0.5); r[p[:9]]=f"{c*100:.1f}/{d*100:.1f}"
    rows.append(r)
pd.set_option('display.width',250); print(pd.DataFrame(rows).to_string(index=False))
