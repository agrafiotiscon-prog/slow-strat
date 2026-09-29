# Research code

| File | Purpose |
|---|---|
| `fetch_data.sh` | Clone the public datasets (gold M5 2004–2026, FX/index H1 2007/2013–2023, 2024–2026 samples) |
| `data.py`, `gold.py`, `assets.py` | Loaders; UTC normalisation; combined gold history (OctaFX → Dukascopy) |
| `indicators.py` | SMA / EMA / RSI / ATR / Bands / ADX implemented to match MT5's built‑ins |
| `engine.py` | Numba bar‑level execution simulator (spread, commission, slippage, swaps, gaps, SL‑first, trailing, time exits) |
| `strategies.py` | Every strategy family that was tested (signals on completed broker‑time bars, rollover‑aware execution) |
| `sweep.py`, `run_*.py`, `survey.py` | Parameter sweeps (selection on 2012–2023, holdout 2024–2026 reported only) |
| `features.py` | Trade‑level feature analysis (entry conditions vs outcome by era) |
| `multi.py`, `idx_research.py`, `idx_server.py`, `run_multi_trend.py`, `run_fx_mr.py` | Multi‑asset tests (FX, indices, silver) in risk units |
| `book.py`, `portfolio.py`, `final_portfolio.py`, `stress.py` | Portfolio construction, presets, cost stress, drawdown brake, Monte Carlo |
| `ext.py` | v2: US Dollar Index (rebuilt from Fed H.10 rates), VIX, WTI, FX closes |
| `features2.py`, `feat_scan.py`, `filter_test.py` | v2: 12 extra indicators + intermarket features; consistency scan by era; filter tests |
| `ml_meta.py` | v2: walk‑forward machine‑learning meta‑filter (rejected: out‑of‑sample AUC ≈ 0.5) |
| `vix_strat.py` | v2: VIX‑stretch index module (rejected) |
| `intermarket/` | v2: Dollar‑Index filter portfolio + plateau (accepted), gold‑in‑EUR filter (rejected) |

Sweep outputs are in `../results/sweeps/`. The authoritative performance numbers come from running the
actual EA through `../tools/mt5sim` (see the main README).
