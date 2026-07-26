"""
test_constraints_and_compare.py
Runs the before/after comparison table and the constraint-check suite.
Before = w_ramp=0.3, no dead-band (previous run)
After  = w_ramp=0.3, dead_band=3.0 (current run)
"""
import sys
import numpy as np
import pandas as pd
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ── "Before" values captured from the w_ramp=0.3 / no-dead-band run ──────────
BEFORE = {
    "A": dict(reversals=22, final_q=130.5, final_choke=68.0, ch_range_10=4.0,
              flp_min=208.6, bhp_min=2451.1),
    "B": dict(reversals=24, final_q=149.8, final_choke=80.0, ch_range_10=4.0,
              flp_min=193.6, bhp_min=2405.3),
    "C": dict(reversals=27, final_q=174.8, final_choke=100.0, ch_range_10=0.0,
              flp_min=178.1, bhp_min=2338.2, flp_headroom=28.1, bhp_headroom=138.2),
}

LIMITS = dict(WHP_min=200, WHP_max=480, FLP_min=150, FLP_max=350,
              BHP_min=2200, BHP_max=3000)

results_after = {}
failures = []

print("=" * 72)
print("BEFORE/AFTER TABLE  (w_ramp=0.3, no-dead-band  ->  +dead_band=3 bbl/hr)")
print("=" * 72)

for s in ["A", "B", "C"]:
    df = pd.read_csv(f"mock_scenario_{s}.csv")
    q      = df["OilRate_bbl_hr"].values
    choke  = df["Choke_pct"].values
    t      = df["Time_hr"].values

    # Settled-phase indices (same definition as previous run)
    if s == "A":
        si = np.arange(20, len(q))
    elif s == "B":
        si = np.concatenate([np.arange(15, 30), np.arange(45, len(q))])
    else:
        si = np.arange(20, len(q))

    dq = np.diff(q[si])
    dc = np.diff(choke[si])
    q_rev      = int(np.sum(dq[:-1] * dq[1:] < 0))
    ch_nz      = int(np.sum(np.abs(dc) > 0))
    ch_range10 = float(choke[-10:].max() - choke[-10:].min())
    final_q    = float(q[-10:].mean())
    final_ch   = float(choke[-1])
    flp_min    = float(df["FLP_psi"].min())
    bhp_min    = float(df["BHP_psi"].min())
    flp_h      = flp_min - 150.0
    bhp_h      = bhp_min - 2200.0

    results_after[s] = dict(
        reversals=q_rev, ch_nz=ch_nz, ch_range10=ch_range10,
        final_q=final_q, final_choke=final_ch,
        flp_min=flp_min, bhp_min=bhp_min,
        flp_headroom=flp_h, bhp_headroom=bhp_h,
    )

    b  = BEFORE[s]
    af = results_after[s]

    print(f"\n{'='*35} SCENARIO {s} {'='*35}")
    print(f"  {'Metric':<40} {'BEFORE':>10}  {'AFTER':>10}  {'Delta':>10}")
    print(f"  {'-'*70}")
    metrics = [
        ("Q direction-reversals (settled phase)", b["reversals"],      af["reversals"],  True, 0),
        ("Choke non-zero moves (settled phase)",  "n/a",               af["ch_nz"],      True, None),
        ("Choke range over last 10 steps (%)",    b["ch_range_10"],    af["ch_range10"], True, 0),
        ("Final Q mean (last 10 steps, bbl/hr)",  b["final_q"],        af["final_q"],    False, None),
        ("Final choke position (%)",              b["final_choke"],    af["final_choke"],False, None),
        ("FLP minimum (psi)",                     b["flp_min"],        af["flp_min"],    False, None),
        ("BHP minimum (psi)",                     b["bhp_min"],        af["bhp_min"],    False, None),
    ]
    if s == "C":
        metrics += [
            ("FLP headroom to 150 psi floor (psi)",  b["flp_headroom"],  af["flp_headroom"],  False, None),
            ("BHP headroom to 2200 psi floor (psi)", b["bhp_headroom"],  af["bhp_headroom"],  False, None),
        ]

    for label, bv, av, lower_is_better, target in metrics:
        if isinstance(bv, float) or isinstance(bv, int):
            delta_str = f"{av - bv:+.1f}"
        else:
            delta_str = "-"
        bv_str = f"{bv:.1f}" if isinstance(bv, (float, int)) else str(bv)
        av_str = f"{av:.1f}"
        print(f"  {label:<40} {bv_str:>10}  {av_str:>10}  {delta_str:>10}")


# ── Pytest-style constraint suite ─────────────────────────────────────────────
print()
print("=" * 72)
print("CONSTRAINT CHECK SUITE  (all scenarios, dead-band run)")
print("=" * 72)

test_results = []

