# Autonomous Production Choke Controller

> **Honeywell Hackathon Submission — Predictive, constraint-aware choke control for a naturally flowing oil well**

---

## Quick Start

```bash
# 1. Install dependencies
pip install numpy pandas matplotlib scikit-learn streamlit plotly

# 2. Generate step-test data (mock simulator)
python step_test_harness.py

# 3. Fit process model
python model.py

# 4. Run all three scenarios
python run_scenarios.py

# 5. Generate final plots (with dead-band annotation)
python plot_final.py

# 6. Launch interactive dashboard
streamlit run dashboard.py
```

---

## File Structure

| File | Purpose |
|---|---|
| `mock_simulator.py` | **Swap target** — replace import here when real simulator arrives |
| `step_test_harness.py` | Runs designed step-test sequence, saves `mock_step_test_data.csv` |
| `model.py` | Fits ARX process model from step-test CSV; exports `ProcessModel` class |
| `controller.py` | `ChokeController` — brute-force MPC with constraint enforcement & rationale logging |
| `run_scenarios.py` | Closed-loop runs of Scenarios A, B, C; saves trend + rationale CSVs |
| `plot_scenarios.py` | Interim scenario plots (per-iteration) |
| `plot_final.py` | **Final** 6-panel plots per scenario, saved as `mock_final_scenario_*.png` |
| `dashboard.py` | Streamlit dashboard with interactive Plotly charts + decision log |
| `test_constraints_and_compare.py` | Constraint validation suite — 20 tests, run after every parameter change |

**All output files prefixed `mock_` are rehearsal data only. Final deliverables use real simulator output.**

---

## Swapping to the Real Simulator (Hackathon Day)

Only **three steps** are needed:

1. Place the real simulator file in this directory.
2. In **`step_test_harness.py`**, change:
   ```python
   from mock_simulator import WellSimulator
   # → from real_simulator import WellSimulator
   ```
3. In **`run_scenarios.py`**, same change.
4. Re-run the pipeline top to bottom with `real_` prefixed output filenames.

`model.py`, `controller.py`, `plot_scenarios.py`, and `dashboard.py` need **zero changes** — they only depend on the CSV interface, not on the simulator internals.

---

## Model Choice Rationale

**ARX (Autoregressive with eXogenous input) linear regression** is used for one-step-ahead prediction inside the controller.

Features per step:
- `y[k-1]` — previous value of the output variable (autoregressive term)
- `u[k]` — current choke position
- `u[k-1]` — previous choke position
- `Δu[k]` — choke move magnitude

**Why ARX over a neural network or more complex model?**

1. The process is a well-conditioned first-order dynamic system — a linear ARX model captures it accurately (R² > 0.97 on test data).
2. Brute-force candidate evaluation calls the model ~10 times per control step. Linear regression is near-instant; complex models add latency with no physical justification.
3. ARX model parameters are interpretable — each coefficient has a clear engineering meaning. This directly supports Q&A defense.
4. The problem statement explicitly sanctions "simplified MPC based on brute-force candidate evaluation." Heavyweight nonlinear models are out of scope.

---

## Control Strategy

### Candidate Generation
At each 1-hour control interval, generate all choke candidates within ±5% of current position at 1% resolution. Clip to [0%, 100%].

### Prediction
For each candidate, use the ARX `ProcessModel` to predict Q, WHP, FLP, BHP one step ahead.

### Scoring (Cost Function)

```
cost = w_track × dead_band_error²
     + w_ramp  × |Δu|
     + soft_barrier_penalty(WHP, FLP, BHP)

where:  dead_band_error = max(0, |predicted_Q - target_Q| - dead_band)
```

**Soft barrier penalty:**
```
penalty = Σ [ barrier_k / (dist_to_lower_limit + ε)²
            + barrier_k / (dist_to_upper_limit + ε)² ]
```

The soft barrier rises steeply as any pressure approaches its hard limit, steering the controller toward the safe interior of the operating envelope rather than the boundary.

