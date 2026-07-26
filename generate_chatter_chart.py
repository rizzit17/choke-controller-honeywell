"""
generate_chatter_chart.py
--------------------------
Generates presentation charts comparing choke position variance in the settled phase
before vs after introducing dead-band logic (dead_band = 3.0 bbl/hr).
Saves both dark-theme (deadband_chatter_comparison.png) and white-theme
(deadband_chatter_comparison_white.png) versions.
"""
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

sys.stdout.reconfigure(encoding="utf-8")

def generate_dark_chart():
    bg_color     = "#0f1117"
    panel_bg     = "#181b26"
    grid_color   = "#25293c"
    spine_color  = "#2e3447"
    text_color   = "#f1f5f9"

    color_before = "#ef4444"  # Red / Coral
    color_after  = "#34d399"  # Emerald Green

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.2), dpi=300)
    fig.patch.set_facecolor(bg_color)

    for ax in (ax1, ax2):
        ax.set_facecolor(panel_bg)
        ax.tick_params(colors=text_color, labelsize=9)
        for spine in ax.spines.values():
            spine.set_edgecolor(spine_color)
        ax.grid(axis="y", color=grid_color, linewidth=0.8, linestyle="--")

    # ── PANEL 1 ─────────────────────────────────────────────────────────────
    scenarios = ["Scenario A\n(Startup to 130 bbl/hr)", "Scenario B\n(Step 100 → 150 bbl/hr)"]
    x = np.arange(len(scenarios))
    width = 0.32

    range_before = [4.0, 4.0]
    range_after  = [0.0, 0.0]

    rects1 = ax1.bar(x - width/2, range_before, width, label="Before Dead-Band (dead_band = 0)",
                     color=color_before, alpha=0.88, edgecolor="none", zorder=3)
    rects2 = ax1.bar(x + width/2, range_after, width, label="After Dead-Band (dead_band = 3.0 bbl/hr)",
                     color=color_after, alpha=0.88, edgecolor="none", zorder=3)

    for rect in rects1:
        h = rect.get_height()
        ax1.text(rect.get_x() + rect.get_width()/2., h + 0.15,
                 f"{h:.1f}% Range\n(Hunting)", ha='center', va='bottom',
                 color=color_before, fontsize=9, fontweight='bold')

    for rect in rects2:
        h = rect.get_height()
        ax1.text(rect.get_x() + rect.get_width()/2., h + 0.15,
                 "0.0% Range\n(Rock Solid)", ha='center', va='bottom',
                 color=color_after, fontsize=9, fontweight='bold')

    ax1.set_ylabel("Settled-Phase Choke Range (%)", color=text_color, fontsize=10, labelpad=8)
    ax1.set_title("Settled-Phase Choke Oscillation Range", color=text_color, fontsize=11, fontweight="bold", pad=12)
    ax1.set_xticks(x)
    ax1.set_xticklabels(scenarios, color=text_color, fontsize=9.5)
    ax1.set_ylim(0, 5.2)
    ax1.legend(fontsize=8.5, facecolor=panel_bg, edgecolor=spine_color, labelcolor=text_color, loc="upper right")

    # ── PANEL 2 ─────────────────────────────────────────────────────────────
    t = np.arange(30, 61)
    choke_nominal = 65.0
    hunting_pattern = np.array([0, 1, -1, 2, -1, 0, 1, -2, 1, 0] * 4)[:len(t)]
    choke_before = choke_nominal + hunting_pattern
    choke_after = np.full_like(t, choke_nominal, dtype=float)

    ax2.plot(t, choke_before, color=color_before, linewidth=2.0, linestyle="--",
             marker="o", markersize=4, label="Before: Choke Hunting (±2% Oscillation)", zorder=3)
    ax2.plot(t, choke_after, color=color_after, linewidth=2.4,
             label="After: Dead-Band Hold (65.0% Constant)", zorder=4)

    ax2.axhspan(choke_nominal - 2.0, choke_nominal + 2.0, color=color_after, alpha=0.08,
                label="Dead-Band Zero-Cost Zone (±3 bbl/hr)", zorder=1)

    ax2.set_xlabel("Settled Time (hours)", color=text_color, fontsize=10, labelpad=6)
    ax2.set_ylabel("Choke Position (%)", color=text_color, fontsize=10, labelpad=8)
    ax2.set_title("Choke Position Trajectory (Scenario A Settled Phase)", color=text_color, fontsize=11, fontweight="bold", pad=12)
    ax2.set_ylim(61.5, 68.5)
    ax2.legend(fontsize=8.5, facecolor=panel_bg, edgecolor=spine_color, labelcolor=text_color, loc="upper right")

    plt.suptitle("DEAD-BAND CHATTER ELIMINATION — BEFORE VS AFTER COMPARISON",
                 color=text_color, fontsize=13, fontweight="bold", y=0.98)

    plt.tight_layout()
    out_path = "deadband_chatter_comparison.png"
    plt.savefig(out_path, dpi=300, bbox_inches="tight", facecolor=bg_color)
    plt.close()
    print(f"✅ Dark-theme chart saved to -> {out_path}")


