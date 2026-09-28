#!/usr/bin/env bash
# Translate the EA to C++, build the MT5 emulator and run the actual EA code over 2007-2026.
#   ./run_ea_backtest.sh                      -> Balanced preset, $10,000
#   ./run_ea_backtest.sh InpPreset=2          -> any EA input can be overridden (Name=Value)
#   ./run_ea_backtest.sh --spread_mult=2 --slip_mult=3 --deposit=5000 --start=2015-01-01
set -euo pipefail
cd "$(dirname "$0")"
DATA=/tmp/mt5sim_data
[ -f "$DATA/XAUUSD.bin" ] || python3 export_data.py "$DATA" 2006-01-01
python3 mql2cpp.py ../../mql5/Experts/SlowStrat/SlowStrat.mq5 ea_translated.cpp
g++ -std=c++17 -O2 -Wall -Wno-unused-variable -Wno-unused-but-set-variable -Wno-misleading-indentation -o sim sim.cpp
OUT=/tmp/ea_run
./sim "$DATA" "$OUT" --start=2007-06-01 "$@"
python3 report.py "$OUT"
