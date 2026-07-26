"""
run_scenarios.py -- REHEARSAL ONLY (runs against mock simulator)
---------------------------------------------------------------
Executes all three required demonstration scenarios in closed-loop:
  A) Startup to target
  B) Target step-change mid-run
  C) Infeasible target -- controller must refuse and settle at max safe rate

Each scenario saves:
  mock_scenario_A.csv / mock_scenario_B.csv / mock_scenario_C.csv
  mock_scenario_A_rationale.csv / ... (decision log)

To use with REAL simulator: change the single import line for WellSimulator.
model.py must be re-run on real step-test data first (generates mock_step_test_data.csv).

Usage:
    python run_scenarios.py
"""

import sys
import numpy as np
import pandas as pd
import os

# ── ONE-LINE SWAP when real simulator arrives ──────────────────────────────────
from mock_simulator import WellSimulator
# from real_simulator import WellSimulator
# ──────────────────────────────────────────────────────────────────────────────

from model import load_model
from controller import ChokeController, ControllerConfig

STEP_TEST_CSV = "mock_step_test_data.csv"
DT = 1.0   # hours per control interval


def closed_loop_run(
    sim: WellSimulator,
    controller: ChokeController,
    target_schedule: list,   # [(start_step, target_Q), ...]
    n_steps: int,
    initial_choke: float = 5.0,
    label: str = "",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Run one closed-loop scenario.

    Parameters
    ----------
    sim : WellSimulator (already reset to initial conditions)
    controller : ChokeController (log reset internally)
    target_schedule : list of (step, target_Q) -- target changes at given step numbers
    n_steps : total control steps to run
    initial_choke : starting choke position (%)
    label : scenario label for print output

    Returns
    -------
    trend_df : per-step trend DataFrame (the 6 required plot variables)
    log_df   : per-step decision rationale DataFrame
    """
    controller.reset_log()

    # Build target array
    targets = np.full(n_steps, target_schedule[0][1])
    for step_idx, tgt in target_schedule[1:]:
        targets[step_idx:] = tgt

    choke = initial_choke
    rows = []

    # Take one burn-in step to initialize measurements
    Q, WHP, FLP, BHP = sim.step(choke)

    for k in range(n_steps):
        t = sim.time
        tgt_Q = targets[k]

        # Controller decision
        next_choke = controller.step(
            current_choke=choke,
            measured_Q=Q,
            measured_WHP=WHP,
            measured_FLP=FLP,
            measured_BHP=BHP,
            target_Q=tgt_Q,
            time_hr=t,
        )

        # Apply to simulator
        Q_new, WHP_new, FLP_new, BHP_new = sim.step(next_choke)

        rows.append({
            "Step":          k + 1,
            "Time_hr":       t,
            "Target_Q":      tgt_Q,
            "Choke_pct":     next_choke,
            "OilRate_bbl_hr": Q_new,
            "WHP_psi":       WHP_new,
            "FLP_psi":       FLP_new,
            "BHP_psi":       BHP_new,
        })

        choke = next_choke
        Q, WHP, FLP, BHP = Q_new, WHP_new, FLP_new, BHP_new

        if label and (k % 10 == 0 or k == n_steps - 1):
            print(f"  [{label}] t={t:.0f}hr  choke={choke:.1f}%  "
                  f"Q={Q:.1f}  tgt={tgt_Q}  WHP={WHP:.1f}  FLP={FLP:.1f}  BHP={BHP:.1f}")

    trend_df = pd.DataFrame(rows)
    log_df   = pd.DataFrame(controller.get_log())
    return trend_df, log_df


def run_all_scenarios():
    if not os.path.exists(STEP_TEST_CSV):
        print(f"{STEP_TEST_CSV} not found. Running step_test_harness.py and model.py automatically...")
        import subprocess
        subprocess.run(["python", "step_test_harness.py"], check=True)
        subprocess.run(["python", "model.py"], check=True)

    print("Loading process model from step-test data...")
    process_model = load_model(STEP_TEST_CSV)
    cfg = ControllerConfig(
        w_track=1.0,
        w_ramp=0.3,
        barrier_k=500.0,
        barrier_eps=2.0,
        hard_margin=3.0,
        delta_u_step=1.0,
        max_ramp_rate=5.0,
    )
    controller = ChokeController(process_model, cfg)

    # ── Scenario A: Startup -> Target ─────────────────────────────────────────
    print("\n=== Scenario A: Startup -> Target [MOCK -- REHEARSAL ONLY] ===")
    # Start at ~5% (near shut-in), ramp up to target = 130 bbl/hr
    sim_A = WellSimulator(seed=10)
    sim_A.reset(initial_choke=5.0)

    trend_A, log_A = closed_loop_run(
        sim=sim_A,
        controller=controller,
        target_schedule=[(0, 130.0)],
        n_steps=60,
        initial_choke=5.0,
        label="A",
    )
    trend_A.to_csv("mock_scenario_A.csv", index=False)
    log_A.to_csv("mock_scenario_A_rationale.csv", index=False)
    print(f"  -> mock_scenario_A.csv  ({len(trend_A)} steps)")

    # ── Scenario B: Target Step-Change ───────────────────────────────────────
    print("\n=== Scenario B: Target Step-Change [MOCK -- REHEARSAL ONLY] ===")
    # Run at 100 bbl/hr for 30 steps, then jump to 150 bbl/hr
    sim_B = WellSimulator(seed=20)
    sim_B.reset(initial_choke=5.0)

    trend_B, log_B = closed_loop_run(
        sim=sim_B,
        controller=controller,
        target_schedule=[(0, 100.0), (30, 150.0)],
        n_steps=70,
        initial_choke=5.0,
        label="B",
    )
    trend_B.to_csv("mock_scenario_B.csv", index=False)
    log_B.to_csv("mock_scenario_B_rationale.csv", index=False)
    print(f"  -> mock_scenario_B.csv  ({len(trend_B)} steps)")

    # ── Scenario C: Infeasible Target ────────────────────────────────────────
    print("\n=== Scenario C: Infeasible Target [MOCK -- REHEARSAL ONLY] ===")
    # Request 300 bbl/hr -- well above the mock's physical maximum (~182 bbl/hr at 100%)
    # At high choke, BHP drops below BHP_min (2200 psi), so controller must cap itself.
    # The mock is deliberately designed so ~155-160 bbl/hr is the highest safe rate.
    sim_C = WellSimulator(seed=30)
    sim_C.reset(initial_choke=5.0)

    trend_C, log_C = closed_loop_run(
        sim=sim_C,
        controller=controller,
        target_schedule=[(0, 300.0)],
        n_steps=60,
        initial_choke=5.0,
        label="C",
    )
    trend_C.to_csv("mock_scenario_C.csv", index=False)
    log_C.to_csv("mock_scenario_C_rationale.csv", index=False)
    print(f"  -> mock_scenario_C.csv  ({len(trend_C)} steps)")

    print("\n=== All scenarios complete. ===")
    print("Files saved (prefixed 'mock_' -- REHEARSAL DATA, not final deliverables).")
    return trend_A, trend_B, trend_C, log_A, log_B, log_C


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    run_all_scenarios()
