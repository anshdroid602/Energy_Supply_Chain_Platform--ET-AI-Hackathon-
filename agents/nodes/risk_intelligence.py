"""Agent 1 — Risk Intelligence.

Fuses GDELT news risk, the Brent tick, and OFAC sanctions into one live
disruption probability per corridor, with the evidence that built it. The
probability IS the confidence-/recency-weighted corridor risk score, so it is
auditable; the LLM only explains it.

Fires the rest of the chain when the probability crosses DISRUPTION_THRESHOLD.
"""
from __future__ import annotations

from .. import config
from ..schemas import Evidence, EventRef, RiskAssessment

SYSTEM = (
    "You are the Risk Intelligence agent in an energy supply-chain sentinel. "
    "Given the evidence, write 2-3 tight sentences explaining the corridor's "
    "disruption probability. Cite the evidence. No markdown, no preamble, no "
    "hedging filler."
)


def make_risk_node(ds, llm, params):
    threshold = params.get("threshold", config.DISRUPTION_THRESHOLD)

    def node(state):
        corridor = state["corridor"]
        info = ds.corridor_risk(corridor)
        prob = round(float(info["risk"]), 3)
        level = info["level"]
        triggered = prob >= threshold

        evidence = [Evidence(
            label="news sentiment ↑",
            detail=f"{info['events']} GDELT risk events in {config.WINDOW_DAYS}d; "
                   f"recency/confidence-weighted risk {prob:.2f}",
            source="GDELT",
            value=prob,
        )]

        tick = ds.brent_tick_change()
        if tick is not None:
            arrow = "↑" if tick >= 0 else "↓"
            evidence.append(Evidence(
                label=f"Brent tick {arrow}",
                detail=f"{tick:+.2f} $/bbl on the latest intraday tick",
                source="yfinance/EIA",
                value=tick,
            ))

        sanctioned = ds.sanctioned_vessels_in_window()
        if sanctioned:
            evidence.append(Evidence(
                label="sanctions flag",
                detail=f"{sanctioned} OFAC-listed vessel(s) currently in the AIS window",
                source="OFAC",
                value=float(sanctioned),
            ))

        top_events = [
            EventRef(
                event_id=e["event_id"],
                event_date=str(e["event_date"]) if e["event_date"] else None,
                summary=e["summary"],
                severity_score=float(e["severity_score"]),
                confidence=float(e["confidence"]),
                lat=e.get("lat"),
                lon=e.get("lon"),
            )
            for e in info["top_events"]
        ]

        template = (
            f"{corridor} shows {level.lower()} disruption risk ({prob:.0%}), built from "
            f"{info['events']} recent GDELT events"
            + (f" and {sanctioned} sanctioned vessel(s)" if sanctioned else "")
            + ". "
            + ("Above threshold — firing the impact and procurement chain."
               if triggered else "Below the trigger threshold; monitoring only.")
        )
        facts = (
            f"Corridor: {corridor}\nDisruption probability: {prob:.2f} ({level})\n"
            f"GDELT events ({config.WINDOW_DAYS}d): {info['events']}\n"
            f"Brent latest tick: {tick if tick is not None else 'n/a'} $/bbl\n"
            f"Sanctioned vessels tracked: {sanctioned}\n"
            f"Triggered (>= {threshold}): {triggered}\n"
            f"Top event: {top_events[0].summary if top_events else 'none'}"
        )
        reasoning = llm.narrate(SYSTEM, facts) or template

        return {"risk": RiskAssessment(
            corridor=corridor,
            disruption_probability=prob,
            risk_level=level,
            triggered=triggered,
            threshold=threshold,
            event_count=info["events"],
            low_evidence=info["events"] < 10,
            evidence=evidence,
            top_events=top_events,
            reasoning=reasoning,
        )}

    return node
