# Autonomous Production Choke Controller

> **Honeywell Hackathon Submission - Predictive, constraint-aware choke control for a naturally flowing oil well**

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
| `mock_simulator.py` | **Swap target** - replace import here when real simulator arrives |

Features per step:
- `y[k-1]` - previous value of the output variable (autoregressive term)
- `u[k]` - current choke position
- `u[k-1]` - previous choke position
- `Δu[k]` - choke move magnitude

**Why ARX over a neural network or more complex model?**

1. The process is a well-conditioned first-order dynamic system - a linear ARX model captures it accurately (R² > 0.97 on test data).
2. Brute-force candidate evaluation calls the model ~10 times per control step. Linear regression is near-instant; complex models add latency with no physical justification.
3. ARX model parameters are interpretable - each coefficient has a clear engineering meaning. This directly supports Q&A defense.
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

<<<<<<< HEAD
During initial testing with a quadratic tracking cost and no dead-band, the controller exhibited **choke chattering**: after reaching the production target, the choke oscillated ±1–2% per step indefinitely rather than holding still. Root cause: once Q is within the noise floor (~±2 bbl/hr), the tracking cost and ramp cost are nearly equal for every candidate, so the controller alternates between adjacent choke positions on successive steps. This is not a safety issue - pressures remained within limits throughout - but it produces a cosmetically poor "sawtooth" settled phase and would cause unnecessary mechanical wear on a real choke valve.
=======
During initial testing with a quadratic tracking cost and no dead-band, the controller exhibited **choke chattering**: after reaching the production target, the choke oscillated ±1-2% per step indefinitely rather than holding still. Root cause: once Q is within the noise floor (~±2 bbl/hr), the tracking cost and ramp cost are nearly equal for every candidate, so the controller alternates between adjacent choke positions on successive steps. This is not a safety issue - pressures remained within limits throughout - but it produces a cosmetically poor "sawtooth" settled phase and would cause unnecessary mechanical wear on a real choke valve.
>>>>>>> a50729b (Final submission pipeline update: master notebook, PDF formatting, clean symbols, and docs)

The fix is a **dead-band** on the tracking error: when `|predicted_Q - target_Q| ≤ dead_band` (default 3 bbl/hr, ≈2.3% of a 130 bbl/hr target), the tracking term collapses to zero and the ramp penalty dominates. The cheapest move is always Δu = 0. Chattering stops entirely, and the choke flatlines once on-target. The dead-band does **not** affect constraint logic (hard rejection and soft barrier are evaluated on absolute predicted pressures, not on tracking error), and it has zero effect on Scenario C where the choke is already physically bounded at 100%.

The controller's decision log explicitly records `DEAD-BAND HOLD` entries during held steps, making this decision visible and auditable.

### Hard Rejection
Any candidate predicted to violate WHP, FLP, or BHP hard limits is **excluded entirely** from selection - not just penalized. This guarantees the chosen action is always within the safe operating envelope.

### Fallback (Scenario C behavior)
If **all** candidates violate hard limits (infeasible target), the controller holds the current choke position. It does not chase the target further - production safety takes priority.

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

| Variable | Minimum | Maximum | Classification |
|---|---|---|---|
| **Choke Opening** | 0% | 100% | **Organizer-Specified** (`.docx`) |
| **Choke Ramp Rate** | −5%/hr | +5%/hr | **Organizer-Specified** (`.docx`, $T_s=1\text{ hr}$) |
| **WHP (Wellhead Pressure)** | 200 psi | 480 psi | **Working Assumption** (derived from dataset range) |
| **FLP (Flowline Pressure)** | 150 psi | 350 psi | **Working Assumption** (derived from dataset range) |
| **BHP (Bottom Hole Pressure)** | 2200 psi | 3000 psi | **Working Assumption** (derived from dataset range) |

> **Note on Operating Envelope Limits**:
> The problem statement (`.docx`) mandates that WHP, FLP, and BHP are active safety constraints, but deliberately leaves their exact numerical bounds to be dictated by the real simulator. 
> The numeric bounds above are **our working assumptions for rehearsal**, established based on the reference dataset's observed operating range.
> All safe operating limits are centralized in the `LIMITS` configuration dictionary in `mock_simulator.py` and `controller.py`. When the organizer's official simulator and exact limits are disclosed on hackathon day, updating the controller to the real limits is a **one-line configuration update**, requiring zero algorithm redesign.

---

## Known Limitations and Assumptions

1. **Single-step prediction**: The ARX model predicts only one step ahead (not a multi-step horizon). This is consistent with the brute-force MPC approach in the problem spec, but means the controller cannot anticipate slowly evolving constraint violations more than one step out. Mitigation: the soft barrier penalty creates a natural "stay away from limits" gradient that adds de facto look-ahead margin.

2. **Linear model**: ARX assumes linear dynamics. If the real simulator shows strong nonlinearity (e.g., production rate vs. choke is highly curved, or time constants vary strongly with operating point), consider fitting separate linear models per operating region (piecewise ARX) without changing the controller architecture.

<<<<<<< HEAD
3. **Mock simulator calibration**: The physics-grounded steady-state model (`Q = Cv(u)·u·sqrt(ΔP)`) is calibrated to all 14 real organizer data points (choke positions 5–95%). Two values - `u=40%` (~101.3 bbl/hr) and `u=100%` (~175.1 bbl/hr) - are physics-model extrapolations with no organizer data backing and are labeled as such in `architecture.md`. Safe operating limits (`LIMITS` dict) are verified against the reference dataset range. Update after receiving the real simulator.
=======
3. **Mock simulator calibration**: The physics-grounded steady-state model (`Q = Cv(u)·u·sqrt(ΔP)`) is calibrated to all 14 real organizer data points (choke positions 5-95%). Two values - `u=40%` (~101.3 bbl/hr) and `u=100%` (~175.1 bbl/hr) - are physics-model extrapolations with no organizer data backing and are labeled as such in `architecture.md`. Safe operating limits (`LIMITS` dict) are verified against the reference dataset range. Update after receiving the real simulator.
>>>>>>> a50729b (Final submission pipeline update: master notebook, PDF formatting, clean symbols, and docs)

4. **No dead-time modeled**: The ARX model assumes zero dead-time (immediate effect of choke change). If the real simulator shows a pure delay of D steps, add D shifted-choke terms to the feature vector in `model.py`.

5. **Noise handling**: Mild Gaussian noise in the mock is filtered implicitly by the linear model. For the real simulator, if noise is heavier, consider adding a simple moving-average measurement smoother before feeding to the controller.
