#!/bin/bash
# one-at-a-time parameter sensitivity of the actual EA (Balanced preset)
runs=("base" "InpGT_Channel=60" "InpGT_Channel=100" "InpGT_SLATR=0.8" "InpGT_SLATR=1.25" "InpGT_TrailR=2.5" "InpGT_TrailR=3.5"
      "InpGT_TrendSMA=150" "InpGT_TrendSMA=250" "InpGA_TPRange=0.8" "InpGA_TPRange=1.2" "InpGA_SLATR=0.8" "InpGA_SLATR=1.25"
      "InpGA_RangeEndUTC=6" "InpGA_TrendEMA=40" "InpGA_TrendEMA=60" "InpID_RSIMax=7" "InpID_RSIMax=15" "InpID_IBSMax=0.2" "InpID_IBSMax=0.3"
      "InpID_SLATR=1.5" "InpID_SLATR=2.5" "InpID_ExitSMA=4" "InpID_ExitSMA=7")
for r in "${runs[@]}"; do
  arg=$r; [ "$r" = "base" ] && arg=""
  ( ./sim /tmp/mt5sim_data /tmp/sens_$r --start=2007-06-01 $arg > /dev/null; python3 report.py /tmp/sens_$r 2>/dev/null | awk -v n="$r" '$1=="FULL"{f=$2" "$3} $1=="2024-2026*"{h=$2" "$3} $1=="2020-2023"{m=$2" "$3} END{printf "%-22s FULL cagr/dd %s | 2020-23 %s | 2024-26 %s\n", n, f, m, h}' ) &
  while [ $(jobs -r | wc -l) -ge 4 ]; do sleep 1; done
done
wait
