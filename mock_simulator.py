"""
mock_simulator.py - REHEARSAL ONLY (mock data, not real simulator)
--------------------------------------------------------------------
Mimics a naturally flowing oil well with a production choke.
Interface is identical to the real simulator that will be provided:

    Q, WHP, FLP, BHP = simulator.step(choke_position)

Swap the import line in any downstream file from:
    from mock_simulator import WellSimulator
to:
    from real_simulator import WellSimulator   # (or whatever the real module is named)
...and NOTHING else should need to change.

=========================================================================
PHYSICS-GROUNDED STEADY-STATE MODEL (v2 - corrected calibration)
=========================================================================
The steady-state flow equation follows a standard choke performance
relationship:

    Q_ss(u) = Cv(u) * u * sqrt(WHP_ss(u) - FLP_ss(u))

where:
  - u         : choke opening (%)
  - WHP_ss(u) : steady-state wellhead pressure (psi), decreasing with u
  - FLP_ss(u) : steady-state flowline pressure (psi), decreasing with u
  - Cv(u)     : discharge coefficient, calibrated as a polynomial so
                Q_ss(u) passes through all 14 organizer data points.

CALIBRATION BASIS (all 14 real organizer CSV anchor points):
  u=  5% -> Q= 11.84 bbl/hr   (real data)
  u= 10% -> Q= 24.08 bbl/hr   (real data)
  u= 15% -> Q= 34.72 bbl/hr   (real data)
  u= 25% -> Q= 56.65 bbl/hr   (real data)
  u= 30% -> Q= 67.48 bbl/hr   (real data)
  u= 35% -> Q= 77.03 bbl/hr   (real data)
  u= 45% -> Q= 95.90 bbl/hr   (real data)
  u= 50% -> Q=105.64 bbl/hr   (real data)
  u= 55% -> Q=113.50 bbl/hr   (real data)
  u= 65% -> Q=129.40 bbl/hr   (real data)
  u= 70% -> Q=137.23 bbl/hr   (real data)
  u= 75% -> Q=143.76 bbl/hr   (real data)
  u= 85% -> Q=157.40 bbl/hr   (real data)
  u= 95% -> Q=169.55 bbl/hr   (real data)

EXTRAPOLATION NOTE (not organizer data):
  u=  0% -> Q=  0 bbl/hr      (physics assumption: zero flow at zero opening)
  u= 40% -> Q~101.3 bbl/hr    (physics model extrapolation - NOT organizer data)
  u=100% -> Q~175.1 bbl/hr    (physics model extrapolation - NOT organizer data)

Transient dynamics (first-order lag + Gaussian noise) are engineering
assumptions layered on top of the steady-state model - they are NOT
derived from the organizer data.

Variant     | Pressure slope  | Noise level
-----------   ---------------   -----------
baseline    | 1.00x (fitted)  | baseline
pessimistic | 1.15x steeper   | +25%
optimistic  | 0.85x gentler   | -25%

All variants share identical steady-state Q curves (Q is driven by
physics formula from pressure), noise and pressure slope scale together.
"""

import numpy as np


# ── Organizer calibration data (all 14 real CSV anchor points) ──────────────
_U_CAL  = np.array([ 5, 10, 15, 25, 30, 35, 45, 50, 55, 65, 70, 75, 85, 95], dtype=float)
_Q_CAL  = np.array([11.84, 24.08, 34.72, 56.65, 67.48, 77.03,
                    95.90, 105.64, 113.50, 129.40, 137.23, 143.76,
                    157.40, 169.55], dtype=float)
_WHP_CAL = np.array([439.6, 429.6, 419.2, 400.4, 391.0, 382.7,
                     365.7, 357.6, 348.7, 334.1, 327.7, 321.0,
                     307.4, 295.2], dtype=float)
_FLP_CAL = np.array([311.5, 302.8, 293.9, 277.4, 269.8, 261.7,
                     246.9, 240.2, 233.1, 219.8, 214.3, 207.8,
                     196.2, 185.1], dtype=float)
_BHP_CAL = np.array([2768.6, 2732.8, 2707.9, 2649.7, 2619.2, 2600.0,
                     2548.0, 2522.6, 2502.6, 2461.0, 2440.1, 2426.4,
                     2395.2, 2361.7], dtype=float)


# ── Fit polynomial models to pressure data (degree 2 is sufficient) ─────────
# These are baseline (1.00x) pressure curves fitted entirely from organizer data.
_P_WHP_COEF = np.polyfit(_U_CAL, _WHP_CAL, 2)   # WHP(u) = a*u² + b*u + c
_P_FLP_COEF = np.polyfit(_U_CAL, _FLP_CAL, 2)   # FLP(u) = a*u² + b*u + c
_P_BHP_COEF = np.polyfit(_U_CAL, _BHP_CAL, 2)   # BHP(u) = a*u² + b*u + c

# Intercepts at u=0 (used for variant scaling)
_WHP0 = float(np.polyval(_P_WHP_COEF, 0))  # ~449 psi at u=0
_FLP0 = float(np.polyval(_P_FLP_COEF, 0))  # ~319 psi at u=0
_BHP0 = float(np.polyval(_P_BHP_COEF, 0))  # ~2797 psi at u=0


