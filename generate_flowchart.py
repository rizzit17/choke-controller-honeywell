"""
generate_flowchart.py
---------------------
Generates a high-DPI 5-step methodology flowchart matching the dashboard dark theme.
Saves as methodology_flowchart.png for use in presentation slides and documentation.
"""
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.path import Path

sys.stdout.reconfigure(encoding="utf-8")

BG_COLOR    = "#0f1117"
CARD_BG     = "#181b26"
CARD_BORDER = "#2e3447"
TEXT_COLOR  = "#f1f5f9"
SUB_COLOR   = "#94a3b8"

STEPS = [
    {
        "num": "01",
        "title": "Open-Loop Step Test",
        "desc": "Execute 280-hr step test across 14 choke positions (5%-95%)\nExtract dynamic response & steady-state data",
        "color": "#38bdf8",
        "tag": "DATA ACQUISITION"
    },
    {
        "num": "02",
        "title": "Physics Model Fit",
        "desc": "Calibrate Cv(u) polynomial on 14 empirical points\nTrain ARX Ridge dynamic models for Q, WHP, FLP, BHP",
        "color": "#34d399",
        "tag": "SYSTEM IDENTIFICATION"
    },
    {
        "num": "03",
        "title": "Candidate Generation",
        "desc": "Enumerate candidate moves: u ∈ [u_k − 5%, u_k + 5%]\nEnforce choke bounds 0% ≤ u ≤ 100% at Ts = 1.0 hr",
        "color": "#f59e0b",
        "tag": "MPC ENUMERATION"
    },
    {
        "num": "04",
        "title": "Dual-Layer Safety Filter",
        "desc": "Hard-reject candidates violating WHP, FLP, BHP limits\nApply soft barrier penalty to steer clear of limits",
        "color": "#ef4444",
        "tag": "CONSTRAINT SAFETY"
    },
    {
        "num": "05",
        "title": "Dead-Band Selection",
        "desc": "Minimize cost function with dead-band edb = 3.0 bbl/hr\nSuppress chatter & apply optimal choke move u_{k+1}",
        "color": "#a78bfa",
        "tag": "OPTIMAL EXECUTION"
    }
]

def build_flowchart():
    fig = plt.figure(figsize=(16, 4.5), dpi=300)
    fig.patch.set_facecolor(BG_COLOR)
    ax = fig.add_subplot(111)
    ax.set_facecolor(BG_COLOR)
    ax.axis("off")

    n_steps = len(STEPS)
    box_width  = 2.5
    box_height = 2.4
    gap        = 0.55
    start_x    = 0.4
    start_y    = 0.9

    for i, step in enumerate(STEPS):
        x = start_x + i * (box_width + gap)
        y = start_y

        # Card Box
        rect = mpatches.FancyBboxPatch(
            (x, y), box_width, box_height,
            boxstyle="round,pad=0.15,rounding_size=0.12",
            facecolor=CARD_BG,
            edgecolor=step["color"],
            linewidth=1.8,
            zorder=2
        )
        ax.add_patch(rect)

        # Header Tag pill
        tag_rect = mpatches.FancyBboxPatch(
            (x + 0.15, y + box_height - 0.38), box_width - 0.3, 0.28,
            boxstyle="round,pad=0.05,rounding_size=0.06",
            facecolor=step["color"],
            edgecolor="none",
            alpha=0.20,
            zorder=3
        )
        ax.add_patch(tag_rect)

        # Step Tag Text
        ax.text(
            x + box_width / 2, y + box_height - 0.24,
            f"STEP {step['num']} • {step['tag']}",
            color=step["color"],
            fontsize=7.5,
            fontweight="bold",
            ha="center",
            va="center",
            zorder=4
        )

        # Title
        ax.text(
            x + box_width / 2, y + box_height - 0.75,
            step["title"],
            color=TEXT_COLOR,
            fontsize=10.5,
            fontweight="bold",
            ha="center",
            va="center",
            zorder=4
        )

        # Divider line
        ax.plot(
            [x + 0.2, x + box_width - 0.2],
            [y + box_height - 1.05, y + box_height - 1.05],
            color=CARD_BORDER,
            linewidth=0.8,
            zorder=4
        )

        # Description
        ax.text(
            x + box_width / 2, y + (box_height - 1.05) / 2,
            step["desc"],
            color=SUB_COLOR,
            fontsize=8.0,
            linespacing=1.45,
            ha="center",
            va="center",
            zorder=4
        )

        # Connecting Arrow (if not last step)
        if i < n_steps - 1:
            arrow_start_x = x + box_width + 0.05
            arrow_end_x   = x + box_width + gap - 0.05
            arrow_y       = y + box_height / 2

            ax.annotate(
                "",
                xy=(arrow_end_x, arrow_y),
                xytext=(arrow_start_x, arrow_y),
                arrowprops=dict(
                    arrowstyle="-|>",
                    color=step["color"],
                    linewidth=2.2,
                    mutation_scale=14,
                    shrinkA=0,
                    shrinkB=0
                ),
                zorder=5
            )

    # Main Title & Subtitle at top
    plt.suptitle(
        "AUTONOMOUS CHOKE CONTROLLER - 5-STEP CONTROL METHODOLOGY",
        color=TEXT_COLOR,
        fontsize=13,
        fontweight="bold",
        y=0.97
    )

    ax.text(
        start_x + (n_steps * (box_width + gap) - gap) / 2,
        start_y + box_height + 0.35,
        "Physics-Grounded Model Identification → Brute-Force Predictive Optimization → Dual-Layer Safety Filter",
        color=SUB_COLOR,
        fontsize=9.0,
        ha="center",
        va="center"
    )

    ax.set_xlim(0, start_x * 2 + n_steps * box_width + (n_steps - 1) * gap)
    ax.set_ylim(0.4, start_y + box_height + 0.6)

    plt.tight_layout()
    out_path = "methodology_flowchart.png"
    plt.savefig(out_path, dpi=300, bbox_inches="tight", facecolor=BG_COLOR)
    plt.close()
    print(f"✅ Flowchart successfully generated and saved to -> {out_path}")

if __name__ == "__main__":
    build_flowchart()
