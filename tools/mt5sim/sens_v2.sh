#!/bin/bash
# stress + one-at-a-time sensitivity of the actual EA v2 (Balanced preset)
DATA=/tmp/mt5sim_data
runs=("base|" "spread_x2|--spread_mult=2" "slip_x3|--slip_mult=3" "spread_x2_slip_x3|--spread_mult=2 --slip_mult=3"
      "gmt0_server|UTC0" "deposit_2500|--deposit=2500" "deposit_5000|--deposit=5000" "no_asia|InpGoldAsiaEnable=false" "no_dxy_filter|InpID_DXYFilter=false"
      "GT_Channel=60|InpGT_Channel=60" "GT_Channel=100|InpGT_Channel=100" "GT_SLATR=0.8|InpGT_SLATR=0.8" "GT_SLATR=1.25|InpGT_SLATR=1.25"
      "GT_TrailR=2.5|InpGT_TrailR=2.5" "GT_TrailR=3.5|InpGT_TrailR=3.5" "GT_TrendSMA=150|InpGT_TrendSMA=150" "GT_TrendSMA=250|InpGT_TrendSMA=250"
      "GA_TPRange=0.8|InpGA_TPRange=0.8" "GA_TPRange=1.2|InpGA_TPRange=1.2" "GA_SLATR=0.8|InpGA_SLATR=0.8" "GA_SLATR=1.25|InpGA_SLATR=1.25"
      "ID_RSIMax=7|InpID_RSIMax=7" "ID_RSIMax=15|InpID_RSIMax=15" "ID_IBSMax=0.2|InpID_IBSMax=0.2" "ID_IBSMax=0.3|InpID_IBSMax=0.3"
      "ID_SLATR=1.5|InpID_SLATR=1.5" "ID_SLATR=2.5|InpID_SLATR=2.5" "DXY_thr=0|InpID_DXYMaxAboveSMA=0" "DXY_thr=2|InpID_DXYMaxAboveSMA=2"
      "DXY_SMA=150|InpID_DXYSMA=150" "DXY_SMA=250|InpID_DXYSMA=250" "idx_max2|InpID_MaxConcurrent=2")
for r in "${runs[@]}"; do
  name=${r%%|*}; arg=${r#*|}; data=$DATA; extra=""
  if [ "$arg" = "UTC0" ]; then data=/tmp/mt5sim_data_utc0; arg="InpServerGMTOffsetWinter=0 InpServerUsesUSDST=false"; fi
  ( ./sim $data /tmp/s2_$name --start=2007-06-01 $arg > /dev/null
    python3 report.py /tmp/s2_$name 2>/dev/null | awk -v n="$name" '$1=="FULL"{f=$2" "$3} $1=="2020-2023"{m=$2" "$3} $1=="2024-2026*"{h=$2" "$3} END{printf "%-18s FULL cagr/dd %s | 2020-23 %s | 2024-26 %s\n", n, f, m, h}' ) &
  while [ $(jobs -r | wc -l) -ge 4 ]; do sleep 1; done
done
wait