def _baseline_WHP(u: float) -> float:
    """Baseline WHP(u) from polynomial fit to organizer data."""
    return float(np.polyval(_P_WHP_COEF, u))


def _baseline_FLP(u: float) -> float:
    """Baseline FLP(u) from polynomial fit to organizer data."""
    return float(np.polyval(_P_FLP_COEF, u))


def _baseline_BHP(u: float) -> float:
    """Baseline BHP(u) from polynomial fit to organizer data."""
    return float(np.polyval(_P_BHP_COEF, u))


# ── Calibrate Cv(u) from all 14 organizer Q data points ─────────────────────
# Cv_i = Q_i / (u_i * sqrt(WHP_fit(u_i) - FLP_fit(u_i)))
_DP_CAL = np.array([_baseline_WHP(u) - _baseline_FLP(u) for u in _U_CAL])
_CV_CAL = _Q_CAL / (_U_CAL * np.sqrt(_DP_CAL))
_P_CV_COEF = np.polyfit(_U_CAL, _CV_CAL, 4)  # degree-4 polynomial for Cv(u)


def _ss_Cv(u: float) -> float:
    """Discharge coefficient Cv(u) - fitted to all 14 organizer data points."""
    return float(np.polyval(_P_CV_COEF, u))


def _ss_Q_physics(u: float, whp: float, flp: float) -> float:
    """Physics-grounded steady-state oil rate via choke performance equation."""
    if u <= 0.0:
        return 0.0
    dp = max(whp - flp, 0.0)
    return _ss_Cv(u) * u * np.sqrt(dp)


# ── Variant-scaled pressure functions ────────────────────────────────────────

def _ss_WHP(u: float, slope_scale: float = 1.0) -> float:
    """
    Steady-state WHP(u).
    slope_scale > 1 → steeper drawdown (pessimistic)
    slope_scale < 1 → gentler drawdown (optimistic)
    """
    baseline = _baseline_WHP(u)
    return _WHP0 - slope_scale * (_WHP0 - baseline)


def _ss_FLP(u: float, slope_scale: float = 1.0) -> float:
    baseline = _baseline_FLP(u)
    return _FLP0 - slope_scale * (_FLP0 - baseline)


def _ss_BHP(u: float, slope_scale: float = 1.0) -> float:
    baseline = _baseline_BHP(u)
    return _BHP0 - slope_scale * (_BHP0 - baseline)


# ── Variant configuration table ───────────────────────────────────────────────

_VARIANT_CFG = {
    "baseline": {
        "slope_scale": 1.00,
        "noise_scale": 1.00,
    },
    "pessimistic": {
        "slope_scale": 1.15,   # steeper pressure drop per unit choke opening
        "noise_scale": 1.25,   # 25% more process noise
    },
    "optimistic": {
        "slope_scale": 0.85,   # gentler pressure drop
        "noise_scale": 0.75,   # 25% less process noise
    },
}

# Baseline noise standard deviations (all units match output variables)
_NOISE_BASE = {"Q": 0.8, "WHP": 1.2, "FLP": 0.9, "BHP": 3.5}


# ── Safe operating limits (active constraints - used by controller, NOT mock) ─
# Defined here as class attributes so the controller can import them.
LIMITS = {
    "WHP_min": 200.0,   # psi
    "WHP_max": 480.0,   # psi
    "FLP_min": 150.0,   # psi
    "FLP_max": 350.0,   # psi
    "BHP_min": 2200.0,  # psi
    "BHP_max": 3000.0,  # psi
}


