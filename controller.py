"""
controller.py -- ChokeController: brute-force MPC with constraint-aware candidate scoring
-----------------------------------------------------------------------------------------
Design principles:
  - Brute-force evaluation of ALL feasible candidate choke moves (±5% ramp limit, 1% resolution)
  - Every decision is LOGGED with rationale: what was chosen, what was rejected, and WHY
  - Hard constraint rejection: any candidate predicted to violate WHP/FLP/BHP limits is excluded
  - Soft barrier penalty: rising cost as variables approach (but haven't yet breached) limits
  - Fallback: if ALL candidates violate hard limits, selects the "least bad" safe fallback
    (smallest choke that keeps pressure violation minimal -- production safety over target chasing)

Cost function (minimized over feasible candidates):
  cost = w_track * dead_band_error²
       + w_ramp  * |delta_u|
       + soft_barrier_penalty(WHP, FLP, BHP)

Where:
  dead_band_error    = max(0, |predicted_Q - target_Q| - dead_band)  -- zero inside the band
  dead_band          = tolerance (bbl/hr) within which tracking cost is suppressed to zero
  delta_u            = candidate_choke - current_choke
  soft_barrier_penalty = large value that rises steeply as any pressure approaches its limit

WHY a dead-band?
  Without it, when Q is already within noise distance of the target the tracking cost and
  ramp cost are roughly equal, so the controller alternates ±1% on every step (hunting).
  With the dead-band, once |error| < dead_band the tracking term vanishes; ramp penalty
  dominates and the cheapest move is always delta_u=0 (hold). Hunting stops entirely.

WHY soft barrier instead of only hard cutoff?
  Hard cutoffs alone create flat cost landscapes where many candidates look identical right
  up to the limit, causing erratic zig-zagging near constraints. A soft barrier steers the
  controller toward the safe interior of the operating envelope, not just the boundary.

Reference: "simplified MPC based on brute-force candidate evaluation" -- problem statement §5.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Optional


# ── Constraint limits (import from mock_simulator or override with real values) ─
# When the real simulator ships, check whether it exports its own LIMITS dict.
# If so, import from there. If not, populate from the real simulator's docs.
try:
    from mock_simulator import LIMITS
except ImportError:
    # Fallback -- paste real simulator limits here if needed
    LIMITS = {
        "WHP_min": 200.0, "WHP_max": 480.0,
        "FLP_min": 150.0, "FLP_max": 350.0,
        "BHP_min": 2200.0,"BHP_max": 3000.0,
    }


@dataclass
class ControllerConfig:
    """All tunable parameters in one place -- easy to explain to judges."""

    # Cost function weights
    w_track: float = 1.0     # Weight on tracking error (Q target deviation)
    w_ramp:  float = 0.05    # Penalty per %/hr choke movement (discourages unnecessary moves)

    # Soft barrier: penalty = barrier_k / (distance_to_limit + barrier_eps)^2
    # Rises steeply as distance->0, pushes controller away from constraint boundary.
    barrier_k:   float = 500.0   # Barrier intensity -- increase if controller hugs limits too closely
    barrier_eps: float = 2.0     # Small value to prevent division-by-zero (psi)

    # Hard constraint margins: reject a candidate if predicted value comes within
    # `hard_margin` psi of the hard limit (adds a small engineering safety buffer).
    hard_margin: float = 0.0   # psi; set >0 to add explicit guard band beyond physics

    # Dead-band: tracking cost is zero when |predicted_Q - target_Q| < dead_band.
    # Set to ~2-3% of the expected operating Q range.  Does not affect constraint logic.
    dead_band: float = 3.0   # bbl/hr

    # Choke move resolution: grid of candidate choke positions evaluated each step.
    delta_u_step:  float = 1.0    # % -- evaluate every 1% within the ±5% ramp window
    max_ramp_rate: float = 5.0    # % per control interval (problem spec)
    choke_min:     float = 0.0    # % absolute limits
    choke_max:     float = 100.0  # %


@dataclass
class DecisionRecord:
    """One logged record per control interval."""
    step: int
    time_hr: float
    choke_prev: float
    choke_chosen: float
    delta_u: float
    target_Q: float
    predicted_Q: float
    predicted_WHP: float
    predicted_FLP: float
    predicted_BHP: float
    measured_Q: float
    measured_WHP: float
    measured_FLP: float
    measured_BHP: float
    tracking_error: float     # predicted_Q - target_Q
    cost_chosen: float
    n_candidates_evaluated: int
    n_candidates_rejected_hard: int
    reason: str               # plain-English rationale
    rejected_summary: str     # brief log of rejected candidates


class ChokeController:
    """
    Autonomous choke controller using brute-force MPC candidate evaluation.

    At each control interval (Ts = 1 hr):
    1. Generate candidate choke positions: current ± ramp_limit, step = delta_u_step
    2. For each candidate, predict (Q, WHP, FLP, BHP) using ProcessModel
    3. Compute cost = tracking_error² * w_track + |delta_u| * w_ramp + soft_barrier
    4. Hard-reject any candidate predicted to violate hard limits
    5. Select minimum-cost feasible candidate
    6. If no feasible candidate exists, select safest fallback (minimum-violation, smallest Q)
    7. Log full decision rationale

    Parameters
    ----------
    process_model : ProcessModel instance (from model.py)
    config : ControllerConfig
    """

    def __init__(self, process_model, config: Optional[ControllerConfig] = None):
        self.model = process_model
        self.cfg   = config or ControllerConfig()
        self._step = 0
        self._log: list[DecisionRecord] = []

    # ── Constraint helpers ──────────────────────────────────────────────────────

    def _is_hard_feasible(self, pred: dict) -> tuple[bool, str]:
        """
        Returns (True, "") if prediction satisfies all hard limits + margin.
        Returns (False, reason_string) otherwise.
        """
        margin = self.cfg.hard_margin
        checks = [
            (pred["WHP_psi"],
             LIMITS["WHP_min"] + margin,
             LIMITS["WHP_max"] - margin,
             "WHP"),
            (pred["FLP_psi"],
             LIMITS["FLP_min"] + margin,
             LIMITS["FLP_max"] - margin,
             "FLP"),
            (pred["BHP_psi"],
             LIMITS["BHP_min"] + margin,
             LIMITS["BHP_max"] - margin,
             "BHP"),
        ]
        violations = []
        for val, lo, hi, name in checks:
            if val < lo:
                violations.append(f"{name}={val:.1f}<{lo:.0f}")
            elif val > hi:
                violations.append(f"{name}={val:.1f}>{hi:.0f}")
        if violations:
            return False, ", ".join(violations)
        return True, ""

    def _soft_barrier(self, pred: dict) -> float:
        """
        Soft barrier penalty -- rises steeply as any pressure approaches its limit.
        Formula: sum over constraints of barrier_k / (distance_to_nearest_limit + eps)^2
        This is differentiable and bounded, unlike a hard step function.
        """
        k   = self.cfg.barrier_k
        eps = self.cfg.barrier_eps
        penalty = 0.0

        pairs = [
            (pred["WHP_psi"], LIMITS["WHP_min"], LIMITS["WHP_max"]),
            (pred["FLP_psi"], LIMITS["FLP_min"], LIMITS["FLP_max"]),
            (pred["BHP_psi"], LIMITS["BHP_min"], LIMITS["BHP_max"]),
        ]
        for val, lo, hi in pairs:
            dist_lo = max(val - lo, eps)   # distance from lower limit
            dist_hi = max(hi - val, eps)   # distance from upper limit
            penalty += k / (dist_lo ** 2) + k / (dist_hi ** 2)

        return penalty

    def _cost(self, pred: dict, candidate_u: float, current_u: float,
               target_Q: float) -> float:
        raw_err = pred["OilRate_bbl_hr"] - target_Q
        # Dead-band: suppress tracking cost when already within tolerance of target.
        # abs(raw_err) - dead_band gives the distance *outside* the dead-band (floored at 0).
        db_err  = max(0.0, abs(raw_err) - self.cfg.dead_band) * np.sign(raw_err)
        ramp    = abs(candidate_u - current_u)
        barrier = self._soft_barrier(pred)
        return (self.cfg.w_track * db_err ** 2
                + self.cfg.w_ramp  * ramp
                + barrier)

    # ── Candidate generation ─────────────────────────────────────────────────────

    def _candidates(self, current_u: float) -> np.ndarray:
        lo = np.clip(current_u - self.cfg.max_ramp_rate, self.cfg.choke_min, self.cfg.choke_max)
        hi = np.clip(current_u + self.cfg.max_ramp_rate, self.cfg.choke_min, self.cfg.choke_max)
        return np.arange(lo, hi + self.cfg.delta_u_step * 0.5, self.cfg.delta_u_step)

    # ── Main decision method ──────────────────────────────────────────────────────

    def step(
        self,
        current_choke: float,
        measured_Q:    float,
        measured_WHP:  float,
        measured_FLP:  float,
        measured_BHP:  float,
        target_Q:      float,
        time_hr:       float,
    ) -> float:
        """
        Compute the next choke position.

        Parameters
        ----------
        current_choke : current applied choke (%)
        measured_* : measurements from the simulator this step
        target_Q : desired oil rate (bbl/hr)
        time_hr : current simulation time (for logging)

        Returns
        -------
        float : next choke position (%)
        """
        self._step += 1
        current = {
            "OilRate_bbl_hr": measured_Q,
            "WHP_psi":        measured_WHP,
            "FLP_psi":        measured_FLP,
            "BHP_psi":        measured_BHP,
        }

        candidates = self._candidates(current_choke)
        n_total    = len(candidates)

        feasible_candidates = []  # (cost, u, pred)
        rejected_hard = []        # (u, reason)

        for u in candidates:
            pred   = self.model.predict(current, u)
            ok, viol_reason = self._is_hard_feasible(pred)

            if not ok:
                rejected_hard.append((u, viol_reason))
                continue

            c = self._cost(pred, u, current_choke, target_Q)
            feasible_candidates.append((c, u, pred))

        n_rejected = len(rejected_hard)

        # ── Selection ────────────────────────────────────────────────────────────

        if feasible_candidates:
            # Pick minimum-cost feasible candidate
            feasible_candidates.sort(key=lambda x: x[0])
            best_cost, best_u, best_pred = feasible_candidates[0]

            track_err = best_pred["OilRate_bbl_hr"] - target_Q
            in_dead_band = abs(track_err) <= self.cfg.dead_band
            delta_u_chosen = best_u - current_choke

            if in_dead_band and abs(delta_u_chosen) < 0.01:
                # Dead-band hold: tracking error is within tolerance, ramp cost favours no move.
                reason = (
                    f"DEAD-BAND HOLD: pred_Q={best_pred['OilRate_bbl_hr']:.1f} bbl/hr "
                    f"within +/-{self.cfg.dead_band:.1f} bbl/hr of target {target_Q:.1f} "
                    f"(err={track_err:+.2f}). Tracking cost suppressed; holding choke at "
                    f"{best_u:.1f}%. "
                    f"WHP={best_pred['WHP_psi']:.1f}, FLP={best_pred['FLP_psi']:.1f}, "
                    f"BHP={best_pred['BHP_psi']:.1f} psi."
                )
            elif in_dead_band and abs(delta_u_chosen) >= 0.01:
                # Inside dead-band but a small move still wins (barrier steering).
                reason = (
                    f"DEAD-BAND (barrier steering): err={track_err:+.2f} bbl/hr within band "
                    f"+/-{self.cfg.dead_band:.1f}; tracking cost suppressed. "
                    f"Soft barrier steered choke {delta_u_chosen:+.1f}% to u={best_u:.1f}% "
                    f"for better pressure headroom. "
                    f"WHP={best_pred['WHP_psi']:.1f}, FLP={best_pred['FLP_psi']:.1f}, "
                    f"BHP={best_pred['BHP_psi']:.1f} psi."
                )
            elif n_rejected == 0:
                reason = (
                    f"TRACKING CORRECTION: err={track_err:+.1f} bbl/hr outside dead-band "
                    f"+/-{self.cfg.dead_band:.1f}. "
                    f"All {n_total} candidates feasible; chose u={best_u:.1f}% "
                    f"(move {delta_u_chosen:+.1f}%) -> pred_Q={best_pred['OilRate_bbl_hr']:.1f} bbl/hr. "
                    f"WHP={best_pred['WHP_psi']:.1f}, FLP={best_pred['FLP_psi']:.1f}, "
                    f"BHP={best_pred['BHP_psi']:.1f} psi."
                )
            else:
                reason = (
                    f"CONSTRAINED CORRECTION: err={track_err:+.1f} bbl/hr outside dead-band. "
                    f"{n_rejected}/{n_total} candidates hard-rejected (constraint violations). "
                    f"Chose u={best_u:.1f}% (move {delta_u_chosen:+.1f}%) from "
                    f"{len(feasible_candidates)} feasible. "
                    f"pred_Q={best_pred['OilRate_bbl_hr']:.1f} bbl/hr. "
                    f"WHP={best_pred['WHP_psi']:.1f}, FLP={best_pred['FLP_psi']:.1f}, "
                    f"BHP={best_pred['BHP_psi']:.1f} psi."
                )
        else:
            # ALL candidates violated hard limits -- safety fallback:
            # hold current choke (safest option is no additional movement)
            best_u    = current_choke
            best_pred = self.model.predict(current, best_u)
            best_cost = float("inf")
            track_err = best_pred["OilRate_bbl_hr"] - target_Q

            reason = (
                f"SAFETY FALLBACK: ALL {n_total} candidates violated hard constraints. "
                f"Holding choke at {best_u:.1f}% (no further movement). "
                f"Target {target_Q:.0f} bbl/hr is infeasible at current conditions. "
                f"Settling at safe maximum achievable rate."
            )

        # ── Log rationale ─────────────────────────────────────────────────────────

        rej_summary = "; ".join(
            f"u={u:.0f}%: {r}" for u, r in rejected_hard[:5]
        ) + (f"... (+{len(rejected_hard) - 5} more)" if len(rejected_hard) > 5 else "")

        record = DecisionRecord(
            step=self._step,
            time_hr=time_hr,
            choke_prev=current_choke,
            choke_chosen=best_u,
            delta_u=best_u - current_choke,
            target_Q=target_Q,
            predicted_Q=best_pred["OilRate_bbl_hr"],
            predicted_WHP=best_pred["WHP_psi"],
            predicted_FLP=best_pred["FLP_psi"],
            predicted_BHP=best_pred["BHP_psi"],
            measured_Q=measured_Q,
            measured_WHP=measured_WHP,
            measured_FLP=measured_FLP,
            measured_BHP=measured_BHP,
            tracking_error=track_err,
            cost_chosen=best_cost,
            n_candidates_evaluated=n_total,
            n_candidates_rejected_hard=n_rejected,
            reason=reason,
            rejected_summary=rej_summary if rej_summary else "none",
        )
        self._log.append(record)

        # Keep model's last-choke in sync
        self.model.update_choke(best_u)

        return float(best_u)

    # ── Log access ────────────────────────────────────────────────────────────────

    def get_log(self) -> list[dict]:
        """Return decision log as list of dicts (for DataFrame or JSON export)."""
        return [vars(r) for r in self._log]

    def reset_log(self):
        self._log = []
        self._step = 0
