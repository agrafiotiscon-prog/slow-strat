"""Cost stress tests, drawdown-brake variants and Monte Carlo for the presets."""
import pickle
import numpy as np, pandas as pd
import final_portfolio as F

pd.set_option("display.width", 250)


def brake_sim(idx, C, L, W, a, z, start=0.04, full=0.10, floor=0.5):
    m = (idx >= a) & (idx < z)
    keys = [k for k in W if W[k] > 0]
    inc = sum(W[k] * np.diff(C[k][m], prepend=C[k][m][0]) for k in keys) / 100.0
    exc = sum(W[k] * (L[k][m] - C[k][m]) for k in keys) / 100.0
    eq = 1.0; pk = 1.0; out = np.empty(m.sum()); lo = np.empty(m.sum())
    for i in range(len(inc)):
        dd = 1 - eq / pk
        mult = 1.0 if dd <= start else max(floor, 1 - (dd - start) / (full - start) * (1 - floor))
        eq *= 1 + inc[i] * mult
        lo[i] = eq * (1 + exc[i] * mult)
        pk = max(pk, eq); out[i] = eq
    t = idx[m]; yrs = (t[-1] - t[0]).days / 365.25
    p = np.maximum.accumulate(out)
    return out[-1] ** (1 / yrs) - 1, ((p - lo) / p).max()


if __name__ == "__main__":
    base = pickle.load(open("/tmp/final_curves.pkl", "rb"))[0]
    sets = {"base costs": base}
    for lab, sm, sl in [("spread x2", 2.0, 1.0), ("slippage x3", 1.0, 3.0), ("spread x2 + slip x3", 2.0, 3.0)]:
        sets[lab] = F.build_curves(spread_mult=sm, slip_mult=sl)[0]
    rows = []
    for lab, cur in sets.items():
        idx, C, L = F.hourly(cur)
        for pn, W in F.PRESETS.items():
            for p in ["FULL 2007-2026", "2020-2023", "2024-2026 (holdout)"]:
                st, _ = F.simulate(idx, C, L, W, *F.PER[p])
                rows.append({"costs": lab, "preset": pn, "period": p, "cagr": st["cagr"], "maxdd": st["maxdd"]})
    print(pd.DataFrame(rows).pivot_table(index=["preset", "costs"], columns="period", values=["cagr", "maxdd"]).round(3).to_string())

    idx, C, L = F.hourly(base)
    print("\n--- drawdown brake (Balanced)")
    for br in [None, (0.03, 0.08, 0.5), (0.04, 0.10, 0.5), (0.05, 0.12, 0.4)]:
        out = []
        for p in ["FULL 2007-2026", "2020-2023", "2024-2026 (holdout)"]:
            a, z = F.PER[p]
            if br is None:
                st, _ = F.simulate(idx, C, L, F.PRESETS["Balanced"], a, z); c, d = st["cagr"], st["maxdd"]
            else:
                c, d = brake_sim(idx, C, L, F.PRESETS["Balanced"], a, z, *br)
            out.append(f"{p}: {c*100:5.1f}% / DD {d*100:4.1f}%")
        print(br, " | ".join(out))

    # Monte Carlo: block-bootstrap monthly returns (3-month blocks) of the Balanced preset
    print("\n--- Monte Carlo (Balanced), 12-month horizon, 20k paths, 3-month blocks")
    rng = np.random.default_rng(7)
    for p in ["FULL 2007-2026", "2024-2026 (holdout)"]:
        _, eq = F.simulate(idx, C, L, F.PRESETS["Balanced"], *F.PER[p])
        mr = eq.resample("ME").last().pct_change().dropna().values
        paths = []
        dds = []
        for _ in range(20000):
            seq = []
            while len(seq) < 12:
                s = rng.integers(0, len(mr) - 3)
                seq.extend(mr[s:s + 3])
            seq = np.array(seq[:12])
            e = np.cumprod(1 + seq)
            paths.append(e[-1] - 1)
            pk = np.maximum.accumulate(np.r_[1, e])
            dds.append((1 - np.r_[1, e] / pk).max())
        paths = np.array(paths); dds = np.array(dds)
        print(f"{p}: 1y return p5 {np.percentile(paths,5)*100:.1f}%  median {np.median(paths)*100:.1f}%  p95 {np.percentile(paths,95)*100:.1f}% | "
              f"P(loss) {np.mean(paths<0)*100:.1f}% | month-end DD median {np.median(dds)*100:.1f}% p95 {np.percentile(dds,95)*100:.1f}%")
