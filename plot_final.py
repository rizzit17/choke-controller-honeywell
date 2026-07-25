"""
plot_final.py -- generates mock_final_scenario_{A,B,C}_plot.png
----------------------------------------------------------------
Same 6 required panels per scenario as plot_scenarios.py but:
  - Labeled "mock_final_" to distinguish from interim plots
  - Tighter subplot spacing
  - Dead-band annotation band added to Oil Rate panel (target +/- 3 bbl/hr shaded)
  - Constraint limit bands drawn on pressure panels
  - Target-change vertical marker for Scenario B (gold dashed)
  - Phase labels on Scenario B oil-rate panel

Usage:
    python plot_final.py
(Requires mock_scenario_A/B/C.csv from run_scenarios.py)
"""

import sys
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches
import numpy as np
import os

sys.stdout.reconfigure(encoding="utf-8")

try:
    from mock_simulator import LIMITS
except ImportError:
    LIMITS = dict(WHP_min=200, WHP_max=480, FLP_min=150, FLP_max=350,
                  BHP_min=2200, BHP_max=3000)

DEAD_BAND = 3.0   # bbl/hr — must match controller ControllerConfig.dead_band

SCENARIOS = {
    "A": dict(
        csv="mock_scenario_A.csv",
        out="mock_final_scenario_A_plot.png",
        title="Scenario A  |  Startup to Target  (130 bbl/hr)",
        subtitle="Choke opened from ~5% at startup; controller ramps to production target respecting all constraints.",
        target_change_step=None,
        phase_labels=None,
    ),
    "B": dict(
        csv="mock_scenario_B.csv",
        out="mock_final_scenario_B_plot.png",
        title="Scenario B  |  Target Step-Change  (100 -> 150 bbl/hr)",
        subtitle="Target increases mid-run at t=30 hr; controller re-tracks within ramp-rate and pressure constraints.",
        target_change_step=30,
        phase_labels=[("Phase 1: 100 bbl/hr", 5, 28), ("Phase 2: 150 bbl/hr", 35, 68)],
    ),
    "C": dict(
        csv="mock_scenario_C.csv",
        out="mock_final_scenario_C_plot.png",
        title="Scenario C  |  Infeasible Target  (300 bbl/hr requested)",
        subtitle="Target exceeds safe operating envelope. Controller refuses to violate pressure limits; "
                 "settles at max safe rate (~175 bbl/hr). Choke pinned at 100%.",
        target_change_step=None,
        phase_labels=None,
    ),
}

BG       = "#0f1117"
PANEL_BG = "#1a1d27"
GRID_COL = "#252836"
SPINE    = "#3a3d4d"

COLORS = dict(
    OilRate_bbl_hr="#34d399",
    WHP_psi="#60a5fa",
    FLP_psi="#f59e0b",
    BHP_psi="#f87171",
    Choke_pct="#a78bfa",
    target="rgba(255,255,255,0.75)",
    limit="#ef4444",
    change_line="#fbbf24",
    db_band="#34d399",
)

LIMIT_MAP = dict(
    WHP_psi=("WHP_min", "WHP_max"),
    FLP_psi=("FLP_min", "FLP_max"),
    BHP_psi=("BHP_min", "BHP_max"),
)

PANEL_CFG = [
    # (col, ylabel, color_key, show_target, show_db_band, show_limits)
    ("OilRate_bbl_hr", "Oil Rate (bbl/hr)",        "OilRate_bbl_hr", True,  True,  False),
    ("WHP_psi",        "Wellhead Pressure (psi)",   "WHP_psi",        False, False, True),
    ("FLP_psi",        "Flowline Pressure (psi)",   "FLP_psi",        False, False, True),
    ("BHP_psi",        "Bottom-Hole Pressure (psi)","BHP_psi",        False, False, True),
    ("Choke_pct",      "Choke Position (%)",        "Choke_pct",      False, False, False),
]


def style_ax(ax):
    ax.set_facecolor(PANEL_BG)
    ax.tick_params(colors="white", labelsize=8)
    for spine in ax.spines.values():
        spine.set_edgecolor(SPINE)
    ax.grid(axis="y", color=GRID_COL, linewidth=0.6, linestyle="--")
    ax.grid(axis="x", color=GRID_COL, linewidth=0.3, linestyle=":")


