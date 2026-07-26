# Simulator One-Line Swap Checklist

This guide provides step-by-step instructions to transition the Autonomous Choke Controller codebase from the mock simulator (`mock_simulator.py`) to Honeywell's real hackathon plant simulator.

---

## 📋 Swap Protocol

### Step 1: Update Import in Core Scripts
In each of the following files, update the simulator import line:

1. **`step_test_harness.py`**
   ```python
   # OLD (Mock Simulator)
   from mock_simulator import WellSimulator

   # NEW (Real Hackathon Simulator)
   from real_simulator import WellSimulator
   ```

2. **`run_scenarios.py`**
   ```python
   # OLD
   from mock_simulator import WellSimulator

   # NEW
   from real_simulator import WellSimulator
   ```

3. **`dashboard.py`**
   ```python
   # OLD
   from mock_simulator import WellSimulator

   # NEW
   from real_simulator import WellSimulator
   ```

---

### Step 2: Verify Operating Pressure Limits (`LIMITS`)
If the real simulator provides custom pressure limits, update `LIMITS` in `mock_simulator.py` or import them directly:

```python
LIMITS = {
    "WHP_min": 200.0, "WHP_max": 480.0,
    "FLP_min": 150.0, "FLP_max": 350.0,
    "BHP_min": 2200.0, "BHP_max": 3000.0,
}
```

---

### Step 3: Re-Run Full Pipeline
Execute the commands in sequence to generate new models and closed-loop results:

```bash
# 1. Run open-loop step test to collect new training data
python step_test_harness.py

# 2. Fit ARX model on real step-test data
python model.py

# 3. Execute closed-loop Scenarios A, B, and C
python run_scenarios.py

# 4. Run full 3x3 stress test matrix
python stress_test_all_variants.py

# 5. Re-build and re-execute master Jupyter notebook
python build_master_notebook.py
jupyter nbconvert --execute --to notebook --inplace choke_controller_final_submission.ipynb
```

---

### Verification
- Check that $R^2 > 0.99$ in `model.py` fit summary.
- Verify 0 constraint violations in `stress_test_all_variants.py`.
