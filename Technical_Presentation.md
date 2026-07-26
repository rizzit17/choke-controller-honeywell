# Autonomous Production Choke Controller for a Single Naturally Flowing Oil Well
## Technical Presentation

---

## 1. Process Understanding & Model

### 1.1 Step-Test Results

- Conducted a full-range open-loop step test sweeping choke position across the operable range (5% to 95%, matching the 14 real anchor points present in the organizer-provided reference dataset).
- Observed steady-state Oil Flow Rate (Q) increases monotonically with choke opening, following a smooth first-order-lag approach to each new steady state after every step change (no dead-time artifact, no oscillation, no reverse-direction anomalies).
- Wellhead Pressure (WHP), Flowline Pressure (FLP), and Bottom Hole Pressure (BHP) all decrease monotonically as choke opens further, consistent with expected choke/orifice flow physics (opening the choke increases flow, which increases frictional/velocity pressure losses and reduces upstream pressures).
- Verified our recalibrated model against all 14 real organizer reference points, with prediction error within ±1.0 bbl/hr at every anchor point (initial calibration attempt was caught and corrected after discovering it had drifted from the actual reference dataset - documented transparently in our engineering log).

### 1.2 Model Assumptions

- The well is treated as a single naturally flowing well with one production choke as the sole manipulated variable, per the problem statement's stated scope (no gas lift, no ESP, no facility network interactions, no changing reservoir properties or GOR/water cut).
- Steady-state flow relationship is grounded in standard choke/orifice flow physics: Q ≈ Cv(u) · u · √(P_upstream − P_downstream), where P_upstream ≈ WHP and P_downstream ≈ FLP, with the discharge coefficient Cv(u) calibrated by regression against the 14 real reference data points.
- Transient dynamics (first-order lag time constant, measurement noise) are engineering assumptions layered on top of the steady-state physics relationship, since the reference dataset only provides steady-state behavior at each tested choke position, not the underlying noise/lag parameters.
- Numeric safe operating limits for WHP, FLP, and BHP are not specified anywhere in the problem statement. We derived working limits from the observed operating range in our step-test data, with safety margin, centralized in a single configuration dictionary so they can be updated instantly once the organizer's real simulator or documentation discloses the true limits.

### 1.3 Dynamic Model Developed

- Per-output-variable ARX (AutoRegressive with eXogenous input) models fit via Ridge regression, using current and recent choke position as inputs to predict Q, WHP, FLP, and BHP.
- Validation on held-out step-test data: R² = 0.997 (Oil Rate), 0.994 (WHP), 0.996 (FLP), 0.994 (BHP) - strong fit across all four output variables.
- Model is fully data-driven, not tuned to any internal simulator formula, ensuring it generalizes cleanly when the real Honeywell simulator is substituted.

---

## 2. Control Strategy

### 2.1 Prediction Methodology

- At each 1-hour control interval, the controller receives current Q, WHP, FLP, BHP, and choke position (exactly the inputs specified in the problem statement - no additional or hidden state is used).
- For each candidate choke move, the identified ARX model predicts the resulting Q, WHP, FLP, and BHP one control interval ahead.

### 2.2 Choke Move Selection Logic

- Brute-force candidate evaluation (explicitly sanctioned by the problem statement): all feasible choke moves within the ±5% per-interval ramp limit are enumerated, respecting the 0-100% choke bounds.
- Each candidate is scored using a cost function combining: (a) a dead-band-filtered tracking error term (suppressing cost once within ±3 bbl/hr of target, to prevent chattering from sensor noise), (b) a soft constraint barrier that rises sharply as any predicted pressure approaches its safe limit, and (c) a ramp-movement penalty.
- The lowest-cost feasible candidate is selected as the next choke position.

### 2.3 Constraint Handling Approach

- **Hard rejection layer:** any candidate predicted to violate a WHP/FLP/BHP safe limit (adjusted by a 3.0 psi safety guard margin, sized against observed sensor noise of σ=0.91 psi to avoid spurious rejections) is discarded outright.
- **Soft barrier layer:** a continuous penalty steers candidates away from constraint boundaries before they become critical, rather than relying on hard rejection alone.
- **Safety fallback:** if no candidate is feasible (as in the infeasible-target scenario), the controller holds position or selects the least-constraint-violating safe option, prioritizing constraint protection over target-chasing.
- **Explainability:** every control decision - including every rejected candidate - is logged with a plain-English reason, categorized into five distinct rationale states (Hold, Barrier-Steering, Tracking Correction, Constrained Correction, Safety Fallback), giving a full auditable decision trail.

---

## 3. Results

### 3.1 Scenario Outcomes

- **Scenario A (Startup to Target):** Controller ramped the well from near-shut-in conditions to the 130 bbl/hr target, settling smoothly with zero constraint violations.
- **Scenario B (Target Step-Change):** Controller tracked 100 bbl/hr, then correctly re-tracked to a new 150 bbl/hr target mid-run, respecting all pressure and ramp-rate constraints throughout the transition.
- **Scenario C (Infeasible Target):** Requested target of 300 bbl/hr correctly identified as unachievable. Controller opened the choke to its 100% physical ceiling, settled at the maximum safely achievable production rate, and never violated a single constraint.

### 3.2 Tracking Performance

- Across all validated scenario runs (baseline, pessimistic, and optimistic simulated well-behavior variants), all feasible production targets were tracked within a worst-case error of 0.9%.
- Chattering near setpoint (caused by sensor noise interacting with model prediction sensitivity) was identified during development, diagnosed to its root cause, and eliminated via a dead-band mechanism in the cost function - verified via before/after comparison showing choke position variance reduced from a 4% oscillation range to a fully stable 0% range in the settled phase, with zero degradation in tracking accuracy.

### 3.3 Safety Performance

- 57 automated constraint checks executed across all 3 scenarios × 3 simulated process-behavior variants (baseline, pessimistic, optimistic) - 57/57 passing, zero WHP/FLP/BHP violations in any run.
- Tightest observed safety margin: Flowline Pressure at +7 psi above its working safety floor, under the pessimistic variant's Scenario C (maximum-choke, infeasible-target) conditions - confirmed safely clear of violation, with an additional deliberately-sized 3 psi hard-rejection guard band verified not to trigger any false safety rejections.
- Controller design and constraint-handling logic held without modification across all three tested process-behavior variants, demonstrating robustness beyond a single calibration.

### 3.4 Lessons Learned

- **Chattering diagnosis:** Initial hunting behavior (choke oscillating ±1-2% near setpoint) was first hypothesized to be a ramp-penalty tuning issue; testing showed this hypothesis was only partially correct. The true root cause was that tracking cost and ramp cost became nearly equal at the sensor-noise floor near setpoint. A dead-band correctly and completely resolved the issue, verified via before/after data rather than assumption.
- **Calibration integrity:** Our team caught and corrected a mid-development calibration error where model reference points had drifted from the actual organizer-provided dataset, re-verified the full pipeline against all 14 real data points, and re-ran the complete stress-test suite to confirm no regressions - reinforcing the importance of tracing every number back to verified source data rather than accepting intermediate results at face value.
- **Assumption transparency:** Where the problem statement leaves numeric safety limits unspecified, we made this explicit throughout our documentation rather than presenting an assumption as a given requirement, and engineered our system so any future correction requires only a one-line configuration update, not a redesign.
