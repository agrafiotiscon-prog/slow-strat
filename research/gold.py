"""Combined gold M5 history: OctaFX feed until 2020-01-08, Dukascopy from 2020-01-09 (both UTC, bid)."""
import numpy as np
import pandas as pd

import data as D
import strategies as S

_cache = {}


def m5(start="2004-06-01", end=None) -> pd.DataFrame:
    if "full" not in _cache:
        g = D.gold_m5_duka()
        o = D.gold_m5_octa_raw()
        o = o.loc[:g.index[0] - pd.Timedelta(minutes=5)]   # OctaFX until Dukascopy starts (2020-01-09)
        _cache["full"] = pd.concat([o, g])
    return _cache["full"].loc[start:end]


def spread(bars: pd.DataFrame) -> np.ndarray:
    return S.spread_model(bars)
