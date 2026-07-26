"""
stress_test_all_variants.py
----------------------------
Runs all 3 scenarios × 3 simulator variants = 9 closed-loop runs.
Checks 3 constraint criteria per scenario × 3 variants = 27 checks.
Prints a full PASS/FAIL table and flags any violations before touching controller.

Usage:
    python stress_test_all_variants.py
"""
import sys
import numpy as np
import pandas as pd
sys.stdout.reconfigure(encoding="utf-8")

from mock_simulator import WellSimulator, LIMITS
from model import load_model
from controller import ChokeController, ControllerConfig
from run_scenarios import closed_loop_run

STEP_TEST_CSV = "mock_step_test_data.csv"
VARIANTS      = ["baseline", "pessimistic", "optimistic"]
SCENARIOS     = ["A", "B", "C"]

# Controller config — unchanged from baseline dead-band run
def make_controller():
    process_model = load_model(STEP_TEST_CSV)
    cfg = ControllerConfig(
        w_track=1.0,
        w_ramp=0.3,
        barrier_k=500.0,
        barrier_eps=2.0,
        hard_margin=0.0,
        delta_u_step=1.0,
        max_ramp_rate=5.0,
    )
    return ChokeController(process_model, cfg)


def run_scenario(variant: str, scenario: str, controller):
    """Run one scenario with one variant, return trend DataFrame."""
    seeds = {"A": 10, "B": 20, "C": 30}
    sim = WellSimulator(seed=seeds[scenario], variant=variant)
    sim.reset(initial_choke=5.0)

    if scenario == "A":
        trend, _ = closed_loop_run(
            sim=sim, controller=controller,
            target_schedule=[(0, 130.0)],
            n_steps=60, initial_choke=5.0, label="",
        )
    elif scenario == "B":
        trend, _ = closed_loop_run(
            sim=sim, controller=controller,
            target_schedule=[(0, 100.0), (30, 150.0)],
            n_steps=70, initial_choke=5.0, label="",
        )
    else:  # C
        trend, _ = closed_loop_run(
            sim=sim, controller=controller,
            target_schedule=[(0, 300.0)],
            n_steps=60, initial_choke=5.0, label="",
        )
    return trend


def check_run(df: pd.DataFrame, scenario: str, variant: str):
    """
    Run all checks for one scenario/variant combo.
    Returns list of (check_name, passed, detail) tuples.
    """
    results = []
    choke = df["Choke_pct"].values

    # ── 1. No WHP violation ──────────────────────────────────────────────────
    viol = int(((df.WHP_psi < LIMITS["WHP_min"]) | (df.WHP_psi > LIMITS["WHP_max"])).sum())
    ok = (viol == 0)
    headroom_lo = float(df.WHP_psi.min() - LIMITS["WHP_min"])
    headroom_hi = float(LIMITS["WHP_max"] - df.WHP_psi.max())
    results.append((f"[{variant}/{scenario}] no_WHP_violation", ok,
                    f"{viol} steps violated | min_headroom_lo={headroom_lo:.1f} min_headroom_hi={headroom_hi:.1f} psi"))

    # ── 2. No FLP violation ──────────────────────────────────────────────────
    viol = int(((df.FLP_psi < LIMITS["FLP_min"]) | (df.FLP_psi > LIMITS["FLP_max"])).sum())
    ok = (viol == 0)
    headroom_lo = float(df.FLP_psi.min() - LIMITS["FLP_min"])
    headroom_hi = float(LIMITS["FLP_max"] - df.FLP_psi.max())
    results.append((f"[{variant}/{scenario}] no_FLP_violation", ok,
                    f"{viol} steps violated | min_headroom_lo={headroom_lo:.1f} min_headroom_hi={headroom_hi:.1f} psi"))

    # ── 3. No BHP violation ──────────────────────────────────────────────────
    viol = int(((df.BHP_psi < LIMITS["BHP_min"]) | (df.BHP_psi > LIMITS["BHP_max"])).sum())
    ok = (viol == 0)
    headroom_lo = float(df.BHP_psi.min() - LIMITS["BHP_min"])
    results.append((f"[{variant}/{scenario}] no_BHP_violation", ok,
                    f"{viol} steps violated | BHP_min_headroom={headroom_lo:.1f} psi"))

    # ── 4. Choke bounds [0, 100] ─────────────────────────────────────────────
    viol = int(((choke < 0.0) | (choke > 100.0 + 1e-9)).sum())
    ok = (viol == 0)
    results.append((f"[{variant}/{scenario}] choke_bounds_0_100", ok,
                    f"{viol} steps out of bounds"))

    # ── 5. Ramp rate ≤ 5%/hr ────────────────────────────────────────────────
    ramp_max = float(np.abs(np.diff(choke)).max()) if len(choke) > 1 else 0.0
    ok = ramp_max <= 5.0 + 1e-9
    results.append((f"[{variant}/{scenario}] ramp_rate_max5pct", ok,
                    f"max={ramp_max:.2f}%/hr"))

    # ── 6. Settling / scenario-specific ─────────────────────────────────────
    if scenario == "A":
        final_q = float(df["OilRate_bbl_hr"].iloc[-10:].mean())
        target  = float(df["Target_Q"].iloc[-1])
        pct_err = abs(final_q - target) / target * 100
        ok = pct_err < 5.0
        results.append((f"[{variant}/{scenario}] target_within_5pct", ok,
                        f"final_Q={final_q:.1f}, tgt={target:.0f}, err={pct_err:.1f}%"))

    elif scenario == "B":
        p1_q = float(df.loc[df["Target_Q"] == 100.0, "OilRate_bbl_hr"].iloc[-5:].mean())
        p2_q = float(df.loc[df["Target_Q"] == 150.0, "OilRate_bbl_hr"].iloc[-5:].mean())
        for phase, actual_q, tgt in [("Phase1", p1_q, 100.0), ("Phase2", p2_q, 150.0)]:
            pct_err = abs(actual_q - tgt) / tgt * 100
            ok = pct_err < 5.0
            results.append((f"[{variant}/{scenario}] {phase}_within_5pct", ok,
                            f"Q={actual_q:.1f}, tgt={tgt:.0f}, err={pct_err:.1f}%"))

    else:  # C — infeasible
        final_q = float(df["OilRate_bbl_hr"].iloc[-10:].mean())
        target  = float(df["Target_Q"].iloc[-1])
        ok = final_q < target * 0.75
        results.append((f"[{variant}/{scenario}] correctly_below_infeasible_tgt", ok,
                        f"settled={final_q:.1f} < 0.75×{target:.0f}={target*0.75:.0f}"))

    return results


