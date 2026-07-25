"""
mock_simulator.py — REHEARSAL ONLY (mock data, not real simulator)
--------------------------------------------------------------------
Mimics a naturally flowing oil well with a production choke.
Interface is identical to the real simulator that will be provided:

    Q, WHP, FLP, BHP = simulator.step(choke_position)

Swap the import line in any downstream file from:
    from mock_simulator import WellSimulator
to:
    from real_simulator import WellSimulator   # (or whatever the real module is named)
...and NOTHING else should need to change.

Internal model (do NOT use this in model.py — model.py must be fully data-driven):
- Each output follows a first-order lag toward a choke-dependent steady state.
- Steady states are calibrated so: 30%→~93, 40%→~111, 55%→~140, 65%→~157 bbl/hr
- Pressures decrease as choke opens (physically correct drawdown behavior).
- Mild Gaussian noise is added to all outputs.
- Scenario C: achievable Q tops out ~155 bbl/hr safely (to force infeasibility at high targets).
"""

import numpy as np


# ── Steady-state maps (quadratic fits anchored to reference dataset) ──────────
# These are INTERNAL to the mock. model.py must not read this file.

def _ss_Q(u):
    """Steady-state oil rate (bbl/hr) at choke u (%)."""
    # Anchor: 0%→0, 30%→93, 40%→111, 55%→140, 65%→157, 85%→175, 100%→182
    # Simple quadratic: Q_ss = a*u^2 + b*u  (passes through origin)
    # Fit by inspection of anchors — kept simple deliberately.
    return 2.45 * u - 0.007 * u ** 2   # bbl/hr, domain [0, 100]

def _ss_WHP(u):
    """Steady-state wellhead pressure (psi) at choke u (%)."""
    # WHP decreases from ~450 psi at fully closed to ~230 psi at fully open
    return 450.0 - 2.1 * u + 0.005 * u ** 2

def _ss_FLP(u):
    """Steady-state flowline pressure (psi) at choke u (%)."""
    # FLP follows WHP but offset lower (downstream of choke)
    return 320.0 - 1.8 * u + 0.004 * u ** 2

def _ss_BHP(u):
    """Steady-state bottom hole pressure (psi) at choke u (%)."""
    # BHP draws down as choke opens; higher drawdown = lower BHP
    return 2800.0 - 6.5 * u + 0.02 * u ** 2


# ── Safe operating limits (active constraints — used by controller, NOT mock) ─
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
    Mock naturally flowing well simulator.

    Parameters
    ----------
    tau_Q, tau_WHP, tau_FLP, tau_BHP : float
        First-order time constants (hours) for each output.
        Higher = slower response to choke changes.
    noise_std : dict
        Standard deviation of Gaussian noise per output variable.
    dt : float
        Control interval in hours (default 1 hr, matching problem spec).
    seed : int or None
        RNG seed for reproducibility.
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
    ):
        self.tau = {"Q": tau_Q, "WHP": tau_WHP, "FLP": tau_FLP, "BHP": tau_BHP}
        self.dt = dt
        self.rng = np.random.default_rng(seed)

        if noise_std is None:
            noise_std = {"Q": 0.8, "WHP": 1.2, "FLP": 0.9, "BHP": 3.5}
        self.noise_std = noise_std

        # Discrete-time first-order lag coefficients: y[k] = alpha*y[k-1] + (1-alpha)*y_ss
        self._alpha = {
            k: np.exp(-dt / self.tau[k]) for k in self.tau
        }

        self._state = None  # will be set on reset()
        self._choke = None
        self._time = 0.0
        self.reset()

    def reset(self, initial_choke: float = 0.0):
        """
        Reset simulator to initial conditions.

        Parameters
        ----------
        initial_choke : float
            Starting choke position (%). Default 0 (well shut-in).
        """
        u = float(np.clip(initial_choke, 0.0, 100.0))
        self._choke = u
        self._time = 0.0
        # Initialize states at steady state of initial choke (clean, no noise)
        self._state = {
            "Q":   _ss_Q(u),
            "WHP": _ss_WHP(u),
            "FLP": _ss_FLP(u),
            "BHP": _ss_BHP(u),
        }

    def step(self, choke_position: float):
        """
        Advance simulator by one control interval (dt hours).

        Parameters
        ----------
        choke_position : float
            Desired choke opening (%). Will be clipped to [0, 100].

        Returns
        -------
        Q : float   — Oil flow rate (bbl/hr)
        WHP : float — Wellhead pressure (psi)
        FLP : float — Flowline pressure (psi)
        BHP : float — Bottom hole pressure (psi)
        """
        u = float(np.clip(choke_position, 0.0, 100.0))
        self._choke = u
        self._time += self.dt

        targets = {
            "Q":   _ss_Q(u),
            "WHP": _ss_WHP(u),
            "FLP": _ss_FLP(u),
            "BHP": _ss_BHP(u),
        }

        results = {}
        for var, alpha in self._alpha.items():
            clean = alpha * self._state[var] + (1.0 - alpha) * targets[var]
            noisy = clean + self.rng.normal(0.0, self.noise_std[var])
            self._state[var] = clean   # evolve state without noise accumulation
            results[var] = noisy

        Q   = float(results["Q"])
        WHP = float(results["WHP"])
        FLP = float(results["FLP"])
        BHP = float(results["BHP"])
        return Q, WHP, FLP, BHP

    @property
    def time(self) -> float:
        """Current simulation time (hours)."""
        return self._time

    @property
    def choke(self) -> float:
        """Last commanded choke position (%)."""
        return self._choke


if __name__ == "__main__":
    # Smoke test — prints 5 steps at choke=40%
    sim = WellSimulator(seed=0)
    sim.reset(initial_choke=0.0)
    print(f"{'t':>4}  {'Q':>8}  {'WHP':>8}  {'FLP':>8}  {'BHP':>8}")
    for _ in range(5):
        Q, WHP, FLP, BHP = sim.step(40.0)
        print(f"{sim.time:>4.0f}  {Q:>8.2f}  {WHP:>8.2f}  {FLP:>8.2f}  {BHP:>8.2f}")
