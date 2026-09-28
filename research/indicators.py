"""Indicators implemented to match MetaTrader 5 built-ins.

  sma   == iMA(MODE_SMA)
  ema   == iMA(MODE_EMA)       (alpha = 2/(n+1), seeded with first value)
  rsi   == iRSI                (Wilder / SMMA smoothing, seeded with SMA)
  atr   == iATR                (MT5 iATR is a SIMPLE average of true range)
  bands == iBands              (SMA +/- k * population stdev)
"""
from __future__ import annotations

import numba as nb
import numpy as np
import pandas as pd


def sma(x: pd.Series, n: int) -> pd.Series:
    return x.rolling(n, min_periods=n).mean()


@nb.njit(cache=True)
def _ema(x, n):
    out = np.empty_like(x)
    a = 2.0 / (n + 1.0)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def ema(x: pd.Series, n: int) -> pd.Series:
    return pd.Series(_ema(x.values.astype(np.float64), n), x.index)


@nb.njit(cache=True)
def _rsi(c, n):
    m = len(c)
    out = np.full(m, np.nan)
    if m <= n:
        return out
    up = 0.0
    dn = 0.0
    for i in range(1, n + 1):
        d = c[i] - c[i - 1]
        if d > 0:
            up += d
        else:
            dn -= d
    up /= n
    dn /= n
    out[n] = 100.0 if dn == 0 else 100.0 - 100.0 / (1.0 + up / dn)
    for i in range(n + 1, m):
        d = c[i] - c[i - 1]
        u = d if d > 0 else 0.0
        w = -d if d < 0 else 0.0
        up = (up * (n - 1) + u) / n
        dn = (dn * (n - 1) + w) / n
        out[i] = 100.0 if dn == 0 else 100.0 - 100.0 / (1.0 + up / dn)
    return out


def rsi(c: pd.Series, n: int) -> pd.Series:
    return pd.Series(_rsi(c.values.astype(np.float64), n), c.index)


def true_range(df: pd.DataFrame) -> pd.Series:
    pc = df.close.shift(1)
    tr = pd.concat([df.high - df.low, (df.high - pc).abs(), (df.low - pc).abs()], axis=1).max(axis=1)
    tr.iloc[0] = df.high.iloc[0] - df.low.iloc[0]
    return tr


def atr(df: pd.DataFrame, n: int) -> pd.Series:
    return true_range(df).rolling(n, min_periods=n).mean()


def bands(c: pd.Series, n: int, k: float):
    m = c.rolling(n, min_periods=n).mean()
    s = c.rolling(n, min_periods=n).std(ddof=0)
    return m - k * s, m, m + k * s


def donchian(df: pd.DataFrame, n: int):
    return df.high.rolling(n, min_periods=n).max(), df.low.rolling(n, min_periods=n).min()


def adx(df: pd.DataFrame, n: int) -> pd.Series:
    """Wilder ADX (as in iADXWilder)."""
    up = df.high.diff()
    dn = -df.low.diff()
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = true_range(df)
    a = 1.0 / n
    atr_w = tr.ewm(alpha=a, adjust=False).mean()
    pdi = 100 * pd.Series(pdm, df.index).ewm(alpha=a, adjust=False).mean() / atr_w
    ndi = 100 * pd.Series(ndm, df.index).ewm(alpha=a, adjust=False).mean() / atr_w
    dx = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)
    return dx.ewm(alpha=a, adjust=False).mean()