### Dead-Band Engineering Decision

During initial testing with a quadratic tracking cost and no dead-band, the controller exhibited **choke chattering**: after reaching the production target, the choke oscillated ±1–2% per step indefinitely rather than holding still. Root cause: once Q is within the noise floor (~±2 bbl/hr), the tracking cost and ramp cost are nearly equal for every candidate, so the controller alternates between adjacent choke positions on successive steps. This is not a safety issue — pressures remained within limits throughout — but it produces a cosmetically poor "sawtooth" settled phase and would cause unnecessary mechanical wear on a real choke valve.

The fix is a **dead-band** on the tracking error: when `|predicted_Q - target_Q| ≤ dead_band` (default 3 bbl/hr, ≈2.3% of a 130 bbl/hr target), the tracking term collapses to zero and the ramp penalty dominates. The cheapest move is always Δu = 0. Chattering stops entirely, and the choke flatlines once on-target. The dead-band does **not** affect constraint logic (hard rejection and soft barrier are evaluated on absolute predicted pressures, not on tracking error), and it has zero effect on Scenario C where the choke is already physically bounded at 100%.

The controller's decision log explicitly records `DEAD-BAND HOLD` entries during held steps, making this decision visible and auditable.

### Hard Rejection
Any candidate predicted to violate WHP, FLP, or BHP hard limits is **excluded entirely** from selection — not just penalized. This guarantees the chosen action is always within the safe operating envelope.

### Fallback (Scenario C behavior)
If **all** candidates violate hard limits (infeasible target), the controller holds the current choke position. It does not chase the target further — production safety takes priority.

### Tuned Parameters

| Parameter | Value | Rationale |
|---|---|---|
| `w_track` | 1.0 | Primary objective: minimize tracking error |
| `w_ramp` | 0.3 | Penalises unnecessary moves; raised from 0.05 after initial chattering analysis |
| `dead_band` | 3.0 bbl/hr | Suppresses tracking cost within noise floor; eliminates choke hunting |
| `barrier_k` | 500 | Steep penalty near limits without distorting cost far from limits |
| `barrier_eps` | 2.0 psi | Prevents division by zero; small relative to ~200 psi pressure ranges |

---

## Safe Operating Limits

| Variable | Minimum | Maximum |
|---|---|---|
| WHP (Wellhead Pressure) | 200 psi | 480 psi |
| FLP (Flowline Pressure) | 150 psi | 350 psi |
| BHP (Bottom Hole Pressure) | 2200 psi | 3000 psi |
| Choke Opening | 0% | 100% |
| Choke Ramp Rate | −5%/hr | +5%/hr |

*Note: When real simulator is received, verify/update WHP/FLP/BHP limits from its documentation or by inspection of the step-test data range.*

---

## Known Limitations and Assumptions

1. **Single-step prediction**: The ARX model predicts only one step ahead (not a multi-step horizon). This is consistent with the brute-force MPC approach in the problem spec, but means the controller cannot anticipate slowly evolving constraint violations more than one step out. Mitigation: the soft barrier penalty creates a natural "stay away from limits" gradient that adds de facto look-ahead margin.

2. **Linear model**: ARX assumes linear dynamics. If the real simulator shows strong nonlinearity (e.g., production rate vs. choke is highly curved, or time constants vary strongly with operating point), consider fitting separate linear models per operating region (piecewise ARX) without changing the controller architecture.

3. **Mock simulator calibration**: Limits and steady-state values in `mock_simulator.py` are approximations from the reference dataset. Actual safe limits from the real simulator may differ — update `LIMITS` in `controller.py` accordingly.

4. **No dead-time modeled**: The ARX model assumes zero dead-time (immediate effect of choke change). If the real simulator shows a pure delay of D steps, add D shifted-choke terms to the feature vector in `model.py`.

5. **Noise handling**: Mild Gaussian noise in the mock is filtered implicitly by the linear model. For the real simulator, if noise is heavier, consider adding a simple moving-average measurement smoother before feeding to the controller.