for s in ["A", "B", "C"]:
    df = pd.read_csv(f"mock_scenario_{s}.csv")
    choke = df["Choke_pct"].values

    # --- test_no_whp_violation ---
    viol = int(((df.WHP_psi < LIMITS["WHP_min"]) | (df.WHP_psi > LIMITS["WHP_max"])).sum())
    passed = viol == 0
    test_results.append((f"test_scenario_{s}_no_whp_violation", passed, f"{viol} steps violated"))
    if not passed:
        failures.append(f"Scenario {s}: WHP violated {viol} steps")

    # --- test_no_flp_violation ---
    viol = int(((df.FLP_psi < LIMITS["FLP_min"]) | (df.FLP_psi > LIMITS["FLP_max"])).sum())
    passed = viol == 0
    test_results.append((f"test_scenario_{s}_no_flp_violation", passed, f"{viol} steps violated"))
    if not passed:
        failures.append(f"Scenario {s}: FLP violated {viol} steps")

    # --- test_no_bhp_violation ---
    viol = int(((df.BHP_psi < LIMITS["BHP_min"]) | (df.BHP_psi > LIMITS["BHP_max"])).sum())
    passed = viol == 0
    test_results.append((f"test_scenario_{s}_no_bhp_violation", passed, f"{viol} steps violated"))
    if not passed:
        failures.append(f"Scenario {s}: BHP violated {viol} steps")

    # --- test_choke_bounds ---
    viol = int(((choke < 0.0) | (choke > 100.0)).sum())
    passed = viol == 0
    test_results.append((f"test_scenario_{s}_choke_bounds_0_100", passed, f"{viol} steps out of bounds"))
    if not passed:
        failures.append(f"Scenario {s}: Choke out of bounds {viol} steps")

    # --- test_ramp_rate ---
    ramp_max = float(np.abs(np.diff(choke)).max())
    passed = ramp_max <= 5.0 + 1e-9   # float tolerance
    test_results.append((f"test_scenario_{s}_ramp_rate_max5pct", passed, f"max={ramp_max:.2f}%/hr"))
    if not passed:
        failures.append(f"Scenario {s}: Ramp rate {ramp_max:.2f}%/hr exceeds 5%/hr")

    # --- test_scenario_C_no_choke_increase_after_100 ---
    if s == "C":
        choke_at_100_idx = np.where(choke >= 100.0)[0]
        if len(choke_at_100_idx):
            first_100 = choke_at_100_idx[0]
            post_choke = choke[first_100:]
            viol = int((post_choke > 100.0 + 1e-9).sum())
            passed = viol == 0
            test_results.append(("test_scenario_C_choke_stays_at_100_not_above", passed,
                                  f"{viol} steps above 100%"))
            if not passed:
                failures.append(f"Scenario C: Choke exceeded 100% after hitting ceiling")

    # --- test_scenario_A_reaches_target ---
    if s == "A":
        final_q = float(df["OilRate_bbl_hr"].iloc[-10:].mean())
        target  = float(df["Target_Q"].iloc[-1])
        pct_err = abs(final_q - target) / target * 100
        passed  = pct_err < 5.0
        test_results.append(("test_scenario_A_target_reached_within_5pct", passed,
                              f"final_Q={final_q:.1f}, target={target:.0f}, err={pct_err:.1f}%"))
        if not passed:
            failures.append(f"Scenario A: Final Q {final_q:.1f} not within 5% of target {target:.0f}")

    # --- test_scenario_B_phase1 and phase2 ---
    if s == "B":
        phase1_q = float(df.loc[df["Target_Q"] == 100.0, "OilRate_bbl_hr"].iloc[-5:].mean())
        phase2_q = float(df.loc[df["Target_Q"] == 150.0, "OilRate_bbl_hr"].iloc[-5:].mean())
        for phase, actual_q, target in [("Phase1", phase1_q, 100.0), ("Phase2", phase2_q, 150.0)]:
            pct_err = abs(actual_q - target) / target * 100
            passed  = pct_err < 5.0
            test_results.append((f"test_scenario_B_{phase}_within_5pct", passed,
                                  f"Q={actual_q:.1f}, tgt={target:.0f}, err={pct_err:.1f}%"))
            if not passed:
                failures.append(f"Scenario B {phase}: Q {actual_q:.1f} not within 5% of target {target:.0f}")

    # --- test_scenario_C_target_infeasible_acknowledged ---
    if s == "C":
        final_q = float(df["OilRate_bbl_hr"].iloc[-10:].mean())
        target  = float(df["Target_Q"].iloc[-1])
        # Controller should NOT have reached the target (it's infeasible)
        passed  = final_q < target * 0.75   # settled Q should be < 75% of 300 = 225
        test_results.append(("test_scenario_C_correctly_below_infeasible_target", passed,
                              f"settled={final_q:.1f} < 0.75*{target:.0f}={target*0.75:.0f}"))
        if not passed:
            failures.append(f"Scenario C: Settled Q {final_q:.1f} suspiciously close to infeasible target {target:.0f}")

# Print results
print()
for name, passed, detail in test_results:
    status = "PASS" if passed else "FAIL"
    marker = "." if passed else "F"
    print(f"  [{status}] {name}")
    if not passed or "err=" in detail:
        print(f"         {detail}")

print()
total = len(test_results)
n_pass = sum(1 for _, p, _ in test_results if p)
n_fail = total - n_pass
print(f"{'='*72}")
print(f"  {n_pass}/{total} tests passed  |  {n_fail} failed")
if failures:
    print("\n  FAILURES:")
    for f in failures:
        print(f"    - {f}")
else:
    print("  ALL TESTS PASSED -- zero constraint violations, all targets within tolerance.")
print(f"{'='*72}")
