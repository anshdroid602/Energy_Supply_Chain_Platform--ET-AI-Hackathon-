"""Agent 2 — Scenario Modeller.

Turns the detected threat into a distribution of impact via a mean-reverting
jump-diffusion + 10k Monte Carlo paths (agents/montecarlo.py). The detector
picks the jump archetype by severity: a Critical corridor gets the persistent
(regime-shift) jump, otherwise the mean-reverting (partial) one.

All maths is numpy and deterministic; the LLM only narrates. The economic
cascade is labelled simplified — we report the intervals, not false precision.
"""
from __future__ import annotations

from .. import montecarlo
from ..schemas import Percentiles, ScenarioResult

SYSTEM = (
    "You are the Scenario Modeller in an energy supply-chain sentinel. In 2-3 "
    "sentences, explain the Monte-Carlo impact for a policymaker in rupees and "
    "days. Lead with the median and the 95% tail. State plainly that the "
    "price->economy cascade is a simplified elasticity. No markdown."
)

CAVEAT = (
    "The Brent price model is calibrated on real supply shocks, but the "
    "price -> supply -> reserve-cover -> cost cascade is a simplified "
    "elasticity. Read the confidence interval, not the point estimate."
)


def make_scenario_node(ds, llm, params):
    def node(state):
        risk = state["risk"]
        corridor = state["corridor"]
        refinery = state["refinery"]

        g = ds.live_graph()
        corridor_share = ds.corridor_import_share(g, corridor, refinery)
        spot = ds.latest_brent()
        daily_bbl = ds.india_daily_crude_bbl()

        # Severity picks the archetype: Critical (>=0.8) -> regime-shift jump.
        jump_type = "persistent" if risk.disruption_probability >= 0.8 else "mean_reverting"

        sim = montecarlo.simulate(
            spot, jump_type,
            corridor_share=corridor_share,
            india_daily_bbl=daily_bbl,
            assumptions=params.get("assumptions"),
        )

        template = (
            f"Median Brent {sim['median_pct_change']:+.0f}% "
            f"(95% VaR {sim['p95_var_pct']:+.0f}%); reserve cover "
            f"{sim['reserve_cover_days_before']:.1f} -> {sim['reserve_cover_days_after']:.1f} days, "
            f"P(cover < 7 days) = {sim['p_cover_below_7']:.2f}. Est. extra import bill "
            f"~Rs.{sim['cost_inr_crore_per_day']:.0f} crore/day (95% ~Rs."
            f"{sim['cost_inr_crore_per_day_p95']:.0f} crore/day). "
            "Price-to-economy cascade is a simplified elasticity."
        )
        facts = (
            f"Corridor: {corridor}; jump archetype: {sim['jump_type_label']}\n"
            f"Brent spot: ${spot:.1f}; paths: {sim['n_paths']}; horizon: {sim['horizon_days']}d\n"
            f"Median Brent change: {sim['median_pct_change']}%; 95% VaR: {sim['p95_var_pct']}%\n"
            f"Reserve cover: {sim['reserve_cover_days_before']} -> {sim['reserve_cover_days_after']} days; "
            f"P(cover<7)={sim['p_cover_below_7']}\n"
            f"Extra import bill: Rs.{sim['cost_inr_crore_per_day']} crore/day "
            f"(95%: Rs.{sim['cost_inr_crore_per_day_p95']} crore/day)\n"
            f"Corridor import share: {corridor_share:.0%}"
        )
        reasoning = llm.narrate(SYSTEM, facts) or template

        return {"scenario": ScenarioResult(
            n_paths=sim["n_paths"],
            horizon_days=sim["horizon_days"],
            jump_type=sim["jump_type"],
            jump_type_label=sim["jump_type_label"],
            brent_spot_usd=sim["brent_spot_usd"],
            median_pct_change=sim["median_pct_change"],
            p95_var_pct=sim["p95_var_pct"],
            pct_change=Percentiles(**sim["pct_change"]),
            brent_usd=Percentiles(**sim["brent_usd"]),
            reserve_cover_days_before=sim["reserve_cover_days_before"],
            reserve_cover_days_after=sim["reserve_cover_days_after"],
            p_cover_below_7=sim["p_cover_below_7"],
            cost_inr_crore_per_day=sim["cost_inr_crore_per_day"],
            cost_inr_crore_per_day_p95=sim["cost_inr_crore_per_day_p95"],
            assumptions=sim["assumptions"],
            caveat=CAVEAT,
            reasoning=reasoning,
        )}

    return node
