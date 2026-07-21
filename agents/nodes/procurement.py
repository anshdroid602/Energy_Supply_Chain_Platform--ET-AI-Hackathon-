"""Agent 3 — Procurement Orchestrator.

Ranks alternative crude sources + routes for the refinery given TODAY's live
chokepoint risk, using the knowledge graph's `alternatives()` (viable safe
route + grade fit + import share). Adds a transparent cost delta (a freight +
grade proxy) and produces the concrete "buy X via Y, +$Z/bbl, ETA N days"
recommendation the brief demands.
"""
from __future__ import annotations

from api import graph as kg

from .. import config
from ..schemas import ProcurementOption, ProcurementRecommendation

SYSTEM = (
    "You are the Procurement Orchestrator in an energy supply-chain sentinel. "
    "In 2-3 sentences, justify the ranked crude alternatives given today's "
    "chokepoint risk. Be concrete about the top pick's route, ETA and cost. "
    "No markdown, no hedging."
)


def _cost_delta(eta_days, grade_fit, params):
    a = {**config.ASSUMPTIONS, **(params.get("assumptions") or {})}
    freight = a["freight_usd_per_bbl_per_day"] * (eta_days or 0.0)
    grade_penalty = 0.0 if grade_fit else 2.0   # off-grade crude discount/penalty proxy
    return round(freight + grade_penalty, 2)


def make_procurement_node(ds, llm, params):
    max_risk = params.get("max_risk", 0.5)

    def node(state):
        refinery = state["refinery"]
        g = ds.live_graph()
        raw = kg.alternatives(g, refinery, max_risk)
        chokepoint_risk = {n: round(d.get("risk", 0.0), 3)
                           for n, d in g.nodes(data=True) if d.get("type") == "chokepoint"}

        options = []
        for i, o in enumerate(raw):
            route = o.get("safest_viable_route") or o.get("fastest_route")
            eta = route["eta_days"] if route else None
            options.append(ProcurementOption(
                supplier=o["supplier"],
                grade=o.get("grade"),
                grade_name=o.get("grade_name"),
                grade_fit=o.get("grade_fit", False),
                import_share_pct=o.get("import_share_pct"),
                viable=o.get("viable", False),
                blocked_reason=o.get("blocked_reason"),
                eta_days=eta,
                path=route["path"] if route else [],
                path_risk=route["path_risk"] if route else None,
                cost_delta_usd_per_bbl=_cost_delta(eta, o.get("grade_fit", False), params),
                rank=i + 1,
            ))

        top = next((o for o in options if o.viable), options[0] if options else None)

        if top:
            route_str = " -> ".join(top.path) if top.path else "no route"
            summary_tmpl = (
                f"Buy {top.grade_name or top.grade or 'crude'} from {top.supplier} via "
                f"{route_str}: ETA {top.eta_days:.0f} days, ~+${top.cost_delta_usd_per_bbl:.2f}/bbl "
                f"(freight+grade), route risk {(top.path_risk or 0):.0%}."
            )
        else:
            summary_tmpl = "No supplier has a safe, grade-fitting route to this refinery today."

        viable_list = ", ".join(
            f"{o.supplier} (ETA {o.eta_days:.0f}d, +${o.cost_delta_usd_per_bbl:.1f}/bbl)"
            for o in options if o.viable
        ) or "none"
        facts = (
            f"Refinery: {refinery}; max acceptable chokepoint risk: {max_risk}\n"
            f"Chokepoint risk: {chokepoint_risk}\n"
            f"Viable options (ranked): {viable_list}\n"
            f"Top pick: {summary_tmpl}"
        )
        reasoning = llm.narrate(SYSTEM, facts) or summary_tmpl
        # The recommendation itself is the money line — keep it deterministic
        # (always correct, always fast) rather than a second LLM round-trip.
        summary = summary_tmpl

        return {"procurement": ProcurementRecommendation(
            refinery=refinery,
            max_risk=max_risk,
            chokepoint_risk=chokepoint_risk,
            options=options,
            top_pick=top,
            reasoning=reasoning,
            policymaker_summary=summary,
        )}

    return node