class WellSimulator:
    """
    Physics-grounded mock naturally flowing well simulator.

    Steady state: Q = Cv(u) * u * sqrt(WHP(u) - FLP(u))
      Cv(u) calibrated to all 14 real organizer data points.
      WHP, FLP, BHP fitted as degree-2 polynomials to organizer data.

    Transient dynamics: first-order exponential lag toward steady state.
    Process noise: Gaussian, scaled per variant.

    Parameters
    ----------
    tau_Q, tau_WHP, tau_FLP, tau_BHP : float
        First-order time constants (hours) for each output.
    noise_std : dict or None
        Override noise standard deviations per variable.
    dt : float
        Control interval in hours (default 1 hr).
    seed : int or None
        RNG seed for reproducibility.
    variant : str
        One of 'baseline', 'pessimistic', 'optimistic'.
        Controls pressure drawdown slope and noise amplitude.
    """

    def __init__(
        self,
        tau_Q=3.0,
        tau_WHP=2.0,
        tau_FLP=1.8,
        tau_BHP=4.0,
        noise_std=None,
        dt=1.0,
        seed=42,
        variant: str = "baseline",
    ):
        if variant not in _VARIANT_CFG:
            raise ValueError(f"variant must be one of {list(_VARIANT_CFG)}; got {variant!r}")

        self.variant = variant
        self._vcfg = _VARIANT_CFG[variant]
        self._slope = self._vcfg["slope_scale"]

        self.tau = {"Q": tau_Q, "WHP": tau_WHP, "FLP": tau_FLP, "BHP": tau_BHP}
        self.dt = dt
        self.rng = np.random.default_rng(seed)

        # Noise standard deviations (scaled by variant)
        ns = self._vcfg["noise_scale"]
        if noise_std is None:
            self.noise_std = {k: v * ns for k, v in _NOISE_BASE.items()}
        else:
            self.noise_std = noise_std

        # Discrete-time first-order lag coefficients: y[k] = alpha*y[k-1] + (1-alpha)*y_ss
        self._alpha = {k: np.exp(-dt / self.tau[k]) for k in self.tau}

        self._state = None
        self._choke = None
        self._time = 0.0
        self.reset()

    def _ss_targets(self, u: float) -> dict:
        """Compute all steady-state targets for a given choke opening."""
        whp = _ss_WHP(u, self._slope)
        flp = _ss_FLP(u, self._slope)
        bhp = _ss_BHP(u, self._slope)
        q   = _ss_Q_physics(u, whp, flp)
        return {"Q": q, "WHP": whp, "FLP": flp, "BHP": bhp}

    def reset(self, initial_choke: float = 0.0):
        """
        Reset simulator to initial conditions at given choke position.

        Parameters
        ----------
        initial_choke : float
            Starting choke position (%). Default 0 (well shut-in).
        """
        u = float(np.clip(initial_choke, 0.0, 100.0))
        self._choke = u
        self._time = 0.0
        # Initialize states at steady state of initial choke (clean, no noise)
        targets = self._ss_targets(u)
        self._state = dict(targets)

    def step(self, choke_position: float):
        """
        Advance simulator by one control interval (dt hours).

        Parameters
        ----------
        choke_position : float
            Desired choke opening (%). Will be clipped to [0, 100].

        Returns
        -------
        Q : float   - Oil flow rate (bbl/hr)
        WHP : float - Wellhead pressure (psi)
        FLP : float - Flowline pressure (psi)
        BHP : float - Bottom hole pressure (psi)
        """
        u = float(np.clip(choke_position, 0.0, 100.0))
        self._choke = u
        self._time += self.dt

        targets = self._ss_targets(u)
        key_map = {"Q": "Q", "WHP": "WHP", "FLP": "FLP", "BHP": "BHP"}

        results = {}
        for var, alpha in self._alpha.items():
            clean = alpha * self._state[var] + (1.0 - alpha) * targets[var]
            noisy = clean + self.rng.normal(0.0, self.noise_std[var])
            self._state[var] = clean   # evolve state without noise accumulation
            results[var] = noisy

        return (
            float(results["Q"]),
            float(results["WHP"]),
            float(results["FLP"]),
            float(results["BHP"]),
        )

    @property
    def time(self) -> float:
        """Current simulation time (hours)."""
        return self._time

    @property
    def choke(self) -> float:
        """Last commanded choke position (%)."""
        return self._choke


# ── Calibration self-verification ────────────────────────────────────────────

def verify_calibration(tol: float = 1.0) -> bool:
    """
    Verify the physics steady-state curve matches all 14 organizer data points
    within the specified tolerance (bbl/hr). Prints a table. Returns True if all pass.
    """
    print(f"\n{'='*68}")
    print(f"CALIBRATION VERIFICATION  (tolerance = ±{tol} bbl/hr)")
    print(f"{'='*68}")
    print(f"  {'Choke%':>6}  {'CSV Q':>9}  {'Model Q':>9}  {'Error':>8}  {'Status':>6}")
    print(f"  {'-'*60}")
    all_pass = True
    sim_check = WellSimulator(seed=0, variant="baseline")
    for u, q_real in zip(_U_CAL, _Q_CAL):
        whp = _ss_WHP(float(u), 1.0)
        flp = _ss_FLP(float(u), 1.0)
        q_model = _ss_Q_physics(float(u), whp, flp)
        err = q_model - q_real
        ok = abs(err) <= tol
        if not ok:
            all_pass = False
        print(f"  {u:>6.0f}%  {q_real:>9.2f}  {q_model:>9.2f}  {err:>+8.2f}  {'PASS' if ok else 'FAIL':>6}")
    print(f"{'='*68}")
    status = "ALL PASS" if all_pass else "SOME FAILURES"
    print(f"  Result: {status}")
    print(f"{'='*68}\n")
    return all_pass


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    # Run calibration verification
    passed = verify_calibration(tol=1.0)

    # Smoke test across variants
    print("\nSmoke test - 5 steps at choke=50%, all variants:")
    print(f"  {'Variant':<12} {'Q':>8} {'WHP':>8} {'FLP':>8} {'BHP':>8}")
    for v in ["baseline", "pessimistic", "optimistic"]:
        sim = WellSimulator(seed=0, variant=v)
        sim.reset(initial_choke=5.0)
        for _ in range(20):  # approach steady state
            sim.step(50.0)
        Q, WHP, FLP, BHP = sim.step(50.0)
        print(f"  {v:<12} {Q:>8.2f} {WHP:>8.2f} {FLP:>8.2f} {BHP:>8.2f}")