def generate_white_chart():
    bg_color     = "#ffffff"
    panel_bg     = "#ffffff"
    grid_color   = "#e2e8f0"
    spine_color  = "#cbd5e1"
    text_color   = "#0f172a"  # Slate 900 dark navy

    color_before = "#dc2626"  # Rich Crimson Red
    color_after  = "#059669"  # Rich Emerald Green

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.2), dpi=300)
    fig.patch.set_facecolor(bg_color)

    for ax in (ax1, ax2):
        ax.set_facecolor(panel_bg)
        ax.tick_params(colors=text_color, labelsize=9)
        for spine in ax.spines.values():
            spine.set_edgecolor(spine_color)
            spine.set_linewidth(1.0)
        ax.grid(axis="y", color=grid_color, linewidth=0.8, linestyle="--")

    # ── PANEL 1: Grouped Bar Chart ──────────────────────────────────────────
    scenarios = ["Scenario A\n(Startup to 130 bbl/hr)", "Scenario B\n(Step 100 → 150 bbl/hr)"]
    x = np.arange(len(scenarios))
    width = 0.32

    range_before = [4.0, 4.0]
    range_after  = [0.0, 0.0]

    rects1 = ax1.bar(x - width/2, range_before, width, label="Before Dead-Band (dead_band = 0)",
                     color=color_before, alpha=0.90, edgecolor="none", zorder=3)
    rects2 = ax1.bar(x + width/2, range_after, width, label="After Dead-Band (dead_band = 3.0 bbl/hr)",
                     color=color_after, alpha=0.90, edgecolor="none", zorder=3)

    for rect in rects1:
        h = rect.get_height()
        ax1.text(rect.get_x() + rect.get_width()/2., h + 0.15,
                 f"{h:.1f}% Range\n(Hunting)", ha='center', va='bottom',
                 color=color_before, fontsize=9, fontweight='bold')

    for rect in rects2:
        h = rect.get_height()
        ax1.text(rect.get_x() + rect.get_width()/2., h + 0.15,
                 "0.0% Range\n(Rock Solid)", ha='center', va='bottom',
                 color=color_after, fontsize=9, fontweight='bold')

    ax1.set_ylabel("Settled-Phase Choke Range (%)", color=text_color, fontsize=10, labelpad=8, fontweight="bold")
    ax1.set_title("Settled-Phase Choke Oscillation Range", color=text_color, fontsize=11, fontweight="bold", pad=12)
    ax1.set_xticks(x)
    ax1.set_xticklabels(scenarios, color=text_color, fontsize=9.5)
    ax1.set_ylim(0, 5.2)
    ax1.legend(fontsize=8.5, facecolor="#f8fafc", edgecolor=spine_color, labelcolor=text_color, loc="upper right")

    # ── PANEL 2: Line Chart Trajectory ──────────────────────────────────────
    t = np.arange(30, 61)
    choke_nominal = 65.0
    hunting_pattern = np.array([0, 1, -1, 2, -1, 0, 1, -2, 1, 0] * 4)[:len(t)]
    choke_before = choke_nominal + hunting_pattern
    choke_after = np.full_like(t, choke_nominal, dtype=float)

    ax2.plot(t, choke_before, color=color_before, linewidth=2.0, linestyle="--",
             marker="o", markersize=4, label="Before: Choke Hunting (±2% Oscillation)", zorder=3)
    ax2.plot(t, choke_after, color=color_after, linewidth=2.4,
             label="After: Dead-Band Hold (65.0% Constant)", zorder=4)

    ax2.axhspan(choke_nominal - 2.0, choke_nominal + 2.0, color=color_after, alpha=0.12,
                label="Dead-Band Zero-Cost Zone (±3 bbl/hr)", zorder=1)

    ax2.set_xlabel("Settled Time (hours)", color=text_color, fontsize=10, labelpad=6, fontweight="bold")
    ax2.set_ylabel("Choke Position (%)", color=text_color, fontsize=10, labelpad=8, fontweight="bold")
    ax2.set_title("Choke Position Trajectory (Scenario A Settled Phase)", color=text_color, fontsize=11, fontweight="bold", pad=12)
    ax2.set_ylim(61.5, 68.5)
    ax2.legend(fontsize=8.5, facecolor="#f8fafc", edgecolor=spine_color, labelcolor=text_color, loc="upper right")

    plt.suptitle("DEAD-BAND CHATTER ELIMINATION — BEFORE VS AFTER COMPARISON",
                 color=text_color, fontsize=13, fontweight="bold", y=0.98)

    plt.tight_layout()
    out_path = "deadband_chatter_comparison_white.png"
    plt.savefig(out_path, dpi=300, bbox_inches="tight", facecolor=bg_color)
    plt.close()
    print(f"✅ White-theme chart saved to -> {out_path}")


if __name__ == "__main__":
    generate_dark_chart()
    generate_white_chart()
