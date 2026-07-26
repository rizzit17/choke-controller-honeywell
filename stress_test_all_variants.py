"""
stress_test_all_variants.py
----------------------------
Runs all 3 scenarios × 3 simulator variants = 9 closed-loop runs.
Checks constraint criteria per scenario × 3 variants.
Prints a full PASS/FAIL table and before/after headroom comparison.

Final locked config: dead_band=3.0, w_ramp=0.3, hard_margin=3.0

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

HARD_MARGIN = 3.0   # LOCKED: explicit 3 psi guard band above raw limits

# Before-values (hard_margin=0.0 run from previous stress test)
_BEFORE = {
    ("baseline",    "A"): {"settled_flp_hdroom": 59.4,  "transient_flp_min": 7.0,  "settled_bhp_hdroom": None, "chatter": 0},
    ("baseline",    "B"): {"settled_flp_hdroom": 45.2,  "transient_flp_min": None,  "settled_bhp_hdroom": None, "chatter": 1},
    ("baseline",    "C"): {"settled_flp_hdroom": 28.5,  "transient_flp_min": None,  "settled_bhp_hdroom": None, "chatter": 0},
    ("pessimistic", "A"): {"settled_flp_hdroom": 40.0,  "transient_flp_min": None,  "settled_bhp_hdroom": None, "chatter": 0},
    ("pessimistic", "B"): {"settled_flp_hdroom": 24.9,  "transient_flp_min": None,  "settled_bhp_hdroom": None, "chatter": 1},
    ("pessimistic", "C"): {"settled_flp_hdroom":  7.0,  "transient_flp_min": 7.0,  "settled_bhp_hdroom": None, "chatter": 0},
    ("optimistic",  "A"): {"settled_flp_hdroom": 76.7,  "transient_flp_min": None,  "settled_bhp_hdroom": None, "chatter": 0},
    ("optimistic",  "B"): {"settled_flp_hdroom": 64.0,  "transient_flp_min": None,  "settled_bhp_hdroom": None, "chatter": 0},
    ("optimistic",  "C"): {"settled_flp_hdroom": 49.9,  "transient_flp_min": None,  "settled_bhp_hdroom": None, "chatter": 0},
}


def make_controller():
    """Controller with final locked config: hard_margin=3.0."""
    process_model = load_model(STEP_TEST_CSV)
    cfg = ControllerConfig(
        w_track=1.0,
        w_ramp=0.3,
        barrier_k=500.0,
        barrier_eps=2.0,
        hard_margin=HARD_MARGIN,
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
    else:
        trend, _ = closed_loop_run(
            sim=sim, controller=controller,
            target_schedule=[(0, 300.0)],
            n_steps=60, initial_choke=5.0, label="",
        )
    return trend


def check_run(df: pd.DataFrame, scenario: str, variant: str):
    """Check all constraint criteria. Returns list of (name, passed, detail)."""
    results = []
    choke = df["Choke_pct"].values
    effective_flp_floor = LIMITS["FLP_min"] + HARD_MARGIN   # 153.0 psi
    effective_bhp_floor = LIMITS["BHP_min"] + HARD_MARGIN   # 2203.0 psi
    effective_whp_floor = LIMITS["WHP_min"] + HARD_MARGIN   # 203.0 psi

    # WHP (hard_margin-adjusted)
    viol = int(((df.WHP_psi < LIMITS["WHP_min"]) | (df.WHP_psi > LIMITS["WHP_max"])).sum())
    ok = (viol == 0)
    headroom_lo = float(df.WHP_psi.min() - LIMITS["WHP_min"])
    results.append((f"[{variant}/{scenario}] no_WHP_violation", ok,
                    f"{viol} steps violated | raw_min_hdroom={headroom_lo:.1f} psi"))

    # FLP (raw limit — hard rejection uses adjusted, but pass/fail checks raw)
    viol = int(((df.FLP_psi < LIMITS["FLP_min"]) | (df.FLP_psi > LIMITS["FLP_max"])).sum())
    ok = (viol == 0)
    headroom_lo = float(df.FLP_psi.min() - LIMITS["FLP_min"])
    results.append((f"[{variant}/{scenario}] no_FLP_violation", ok,
                    f"{viol} steps violated | raw_min_hdroom={headroom_lo:.1f} psi"))

    # BHP (raw limit)
    viol = int(((df.BHP_psi < LIMITS["BHP_min"]) | (df.BHP_psi > LIMITS["BHP_max"])).sum())
    ok = (viol == 0)
    headroom_lo = float(df.BHP_psi.min() - LIMITS["BHP_min"])
    results.append((f"[{variant}/{scenario}] no_BHP_violation", ok,
                    f"{viol} steps violated | raw_min_hdroom={headroom_lo:.1f} psi"))

    # Choke bounds
    viol = int(((choke < 0.0) | (choke > 100.0 + 1e-9)).sum())
    ok = (viol == 0)
    results.append((f"[{variant}/{scenario}] choke_bounds_0_100", ok,
                    f"{viol} steps out of bounds"))

    # Ramp rate
    ramp_max = float(np.abs(np.diff(choke)).max()) if len(choke) > 1 else 0.0
    ok = ramp_max <= 5.0 + 1e-9
    results.append((f"[{variant}/{scenario}] ramp_rate_max5pct", ok,
                    f"max={ramp_max:.2f}%/hr"))

    # Settling
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
    else:
        final_q = float(df["OilRate_bbl_hr"].iloc[-10:].mean())
        target  = float(df["Target_Q"].iloc[-1])
        ok = final_q < target * 0.75
        results.append((f"[{variant}/{scenario}] correctly_below_infeasible_tgt", ok,
                        f"settled={final_q:.1f} < 0.75x{target:.0f}={target*0.75:.0f}"))

    return results


def detailed_margins(df: pd.DataFrame, scenario: str) -> dict:
    """Compute settled & transient headroom stats for the before/after table."""
    flp = df["FLP_psi"].values
    bhp = df["BHP_psi"].values
    choke = df["Choke_pct"].values
    t_hr  = df["Time_hr"].values
    q     = df["OilRate_bbl_hr"].values

    # Settled phase definition
    if scenario == "A":
        si = np.arange(20, len(q))
    elif scenario == "B":
        si = np.concatenate([np.arange(15, 30), np.arange(45, len(q))])
    else:
        si = np.arange(20, len(q))

    # FLP headrooms
    flp_raw_min   = float(flp.min())
    flp_transient = float(flp_raw_min - LIMITS["FLP_min"])          # vs raw floor
    flp_adjusted  = float(flp_raw_min - (LIMITS["FLP_min"] + HARD_MARGIN))  # vs guard threshold

    flp_settled_min = float(flp[si].min())
    flp_settled_hdroom = float(flp_settled_min - LIMITS["FLP_min"])

    # BHP headroom (settled)
    bhp_settled_min = float(bhp[si].min())
    bhp_settled_hdroom = float(bhp_settled_min - LIMITS["BHP_min"])

    # Chatter: non-zero choke moves in settled phase
    dc_settled = np.abs(np.diff(choke[si]))
    chatter = int(np.sum(dc_settled > 0.01))

    # Q settling
    final_q = float(q[-10:].mean())
    target  = float(df["Target_Q"].iloc[-1])
    pct_err = abs(final_q - target) / target * 100

    return {
        "final_q": round(final_q, 1),
        "target":  target,
        "pct_err": round(pct_err, 1),
        "final_choke": float(choke[-1]),
        "flp_transient_raw_hdroom": round(flp_transient, 1),
        "flp_transient_adj_hdroom": round(flp_adjusted, 1),    # vs 153 psi guard
        "flp_settled_hdroom": round(flp_settled_hdroom, 1),
        "bhp_settled_hdroom": round(bhp_settled_hdroom, 1),
        "chatter": chatter,
    }


def main():
    print("\n" + "=" * 78)
    print("STRESS-TEST: 3 Scenarios x 3 Variants — hard_margin=3.0 (LOCKED CONFIG)")
    print(f"  FLP effective rejection threshold: {LIMITS['FLP_min'] + HARD_MARGIN:.0f} psi  "
          f"(raw 150 + margin 3)")
    print(f"  BHP effective rejection threshold: {LIMITS['BHP_min'] + HARD_MARGIN:.0f} psi  "
          f"(raw 2200 + margin 3)")
    print("=" * 78)

    print("\nLoading process model...")
    controller = make_controller()

    all_checks   = []
    all_details  = {}
    violations   = []

    for variant in VARIANTS:
        for scenario in SCENARIOS:
            print(f"  Running {variant}/{scenario}...", end=" ", flush=True)
            df = run_scenario(variant, scenario, controller)
            checks = check_run(df, scenario, variant)
            all_checks.extend(checks)
            all_details[(variant, scenario)] = detailed_margins(df, scenario)
            failed_here = [(n, d) for n, p, d in checks if not p]
            if failed_here:
                violations.extend(failed_here)
                print("VIOLATION DETECTED")
            else:
                print("OK")

    # ── Full PASS/FAIL table ──────────────────────────────────────────────────
    print("\n" + "=" * 78)
    print("FULL PASS/FAIL TABLE")
    print("=" * 78)
    for name, passed, detail in all_checks:
        status = "PASS" if passed else "FAIL ⚠"
        print(f"  [{status}]  {name}")
        if not passed or "err=" in detail:
            print(f"           {detail}")

    n_pass = sum(1 for _, p, _ in all_checks if p)
    n_fail = len(all_checks) - n_pass
    print(f"\n  {n_pass}/{len(all_checks)} checks passed  |  {n_fail} failed")

    # ── Before/After table (hard_margin=0.0 → 3.0) ────────────────────────────
    print("\n" + "=" * 78)
    print("BEFORE vs AFTER  (hard_margin=0.0 → 3.0)")
    print(f"  'FLP raw hdroom'   = FLP_min - 150.0 psi  (physical safety)")
    print(f"  'FLP adj hdroom'   = FLP_min - 153.0 psi  (above guard threshold)")
    print(f"  '* pessi/C transient' = minimum FLP hit during choke ramp-up to 100%")
    print("=" * 78)
    hdr = (f"  {'Variant':<12} {'Scen':<5} {'Final Q':>8} {'Tgt':>6} "
           f"{'FLP settled':>12} {'FLP trans(raw)':>15} {'FLP trans(adj)':>15} "
           f"{'BHP sttld':>10} {'Chatter':>8}")
    print(hdr)
    print("  " + "-" * 88)

    for variant in VARIANTS:
        for scenario in SCENARIOS:
            d = all_details[(variant, scenario)]
            b = _BEFORE.get((variant, scenario), {})
            settled_before = b.get("settled_flp_hdroom", "—")
            trans_before   = b.get("transient_flp_min", "—")

            # Delta indicators
            settled_after = d["flp_settled_hdroom"]
            s_delta = f"({settled_after - settled_before:+.1f})" if isinstance(settled_before, float) else ""

            trans_raw  = d["flp_transient_raw_hdroom"]
            trans_adj  = d["flp_transient_adj_hdroom"]

            marker = " ← KEY" if (variant, scenario) == ("pessimistic", "C") else ""

            print(f"  {variant:<12} {scenario:<5} {d['final_q']:>8.1f} {d['target']:>6.0f} "
                  f"  {settled_after:>+9.1f} psi   {trans_raw:>+11.1f} psi   {trans_adj:>+11.1f} psi"
                  f"  {d['bhp_settled_hdroom']:>+8.1f} psi  {d['chatter']:>7}{marker}")

    # ── Pessimistic/C spotlight ───────────────────────────────────────────────
    d_key = all_details[("pessimistic", "C")]
    print()
    print("  SPOTLIGHT — pessimistic/C (tightest case):")
    print(f"    FLP transient minimum (absolute):     {d_key['flp_transient_raw_hdroom']:+.1f} psi above raw 150 floor")
    print(f"    FLP transient minimum (vs threshold): {d_key['flp_transient_adj_hdroom']:+.1f} psi above 153 psi guard")
    if d_key["flp_transient_adj_hdroom"] > 0:
        print(f"    Result: transient clears guard threshold — NO spurious rejection ✅")
    else:
        print(f"    Result: transient BELOW guard threshold — spurious rejection LIKELY ⚠")
    print(f"    FLP settled headroom (vs raw 150):    {d_key['flp_settled_hdroom']:+.1f} psi")
    print(f"    Chatter moves in settled phase:       {d_key['chatter']}")

    # ── Final status ──────────────────────────────────────────────────────────
    print("\n" + "=" * 78)
    if violations:
        print("⚠  VIOLATIONS DETECTED")
        for name, detail in violations:
            print(f"  FAILED: {name}")
            print(f"    {detail}")
    else:
        print("✅  ALL CHECKS PASSED — FINAL LOCKED CONFIG")
        print(f"    dead_band=3.0 bbl/hr  |  w_ramp=0.3  |  hard_margin=3.0 psi")
    print("=" * 78 + "\n")

    return len(violations) == 0


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
