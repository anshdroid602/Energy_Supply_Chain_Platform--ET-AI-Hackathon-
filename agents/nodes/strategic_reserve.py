"""Agent 4 — Strategic Reserve (stretch, kept a simple explainable rule).

Given the expected daily shortfall from the disruption and the fastest safe
reroute ETA, it sizes the reserve drawdown needed to bridge the gap and how
long the reserve lasts at that rate. Deterministic rule; the LLM narrates.
"""
from __future__ import annotations

from ..schemas import ReservePlan

SYSTEM = (
    "You are the Strategic Reserve agent in an energy supply-chain sentinel. "
    "In 2 sentences, state the reserve drawdown plan and whether the buffer "
    "outlasts the reroute. Plain English, rupees/days/barrels. No markdown."
)

RULE = ("Draw down the strategic reserve to fully cover the corridor shortfall "
        "until the fastest safe reroute lands; raise an alert if the buffer is "
        "shorter than the reroute ETA.")


def make_reserve_node(ds, llm, params):
    def node(state):
        risk = state["risk"]
        scenario = state["scenario"]
        proc = state.get("procurement")

        share = scenario.assumptions["corridor_share"]
        daily_bbl = scenario.assumptions["india_daily_bbl"]
        # Expected lost imports = corridor share x disruption probability.
        gap_bbl = share * risk.disruption_probability * daily_bbl
        gap_kbd = gap_bbl / 1000.0

        R0 = scenario.reserve_cover_days_before
        # Reserve is R0 days of FULL imports; filling only the gap burns
        # `gap/imports` reserve-days per day -> buffer stretches accordingly.
        burn_frac = gap_bbl / daily_bbl if daily_bbl else 0.0
        buffer_days = (R0 / burn_frac) if burn_frac > 0 else 999.0

        eta = (proc.top_pick.eta_days if proc and proc.top_pick and proc.top_pick.eta_days
               else scenario.assumptions["reroute_lag_days"])

        template = (
            f"Lost flow ~{gap_kbd:.0f} kb/d; draw the reserve at that rate. "
            f"At {R0:.1f}-day cover the buffer lasts ~{min(buffer_days, 999):.0f} days vs a "
            f"{eta:.0f}-day reroute — "
            + ("buffer holds." if buffer_days >= eta else "buffer is TIGHT, expedite the reroute.")
        )
        facts = (
            f"Reserve cover: {R0:.1f} days\nDaily import gap: {gap_kbd:.0f} kb/d\n"
            f"Buffer at this drawdown: {min(buffer_days, 999):.0f} days\n"
            f"Reroute ETA: {eta:.0f} days\nRule: {RULE}"
        )
        reasoning = llm.narrate(SYSTEM, facts) or template

        return {"reserve": ReservePlan(
            reserve_cover_days=round(R0, 1),
            daily_gap_kbd=round(gap_kbd, 1),
            drawdown_kbd=round(gap_kbd, 1),
            buffer_days=round(min(buffer_days, 999), 1),
            replenishment_window_days=round(float(eta), 1),
            rule=RULE,
            reasoning=reasoning,
        )}

    return node
