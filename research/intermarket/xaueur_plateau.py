import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np, pandas as pd, book as B, gold, strategies as S, engine as E
b=gold.m5(B.GOLD_START)
rows=[]
for lab,filt,n,ch,sl,tr in [('base','sma200',200,80,1.0,3.0),('xaueur200','sma200_xaueur',200,80,1.0,3.0),('xaueur150','sma200_xaueur',150,80,1.0,3.0),
                     ('xaueur100','sma200_xaueur',100,80,1.0,3.0),('xaueur250','sma200_xaueur',250,80,1.0,3.0),
                     ('base ch60','sma200',200,60,1.0,3.0),('xaueur200 ch60','sma200_xaueur',200,60,1.0,3.0),
                     ('base sl1.25','sma200',200,80,1.25,3.0),('xaueur200 sl1.25','sma200_xaueur',200,80,1.25,3.0)]:
    S.XAUEUR_N=n
    sig=S.trend_bo(b,tf='H4',n_entry=ch,filt=filt,sl_atr=sl,atr_n=20,params=E.StratParams(risk=0.01,trail_r=tr),name='g')
    t,rc,rl=B.gold_r([sig],bars=b)
    x=rc.resample('1D').last().dropna(); eq=(1+0.006*x.diff().fillna(0)).cumprod()
    r={'cfg':lab,'trades':len(t)}
    for e,(a,z) in {'07-11':('2007','2011'),'12-15':('2012','2015'),'16-19':('2016','2019'),'20-23':('2020','2023'),'24-26':('2024','2026'),'ALL':('2007','2026')}.items():
        q=eq.loc[a:z]; yrs=(q.index[-1]-q.index[0]).days/365.25; cg=(q.iloc[-1]/q.iloc[0])**(1/yrs)-1; dd=(1-q/q.cummax()).max()
        r[e]=f"{cg*100:.1f}/{dd*100:.1f}"
    rows.append(r)
pd.set_option('display.width',250); print(pd.DataFrame(rows).to_string(index=False))
