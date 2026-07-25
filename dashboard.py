"""
dashboard.py — Streamlit dashboard for scenario visualization
-------------------------------------------------------------
Run with:
    streamlit run dashboard.py

Features:
  - Scenario selector (A / B / C)
  - 6 required trend plots per scenario (interactive, via plotly)
  - Decision rationale log table (searchable)
  - Key metrics summary panel
  - Constraint violation indicator (should always show zero violations)

[MOCK DATA — REHEARSAL ONLY until real simulator is swapped in]
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os

# ── Page config ─────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Autonomous Choke Controller — Dashboard",
    page_icon="🛢️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Constraint limits ────────────────────────────────────────────────────────────
try:
    from mock_simulator import LIMITS
except ImportError:
    LIMITS = {
        "WHP_min": 200.0, "WHP_max": 480.0,
        "FLP_min": 150.0, "FLP_max": 350.0,
        "BHP_min": 2200.0,"BHP_max": 3000.0,
    }

# ── Data files ───────────────────────────────────────────────────────────────────
SCENARIOS = {
    "A — Startup to Target": {
        "trend": "mock_scenario_A.csv",
        "log":   "mock_scenario_A_rationale.csv",
        "desc":  "Well starts near shut-in (choke ≈ 5%). Controller autonomously ramps "
                 "choke to achieve the production target of 130 bbl/hr while respecting "
                 "all pressure constraints and the ±5%/hr choke ramp-rate limit.",
        "target_change_step": None,
    },
    "B — Target Step-Change": {
        "trend": "mock_scenario_B.csv",
        "log":   "mock_scenario_B_rationale.csv",
        "desc":  "Controller tracks 100 bbl/hr for 30 hours, then the target changes to "
                 "150 bbl/hr. Controller re-tracks the new target without violating constraints.",
        "target_change_step": 30,
    },
    "C — Infeasible Target": {
        "trend": "mock_scenario_C.csv",
        "log":   "mock_scenario_C_rationale.csv",
        "desc":  "Requested target of 300 bbl/hr exceeds the safe operating envelope. "
                 "Controller correctly refuses to violate BHP/WHP/FLP limits and instead "
                 "settles at the maximum safely achievable production rate.",
        "target_change_step": None,
    },
}

COLORS = {
    "OilRate_bbl_hr": "#34d399",
    "WHP_psi":        "#60a5fa",
    "FLP_psi":        "#f59e0b",
    "BHP_psi":        "#f87171",
    "Choke_pct":      "#a78bfa",
    "Target_Q":       "rgba(255,255,255,0.6)",
}

BG = "#0f1117"
PANEL_BG = "#1a1d27"


# ── Helpers ──────────────────────────────────────────────────────────────────────

def check_violations(df: pd.DataFrame) -> dict:
    v = {}
    v["WHP"] = int(((df["WHP_psi"] < LIMITS["WHP_min"]) | (df["WHP_psi"] > LIMITS["WHP_max"])).sum())
    v["FLP"] = int(((df["FLP_psi"] < LIMITS["FLP_min"]) | (df["FLP_psi"] > LIMITS["FLP_max"])).sum())
    v["BHP"] = int(((df["BHP_psi"] < LIMITS["BHP_min"]) | (df["BHP_psi"] > LIMITS["BHP_max"])).sum())
    v["total"] = v["WHP"] + v["FLP"] + v["BHP"]
    return v


def make_trend_figure(df: pd.DataFrame, target_change_step=None) -> go.Figure:
    rows = 5
    subplot_titles = [
        "Oil Rate vs Target (bbl/hr)",
        "Wellhead Pressure — WHP (psi)",
        "Flowline Pressure — FLP (psi)",
        "Bottom Hole Pressure — BHP (psi)",
        "Choke Position (%)",
    ]
    fig = make_subplots(
        rows=rows, cols=1,
        subplot_titles=subplot_titles,
        shared_xaxes=True,
        vertical_spacing=0.06,
    )
    t = df["Time_hr"]

    # Panel 1: Oil Rate + Target
    fig.add_trace(go.Scatter(x=t, y=df["Target_Q"], name="Target Q",
                             line=dict(color=COLORS["Target_Q"], dash="dash", width=1.5),
                             showlegend=True), row=1, col=1)
    fig.add_trace(go.Scatter(x=t, y=df["OilRate_bbl_hr"], name="Actual Q",
                             line=dict(color=COLORS["OilRate_bbl_hr"], width=2),
                             showlegend=True), row=1, col=1)

    # Panels 2-4: Pressure + limits
    for panel_i, (col, lim_lo, lim_hi) in enumerate([
        ("WHP_psi", "WHP_min", "WHP_max"),
        ("FLP_psi", "FLP_min", "FLP_max"),
        ("BHP_psi", "BHP_min", "BHP_max"),
    ], start=2):
        fig.add_trace(go.Scatter(x=t, y=df[col], name=col.replace("_psi",""),
                                 line=dict(color=COLORS[col], width=2),
                                 showlegend=True), row=panel_i, col=1)
        fig.add_hline(y=LIMITS[lim_lo], line_dash="dot",
                      line_color="rgba(239,68,68,0.7)", line_width=1,
                      annotation_text=f"Min {LIMITS[lim_lo]:.0f}",
                      annotation_font_color="rgba(239,68,68,0.8)",
                      row=panel_i, col=1)
        fig.add_hline(y=LIMITS[lim_hi], line_dash="dot",
                      line_color="rgba(239,68,68,0.7)", line_width=1,
                      annotation_text=f"Max {LIMITS[lim_hi]:.0f}",
                      annotation_font_color="rgba(239,68,68,0.8)",
                      row=panel_i, col=1)

    # Panel 5: Choke
    fig.add_trace(go.Scatter(x=t, y=df["Choke_pct"], name="Choke %",
                             line=dict(color=COLORS["Choke_pct"], width=2),
                             fill="tozeroy",
                             fillcolor="rgba(167,139,250,0.08)",
                             showlegend=True), row=5, col=1)

    # Target change marker for Scenario B
    if target_change_step is not None:
        try:
            t_change = df.loc[df["Step"] == target_change_step, "Time_hr"].values[0]
            for r in range(1, 6):
                fig.add_vline(x=t_change, line_dash="dash",
                              line_color="rgba(251,191,36,0.5)", line_width=1.2, row=r, col=1)
        except (IndexError, KeyError):
            pass

    fig.update_layout(
        height=720,
        paper_bgcolor=BG,
        plot_bgcolor=PANEL_BG,
        font=dict(color="white", size=11),
        legend=dict(bgcolor="rgba(26,29,39,0.8)", bordercolor="#3a3d4d",
                    borderwidth=1, font=dict(size=10)),
        margin=dict(l=10, r=10, t=30, b=10),
        xaxis5=dict(title="Time (hours)"),
    )
    for i in range(1, 6):
        fig.update_xaxes(gridcolor=GRID_COL, gridwidth=0.5, row=i, col=1)
        fig.update_yaxes(gridcolor=GRID_COL, gridwidth=0.5, row=i, col=1)

    return fig

GRID_COL = "#2a2d3a"


# ── Sidebar ──────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🛢️ Choke Controller")
    st.markdown("**Autonomous Production Choke Controller**")
    st.caption("Predictive, constraint-aware control for a naturally flowing oil well")
    st.divider()

    scenario_label = st.radio(
        "Select Scenario",
        list(SCENARIOS.keys()),
        index=0,
    )
    st.divider()

    st.markdown("**Constraint Limits**")
    st.markdown(f"""
