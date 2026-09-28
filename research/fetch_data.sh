#!/usr/bin/env bash
# Fetch the public historical data used by the research (all from public GitHub repositories).
#   XAUUSD M5 2020-01 .. today (Dukascopy, auto-updated): farshoffs/casio
#   XAUUSD M5 2004 .. 2026-01 (OctaFX MT4 export):          farshoffs/casio
#   FX / index / metals H1 2007 .. 2023-09 (MT5 export):    TheSnowGuru/Stocks-Futures-Financial-Time-series-Tick-Bar-Data
#   last ~6 months M1 and ~2y daily samples (auto-updated):  getdata-finance/*
set -euo pipefail
DEST="${DATA_REPOS:-/home/user/data_repos}"
mkdir -p "$DEST" "$DEST/gdf"
cd "$DEST"
export GIT_LFS_SKIP_SMUDGE=1

if [ ! -d farshoffs_casio ]; then
  git clone --depth 1 --filter=blob:none --no-checkout https://github.com/farshoffs/casio farshoffs_casio
  git -C farshoffs_casio checkout HEAD -- data/xauusd_m5.csv data/xauusd_m5_secondary_octafx_mt4.csv
fi

SNOW=TheSnowGuru_Stocks-Futures-Financial-Time-series-Tick-Bar-Data
if [ ! -d "$SNOW" ]; then
  git clone --depth 1 --filter=blob:none --no-checkout https://github.com/TheSnowGuru/Stocks-Futures-Financial-Time-series-Tick-Bar-Data "$SNOW"
  git -C "$SNOW" checkout HEAD -- 'forex/*_H1.csv' 'forex/audcad/AUDCAD60.csv' 'indices/*_H1.csv' 'commodities/gold/XAUUSD_H1.csv' 'commodities/silver/XAGUSD_H1.csv'
fi

cd gdf
clone() { [ -d "$2" ] || git clone -q --depth 1 "https://github.com/getdata-finance/$1" "$2"; }
for s in eurusd gbpusd usdjpy audusd usdcad usdchf eurjpy eurgbp; do clone "$s-1m-ohlcv-forex-historical-data" "$s-1m"; done
for s in xauusd xagusd; do clone "$s-1m-ohlcv-metals-historical-data" "$s-1m"; done
for s in nas100 us30 spx500 jpn225; do
  for tf in 1m 1d; do clone "$s-$tf-ohlcv-index-historical-data" "$s-$tf"; done
done
clone gbpusd-1d-ohlcv-forex-historical-data gbpusd-1d
echo "data ready in $DEST"