def plot_scenario(key: str, cfg: dict):
    df = pd.read_csv(cfg["csv"])
    t  = df["Time_hr"].values

    fig = plt.figure(figsize=(13, 14))
    fig.patch.set_facecolor(BG)
    gs = gridspec.GridSpec(5, 1, figure=fig, hspace=0.38,
                           top=0.92, bottom=0.05, left=0.09, right=0.97)

    axes = []
    for i, (col, ylabel, ck, show_tgt, show_db, show_lim) in enumerate(PANEL_CFG):
        ax = fig.add_subplot(gs[i])
        style_ax(ax)
        axes.append(ax)

        y = df[col].values
        color = COLORS[ck]

        # Dead-band shading on oil-rate panel
        if show_db and "Target_Q" in df.columns:
            tgt_arr = df["Target_Q"].values
            ax.fill_between(t, tgt_arr - DEAD_BAND, tgt_arr + DEAD_BAND,
                            color=COLORS["db_band"], alpha=0.10, label=f"Dead-band (+/-{DEAD_BAND} bbl/hr)",
                            zorder=1)

        # Target dashed line
        if show_tgt and "Target_Q" in df.columns:
            ax.plot(t, df["Target_Q"].values, color="white", linewidth=1.4,
                    linestyle="--", alpha=0.70, label="Target Q", zorder=2)

        # Main signal
        ax.plot(t, y, color=color, linewidth=1.8, label=ylabel, zorder=3)

        # Constraint limit lines on pressure panels
        if show_lim and col in LIMIT_MAP:
            lo_key, hi_key = LIMIT_MAP[col]
            lo, hi = LIMITS[lo_key], LIMITS[hi_key]
            ax.axhline(lo, color=COLORS["limit"], linewidth=1.0, linestyle=":",
                       alpha=0.85, zorder=4)
            ax.axhline(hi, color=COLORS["limit"], linewidth=1.0, linestyle=":",
                       alpha=0.85, zorder=4)
            ax.fill_between(t, lo, hi, color=COLORS["limit"], alpha=0.035, zorder=0)
            # Annotations
            xlim_r = t[-1]
            ax.annotate(f"Min {lo:.0f}", xy=(xlim_r, lo), xytext=(-4, 4),
                        textcoords="offset points", color=COLORS["limit"],
                        fontsize=6.5, ha="right")
            ax.annotate(f"Max {hi:.0f}", xy=(xlim_r, hi), xytext=(-4, -8),
                        textcoords="offset points", color=COLORS["limit"],
                        fontsize=6.5, ha="right")

        # Choke panel: y-limits and boundary markers
        if col == "Choke_pct":
            ax.set_ylim(-3, 108)
            ax.axhline(0,   color=COLORS["limit"], linewidth=0.7, linestyle=":", alpha=0.6)
            ax.axhline(100, color=COLORS["limit"], linewidth=0.7, linestyle=":", alpha=0.6)

        ax.set_ylabel(ylabel, color="white", fontsize=8.5, labelpad=4)

        # Legend on oil-rate panel only
        if show_tgt:
            ax.legend(fontsize=7, facecolor=PANEL_BG, labelcolor="white",
                      framealpha=0.75, loc="lower right", ncol=3)

        # X-axis label on last panel only
        if i == len(PANEL_CFG) - 1:
            ax.set_xlabel("Time (hours)", color="white", fontsize=9)
        else:
            ax.set_xticklabels([])

    # Target step-change vertical marker (Scenario B)
    if cfg["target_change_step"] is not None:
        tc_step = cfg["target_change_step"]
        change_mask = df["Step"] == tc_step
        if change_mask.any():
            t_change = df.loc[change_mask, "Time_hr"].iloc[0]
            for ax in axes:
                ax.axvline(t_change, color=COLORS["change_line"], linewidth=1.1,
                           linestyle="--", alpha=0.65, zorder=5)

    # Phase labels on oil-rate panel (Scenario B)
    if cfg["phase_labels"]:
        ax_q = axes[0]
        y_pos = ax_q.get_ylim()[1] * 0.88
        for label, t_lo, t_hi in cfg["phase_labels"]:
            t_mid = (t_lo + t_hi) / 2
            ax_q.text(t_mid, y_pos, label, color="white", fontsize=7.5,
                      ha="center", va="top", alpha=0.7,
                      bbox=dict(boxstyle="round,pad=0.2", facecolor=PANEL_BG,
                                edgecolor=SPINE, alpha=0.7))

    fig.suptitle(
        f"[MOCK DATA -- REHEARSAL ONLY]   {cfg['title']}",
        color="white", fontsize=11, fontweight="bold", y=0.975,
    )
    # Subtitle
    fig.text(0.5, 0.957, cfg["subtitle"], ha="center", color="#9ca3af", fontsize=8.5)

    plt.savefig(cfg["out"], dpi=160, bbox_inches="tight", facecolor=BG)
    plt.close()
    print(f"  Saved -> {cfg['out']}")


def main():
    print("=== Generating Final Scenario Plots [MOCK -- REHEARSAL ONLY] ===")
    for key, cfg in SCENARIOS.items():
        if not os.path.exists(cfg["csv"]):
            print(f"  [SKIP] {cfg['csv']} not found.")
            continue
        plot_scenario(key, cfg)
    print("Done.")


if __name__ == "__main__":
    main()
