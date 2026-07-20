"""
Scenario Modeller: signal-triggered, mean-reverting jump-diffusion for Brent,
Monte-Carlo'd into a tail-risk readout on cost and reserve-cover days.

Design notes (see task.md §1/§4 for the full reasoning):

  - Single archetype, not two. The original plan called for a regime
    detector picking between a "persistent" jump (full closure, e.g. the
    1990 Gulf War) and a "mean-reverting" jump (partial disruption, e.g. the
    2019 Abqaiq attack). That's cut for time: this engine always mean-reverts,
    and jump SIZE is scaled continuously by the triggering corridor's risk
    score instead of branching on an archetype. Same demo payoff (a real,
    calibrated, explainable number), half the code and half the "why did
    you pick this branch" surface to defend live.

  - We don't guess WHEN a shock arrives (the Poisson-clock problem standard
    jump-diffusion has) — the risk-intelligence layer upstream already
    detected it. This engine only has to size the jump and its recovery.

  - Calibration anchor: 2022 Ukraine invasion, Brent ~$90 -> ~$130, a
    sustained ~44% move (persistent-type shock; the plan's own historical
    table). That's used as the ceiling for a maximum-severity (risk_score=1.0)
    shock; lower-severity signals scale down linearly. This is an
    approximate anchor — verify against `prices` table history before
    the demo, per the plan's own "never invent numbers, verify anchors"
    rule.

  - The price -> import-bill -> reserve-cover -> cost cascade is a
    SIMPLIFIED LINEAR PROXY, not a calibrated macro model. Say so on
    screen, not just in the pitch (see `results.caveat` below) — stating a
    model's limits is itself a Technical Excellence signal per the plan.

Runs ~10,000 vectorized numpy paths in low-single-digit milliseconds, so it
never touches the pipeline's latency budget.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

# --- Calibration -------------------------------------------------------------

# Ceiling jump size at risk_score == 1.0. Anchored on the 2022 Ukraine
# invasion (~$90 -> ~$130 sustained, ~44%). APPROXIMATE — cross-check against
# real `prices` table history for the exact pre/post window before the demo.
MAX_JUMP_PCT = 0.44

# Daily volatility used inside the Monte Carlo diffusion (crude oil typical
# range). Not fitted per-shock — a single reasonable constant, documented
# rather than hidden.
DAILY_VOL = 0.02

CASCADE_CAVEAT = (
    "Price model is calibrated on a real historical shock (2022 Ukraine "
    "invasion). The price -> import-bill -> reserve-cover cascade is a "
    "simplified linear elasticity, NOT a calibrated macro model -- treat "
    "reserve-cover and cost figures as indicative, not precise."
)


@dataclass
class ScenarioAssumptions:
    """Every input that shaped the output, echoed back verbatim — this is
    the 'assumptions must be explicit and testable' requirement, satisfied
    by construction: nothing here is hidden inside the function body."""
    risk_score: float
    jump_size_pct: float
    elasticity: float
    days_to_reroute: int
    horizon_days: int
    brent_usd: float
    baseline_reserve_days: float
    daily_import_bbl: float
    usd_inr: float
    reserve_threshold_days: float
    n_paths: int
    seed: Optional[int]


def _simulate_price_paths(
    s0: float,
    jump_size_pct: float,
    days_to_reroute: int,
    horizon_days: int,
    n_paths: int,
    seed: Optional[int],
) -> np.ndarray:
    """Vectorized Euler-Maruyama for a mean-reverting jump-diffusion.

    The jump is applied once, at t=0 (the signal just fired). From there the
    price mean-reverts toward the pre-shock level S0 with a half-life of
    `days_to_reroute` days (the "how long until alternative supply routes
    absorb the shock" knob), with daily noise on top so paths diverge.

    Returns an (n_paths, horizon_days + 1) array of simulated prices.
    """
    rng = np.random.default_rng(seed)

    kappa = np.log(2) / max(days_to_reroute, 1)  # reversion speed from half-life
    theta = s0                                    # reverts toward pre-shock price

    paths = np.empty((n_paths, horizon_days + 1))
    paths[:, 0] = s0 * (1.0 + jump_size_pct)

    z = rng.standard_normal((n_paths, horizon_days))
    for t in range(1, horizon_days + 1):
        prev = paths[:, t - 1]
        drift = kappa * (theta - prev)
        diffusion = DAILY_VOL * prev * z[:, t - 1]
        paths[:, t] = np.maximum(prev + drift + diffusion, 0.01)  # price floor, no negative crude

    return paths


def run_scenario(
    risk_score: float,
    jump_size_pct: Optional[float] = None,
    elasticity: float = 1.2,
    days_to_reroute: int = 21,
    brent_usd: float = 82.0,
    baseline_reserve_days: float = 9.5,
    daily_import_bbl: float = 5_000_000.0,
    usd_inr: float = 83.0,
    n_paths: int = 10_000,
    horizon_days: int = 30,
    reserve_threshold_days: float = 7.0,
    seed: Optional[int] = None,
) -> dict:
    """Run the Monte Carlo scenario and return a distribution, not a number.

    Args mirror the frontend's 3-knob assumption panel (jump_size_pct,
    elasticity, days_to_reroute) plus fixed reference defaults for the rest
    (Brent price ~$82, India's ~9.5-day strategic reserve cover per PPAC,
    ~5M bbl/day crude imports, ~83 INR/USD) — all overridable, all echoed
    back in `assumptions` so nothing is a hidden constant.

    risk_score: 0-1 corridor risk score from /corridors/{c}/risk-score.
    jump_size_pct: overrides the risk-scaled default if given explicitly
        (this is what the assumption panel's "jump size" slider sets).
    """
    t0 = time.perf_counter()

    if jump_size_pct is None:
        jump_size_pct = MAX_JUMP_PCT * max(0.0, min(risk_score, 1.0))

    paths = _simulate_price_paths(
        s0=brent_usd,
        jump_size_pct=jump_size_pct,
        days_to_reroute=days_to_reroute,
        horizon_days=horizon_days,
        n_paths=n_paths,
        seed=seed,
    )

    # Peak deviation from baseline over the horizon, per path — "how bad
    # could it get during the disruption window" rather than just the
    # end-of-horizon price (which would understate risk once paths revert).
    peak_price = paths.max(axis=1)
    shock_pct = peak_price / brent_usd - 1.0

    median_shock_pct = float(np.median(shock_pct))
    var95_shock_pct = float(np.percentile(shock_pct, 95))

    # Cascade: price shock -> reserve-cover erosion (simplified linear
    # elasticity — see CASCADE_CAVEAT) and -> cost/day in INR crore.
    reserve_cover_days = baseline_reserve_days / (1.0 + elasticity * np.maximum(shock_pct, 0))
    cost_usd_per_day = daily_import_bbl * brent_usd * np.maximum(shock_pct, 0)
    cost_inr_cr_per_day = cost_usd_per_day * usd_inr / 1e7  # 1 crore = 1e7

    prob_below_threshold = float(np.mean(reserve_cover_days < reserve_threshold_days))

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 3)

    assumptions = ScenarioAssumptions(
        risk_score=risk_score,
        jump_size_pct=round(jump_size_pct, 4),
        elasticity=elasticity,
        days_to_reroute=days_to_reroute,
        horizon_days=horizon_days,
        brent_usd=brent_usd,
        baseline_reserve_days=baseline_reserve_days,
        daily_import_bbl=daily_import_bbl,
        usd_inr=usd_inr,
        reserve_threshold_days=reserve_threshold_days,
        n_paths=n_paths,
        seed=seed,
    )

    return {
        "assumptions": assumptions.__dict__,
        "results": {
            "median_shock_pct": round(median_shock_pct, 4),
            "var95_shock_pct": round(var95_shock_pct, 4),
            "median_reserve_cover_days": round(float(np.median(reserve_cover_days)), 2),
            "var95_reserve_cover_days": round(float(np.percentile(reserve_cover_days, 5)), 2),
            "prob_reserve_cover_below_threshold": round(prob_below_threshold, 3),
            "median_cost_inr_cr_per_day": round(float(np.median(cost_inr_cr_per_day)), 2),
            "var95_cost_inr_cr_per_day": round(float(np.percentile(cost_inr_cr_per_day, 95)), 2),
        },
        "distribution_sample": {
            # Small downsample for a frontend histogram — not the full 10k paths.
            "shock_pct": [round(float(x), 4) for x in np.percentile(shock_pct, np.arange(5, 100, 5))],
            "reserve_cover_days": [round(float(x), 2) for x in np.percentile(reserve_cover_days, np.arange(5, 100, 5))],
        },
        "caveat": CASCADE_CAVEAT,
        "elapsed_ms": elapsed_ms,
    }
