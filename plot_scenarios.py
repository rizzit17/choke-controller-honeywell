"""
plot_scenarios.py -- REHEARSAL ONLY
------------------------------------
Generates the exact 6 required plot trends per scenario:
  1. Target Oil Rate
  2. Actual Oil Rate
  3. Wellhead Pressure (WHP)
  4. Flowline Pressure (FLP)
  5. Bottom Hole Pressure (BHP)
  6. Choke Position

Saves one figure per scenario as a PNG:
  mock_scenario_A_plot.png
  mock_scenario_B_plot.png
  mock_scenario_C_plot.png

Usage:
    python plot_scenarios.py
    (requires scenario CSVs from run_scenarios.py)
"""

import sys
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import os

try:
    from mock_simulator import LIMITS
except ImportError:
    LIMITS = {
        "WHP_min": 200.0, "WHP_max": 480.0,
        "FLP_min": 150.0, "FLP_max": 350.0,
        "BHP_min": 2200.0,"BHP_max": 3000.0,
    }

SCENARIOS = {
    "A": {
        "csv": "mock_scenario_A.csv",
        "out": "mock_scenario_A_plot.png",
        "title": "Scenario A -- Startup to Target",
        "subtitle": "Well starts near shut-in; controller ramps to production target",
    },
    "B": {
        "csv": "mock_scenario_B.csv",
        "out": "mock_scenario_B_plot.png",
        "title": "Scenario B -- Target Step-Change (100 -> 150 bbl/hr)",
        "subtitle": "Target increases mid-run; controller re-tracks within ramp-rate constraints",
    },
    "C": {
        "csv": "mock_scenario_C.csv",
        "out": "mock_scenario_C_plot.png",
        "title": "Scenario C -- Infeasible Target (300 bbl/hr requested)",
        "subtitle": "Target exceeds safe operating envelope; controller settles at max safe rate",
    },
}

BG_DARK  = "#0f1117"
BG_PANEL = "#1a1d27"
GRID_COL = "#2a2d3a"
SPINE_COL = "#3a3d4d"

PANEL_CFG = [
    # (column, label, color, show_target_col, show_limits)
    ("OilRate_bbl_hr", "Oil Rate (bbl/hr)",       "#34d399", True,  False),
    ("WHP_psi",        "WHP (psi)",                "#60a5fa", False, True),
    ("FLP_psi",        "FLP (psi)",                "#f59e0b", False, True),
    ("BHP_psi",        "BHP (psi)",                "#f87171", False, True),
    ("Choke_pct",      "Choke Position (%)",       "#a78bfa", False, False),
]

LIMIT_MAP = {
    "WHP_psi": ("WHP_min", "WHP_max"),
    "FLP_psi": ("FLP_min", "FLP_max"),
    "BHP_psi": ("BHP_min", "BHP_max"),
}


def plot_scenario(df: pd.DataFrame, cfg: dict, scenario_key: str):
    n_panels = len(PANEL_CFG)
    fig = plt.figure(figsize=(14, 14))
    fig.patch.set_facecolor(BG_DARK)

    gs = gridspec.GridSpec(n_panels, 1, hspace=0.40)

    t = df["Time_hr"].values

    for i, (col, label, color, show_target, show_limits) in enumerate(PANEL_CFG):
        ax = fig.add_subplot(gs[i])
        ax.set_facecolor(BG_PANEL)
        ax.tick_params(colors="white", labelsize=7.5)
        for spine in ax.spines.values():
            spine.set_edgecolor(SPINE_COL)
        ax.grid(axis="y", color=GRID_COL, linewidth=0.5, linestyle="--")

        # Main signal
        ax.plot(t, df[col].values, color=color, linewidth=1.6, label=label, zorder=3)

        # Target line (oil rate panel only)
        if show_target and "Target_Q" in df.columns:
            ax.plot(t, df["Target_Q"].values,
                    color="white", linewidth=1.2, linestyle="--",
                    alpha=0.7, label="Target", zorder=2)
            ax.legend(fontsize=7.5, facecolor=BG_PANEL, labelcolor="white",
                      framealpha=0.8, loc="lower right")

        # Constraint limit bands (pressure panels)
        if show_limits and col in LIMIT_MAP:
            lo_key, hi_key = LIMIT_MAP[col]
            lo, hi = LIMITS[lo_key], LIMITS[hi_key]
            ax.axhline(lo, color="#ef4444", linewidth=1.0, linestyle=":",
                       alpha=0.85, label=f"Min {lo:.0f}")
            ax.axhline(hi, color="#ef4444", linewidth=1.0, linestyle=":",
                       alpha=0.85, label=f"Max {hi:.0f}")
            ax.fill_between(t, lo, hi, color="#ef4444", alpha=0.04)
            ax.legend(fontsize=7, facecolor=BG_PANEL, labelcolor="white",
                      framealpha=0.8, loc="upper right")

        # Choke position: draw ±5% ramp annotation
        if col == "Choke_pct":
            ax.set_ylim(-2, 105)
            ax.axhline(0,   color="#6b7280", linewidth=0.6, linestyle=":")
            ax.axhline(100, color="#6b7280", linewidth=0.6, linestyle=":")

        ax.set_ylabel(label, color="white", fontsize=8.5)
        if i < n_panels - 1:
            ax.set_xticklabels([])
        else:
            ax.set_xlabel("Time (hours)", color="white", fontsize=9)

    # Mark target step-change for Scenario B
    if scenario_key == "B" and "Target_Q" in df.columns:
        change_mask = df["Target_Q"].diff().abs() > 1
        for ax in fig.axes:
            for t_change in df.loc[change_mask, "Time_hr"]:
                ax.axvline(t_change, color="#fbbf24", linewidth=0.8,
                           linestyle="--", alpha=0.6)

    fig.suptitle(
        f"[MOCK DATA -- REHEARSAL ONLY]  {cfg['title']}\n"
        f"{cfg['subtitle']}",
        color="white", fontsize=11, fontweight="bold", y=0.99
    )

    plt.savefig(cfg["out"], dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close()
    print(f"  -> {cfg['out']}")


def main():
    print("=== Generating Scenario Plots [MOCK -- REHEARSAL ONLY] ===")
    for key, cfg in SCENARIOS.items():
        if not os.path.exists(cfg["csv"]):
            print(f"  [SKIP] {cfg['csv']} not found -- run run_scenarios.py first.")
            continue
        df = pd.read_csv(cfg["csv"])
        plot_scenario(df, cfg, key)
        print(f"  Scenario {key}: {len(df)} steps plotted.")
    print("Done.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
