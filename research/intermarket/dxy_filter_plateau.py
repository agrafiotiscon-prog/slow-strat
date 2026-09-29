import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np, pandas as pd, multi as M, assets as A, idx_server, final_portfolio as F
kw=dict(F.IDX_DIP); rows=[]
for n in [100,150,200,250]:
    for thr in [None,0.0,0.01,0.02,0.03]:
        if thr is None and n!=200: continue
        allt=[]
        for s in ["US500","NAS100","US30"]:
            tr,rc,rl=M.r_curve(s,idx_server.dip,bars=A.exec_bars(s),dxy_max=thr,dxy_n=n,**kw); allt.append(tr)
        t=pd.concat(allt); r={'sma':n,'thr':thr,'n':len(t),'win':(t.r>0).mean(),'avgR':t.r.mean()}
        for e,(a,z) in {'13-15':('2013','2016'),'16-19':('2016','2020'),'20-23':('2020','2024'),'24-26':('2024','2027')}.items():
            x=t[(t.entry_time>=a)&(t.entry_time<z)]; r[e]=x.r.mean(); r[e+' sumR']=x.r.sum()
        rows.append(r)
pd.set_option('display.width',250); print(pd.DataFrame(rows).round(3).to_string(index=False))
