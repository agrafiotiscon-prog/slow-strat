#!/usr/bin/env python3
"""Export research data (bars in broker server time + the research spread model) for the C++ MT5 simulator.

Binary format per symbol file:  int64 n, then n records of
   int64 server_time, double open, high, low, close, spread
Server time = New York + 7h (GMT+2 winter / GMT+3 summer), like most MT5 brokers.
"""
import os
import struct
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "research"))
import assets as A  # noqa: E402
import gold  # noqa: E402
import multi as M  # noqa: E402
import strategies as S  # noqa: E402


TZ = os.environ.get("SIM_TZ", "ny7")   # ny7 = GMT+2/+3 New-York-close server; utcN = fixed GMT+N


def write(path, bars: pd.DataFrame, spread: np.ndarray):
    st = S.server_time(bars.index) if TZ == "ny7" else bars.index + pd.Timedelta(hours=int(TZ[3:]))
    t = (st.values.astype("datetime64[s]").astype(np.int64))
    arr = np.zeros(len(bars), dtype=[("t", "<i8"), ("o", "<f8"), ("h", "<f8"), ("l", "<f8"), ("c", "<f8"), ("sp", "<f8")])
    arr["t"] = t
    arr["o"], arr["h"], arr["l"], arr["c"] = bars.open.values, bars.high.values, bars.low.values, bars.close.values
    arr["sp"] = spread
    # MT5 never has two bars with the same server time: drop duplicates created by DST fall-back
    _, keep = np.unique(arr["t"], return_index=True)
    arr = arr[np.sort(keep)]
    with open(path, "wb") as f:
        f.write(struct.pack("<q", len(arr)))
        f.write(arr.tobytes())
    print(path, len(arr), pd.Timestamp(arr["t"][0], unit="s"), pd.Timestamp(arr["t"][-1], unit="s"))


def write_fx_daily(out, start):
    """FX daily bars from FRED noon rates, stamped at the server-day open (for the Dollar Index filter)."""
    import ext
    conv = {"EURUSD": ("Euro", True), "USDJPY": ("Japan", False), "GBPUSD": ("United Kingdom", True),
            "USDCAD": ("Canada", False), "USDSEK": ("Sweden", False), "USDCHF": ("Switzerland", False)}
    for sym, (country, invert) in conv.items():
        r = ext.fx_close(country)
        r = r[r.index >= pd.Timestamp(start)]
        v = (1.0 / r.values) if invert else r.values
        arr = np.zeros(len(r), dtype=[("t", "<i8"), ("o", "<f8"), ("h", "<f8"), ("l", "<f8"), ("c", "<f8"), ("sp", "<f8")])
        arr["t"] = r.index.values.astype("datetime64[s]").astype(np.int64)   # server-day 00:00
        arr["o"] = arr["h"] = arr["l"] = arr["c"] = v
        with open(f"{out}/{sym}.bin", "wb") as f:
            f.write(struct.pack("<q", len(arr)))
            f.write(arr.tobytes())
        print(f"{out}/{sym}.bin", len(arr))


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/mt5sim_data"
    start = sys.argv[2] if len(sys.argv) > 2 else "2007-01-01"
    os.makedirs(out, exist_ok=True)
    g = gold.m5(start)
    write(f"{out}/XAUUSD.bin", g, S.spread_model(g, floor=0.25))
    meta = {"XAUUSD": 0.08}
    for s in ["US500", "NAS100", "US30"]:
        b = A.exec_bars(s)
        b = b[b.index >= pd.Timestamp(start)]
        sp = S.spread_model(b, bps=M.SPREAD_BP[s], floor=0.0, roll_mult=4.0) + 2 * M.COMM_BP[s] * 1e-4 * b.close.values
        write(f"{out}/{s}.bin", b, sp)
        meta[s] = float(np.median(b.close.values) * 0.3e-4)
    write_fx_daily(out, start)
    with open(f"{out}/slip.txt", "w") as f:
        for k, v in meta.items():
            f.write(f"{k} {v}\n")
