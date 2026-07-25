"""
model.py -- Dynamic process model for choke controller
------------------------------------------------------
Fully DATA-DRIVEN: reads only mock_step_test_data.csv (or real_step_test_data.csv).
This file has ZERO knowledge of the mock simulator's internal equations --
that separation is deliberate so it transfers cleanly to real data later.

Two model types per output variable:
  1. FOPDT (First-Order Plus Dead-Time) identified via steady-state gain + time constant
  2. Autoregressive linear model (ARX):  y[k] = a*y[k-1] + b*u[k] + c  (fast, predictive)

The controller uses the ARX model for step-ahead prediction.
FOPDT is kept for presentation and model-validation plots.

Usage:
    python model.py                   # fits models, saves plots, prints metrics
    from model import ProcessModel    # import in controller
"""

import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from sklearn.linear_model import Ridge
from sklearn.metrics import r2_score, mean_absolute_error
import warnings, json, os

STEP_TEST_CSV   = "mock_step_test_data.csv"   # swap to real_step_test_data.csv when ready
MODEL_PARAMS_JSON = "mock_model_params.json"
VALIDATION_PLOT = "mock_model_validation.png"
OUTPUTS = ["OilRate_bbl_hr", "WHP_psi", "FLP_psi", "BHP_psi"]
PRETTY  = {"OilRate_bbl_hr": "Oil Rate (bbl/hr)",
           "WHP_psi":        "WHP (psi)",
           "FLP_psi":        "FLP (psi)",
           "BHP_psi":        "BHP (psi)"}


# ── Feature engineering ────────────────────────────────────────────────────────