# ── Summary table helper ──────────────────────────────────────────────────────

def summary_row(df: pd.DataFrame, scenario: str, variant: str) -> dict:
    choke = df["Choke_pct"].values
    final_choke = float(choke[-1])
    final_q = float(df["OilRate_bbl_hr"].iloc[-10:].mean())
    target  = float(df["Target_Q"].iloc[-1])
    pct_err = abs(final_q - target) / target * 100

    # Tightest constraint margins
    whp_lo_hd = float(df.WHP_psi.min() - LIMITS["WHP_min"])
    flp_lo_hd = float(df.FLP_psi.min() - LIMITS["FLP_min"])
    bhp_lo_hd = float(df.BHP_psi.min() - LIMITS["BHP_min"])
    margins = {"WHP": whp_lo_hd, "FLP": flp_lo_hd, "BHP": bhp_lo_hd}
    tightest_var  = min(margins, key=margins.get)
    tightest_val  = margins[tightest_var]

    # Chattering check: non-zero choke moves in last 20 settled steps
    settled_choke = choke[-20:]
    chatter_moves = int(np.sum(np.abs(np.diff(settled_choke)) > 0.01))

    return {
        "Scenario": scenario, "Variant": variant,
        "Final_Q": round(final_q, 1), "Target_Q": target,
        "Pct_Err": round(pct_err, 1),
        "Final_Choke": round(final_choke, 1),
        "Tightest_Var": tightest_var,
        "Tightest_Hdroom_psi": round(tightest_val, 1),
        "Chatter_moves_last20": chatter_moves,
    }


# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 72)
    print("STRESS-TEST: 3 Scenarios × 3 Variants = 9 Runs  (27 checks)")
    print("=" * 72)

    print("\nLoading process model (baseline step-test data)...")
    controller = make_controller()

    all_checks  = []
    summary_rows = []
    violations   = []

    for variant in VARIANTS:
        for scenario in SCENARIOS:
            print(f"  Running {variant}/{scenario}...", end=" ", flush=True)
            df = run_scenario(variant, scenario, controller)
            checks = check_run(df, scenario, variant)
            all_checks.extend(checks)
            summary_rows.append(summary_row(df, scenario, variant))
            failed_here = [(n, d) for n, p, d in checks if not p]
            if failed_here:
                violations.extend(failed_here)
                print("VIOLATION DETECTED")
            else:
                print("OK")

    # ── 27-check PASS/FAIL table ──────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("27-CHECK CONSTRAINT SUITE  (PASS / FAIL)")
    print("=" * 72)
    for name, passed, detail in all_checks:
        status = "PASS" if passed else "FAIL ⚠"
        print(f"  [{status}]  {name}")
        if not passed or "err=" in detail:
            print(f"           {detail}")

    n_pass = sum(1 for _, p, _ in all_checks if p)
    n_fail = len(all_checks) - n_pass
    print(f"\n  {n_pass}/{len(all_checks)} checks passed  |  {n_fail} failed")

    # ── 9-run summary table ───────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("9-RUN SUMMARY TABLE")
    print("=" * 72)
    hdr = f"  {'Scenario':<10} {'Variant':<12} {'Final_Q':>8} {'Target':>7} {'Err%':>6} {'Choke%':>7} {'Tightest':>9} {'Hdroom':>8} {'Chatter':>8}"
    print(hdr)
    print("  " + "-" * 72)
    for row in summary_rows:
        print(f"  {row['Scenario']:<10} {row['Variant']:<12} "
              f"{row['Final_Q']:>8.1f} {row['Target_Q']:>7.0f} {row['Pct_Err']:>6.1f} "
              f"{row['Final_Choke']:>7.1f} {row['Tightest_Var']:>9} "
              f"{row['Tightest_Hdroom_psi']:>8.1f} {row['Chatter_moves_last20']:>8}")

    # ── Violation report ──────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    if violations:
        print("⚠  VIOLATIONS DETECTED — DO NOT modify controller without review")
        print("=" * 72)
        for name, detail in violations:
            print(f"  FAILED: {name}")
            print(f"    {detail}")
    else:
        print("✅  ALL 27 CHECKS PASSED — controller config holds under all variants")
        print("    dead_band=3.0, w_ramp=0.3, hard_margin=0.0 — no loosening needed")
    print("=" * 72 + "\n")

    return len(violations) == 0


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
