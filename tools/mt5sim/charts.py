"""Charts for the README from EA-simulator runs (actual EA code on historical data)."""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import report as R  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else "../../results"
RUNS = {"Conservative": "/tmp/v2f_preset0", "Balanced (default)": "/tmp/v2f_preset1", "Growth": "/tmp/v2f_preset2", "Aggressive": "/tmp/v2f_preset3"}
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
SURF, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"

plt.rcParams.update({"figure.facecolor": SURF, "axes.facecolor": SURF, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "text.color": INK, "font.size": 10,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
                     "grid.linewidth": 0.8, "axes.axisbelow": True})


def holdout_band(ax, y=0.97, va="top"):
    ax.axvspan(pd.Timestamp("2024-01-01"), pd.Timestamp("2026-09-30"), color="#f0efec", zorder=0)
    ax.text(pd.Timestamp("2024-02-15"), y, "2024-2026\nnot used for\ntuning", transform=ax.get_xaxis_transform(),
            va=va, fontsize=8, color=INK2)


# 1. equity curves of the three presets (log scale so years are comparable)
fig, ax = plt.subplots(figsize=(10, 5.2))
for (name, d), col in zip(RUNS.items(), SERIES):
    eq, _ = R.load(d)
    e = eq.equity / eq.equity.iloc[0] * 10000
    ax.plot(e.index, e.values, color=col, lw=2, label=name)
    ax.annotate(f"{name}  ${e.iloc[-1]:,.0f}", (e.index[-1], e.iloc[-1]), xytext=(6, 0), textcoords="offset points",
                va="center", fontsize=9, color=INK)
holdout_band(ax)
ax.set_yscale("log")
ax.yaxis.set_major_formatter(mt.FuncFormatter(lambda v, _: f"${v:,.0f}"))
ax.yaxis.set_minor_formatter(mt.NullFormatter())
ax.set_yticks([10000, 15000, 20000, 30000, 50000, 75000])
ax.set_title("SlowStrat EA v2 - equity from $10,000 (actual EA code, simulated 2007-06 .. 2026-09)", loc="left", fontsize=11)
ax.legend(loc="upper left", frameon=False)
ax.set_xlim(pd.Timestamp("2007-06-01"), pd.Timestamp("2029-06-01"))
fig.tight_layout()
fig.savefig(f"{OUT}/equity_presets.png", dpi=130)

# 2. yearly returns of the default preset
eq, tr = R.load(RUNS["Balanced (default)"])
y = eq.equity.resample("YE").last()
y0 = pd.concat([pd.Series([eq.equity.iloc[0]], index=[eq.index[0]]), y])
yr = y0.pct_change().dropna() * 100
fig, ax = plt.subplots(figsize=(10, 4))
years = [t.year for t in yr.index]
ax.bar(years, yr.values, color=SERIES[0], width=0.72)
for x, v in zip(years, yr.values):
    ax.text(x, v + (0.6 if v >= 0 else -0.6), f"{v:.0f}%", ha="center", va="bottom" if v >= 0 else "top", fontsize=8, color=INK2)
ax.axhline(0, color=INK2, lw=1)
ax.set_title("Balanced preset - calendar-year return (2007 from June, 2026 to Sep 25)", loc="left", fontsize=11)
ax.yaxis.set_major_formatter(mt.FuncFormatter(lambda v, _: f"{v:.0f}%"))
ax.set_xticks(years)
ax.tick_params(axis="x", labelrotation=45)
ax.grid(axis="x", visible=False)
fig.tight_layout()
fig.savefig(f"{OUT}/yearly_balanced.png", dpi=130)

# 3. drawdown (underwater) of the default preset
pk = (eq.best if "best" in eq else eq.equity).cummax()   # intraday peak, same measure as the tables
dd = -(pk - eq.worst) / pk * 100
fig, ax = plt.subplots(figsize=(10, 3.4))
ax.fill_between(dd.index, dd.values, 0, color=SERIES[0], alpha=0.35, lw=0)
ax.plot(dd.index, dd.values, color=SERIES[0], lw=1)
holdout_band(ax, y=0.03, va="bottom")
ax.axhline(-6, color=INK2, lw=1, ls="--")
ax.text(pd.Timestamp("2007-09-01"), -6.4, "6% target", va="top", fontsize=8, color=INK2)
ax.set_title("Balanced preset - drawdown from equity peak (intraday worst)", loc="left", fontsize=11)
ax.yaxis.set_major_formatter(mt.FuncFormatter(lambda v, _: f"{v:.0f}%"))
fig.tight_layout()
fig.savefig(f"{OUT}/drawdown_balanced.png", dpi=130)
print("charts written to", OUT)