| Variable | Min | Max |
|---|---|---|
| WHP | {LIMITS['WHP_min']:.0f} psi | {LIMITS['WHP_max']:.0f} psi |
| FLP | {LIMITS['FLP_min']:.0f} psi | {LIMITS['FLP_max']:.0f} psi |
| BHP | {LIMITS['BHP_min']:.0f} psi | {LIMITS['BHP_max']:.0f} psi |
| Choke | 0% | 100% |
| Ramp | — | ±5%/hr |
""")
    st.divider()
    st.caption("⚠️ MOCK DATA — REHEARSAL ONLY\nSwap simulator import before final run.")


# ── Main ─────────────────────────────────────────────────────────────────────────

cfg  = SCENARIOS[scenario_label]

st.markdown(
    f"<h2 style='color:white;margin-bottom:0'>{scenario_label}</h2>",
    unsafe_allow_html=True,
)
st.caption(cfg["desc"])

# Check files exist
if not os.path.exists(cfg["trend"]):
    st.error(
        f"Data file `{cfg['trend']}` not found. "
        "Run `python run_scenarios.py` first."
    )
    st.stop()

df  = pd.read_csv(cfg["trend"])
log = pd.read_csv(cfg["log"]) if os.path.exists(cfg["log"]) else pd.DataFrame()

# ── Metrics strip ────────────────────────────────────────────────────────────────

viols = check_violations(df)
final_Q   = df["OilRate_bbl_hr"].iloc[-10:].mean()
final_tgt = df["Target_Q"].iloc[-1]
settle_err = abs(final_Q - final_tgt)
max_ramp   = df["Choke_pct"].diff().abs().max()

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric("Constraint Violations", viols["total"],
              delta="✅ Safe" if viols["total"] == 0 else f"⚠️ {viols['total']} violations",
              delta_color="normal" if viols["total"] == 0 else "inverse")
with col2:
    st.metric("Settled Oil Rate", f"{final_Q:.1f} bbl/hr")
with col3:
    st.metric("Target", f"{final_tgt:.0f} bbl/hr")
with col4:
    st.metric("Settling Error", f"{settle_err:.1f} bbl/hr")
with col5:
    st.metric("Max Choke Ramp", f"{max_ramp:.1f}%/hr",
              delta="✅ ≤5%" if max_ramp <= 5.0 else f"⚠️ Exceeds 5%",
              delta_color="normal" if max_ramp <= 5.0 else "inverse")

st.divider()

# ── Trend plot ───────────────────────────────────────────────────────────────────

st.markdown("### Process Trends")
fig = make_trend_figure(df, cfg["target_change_step"])
st.plotly_chart(fig, use_container_width=True)

# ── Decision rationale log ────────────────────────────────────────────────────────

if not log.empty:
    st.markdown("### Controller Decision Log")

    disp_cols = ["step", "time_hr", "choke_prev", "choke_chosen", "delta_u",
                 "target_Q", "predicted_Q", "measured_Q",
                 "n_candidates_evaluated", "n_candidates_rejected_hard", "reason"]
    disp_cols = [c for c in disp_cols if c in log.columns]

    search = st.text_input("🔍 Filter rationale log", placeholder="e.g. 'FALLBACK' or 'BHP'")
    log_display = log[disp_cols]
    if search:
        mask = log_display.apply(lambda row: row.astype(str).str.contains(search, case=False).any(), axis=1)
        log_display = log_display[mask]

    st.dataframe(
        log_display,
        use_container_width=True,
        height=320,
    )
    st.caption(f"{len(log_display)} rows shown")

st.divider()
st.caption(
    "Built for Honeywell Hackathon — Autonomous Production Choke Controller  |  "
    "[MOCK DATA — REHEARSAL ONLY]  |  "
    "Swap mock_simulator import → real simulator before final demo."
)
