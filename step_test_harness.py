"""
step_test_harness.py -- REHEARSAL ONLY (uses mock simulator)
------------------------------------------------------------
Runs a designed step-test sequence across the full 0-100% choke range,
logs every time step to a DataFrame, and saves to CSV.

Usage:
    python step_test_harness.py

Output:
    mock_step_test_data.csv  -- full per-hour log
    mock_step_test_plot.png  -- 5-subplot overview figure

To use with the REAL simulator: change the single import line below.
"""

import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

# ── ONE-LINE SWAP when real simulator arrives ──────────────────────────────────
from mock_simulator import WellSimulator
# from real_simulator import WellSimulator
# ──────────────────────────────────────────────────────────────────────────────

OUTPUT_CSV  = "mock_step_test_data.csv"
OUTPUT_PLOT = "mock_step_test_plot.png"
DT = 1.0  # hours per control interval (matches problem spec)

# ── Step-test sequence design ─────────────────────────────────────────────────
# Strategy: sweep low->high->low, with fine steps in the middle range (where the
# reference dataset lives) and coarser steps at the extremes.  Hold each level
# long enough for a tau≈4hr system to reach ~98% of steady state (≈4×tau = 16hr,
# we use 20 for comfort).  Total ≈ 280 hours (~12 days of simulated time).
# During the real hackathon, re-run this against the real simulator to generate
# actual data -- the model.py fitting step reads ONLY the CSV, never the simulator source.

STEP_SEQUENCE = [
    # (choke_pct, hold_hours)
    ( 5,  20),   # near-zero -- establish baseline
    (15,  20),   # low range
    (25,  20),
    (35,  20),
    (45,  20),   # mid range (overlapping reference dataset)
    (55,  20),
    (65,  20),
    (75,  20),
    (85,  20),
    (95,  20),   # high range
    (70,  20),   # reversal step (test symmetry)
    (50,  20),
    (30,  20),
    (10,  20),   # return toward low
]


def run_step_test(sim: WellSimulator, sequence: list) -> pd.DataFrame:
    rows = []
    prev_choke = 0.0

    for choke_pct, hold_hours in sequence:
        n_steps = int(hold_hours / DT)
        for _ in range(n_steps):
            Q, WHP, FLP, BHP = sim.step(choke_pct)
            rows.append({
                "Time_hr":       sim.time,
                "Choke_pct":     choke_pct,
                "OilRate_bbl_hr": Q,
                "WHP_psi":       WHP,
                "FLP_psi":       FLP,
                "BHP_psi":       BHP,
            })
        prev_choke = choke_pct

    return pd.DataFrame(rows)


def plot_step_test(df: pd.DataFrame, save_path: str):
    fig = plt.figure(figsize=(14, 12))
    fig.patch.set_facecolor("#0f1117")
    gs = gridspec.GridSpec(5, 1, hspace=0.45)

    panel_cfg = [
        ("Choke_pct",       "Choke Position (%)",        "#a78bfa", (0, 100)),
        ("OilRate_bbl_hr",  "Oil Flow Rate (bbl/hr)",    "#34d399", None),
        ("WHP_psi",         "Wellhead Pressure (psi)",   "#60a5fa", None),
        ("FLP_psi",         "Flowline Pressure (psi)",   "#f59e0b", None),
        ("BHP_psi",         "Bottom Hole Pressure (psi)","#f87171", None),
    ]

    for i, (col, label, color, ylim) in enumerate(panel_cfg):
        ax = fig.add_subplot(gs[i])
        ax.set_facecolor("#1a1d27")
        ax.plot(df["Time_hr"], df[col], color=color, linewidth=1.2, label=label)
        ax.set_ylabel(label, color="white", fontsize=8)
        ax.tick_params(colors="white", labelsize=7)
        for spine in ax.spines.values():
            spine.set_edgecolor("#3a3d4d")
        if ylim:
            ax.set_ylim(ylim)
        if i < len(panel_cfg) - 1:
            ax.set_xticklabels([])
        else:
            ax.set_xlabel("Time (hours)", color="white", fontsize=9)
        ax.grid(axis="y", color="#2a2d3a", linewidth=0.5)

    fig.suptitle(
        "[MOCK DATA -- REHEARSAL ONLY]  Step-Test: Full Range Sweep",
        color="white", fontsize=11, fontweight="bold", y=0.98
    )
    plt.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"  Plot saved -> {save_path}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("=== Step-Test Harness [MOCK -- REHEARSAL ONLY] ===")
    sim = WellSimulator(seed=7)
    sim.reset(initial_choke=0.0)

    print(f"Running {sum(h for _, h in STEP_SEQUENCE)} simulated hours across {len(STEP_SEQUENCE)} steps...")
    df = run_step_test(sim, STEP_SEQUENCE)

    df.to_csv(OUTPUT_CSV, index=False)
    print(f"  Data saved -> {OUTPUT_CSV}  ({len(df)} rows)")

    plot_step_test(df, OUTPUT_PLOT)
    print("Done.")
