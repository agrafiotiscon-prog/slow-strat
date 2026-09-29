# SlowStrat v2 — MT5 portfolio Expert Advisor

**Gold trend breakout + gold Asian‑range breakout + US‑index dip buyer with a US Dollar Index filter, plus risk‑based sizing, a drawdown brake, a news filter and rollover/spread protection.**

`mql5/Experts/SlowStrat/SlowStrat.mq5` is the EA. Everything in `research/` and `tools/` is the evidence behind it and can be re‑run.

> **Read this first — honest summary**
>
> The goal was **15–20 % per year with less than 6 % maximum drawdown**, taking mostly high‑probability trades, built for *today's* market.
>
> | Default *Balanced* preset | Annual return | Max drawdown |
> |---|---|---|
> | **Today's market — Jan 2024 → Sep 2026** (never used to design or tune anything) | **+16.1 %/yr** | **5.9 %** |
> | 2025 | +19.6 % | 4.0 % |
> | 2026 to 25 Sep | +14.7 % (21 % annualised) | 4.0 % |
> | **Full history — Jun 2007 → Sep 2026** | **+7.1 %/yr** | **8.8 %** |
>
> These figures come from running the **actual EA code** on historical data, with spreads, commission, slippage and swaps included (see [How it was tested](#how-it-was-tested)). Drawdown is measured from the intraday equity peak, the same way MT5 reports it.
>
> **In the current market regime the EA meets the target. Over the full 19 years it does not.** The weak stretches:
> - **Losing years:** 2010, 2012 and 2022, the worst at −3.4 %.
> - **Longest time without a new equity high:** about 3.5 years (Sep 2020 → Mar 2024).
>
> Dozens of strategy families were tested on gold, silver, 18 FX pairs and 5 stock indices. None delivers 15–20 % with under 6 % drawdown *robustly* across 20 years. Backtests that claim so are almost always overfitted, or use martingale/grid position sizing that eventually blows up. This EA uses neither. **Nothing here is a guarantee. Use a demo account first.**

![Equity curves](results/equity_presets.png)

### What changed in v2 (vs v1)

v1 used price only. For v2 I tested **other tools and data**:
- intermarket data: the US Dollar Index, VIX, oil, the S&P 500 trend, and gold priced in euros and yen;
- gold tick volume;
- 12 more indicators: MACD, Supertrend, Ichimoku, Keltner, Parabolic SAR, Stochastic, CCI, Bollinger %B and width, ADX, RSI and volume ratio;
- a **machine‑learning trade filter**, trained walk‑forward.

Most of these did **not** survive honest testing (details in [What did NOT work](#what-did-not-work-and-was-rejected)). One did, clearly and in every period: **index dips are only bought when the US Dollar Index is not strong.** A strong dollar usually means tighter financial conditions, so dips keep falling.

| Default preset, same measurement | 2007–2026 | 2020–23 (worst regime) | 2024–26 |
|---|---|---|---|
| v1 Balanced | 7.9 %/yr, DD 11.8 % | 4.8 %/yr, DD 11.8 % | 16.3 %/yr, DD 6.2 % |
| **v2 Balanced** | **7.1 %/yr, DD 8.8 %** | **6.5 %/yr, DD 8.8 %** | **16.1 %/yr, DD 5.9 %** |
| v2 Growth (v1‑like risk) | 8.5 %/yr, DD 10.2 % | 7.6 %/yr, DD 10.2 % | 20.7 %/yr, DD 7.1 % |

With v2, index‑dip trades win **76 %** of the time (v1: 70 %) and the average trade is **+0.27 R** (v1: +0.15 R).

### v3 research round: order flow and everything else (trading logic unchanged)

For v3 I tested **order flow** plus every other improvement I could think of, under the same rules as before:
- a rule had to help in each of 2012‑15, 2016‑19 and 2020‑23;
- it had to hold up in 2024‑26;
- nearby settings had to work too;
- the gain had to survive the full engine, not just a trade‑by‑trade split.

**Nothing passed, so the EA's trading logic stays exactly as in v2.** Adding rules that fail these tests would make the backtest prettier and live trading worse. Full results are in [What did NOT work](#what-did-not-work-and-was-rejected). In short:

- **Order flow.** Real order flow (buyer/seller "delta", footprint charts, market depth) **does not exist for spot gold or index CFDs at MT5 brokers**. There is no central exchange tape, and MT5 "volume" is only a count of price ticks. I built every proxy an EA can compute from broker bars:
  - bar delta, cumulative delta and delta divergence;
  - daily and weekly VWAP;
  - the prior day's volume profile (POC and value area);
  - relative volume and climax bars.

  None was a consistent filter for the existing trades. All **21 classic order‑flow strategies** tested lost money after costs: VWAP fades, the value‑area "80 % rule", POC rejections, climax reversals, and opening‑range breakouts confirmed by volume.
- **Institutional positioning:** CFTC Commitments of Traders and SPDR Gold ETF (GLD) holdings. Two near misses, but both hurt at least one period and both need data MT5 does not provide.
- **Sizing and trade management:** volatility‑targeted sizing, trading the equity curve, breakeven stops, limit‑order pullback entries, seasonality and time of day. All rejected.

One practical finding: gold breakouts on **US jobs‑report (NFP) Fridays** were the best trades in the sample (+1.82 R average over 18 trades, versus +0.39 R otherwise). Most enter at the 09:00 New York bar, 30 minutes after the release. The default news blackout (`InpNewsAfterMin = 20`) lets them enter on time. If you set it to 30 minutes or more, the EA keeps retrying but enters later, at a worse price, which was not tested. **Keep the default.**

---

## Contents
1. [What the EA trades](#what-the-ea-trades)
2. [Results](#results)
3. [How it was tested](#how-it-was-tested)
4. [What did NOT work](#what-did-not-work-and-was-rejected)
5. [Installation and settings](#installation-and-settings)
6. [Important factors and risk notices](#important-factors-and-risk-notices)
7. [Verify it yourself in the MT5 Strategy Tester](#verify-it-yourself-in-the-mt5-strategy-tester)
8. [Reproduce the research](#reproduce-the-research)
9. [Limitations](#limitations)

---

## What the EA trades

The EA runs three independent modules from a single chart. Each module has its own magic number. The bars it uses are MT5 broker bars, in server time.

| Module | Symbol | Timeframe | Win rate | Avg trade | Trades / yr | Role |
|---|---|---|---|---|---|---|
| **1. Gold trend breakout** | XAUUSD | H4 signals, M5 trailing | 33 % | **+0.49 R** | ~21 | Main profit engine; catches big gold trends. Few, large winners. |
| **2. Gold Asian‑range breakout** | XAUUSD | M5 | **71 %** | +0.04 R | ~70 | High win rate, small edge. Strong in 2024‑26 (74 % win, +0.14 R). |
| **3. US‑index dip buyer + USD filter** | US500, NAS100, US30 | D1 | **76 %** | **+0.27 R** | ~10 (all 3) | High win rate, uncorrelated with gold. |

All three modules together win **63 %** of their trades. R is the amount risked on a trade; +0.49 R means the average trade made 49 % of what it risked.

### Module 1 — Gold H4 trend breakout
- **Long:** the H4 close is above the highest high of the previous **80** H4 bars, **and** the last completed D1 close is above the **D1 SMA(200)**.
- **Short:** the mirror image.
- **Stop loss:** 1.0 × ATR(20, H4). There is no take‑profit.
- **Trailing stop:** 3 R behind the best price since entry. It updates on every completed M5 bar and only moves in the trade's favour.
- One position at a time. A signal that lands inside the rollover window (16:30–18:30 New York time) is executed at 18:30 NY.

### Module 2 — Gold Asian‑range breakout (the high win‑rate module)
- **Range:** the Asian range is the high/low of 00:00–07:00 UTC.
- **Entry window:** 07:00–12:00 UTC. The **first** M5 close outside the range triggers the trade, but only in the direction of yesterday's close relative to the **daily EMA(50)**. At most one trade per day.
- **Skipped days:** the range must be between 0.3 and 2.0 × the daily ATR(14).
- **Stop loss:** 1.0 × daily ATR(14). **Take‑profit:** 1.0 × the Asian range. The wide stop and small target give the ~71 % win rate.

### Module 3 — US‑index daily dip buyer with a US Dollar Index filter
- **Entry:** buy on the next session, after the daily rollover, when all of these hold on the completed D1 bar:
  - **RSI(2) < 10**
  - **IBS < 0.25**, where IBS (internal bar strength) = (close − low) / (high − low)
  - **close > SMA(200)**
  - **new in v2:** the **US Dollar Index is at most 1 % above its 200‑day average**
- **How the EA builds the Dollar Index:** from your broker's EURUSD, USDJPY, GBPUSD, USDCAD, USDSEK and USDCHF daily closes, using the official ICE weights. It uses the previous day's closes, so there is no look‑ahead. If a pair is missing (USDSEK often is), it is left out.
- **Exit:** at the first daily close above **SMA(5)**, or after 10 daily bars.
- **Stop loss:** 2 × ATR(10, D1).
- Long only. At most 3 index positions open at once.

### Portfolio‑level protection (all modules)
- **Sizing:** each trade risks a fixed % of equity, calculated with `OrderCalcProfit` (works in any account currency). Commission is included.
- **Drawdown brake:** full size until drawdown from the equity peak reaches 3 %, then size shrinks linearly to 50 % at 8 % drawdown.
- **Daily loss limit:** 3 %; after that, no new entries until the next server day.
- **Hard stop:** at 20 % drawdown the EA closes everything and halts.
- **Open‑risk cap:** 6 % of equity across all open trades.
- **Rollover block:** no entries 16:30–18:30 New York time.
- **Spread filter:** gold 4 bp, indices 3 bp.
- **News filter:** MT5 economic calendar, live only. New entries are blocked from 30 min before to 20 min after high‑impact USD events.
- **Stops are server‑side**, and state survives restarts.
- **On‑chart panel:** equity, drawdown, brake level, open risk, clocks, the next high‑impact news and the Dollar Index status.
- **Trade log:** written to `MQL5/Files/SlowStrat_log.csv`.

---

## Results

Setup for these runs:
- **Code and period:** actual EA code, $10,000 start, Jun 2007 → 25 Sep 2026.
- **Gold costs:** spread ≈ 0.8 bp of price with a $0.25 floor ($0.32 at $4,000), 5 × wider around rollover; commission $7 per lot round trip; slippage $0.08 per fill.
- **Index costs:** spread 0.7–1 bp, slippage 0.3 bp.
- **Swaps** (annual rate on position value): gold long −5.5 %, short −1 %; indices long −7 %, short −2 %.
- **Fills:** a gapped stop fills at the worse open. When stop and target are touched in the same bar, the stop is assumed to hit first.
- **Drawdown:** measured from the intraday equity peak.

**CAGR / maximum drawdown by period and preset:**

| Period | Conservative | **Balanced (default)** | Growth | Aggressive |
|---|---|---|---|---|
| 2008–2011 | 1.3 % / 3.8 % | 1.2 % / 6.6 % | 1.1 % / 7.7 % | 0.8 % / 10.3 % |
| 2012–2015 | 4.4 % / 3.4 % | 6.0 % / 5.7 % | 7.0 % / 6.7 % | 9.6 % / 9.9 % |
| 2016–2019 | 5.1 % / 5.2 % | 7.8 % / 7.4 % | 9.2 % / 8.7 % | 12.1 % / 11.9 % |
| 2020–2023 | 4.4 % / 6.3 % | 6.5 % / 8.8 % | 7.6 % / 10.2 % | 9.6 % / 12.8 % |
| **2024 → Sep 2026 (holdout)** | **8.5 % / 3.8 %** | **16.1 % / 5.9 %** | **20.7 % / 7.1 %** | **27.2 % / 9.6 %** |
| 2025 | 9.6 % / 2.2 % | 19.7 % / 4.0 % | 25.9 % / 4.9 % | 35.9 % / 6.9 % |
| 2026 YTD (annualised) | 10.3 % / 2.2 % | 21.0 % / 4.0 % | 29.5 % / 5.0 % | 41.1 % / 6.0 % |
| **Full 2007–2026** | **4.6 % / 6.3 %** | **7.1 % / 8.8 %** | **8.5 % / 10.2 %** | **11.0 % / 12.8 %** |
| $10k grew to | $23,980 | $37,594 | $48,330 | $75,777 |

**Risk per trade by preset:**

| Preset | Gold trend | Gold Asia | Each index |
|---|---|---|---|
| Conservative | 0.30 % | 0.25 % | 0.75 % |
| Balanced | 0.48 % | 0.40 % | 1.20 % |
| Growth | 0.60 % | 0.50 % | 1.50 % |
| Aggressive | 0.90 % | 0.75 % | 2.25 % |

Index data only starts in May 2013, so 2007–2012 is gold‑only.

**Balanced, calendar years:**

| Year | Return | Year | Return | Year | Return | Year | Return |
|---|---|---|---|---|---|---|---|
| 2007 (Jun–Dec) | +6.3 % | 2012 | −2.3 % | 2017 | +9.2 % | 2022 | −3.4 % |
| 2008 | +4.2 % | 2013 | +15.6 % | 2018 | +4.1 % | 2023 | +5.9 % |
| 2009 | +4.4 % | 2014 | +7.3 % | 2019 | +8.9 % | 2024 | +9.7 % |
| 2010 | −2.8 % | 2015 | +4.1 % | 2020 | +23.6 % | 2025 | +19.6 % |
| 2011 | +0.4 % | 2016 | +9.0 % | 2021 | +2.8 % | 2026 (to Sep 25) | +14.7 % |

![Drawdown](results/drawdown_balanced.png)

**What to expect over the next 12 months (Balanced).** Block‑bootstrap Monte Carlo of the EA's monthly returns, 40,000 paths:

| If the market behaves like… | Median 12‑m return | 5 % worst case | Chance of a losing year | Chance of ≥ 10 % | Chance of ≥ 15 % |
|---|---|---|---|---|---|
| 2024–2026 | +16.9 % | +4.0 % | 1 % | 78 % | 58 % |
| the whole 2007–2026 history | +6.4 % | −2.6 % | 14 % | 32 % | 16 % |

Growth has better odds of reaching 10 %: 85 % if the market is like 2024–26 and 39 % if it is like the long history. The cost is more drawdown.

Full per‑period tables and every simulated trade for each preset are in [`results/ea_simulation/`](results/ea_simulation/).

---

## How it was tested

1. **Data (all public).** The usual market‑data sites were blocked from the build environment, so everything came from public GitHub datasets ([`research/fetch_data.sh`](research/fetch_data.sh)):
   - XAUUSD M5 2004 → 27 Sep 2026;
   - FX, index and silver H1 bars for 2007/2013 → Sep 2023;
   - recent M1/daily samples to Sep 2026;
   - **new in v2:** official daily FX rates (Federal Reserve H.10, used to rebuild the Dollar Index, which matches the real index: 114 in Sep 2022, 71 in Mar 2008), VIX daily 1990–2026, and WTI and Brent daily.
2. **Realistic Python engine** ([`research/engine.py`](research/engine.py)):
   - M5 execution with bid/ask spreads, rollover spread spikes, commission, slippage and swaps;
   - gap fills and the stop‑first rule;
   - broker‑style H4/D1 bars;
   - no look‑ahead.
3. **Development versus holdout.** Everything was chosen on **2012–2023**, and a rule had to be positive in *each* of 2012‑15, 2016‑19 and 2020‑23. **Jan 2024 → Sep 2026 was never used for any decision.**
   - v2's intermarket candidates additionally had to hold up in 2024‑26.
   - They also had to show a plateau (nearby settings working too) and have an economic reason to work.
4. **Robustness checks on the actual v2 EA (Balanced).** Full list in [`results/ea_simulation/balanced_stress_and_sensitivity.txt`](results/ea_simulation/balanced_stress_and_sensitivity.txt).
   - **Parameter sensitivity**, 23 variants (each gold, Asia, index and Dollar Index parameter nudged ±20–25 %). All land at:

     | Period | Return | Max drawdown |
     |---|---|---|
     | 2007–2026 | 6.4–8.0 %/yr | 8.2–10.0 % |
     | 2024‑26 | 13.8–16.9 %/yr | 4.7–6.9 % |

   - **Costs:**

     | Stress | 2024‑26 | 2007–2026 |
     |---|---|---|
     | Double spreads | 13.8 %/yr | 4.2 %/yr |
     | Triple slippage | 15.4 %/yr | 6.3 %/yr |
     | Both | 10.7 %/yr (DD 5.6 %) | 3.3 %/yr |

   - **Broker time zone:** a GMT+0 server gives 16.9 %/yr in 2024‑26 but 5.3 %/yr over 2007–2026. New‑York‑close (GMT+2/+3) brokers are recommended.
   - **Account size:** $10k gives the results above. At $5k, 2024‑26 drops to 13.5 %/yr; at $2.5k, 10.6 %/yr. The 0.01‑lot minimum on gold makes the EA skip or undersize trades on small accounts.
   - **Worst cases:**
     - worst single trade −1.48 R (a weekend gap); only 5 of 1,884 trades lost more than 1.2 R;
     - worst day −3.45 %;
     - longest losing streaks: gold trend 9, gold Asia 6, index dips 4.
5. **EA‑versus‑research parity check** ([`tools/mt5sim`](tools/mt5sim)). No MT5 terminal could be downloaded here, so:
   - the EA's source is mechanically translated to C++ and runs against an MT5 API emulator;
   - it **compiles with zero errors and zero warnings under `g++ -Wall`**;
   - over 2007–2026 it reproduces the research trade‑for‑trade:

     | Module | Research trades matched | Correlation of R results |
     |---|---|---|
     | Gold trend | 397 of 398 | 0.994 |
     | Gold Asia | 1,361 of 1,362 | 1.000 |
     | USD‑filtered index dips | 97–100 % | 0.993–0.997 |

---

## What did NOT work (and was rejected)

**New in v3: order flow, positioning, sizing and trade management.** All are tested on the real trades of the v2 modules, and gold results are shown per era.

| Tried | Result |
|---|---|
| **Order‑flow proxies as filters** (15 measures: bar delta, cumulative delta, delta/price divergence, day and week VWAP distance, prior‑day POC and value area, relative volume, climax bars, day volume) | For the gold trend no measure had the same sign across the three development eras and the holdout. The best Asia candidate, delta divergence, gave +0.15 / +0.13 R in 2012‑19 but +0.01 R in 2020‑23 and −0.08 R in 2007‑11. Rejected. [`results/orderflow_filters_*.csv`](results) |
| **Order‑flow strategies** (VWAP‑deviation fade, value‑area "80 % rule", prior‑day POC rejection, volume‑climax reversal, London/NY opening‑range breakout with relative‑volume confirmation: 21 variants) | **All 21 lost money after costs** (best −0.02 R per trade), and none was positive in all three development eras. [`results/orderflow_strategies.csv`](results/orderflow_strategies.csv) |
| **GLD ETF flows** (only trade gold trends that ETF holdings confirm) | Positive trade‑by‑trade in 4 of 5 eras. In the full engine it filtered out too many big winners: the gold module fell from 5.2 to 3.9 %/yr, and 2007‑11 fell from 3.0 to 0.4 %/yr. It also needs an outside data feed. Rejected. |
| **COT positioning** (CFTC managed money, producers, non‑commercials; levels, 1‑ and 3‑year ranks, changes; with the real Friday publication delay) | Most measures flip sign between eras. **Closest miss of the whole round:** skip a gold breakout when hedge funds added more than 4 % of open interest in that direction over the last 2 weeks (a "crowded" move). On the gold module alone, its full‑period return per unit of drawdown beat 99 % of 200 random filters that drop the same share of trades. In the full portfolio, though, it left 2007‑26 return unchanged (6.5 %/yr, drawdown 9.5 → 8.9 %). It improved 2020‑26 but made 2007‑15 worse, and the 8‑ and 13‑week versions did worse than no filter at all. It would also need a weekly CFTC download inside MT5, and the Strategy Tester can't do that. Rejected. [`results/cot_*.csv`](results) |
| **Volatility‑targeted sizing** (scale risk by target ÷ recent volatility, clipped at 0.5–1.5× or 0.67–1.25×) | It mostly added leverage. For the gold trend, return per unit of drawdown got worse in 2007‑11 and 2016‑19 and better elsewhere; the Asia module was also mixed. It doesn't help in every period. Rejected. |
| **Trading the equity curve** (halve a module's risk while its equity is below its 20‑ or 50‑trade average, or stop it entirely) | Lower or equal returns in every era. Drawdown fell in some eras, but return per unit of drawdown fell in 2020‑23 and 2024‑26. Rejected. |
| **Breakeven stop** (at 1, 1.5 or 2 R, with or without +0.25 R locked) | Cuts the big trend winners. The best version (2 R) is 5.5 vs 5.2 %/yr, with drawdown 15.0 vs 13.2 %. Rejected. |
| **Limit‑order pullback entries** (buy 0.1–0.75 ATR below the breakout, same stop) | The trades that pull back are mostly the failed breakouts (adverse selection). Gold trend avg R fell from 0.46 to between 0.44 and −0.06, and the Asia module also got worse. Rejected. [`results/limit_entry_tests.csv`](results/limit_entry_tests.csv) |
| **Seasonality** ("gold rises in January", month‑of‑year) | January looked strong, but placebo months were also positive (gold simply rose), and it was about zero in two eras. Rejected. |
| **Time of day** of the gold breakout entry | No H4 slot was consistently better or worse across eras. Nothing to filter. |

**New in v2 — other tools and data:**

| Tried | Result |
|---|---|
| **Machine‑learning trade filter** (gradient boosting and logistic regression on ~80 features, trained walk‑forward) | Out‑of‑sample AUC 0.42–0.55, i.e. no better than a coin flip. Taking only its "confident" trades *reduced* profits in most years. Rejected: a black box that looks clever is not an edge. |
| **VIX‑spike dip buying** (Connors‑style "VIX stretch") | +0.09…+0.23 R in 2013–23 but flat (+0.00 R) in 2024–26. A broker‑available volatility proxy lost money. Rejected. |
| **Gold also trending in EUR/JPY** (XAUEUR/XAUJPY confirmation) | It looked good trade‑by‑trade. In the full engine it lowered gold returns, and whether it reduced drawdown depended on the setting (SMA 100/150 vs 250). Not a plateau. Rejected. |
| **MACD, RSI, Keltner, Stochastic, CCI, Supertrend, Ichimoku, Parabolic SAR, Bollinger** as confirmation filters | 4‑hour MACD, RSI and Keltner "confirmations" helped in 2012–23 and then flipped sign in 2024–26. The rest never helped consistently. Rejected. |
| **Tick volume, volatility regime, oil trend, S&P 500 trend** as gold filters | Each helped some eras and hurt others, and all cut total profit. Rejected. |
| **Dollar Index moves as a filter for the Asia breakout** | Strong in 2012–23, no benefit in 2024–26, and no economic logic. Rejected as data‑mining. |
| **Treasury yields, silver** | Couldn't be validated: no data for 2024–26 here. Most MT5 brokers don't offer yields anyway. (COT positioning was tested later, in v3; see above.) |

**From v1 research:**
- **Short‑term mean reversion on gold** (RSI‑2 dips, Bollinger fades, previous‑day high/low sweep reversals): no edge after costs.
- **Trend following on FX, silver and non‑US indices:** negative in 2016–2023.
- **FX‑cross mean reversion:** about +0.03 R, too small to trade.
- **The "gold rises every night" effect:** a data artefact caused by rollover spreads.
- **Pyramiding, partial take‑profit, and ADX / efficiency / compression filters:** each made results worse.
- **Martingale, grid and averaging down:** deliberately not used.

---

## Installation and settings

1. **Copy** `mql5/Experts/SlowStrat/SlowStrat.mq5` into your terminal's `MQL5/Experts/SlowStrat/` folder (File → Open Data Folder).
2. **Compile** it in MetaEditor (F7).
3. **Attach** it to **one chart**, for example XAUUSD M5, and enable *Algo Trading*.
4. **Use a hedging account.**
5. **Put the symbols in Market Watch:**
   - XAUUSD (or GOLD);
   - US500/SPX500, NAS100/USTEC, US30/DJ30;
   - **EURUSD, USDJPY, GBPUSD, USDCAD, USDCHF (and USDSEK if available)** for the Dollar Index filter.
   
   Suffixes such as `.r` or `m` are auto‑detected. If your broker uses other names, set `InpGoldSymbol`, `InpIndexSymbols` and `InpDXYSymbols`.
6. **Broker time:** `InpServerGMTOffsetWinter = 2` and `InpServerUsesUSDST = true` suit most brokers (GMT+2/+3). The EA auto‑detects this live, but it must be set correctly in the **Strategy Tester**.
7. **Commission:** set `InpGoldCommissionPerLot` to your broker's gold round‑trip commission per lot (default 7.0).
8. **VPS:** run it 24/5 on a VPS near your broker's server.

| Key input | Default | Meaning |
|---|---|---|
| `InpPreset` | Balanced | Conservative / Balanced / Growth / Aggressive / Custom |
| `InpRiskMultiplier` | 1.0 | Scales every module's risk |
| `InpID_DXYFilter` | true | Dollar Index filter for index dips |
| `InpID_DXYMaxAboveSMA` / `InpID_DXYSMA` | 1.0 % / 200 | Filter threshold / averaging period |
| `InpID_MaxConcurrent` | 3 | Max index positions open at once |
| `InpDDBrake*` | 3 % → 8 %, floor 0.5 | Risk reduction while in drawdown |
| `InpDailyLossLimitPct` | 3 | Pause new entries for the day |
| `InpHardStopDDPct` | 20 | Close all and halt; resume with `InpResetPeakOnStart=true` |
| `InpMaxOpenRiskPct` | 6 | Cap on the sum of initial risk across open trades |
| `InpNewsBeforeMin` / `After` | 30 / 20 | High‑impact news blackout for new entries |

**Choosing a preset:**

| Preset | Pick it if… | What it gave |
|---|---|---|
| **Balanced** (default) | You want roughly 15–20 %/yr with drawdown around or under 6 % in today's market. | 16.1 %/yr, DD 5.9 % in 2024‑26. |
| **Growth** | You care most about the chance of +10 % in a year. | 85 % odds if next year is like 2024‑26, 39 % if it is like the long history. Drawdown 7.1 % recently, 10.2 % historically. |
| **Conservative** | You want drawdown that stayed around 6 % across all 19 years. | About 4–10 %/yr. |
| **Aggressive** | You accept much bigger swings. | Drawdowns up to 12.8 %. |

**Minimum balance:** about **$10,000** for full results; $5,000 works with somewhat lower returns. Check your broker's minimum lot for indices: at 0.1 lot × $1/point you may need more.

---

## Important factors and risk notices

- **Regime dependence — the biggest risk.** Most of the profit comes from gold trends.
  - In trending years (2013 down, 2019‑20, 2024‑26) the EA does well.
  - In sideways years (2010‑12, 2021‑23) it goes flat or loses up to about 9 % (Balanced) and can take **2–3.5 years** to recover.
  - The USD‑filtered index dips soften this but cannot remove it.
- **Correlated index positions.** US500, NAS100 and US30 often dip on the same day, so up to three positions of 1.2 % risk can open together. The worst day in the test was −3.45 %. Setting `InpID_MaxConcurrent = 2` lowers that risk at a small cost in return.
- **The Dollar Index comes from your broker's FX quotes.** If FX history is short (under ~210 daily bars), the filter stays off until there is enough. The on‑chart panel shows its status.
- **High‑impact news.** The MT5 calendar filter (live only, not in the Strategy Tester) blocks new entries around USD events: NFP, CPI, FOMC, GDP, retail sales, PCE and ISM.
  - Open positions are not closed before news; their stops are server‑side.
  - Keep `InpNewsAfterMin` at its default (20). Gold breakouts entered at 09:00 NY on jobs‑report Fridays were the best trades in the test, and a longer blackout would push them later.
  - A news spike can still gap through a stop. The worst case in 19 years was −1.48 R.
- **Rollover (17:00 New York).** Spreads widen 5–20×. The EA never *opens* trades 16:30–18:30 NY, but an existing stop can be hit by the spread spike.
- **Weekend gaps.** Positions are held over weekends, because the trend module needs to be. A gap past the stop fills at the gap price.
- **Swaps.** Gold longs pay about 5–6 %/yr and index longs about 7 %/yr of position value while held. These costs are included in the results.
- **Broker differences.** Spreads, commission, contract sizes, minimum lots, server time zone and the data feed all change results. Run your own tester check.
- **Leverage.** While in trades, gross exposure was typically about 0.5 × equity (95th percentile 1.4 ×), peaking at 4 × when several modules were open at once. Leverage of 1:20 or more is enough.
- **Prop‑firm rules.** The 3 % daily limit and the brake fit typical 5 %/10 % rules. Check the firm's rules on news trading and weekend holding.
- **Past performance does not guarantee future results.** 2024‑26 is only 2.7 years, and it was an exceptional gold bull market.

---

## Verify it yourself in the MT5 Strategy Tester
1. Open the Strategy Tester (Ctrl+R) and choose `SlowStrat\SlowStrat`, XAUUSD, **"1 minute OHLC"** or **"Every tick based on real ticks"**, a date range such as 2015 → today, and a $10,000 deposit.
2. Make sure your broker provides history for XAUUSD, your index symbols **and the FX pairs**. The tester downloads them when the EA requests them.
3. Set `InpServerGMTOffsetWinter` / `InpServerUsesUSDST` for your broker's server.
4. Compare with the tables above for the same years. Expect differences from spreads and data, but the same general shape.
5. `OnTester()` returns return ÷ max drawdown, so "Custom max" optimisation works. Don't over‑optimise: the defaults sit in the middle of a plateau.

## Reproduce the research
```bash
pip install numba pandas numpy pyarrow scipy matplotlib scikit-learn
bash research/fetch_data.sh                 # public data -> /home/user/data_repos (set DATA_REPOS to change)
cd research
python3 run_gold_trend.py                    # gold breakout parameter sweep (dev vs holdout)
python3 final_portfolio.py && python3 stress.py   # v1 portfolio, cost stress, drawdown brake, Monte Carlo
python3 feat_scan.py && python3 filter_test.py    # v2: indicator + intermarket feature scan and filter tests
python3 ml_meta.py && python3 vix_strat.py        # v2: walk-forward ML filter, VIX-stretch module (both rejected)
python3 intermarket/dxy_filter_plateau.py         # v2: Dollar-Index filter plateau (accepted)
python3 intermarket/dxy_filter_portfolio.py       # writes the v2 module trade lists used by the v3 scans below
python3 of_scan.py && python3 of_strats.py        # v3: order-flow proxies as filters / order-flow strategies (rejected)
python3 pos_scan.py && python3 intermarket/gld_filter.py && python3 intermarket/cot_filter.py \
        && python3 intermarket/cot_placebo.py     # v3: COT + GLD-flow positioning (rejected)
python3 sizing_tests.py && python3 seasonal.py && python3 mgmt_tests.py && python3 limit_tests.py  # v3: sizing, seasonality, breakeven, limit entries
cd ../tools/mt5sim
./run_ea_backtest.sh                         # translate + compile + run the ACTUAL EA over 2007-2026
./run_ea_backtest.sh InpPreset=2 --spread_mult=2   # any input / stress
./sens_v2.sh                                 # full stress + sensitivity battery
```

## Limitations
- **Not yet run inside MetaTrader 5 itself.** The build environment could not reach mql5.com. The logic was compiled and executed through a faithful C++ translation and MT5 emulator, and it matched the research trade‑for‑trade. **Compile it in MetaEditor and run the Strategy Tester on your broker before going live.**
- **FX data in the emulator.** The Dollar Index there is built from official daily noon rates. The live EA uses your broker's daily closes, so a few days sitting right at the 1 % threshold can come out differently.
- **Data gaps.** FX and index intraday data are missing from Sep 2023 to Mar 2026 (index daily data exists from May 2024), and index history starts in 2013. Gold is complete from 2004 to 27 Sep 2026.
- **Bid‑only prices.** The price data are bid only; spreads are modelled, not observed.
- **The Asia module is regime‑dependent.** Its long‑run edge is small (+0.04 R), while 2024‑26 was strong (+0.14 R). You can disable it with `InpGoldAsiaEnable=false`. Balanced without it: 13.2 %/yr (DD 7.0 %) in 2024‑26 and 6.3 %/yr (DD 8.9 %) over 2007–2026.

**Disclaimer:** This is research software, not financial advice. Trading leveraged products carries a high risk of loss, including more than your deposit with some brokers. Only trade money you can afford to lose.
