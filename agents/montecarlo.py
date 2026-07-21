"""The quantitative engine: a mean-reverting jump-diffusion for Brent, Monte
Carlo'd to a tail-risk readout on price, reserve cover, and cost.

Why mean-reverting and not plain Merton: commodity prices revert toward a
production-cost level, so geometric-Brownian-plus-jump overstates how long a
spike persists. The jump is calibrated on real supply shocks (config.JUMP_
ARCHETYPES); the detector picks the archetype by the severity of the live
signal. We do NOT sample a Poisson arrival time — the signal layer already
observed the jump forming, so we only size it.

10k vectorised numpy paths run in milliseconds, so this never touches the
47-second clock. Everything is transparent and every knob is in config.

The economic cascade (price -> supply shortfall -> reserve cover -> cost) is a
SIMPLIFIED elasticity, and says so. A beautiful distribution through a toy
cascade is still a toy; we report confidence intervals and never claim false
precision.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np

from . import config


def _pctiles(arr: np.ndarray, scale: float = 1.0, nd: int = 2) -> dict:
    return {
        "p5": round(float(np.percentile(arr, 5)) * scale, nd),
        "p25": round(float(np.percentile(arr, 25)) * scale, nd),
        "p50": round(float(np.percentile(arr, 50)) * scale, nd),
        "p75": round(float(np.percentile(arr, 75)) * scale, nd),
        "p95": round(float(np.percentile(arr, 95)) * scale, nd),
    }


def simulate(
    brent_spot: float,
    jump_type: str,
    *,
    corridor_share: float,
    india_daily_bbl: float,
    assumptions: Optional[dict] = None,
    seed: int = 0,
) -> dict:
    """Run the price-shock simulation + cascade and return a distribution.

    corridor_share : fraction of India's crude that transits the disrupted
                     corridor (derived live from the knowledge graph).
    india_daily_bbl: India's crude imports in barrels/day (from PPAC).
    """
    a = {**config.ASSUMPTIONS, **(assumptions or {})}
    arch = config.JUMP_ARCHETYPES[jump_type]
    n = int(a["n_paths"])
    H = int(a["horizon_days"])
    rng = np.random.default_rng(seed)

    x0 = math.log(brent_spot)
    # Jump size as a fraction of price, clipped at 0 (shocks push Brent up).
    J = np.clip(rng.normal(arch["jump_mean"], arch["jump_sd"], n), 0.0, None)

    # Reversion anchor: mean-reverting decays back to the pre-shock level;
    # persistent settles at an elevated level (a regime shift that sticks).
    theta = x0 + np.log1p(J * arch["persist_fraction"])
    kappa = math.log(2.0) / arch["reversion_half_life_days"]
    sigma = a["brent_daily_vol"]

    x = x0 + np.log1p(J)              # apply the observed jump immediately
    price_sum = np.zeros(n)
    for _ in range(H):
        z = rng.standard_normal(n)
        x = x + kappa * (theta - x) + sigma * z
        price_sum += np.exp(x)

    terminal = np.exp(x)
    mean_price = price_sum / H        # sustained average over the window
    pct_change = terminal / brent_spot - 1.0
    price_delta = np.maximum(mean_price - brent_spot, 0.0)  # $/bbl sustained premium

    # --- economic cascade (SIMPLIFIED elasticity) ---------------------------
    # A larger price jump implies a larger physical shortfall (they share the
    # same underlying disruption). Shortfall is capped by the corridor's share
    # of imports — you can't lose more than flows through it.
    shortfall_frac = np.clip(a["supply_price_coupling"] * J, 0.0, 1.0) * corridor_share
    reroute_lag = a["default_reroute_lag_days"]
    R0 = a["reserve_cover_days"]
    # Reserves cover the daily shortfall until rerouting lands: burn
    # `shortfall_frac` days of cover per day, for `reroute_lag` days.
    cover_after = np.clip(R0 - shortfall_frac * reroute_lag, 0.0, None)

    # Extra daily import bill, in crore rupees/day.
    cost_crore_day = india_daily_bbl * price_delta * a["usd_inr"] / 1e7

    return {
        "n_paths": n,
        "horizon_days": H,
        "jump_type": jump_type,
        "jump_type_label": arch["label"],
        "brent_spot_usd": round(float(brent_spot), 2),
        "median_pct_change": round(float(np.median(pct_change)) * 100, 2),
        "p95_var_pct": round(float(np.percentile(pct_change, 95)) * 100, 2),
        "pct_change": _pctiles(pct_change, scale=100.0),
        "brent_usd": _pctiles(terminal),
        "reserve_cover_days_before": round(R0, 1),
        "reserve_cover_days_after": round(float(np.median(cover_after)), 1),
        "p_cover_below_7": round(float(np.mean(cover_after < 7.0)), 3),
        "cost_inr_crore_per_day": round(float(np.median(cost_crore_day)), 1),
        "cost_inr_crore_per_day_p95": round(float(np.percentile(cost_crore_day, 95)), 1),
        "assumptions": {
            "n_paths": n,
            "horizon_days": H,
            "brent_daily_vol": sigma,
            "usd_inr": a["usd_inr"],
            "reserve_cover_days": R0,
            "supply_price_coupling": a["supply_price_coupling"],
            "reroute_lag_days": reroute_lag,
            "corridor_share": round(corridor_share, 3),
            "india_daily_bbl": round(india_daily_bbl, 0),
            "jump_mean": arch["jump_mean"],
            "jump_sd": arch["jump_sd"],
            "reversion_half_life_days": arch["reversion_half_life_days"],
        },
    }
