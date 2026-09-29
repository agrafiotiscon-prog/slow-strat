"""Bar-level execution simulator that mirrors how the MQL5 EA trades.

Prices are BID OHLC.  Buys fill at ask (= bid + spread), sells at bid.  Long
positions exit on bid, shorts on ask.  Signals must be computed on completed
bars and placed on the bar whose OPEN they execute at (no look-ahead).

Conservative assumptions:
  * If SL and TP are both inside the same bar, SL is assumed to hit first.
  * If the bar opens beyond the SL (gap), the fill is at the open, not the SL.
  * Stops and market orders pay `slip` price units of slippage.
  * Equity drawdown is measured on the worst intrabar mark-to-market.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numba as nb
import numpy as np
import pandas as pd

EXIT_SL, EXIT_TP, EXIT_TIME, EXIT_SIGNAL, EXIT_EOD, EXIT_TRAIL = 0, 1, 2, 3, 4, 5
EXIT_NAMES = {0: "SL", 1: "TP", 2: "TIME", 3: "SIGNAL", 4: "END", 5: "TRAIL"}


@dataclass
class Costs:
    contract: float = 100.0        # units per 1.0 lot (XAUUSD: 100 oz)
    commission: float = 3.5        # $ per lot per side
    slip: float = 0.05             # price units on market orders & stop fills
    lot_step: float = 0.01
    min_lot: float = 0.01
    max_lot: float = 50.0
    swap_long: float = -0.055      # annual rate on notional charged per night
    swap_short: float = -0.01
    triple_dow: int = 2            # Wednesday rollover charges 3 nights


@dataclass
class StratParams:
    risk: float = 0.005            # fraction of equity risked per trade
    max_hold: int = 0              # bars; 0 = unlimited
    be_trigger: float = 0.0        # move SL to breakeven after this many R (0 = off)
    be_offset: float = 0.0         # in R, locked profit when BE triggers
    max_pos: int = 1               # max simultaneous positions for this strategy
    trail_r: float = 0.0           # trail at this many R behind the best price (0 = off)
    trail_start: float = 0.0       # start trailing after this many R of profit
    lim_expiry: int = 0            # bars a pending limit entry stays live (used when Signals.lim > 0)


@nb.njit(cache=True)
def _round_lot(x, step, mn, mx):
    lots = np.floor(x / step + 1e-9) * step
    if lots < mn:
        return 0.0
    if lots > mx:
        return mx
    return lots


@nb.njit(cache=True)
def _simulate(o, h, l, c, spread, roll_mult, sig_dir, sig_sl, sig_tp, sig_exit, sig_lim,
              p_risk, p_hold, p_be, p_beoff, p_maxpos, p_trail, p_trstart, p_lexp,
              contract, commission, slip, lot_step, min_lot, max_lot, swap_l, swap_s,
              equity0, compounding):
    n = o.shape[0]
    K = sig_dir.shape[0]
    MAXP = 64
    # open position book
    pk = np.full(MAXP, -1, np.int64)
    pdir = np.zeros(MAXP, np.int64)
    pentry = np.zeros(MAXP)
    psl = np.zeros(MAXP)
    ptp = np.zeros(MAXP)
    plots = np.zeros(MAXP)
    pbar = np.zeros(MAXP, np.int64)
    prisk = np.zeros(MAXP)    # initial SL distance (price)
    pbest = np.zeros(MAXP)
    pswap = np.zeros(MAXP)
    plim = np.zeros(MAXP, np.bool_)   # opened by a limit fill on bar pbar (no same-bar TP / trail credit)
    pcount = np.zeros(K, np.int64)
    # one pending limit entry per strategy
    q_dir = np.zeros(K, np.int64)
    q_px = np.zeros(K)        # limit price (ask for buys, bid for sells)
    q_sl = np.zeros(K)        # absolute SL price (anchored to the signal-bar market entry)
    q_tp = np.zeros(K)        # TP distance
    q_end = np.zeros(K, np.int64)

    max_tr = n // 2 + 16
    t_k = np.zeros(max_tr, np.int64)
    t_dir = np.zeros(max_tr, np.int64)
    t_ei = np.zeros(max_tr, np.int64)
    t_xi = np.zeros(max_tr, np.int64)
    t_ep = np.zeros(max_tr)
    t_xp = np.zeros(max_tr)
    t_lots = np.zeros(max_tr)
    t_pnl = np.zeros(max_tr)
    t_r = np.zeros(max_tr)
    t_reason = np.zeros(max_tr, np.int64)
    nt = 0

    balance = equity0
    eq_close = np.zeros(n)
    eq_low = np.zeros(n)

    for i in range(n):
        sp = spread[i]
        # ---------- 1. exits at open (signal / time) ----------
        for j in range(MAXP):
            if pk[j] < 0:
                continue
            k = pk[j]
            do_exit = False
            reason = EXIT_SIGNAL
            if sig_exit[k, i] == 2 or sig_exit[k, i] == pdir[j]:
                do_exit = True
            if p_hold[k] > 0 and i - pbar[j] >= p_hold[k]:
                do_exit = True
                reason = EXIT_TIME
            if do_exit:
                if pdir[j] == 1:
                    xp = o[i] - slip
                else:
                    xp = o[i] + sp + slip
                pnl = (xp - pentry[j]) * pdir[j] * plots[j] * contract - 2 * commission * plots[j] + pswap[j]
                balance += pnl
                t_k[nt] = k; t_dir[nt] = pdir[j]; t_ei[nt] = pbar[j]; t_xi[nt] = i
                t_ep[nt] = pentry[j]; t_xp[nt] = xp; t_lots[nt] = plots[j]; t_pnl[nt] = pnl
                t_r[nt] = pnl / (prisk[j] * plots[j] * contract) if prisk[j] > 0 else 0.0
                t_reason[nt] = reason
                nt += 1
                pcount[k] -= 1
                pk[j] = -1

        # ---------- 2. entries at open ----------
        for k in range(K):
            d = sig_dir[k, i]
            if d != 0 and sig_lim[k, i] > 0:
                if pcount[k] >= p_maxpos[k] or not (sig_sl[k, i] > 0):
                    continue
                # new pending limit order (replaces any older one)
                ref = o[i] + sp if d == 1 else o[i]
                q_dir[k] = d
                q_px[k] = ref - d * sig_lim[k, i]
                q_sl[k] = ref + d * slip - d * sig_sl[k, i]   # same SL price a market entry would get
                q_tp[k] = sig_tp[k, i]
                q_end[k] = i + p_lexp[k]
                continue
            if d == 0 or pcount[k] >= p_maxpos[k]:
                continue
            sl_d = sig_sl[k, i]
            if not (sl_d > 0):
                continue
            eq_ref = balance if compounding else equity0
            if d == 1:
                ep = o[i] + sp + slip
            else:
                ep = o[i] - slip
            # money lost at SL per lot: distance + stop slippage + round-trip commission
            per_lot_loss = (sl_d + slip) * contract + 2 * commission
            lots = _round_lot(eq_ref * p_risk[k] / per_lot_loss, lot_step, min_lot, max_lot)
            if lots <= 0:
                continue
            slot = -1
            for j in range(MAXP):
                if pk[j] < 0:
                    slot = j
                    break
            if slot < 0:
                continue
            pk[slot] = k; pdir[slot] = d; pentry[slot] = ep; plots[slot] = lots; pbar[slot] = i
            prisk[slot] = sl_d; pswap[slot] = 0.0; plim[slot] = False
            if d == 1:
                psl[slot] = ep - sl_d
                ptp[slot] = ep + sig_tp[k, i] if sig_tp[k, i] > 0 else 1e18
                pbest[slot] = ep
            else:
                psl[slot] = ep + sl_d
                ptp[slot] = ep - sig_tp[k, i] if sig_tp[k, i] > 0 else -1e18
                pbest[slot] = ep
            pcount[k] += 1

        # ---------- 2b. pending limit fills (anywhere inside the bar) ----------
        for k in range(K):
            if q_dir[k] == 0:
                continue
            if i >= q_end[k]:
                q_dir[k] = 0
                continue
            if pcount[k] >= p_maxpos[k]:
                continue
            d = q_dir[k]
            if d == 1:
                if l[i] + sp > q_px[k]:
                    continue
                ep = min(o[i] + sp, q_px[k])
            else:
                if h[i] < q_px[k]:
                    continue
                ep = max(o[i], q_px[k])
            q_dir[k] = 0
            dist = (q_px[k] - q_sl[k]) * d            # risk distance used for sizing (known at placement)
            rdist = (ep - q_sl[k]) * d                 # actual distance from the fill
            if not (dist > 0) or not (rdist > 0):
                continue
            eq_ref = balance if compounding else equity0
            per_lot_loss = (dist + slip) * contract + 2 * commission
            lots = _round_lot(eq_ref * p_risk[k] / per_lot_loss, lot_step, min_lot, max_lot)
            if lots <= 0:
                continue
            slot = -1
            for j in range(MAXP):
                if pk[j] < 0:
                    slot = j
                    break
            if slot < 0:
                continue
            pk[slot] = k; pdir[slot] = d; pentry[slot] = ep; plots[slot] = lots; pbar[slot] = i
            prisk[slot] = rdist; pswap[slot] = 0.0; plim[slot] = True
            psl[slot] = q_sl[k]
            if d == 1:
                ptp[slot] = ep + q_tp[k] if q_tp[k] > 0 else 1e18
            else:
                ptp[slot] = ep - q_tp[k] if q_tp[k] > 0 else -1e18
            pbest[slot] = ep
            pcount[k] += 1

        # ---------- 3. intrabar SL / TP ----------
        for j in range(MAXP):
            if pk[j] < 0:
                continue
            k = pk[j]
            hit = False
            xp = 0.0
            reason = EXIT_SL
            if pdir[j] == 1:
                sl_hit = l[i] <= psl[j]
                tp_hit = h[i] >= ptp[j] and not (plim[j] and pbar[j] == i)
                if sl_hit:
                    hit = True
                    xp = min(o[i], psl[j]) - slip
                    reason = EXIT_TRAIL if psl[j] > pentry[j] - prisk[j] + 1e-9 else EXIT_SL
                    if tp_hit and o[i] >= ptp[j]:
                        xp = o[i]; reason = EXIT_TP
                elif tp_hit:
                    hit = True
                    xp = max(o[i], ptp[j]); reason = EXIT_TP
            else:
                ah = h[i] + sp
                al = l[i] + sp
                sl_hit = ah >= psl[j]
                tp_hit = al <= ptp[j] and not (plim[j] and pbar[j] == i)
                if sl_hit:
                    hit = True
                    xp = max(o[i] + sp, psl[j]) + slip
                    reason = EXIT_TRAIL if psl[j] < pentry[j] + prisk[j] - 1e-9 else EXIT_SL
                    if tp_hit and o[i] + sp <= ptp[j]:
                        xp = o[i] + sp; reason = EXIT_TP
                elif tp_hit:
                    hit = True
                    xp = min(o[i] + sp, ptp[j]); reason = EXIT_TP
            if hit:
                pnl = (xp - pentry[j]) * pdir[j] * plots[j] * contract - 2 * commission * plots[j] + pswap[j]
                balance += pnl
                t_k[nt] = k; t_dir[nt] = pdir[j]; t_ei[nt] = pbar[j]; t_xi[nt] = i
                t_ep[nt] = pentry[j]; t_xp[nt] = xp; t_lots[nt] = plots[j]
                t_pnl[nt] = pnl
                t_r[nt] = pnl / (prisk[j] * plots[j] * contract) if prisk[j] > 0 else 0.0
                t_reason[nt] = reason
                nt += 1
                pcount[k] -= 1
                pk[j] = -1

        # ---------- 4. trailing / breakeven (effective from next bar) ----------
        for j in range(MAXP):
            if pk[j] < 0:
                continue
            k = pk[j]
            if plim[j] and pbar[j] == i:
                continue
            R = prisk[j]
            if pdir[j] == 1:
                if h[i] > pbest[j]:
                    pbest[j] = h[i]
                gain = pbest[j] - pentry[j]
                if p_be[k] > 0 and gain >= p_be[k] * R:
                    nsl = pentry[j] + p_beoff[k] * R
                    if nsl > psl[j]:
                        psl[j] = nsl
                if p_trail[k] > 0 and gain >= p_trstart[k] * R:
                    nsl = pbest[j] - p_trail[k] * R
                    if nsl > psl[j]:
                        psl[j] = nsl
            else:
                al = l[i] + sp
                if al < pbest[j]:
                    pbest[j] = al
                gain = pentry[j] - pbest[j]
                if p_be[k] > 0 and gain >= p_be[k] * R:
                    nsl = pentry[j] - p_beoff[k] * R
                    if nsl < psl[j]:
                        psl[j] = nsl
                if p_trail[k] > 0 and gain >= p_trstart[k] * R:
                    nsl = pbest[j] + p_trail[k] * R
                    if nsl < psl[j]:
                        psl[j] = nsl

        # ---------- 5. swap at rollover ----------
        if roll_mult[i] > 0:
            for j in range(MAXP):
                if pk[j] < 0:
                    continue
                notional = c[i] * plots[j] * contract
                rate = swap_l if pdir[j] == 1 else swap_s
                sw = notional * rate / 360.0 * roll_mult[i]
                pswap[j] += sw

        # ---------- 6. mark to market ----------
        fl_c = 0.0
        fl_w = 0.0
        for j in range(MAXP):
            if pk[j] < 0:
                continue
            extra = pswap[j] - 2 * commission * plots[j]
            if pdir[j] == 1:
                fl_c += (c[i] - pentry[j]) * plots[j] * contract + extra
                fl_w += (l[i] - pentry[j]) * plots[j] * contract + extra
            else:
                fl_c += (pentry[j] - c[i] - sp) * plots[j] * contract + extra
                fl_w += (pentry[j] - h[i] - sp) * plots[j] * contract + extra
        eq_close[i] = balance + fl_c
        eq_low[i] = balance + fl_w

    # close anything still open at the last close
    for j in range(MAXP):
        if pk[j] < 0:
            continue
        k = pk[j]
        xp = c[n - 1] if pdir[j] == 1 else c[n - 1] + spread[n - 1]
        pnl = (xp - pentry[j]) * pdir[j] * plots[j] * contract - 2 * commission * plots[j] + pswap[j]
        balance += pnl
        t_k[nt] = k; t_dir[nt] = pdir[j]; t_ei[nt] = pbar[j]; t_xi[nt] = n - 1
        t_ep[nt] = pentry[j]; t_xp[nt] = xp; t_lots[nt] = plots[j]; t_pnl[nt] = pnl
        t_r[nt] = pnl / (prisk[j] * plots[j] * contract) if prisk[j] > 0 else 0.0
        t_reason[nt] = EXIT_EOD
        nt += 1
    return (t_k[:nt], t_dir[:nt], t_ei[:nt], t_xi[:nt], t_ep[:nt], t_xp[:nt], t_lots[:nt],
            t_pnl[:nt], t_r[:nt], t_reason[:nt], eq_close, eq_low, balance)


@dataclass
class Signals:
    """Signal arrays aligned to the execution bars for one strategy."""
    name: str
    direction: np.ndarray          # int8, +1/-1 entry at this bar's open
    sl: np.ndarray                 # SL distance in price
    tp: np.ndarray                 # TP distance in price (0 = none)
    exit: np.ndarray | None = None  # +1 close longs, -1 close shorts, 2 close all (at bar open)
    params: StratParams = field(default_factory=StratParams)
    lim: np.ndarray | None = None   # >0: enter with a limit this far better than the open (SL stays anchored)


@dataclass
class Result:
    trades: pd.DataFrame
    equity: pd.Series
    equity_low: pd.Series
    equity0: float

    # ------------------------------------------------------------------
    def stats(self, start=None, end=None) -> dict:
        eq = self.equity
        el = self.equity_low
        tr = self.trades
        if start is not None or end is not None:
            eq = eq.loc[start:end]
            el = el.loc[start:end]
            if len(eq) < 2:
                return {}
            tr = tr[(tr.exit_time >= eq.index[0]) & (tr.exit_time <= eq.index[-1])]
        if len(eq) < 2:
            return {}
        e0 = eq.iloc[0] if start is not None else self.equity0
        years = (eq.index[-1] - eq.index[0]).total_seconds() / (365.25 * 86400)
        final = eq.iloc[-1]
        cagr = (final / e0) ** (1 / years) - 1 if years > 0 and final > 0 else np.nan
        peak = np.maximum.accumulate(np.concatenate([[e0], eq.values]))[1:]
        dd = (peak - el.values) / peak
        mdd = float(dd.max())
        pc = np.maximum.accumulate(np.concatenate([[e0], eq.values]))[1:]
        mdd_close = float(((pc - eq.values) / pc).max())
        daily = eq.resample("1D").last().dropna()
        dr = daily.pct_change().dropna()
        sharpe = dr.mean() / dr.std() * np.sqrt(252) if dr.std() > 0 else np.nan
        wins = tr.pnl > 0
        gp = tr.pnl[wins].sum()
        gl = -tr.pnl[~wins].sum()
        monthly = eq.resample("ME").last()
        mret = monthly.pct_change().dropna()
        yearly = eq.resample("YE").last()
        y0 = pd.concat([pd.Series([e0], index=[eq.index[0]]), yearly])
        yret = y0.pct_change().dropna()
        return dict(
            trades=len(tr), years=round(years, 2), cagr=cagr, maxdd=mdd, maxdd_close=mdd_close,
            mar=cagr / mdd if mdd > 0 else np.nan, sharpe=sharpe,
            winrate=float(wins.mean()) if len(tr) else np.nan,
            pf=gp / gl if gl > 0 else np.inf, avg_r=float(tr.r.mean()) if len(tr) else np.nan,
            trades_per_year=len(tr) / years if years > 0 else np.nan,
            worst_month=float(mret.min()) if len(mret) else np.nan,
            pct_pos_months=float((mret > 0).mean()) if len(mret) else np.nan,
            worst_year=float(yret.min()) if len(yret) else np.nan,
            final=final,
        )


def run(bars: pd.DataFrame, strategies: list[Signals], costs: Costs = Costs(),
        spread: np.ndarray | float = 0.30, equity0: float = 10_000.0, compounding: bool = True) -> Result:
    n = len(bars)
    o = bars.open.values.astype(np.float64)
    h = bars.high.values.astype(np.float64)
    l = bars.low.values.astype(np.float64)
    c = bars.close.values.astype(np.float64)
    sp = np.full(n, spread, np.float64) if np.isscalar(spread) else np.asarray(spread, np.float64)
    idx = bars.index
    # rollover at 17:00 New York (server midnight on NY-close brokers)
    ny = idx.tz_localize("UTC").tz_convert("America/New_York").tz_localize(None)
    day = (ny + pd.Timedelta(hours=7)).normalize()          # trading day label
    newday = np.r_[False, day[1:] != day[:-1]]
    roll = np.zeros(n)
    prev_dow = np.r_[0, (day[:-1]).dayofweek.values]          # trading day just closed
    roll[newday] = 1.0
    roll[newday & (prev_dow == costs.triple_dow)] = 3.0
    K = len(strategies)
    sd = np.zeros((K, n), np.int64)
    ssl = np.zeros((K, n))
    stp = np.zeros((K, n))
    sx = np.zeros((K, n), np.int64)
    slim = np.zeros((K, n))
    for k, s in enumerate(strategies):
        sd[k] = s.direction
        ssl[k] = np.nan_to_num(s.sl)
        stp[k] = np.nan_to_num(s.tp)
        if s.exit is not None:
            sx[k] = s.exit
        if s.lim is not None:
            slim[k] = np.nan_to_num(s.lim)
    P = [s.params for s in strategies]
    arr = lambda f, t=np.float64: np.array([getattr(p, f) for p in P], t)
    out = _simulate(o, h, l, c, sp, roll, sd, ssl, stp, sx, slim,
                    arr("risk"), arr("max_hold", np.int64), arr("be_trigger"), arr("be_offset"),
                    arr("max_pos", np.int64), arr("trail_r"), arr("trail_start"), arr("lim_expiry", np.int64),
                    costs.contract, costs.commission, costs.slip, costs.lot_step, costs.min_lot,
                    costs.max_lot, costs.swap_long, costs.swap_short, equity0, compounding)
    tk, tdir, tei, txi, tep, txp, tl, tpnl, tr, trs, eqc, eql, bal = out
    trades = pd.DataFrame(dict(
        strat=[strategies[k].name for k in tk], dir=tdir, entry_time=idx[tei], exit_time=idx[txi],
        entry=tep, exit=txp, lots=tl, pnl=tpnl, r=tr, reason=[EXIT_NAMES[x] for x in trs],
        bars=txi - tei))
    return Result(trades, pd.Series(eqc, idx), pd.Series(eql, idx), equity0)