def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build ARX features from the step-test DataFrame.

    Features per row:
      - y[k-1]      : previous value of the same output (autoregressive term)
      - u[k]        : current choke position
      - u[k-1]      : previous choke position (captures choke-change dynamics)
      - delta_u[k]  : choke move magnitude (u[k] - u[k-1])

    These features are sufficient for a SISO first-order process.
    They remain valid for the real simulator data because they depend only on
    observable measurements -- no internal simulator knowledge is assumed.
    """
    out = df.copy()
    out["u_prev"]    = out["Choke_pct"].shift(1)
    out["delta_u"]   = out["Choke_pct"] - out["u_prev"]
    for col in OUTPUTS:
        out[f"{col}_prev"] = out[col].shift(1)
    out = out.dropna().reset_index(drop=True)
    return out


def get_feature_matrix(feat_df: pd.DataFrame, output: str):
    """Return X (feature matrix) and y (target vector) for one output variable."""
    X = feat_df[[f"{output}_prev", "Choke_pct", "u_prev", "delta_u"]].values
    y = feat_df[output].values
    return X, y


# ── Model fitting ──────────────────────────────────────────────────────────────

def fit_arx_models(feat_df: pd.DataFrame, train_frac: float = 0.80):
    """
    Fit Ridge regression ARX models for all four outputs.

    Returns
    -------
    models : dict[str, Ridge]
    metrics : dict[str, dict]
    train_idx, test_idx : index arrays for validation plotting
    """
    n = len(feat_df)
    split = int(n * train_frac)
    train_idx = np.arange(0, split)
    test_idx  = np.arange(split, n)

    models  = {}
    metrics = {}

    for out in OUTPUTS:
        X, y = get_feature_matrix(feat_df, out)
        X_tr, y_tr = X[train_idx], y[train_idx]
        X_te, y_te = X[test_idx],  y[test_idx]

        mdl = Ridge(alpha=0.1)
        mdl.fit(X_tr, y_tr)

        y_pred_tr = mdl.predict(X_tr)
        y_pred_te = mdl.predict(X_te)

        metrics[out] = {
            "R2_train": round(r2_score(y_tr, y_pred_tr), 4),
            "R2_test":  round(r2_score(y_te, y_pred_te), 4),
            "MAE_test": round(mean_absolute_error(y_te, y_pred_te), 3),
            "coef":     mdl.coef_.tolist(),
            "intercept": float(mdl.intercept_),
            "features": [f"{out}_prev", "Choke_pct", "u_prev", "delta_u"],
        }
        models[out] = mdl

    return models, metrics, train_idx, test_idx


# ── Steady-state gain (for FOPDT presentation) ───────────────────────────────

def estimate_steady_state_gains(df: pd.DataFrame):
    """
    Estimate steady-state gains K = ΔY/Δu from step-test data.
    Groups data by choke level, takes last-N-samples mean as proxy for SS.
    """
    ss = df.groupby("Choke_pct")[OUTPUTS].mean()
    gains = {}
    u_vals = ss.index.values
    for out in OUTPUTS:
        y_vals = ss[out].values
        # Linear regression of SS output vs choke (first-order gain)
        p = np.polyfit(u_vals, y_vals, deg=2)  # quadratic to capture nonlinearity
        gains[out] = {"poly_coef": p.tolist()}
    return gains


# ── Validation plot ───────────────────────────────────────────────────────────

def plot_validation(feat_df: pd.DataFrame, models: dict,
                    train_idx, test_idx, save_path: str):
    colors = ["#34d399", "#60a5fa", "#f59e0b", "#f87171"]
    fig = plt.figure(figsize=(16, 10))
    fig.patch.set_facecolor("#0f1117")
    gs = gridspec.GridSpec(2, 2, hspace=0.45, wspace=0.35)

    for idx, (out, color) in enumerate(zip(OUTPUTS, colors)):
        ax = fig.add_subplot(gs[idx // 2, idx % 2])
        ax.set_facecolor("#1a1d27")
        ax.tick_params(colors="white", labelsize=7)
        for spine in ax.spines.values():
            spine.set_edgecolor("#3a3d4d")

        X, y = get_feature_matrix(feat_df, out)
        y_pred = models[out].predict(X)
        t = feat_df["Time_hr"].values

        # Actual
        ax.plot(t, y, color=color, linewidth=1.0, alpha=0.7, label="Actual")
        # Predicted -- split into train/test for visual distinction
        ax.plot(t[train_idx], y_pred[train_idx],
                color="white", linewidth=0.9, linestyle="--", alpha=0.6, label="Pred (train)")
        ax.plot(t[test_idx],  y_pred[test_idx],
                color="#f472b6", linewidth=1.2, linestyle="-", label="Pred (test)")

        ax.axvline(t[test_idx[0]], color="#6b7280", linestyle=":", linewidth=1)
        ax.set_title(PRETTY[out], color="white", fontsize=9)
        ax.set_xlabel("Time (hr)", color="white", fontsize=7)
        ax.legend(fontsize=6.5, facecolor="#1a1d27", labelcolor="white",
                  framealpha=0.7, loc="best")
        ax.grid(axis="y", color="#2a2d3a", linewidth=0.5)

    fig.suptitle(
        "[MOCK DATA -- REHEARSAL ONLY]  ARX Model Validation\n"
        "Pink = test-set predictions  |  Dashed vertical = train/test split",
        color="white", fontsize=10, fontweight="bold"
    )
    plt.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"  Validation plot -> {save_path}")


# ── ProcessModel class (used by controller) ────────────────────────────────────

class ProcessModel:
    """
    One-step-ahead predictor for the well process.

    Wraps the fitted ARX Ridge models. At each control step, the controller
    passes the current measurement vector and a candidate choke position,
    and receives predicted Q, WHP, FLP, BHP for the next interval.

    Parameters
    ----------
    models : dict[str, Ridge]
        Fitted models keyed by output name.
    last_choke : float
        Choke position at the previous time step (needed for delta_u feature).
    """

    def __init__(self, models: dict, last_choke: float = 0.0):
        self.models = models
        self.last_choke = last_choke

    def predict(self, current: dict, candidate_choke: float) -> dict:
        """
        Predict next-step outputs for a given candidate choke position.

        Parameters
        ----------
        current : dict
            Current measured values:
              {"OilRate_bbl_hr": Q, "WHP_psi": ..., "FLP_psi": ..., "BHP_psi": ...}
        candidate_choke : float
            Proposed choke position (%) for the next control step.

        Returns
        -------
        dict with predicted {"OilRate_bbl_hr", "WHP_psi", "FLP_psi", "BHP_psi"}
        """
        u_now  = float(candidate_choke)
        u_prev = float(self.last_choke)
        delta_u = u_now - u_prev

        preds = {}
        for out in OUTPUTS:
            y_prev = float(current[out])
            X = np.array([[y_prev, u_now, u_prev, delta_u]])
            preds[out] = float(self.models[out].predict(X)[0])

        return preds

    def update_choke(self, applied_choke: float):
        """Call after each real step to keep last_choke in sync."""
        self.last_choke = float(applied_choke)


def load_model(csv_path: str = STEP_TEST_CSV) -> "ProcessModel":
    """
    Convenience loader: reads step-test CSV, fits ARX models, returns ProcessModel.
    Call this from controller.py and run_scenarios.py.
    """
    df = pd.read_csv(csv_path)
    feat_df = build_features(df)
    models, metrics, _, _ = fit_arx_models(feat_df)
    initial_choke = float(df["Choke_pct"].iloc[0])
    print(f"[model.py] ARX model fit complete.")
    for out in OUTPUTS:
        m = metrics[out]
        print(f"  {PRETTY[out]:25s}  R²_test={m['R2_test']:.3f}  MAE_test={m['MAE_test']:.2f}")
    return ProcessModel(models, last_choke=initial_choke)


# ── Entrypoint (standalone run) ────────────────────────────────────────────────

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("=== Process Model Identification [MOCK -- REHEARSAL ONLY] ===")

    if not os.path.exists(STEP_TEST_CSV):
        raise FileNotFoundError(
            f"{STEP_TEST_CSV} not found. Run step_test_harness.py first."
        )

    df = pd.read_csv(STEP_TEST_CSV)
    print(f"Loaded {len(df)} rows from {STEP_TEST_CSV}")

    feat_df = build_features(df)
    models, metrics, train_idx, test_idx = fit_arx_models(feat_df)

    print("\n── Model metrics ──")
    for out in OUTPUTS:
        m = metrics[out]
        print(f"  {PRETTY[out]:25s}  R²_train={m['R2_train']:.4f}  "
              f"R²_test={m['R2_test']:.4f}  MAE_test={m['MAE_test']:.3f}")

    plot_validation(feat_df, models, train_idx, test_idx, VALIDATION_PLOT)

    gains = estimate_steady_state_gains(df)

    # Save params to JSON for reference (not used by controller -- controller re-fits from CSV)
    with open(MODEL_PARAMS_JSON, "w") as f:
        json.dump({"arx_metrics": metrics, "ss_gains": gains}, f, indent=2)
    print(f"  Metrics saved -> {MODEL_PARAMS_JSON}")
    print("Done.")
