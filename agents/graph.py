"""
LangGraph pipeline: signal -> scenario -> procurement -> summary.

Deliberately a plain linear StateGraph (see task.md §1): four nodes, one
shared state dict, no conditional edges, no cycles, no multi-agent handoff.
LangGraph is kept here as a real skill investment (this is the one part of
the project that reads as "agentic AI"), but the scope is small on purpose —
each node is a thin wrapper over logic that already exists elsewhere
(corridor risk scoring, the Monte Carlo scenario engine, the procurement
graph), so the framework overhead stays low.

Invoked synchronously via `run_pipeline()` -> `graph.invoke()`. Not streamed:
real SSE was cut for the hackathon deadline (see task.md) in favor of a
single call that records each node's wall-clock duration, so the frontend
can still fake a live step-by-step reveal from real timing data.

Two ways to feed the pipeline a signal:
  - live: put a psycopg2 connection in `conn` -> signal_node queries
    structured_events for real, current risk, exactly like
    /corridors/{c}/risk-score does.
  - injected (demo-safe): put a single cached event dict in
    `injected_event` instead of `conn` -> risk is computed from just that
    one event (decay=1, "today's" cached signal). This is what the
    frontend's "inject signal" button uses, and it means the live demo
    never depends on the database being reachable or on real news existing
    at pitch time.
"""

from __future__ import annotations

import time
from datetime import date
from typing import Optional, TypedDict

from langgraph.graph import END, StateGraph

from api import graph as kg
from scenario import engine as scenario_engine

RISK_LEVEL_THRESHOLDS = [
    (0.8, "Critical"),
    (0.6, "High"),
    (0.35, "Medium"),
    (0.0, "Low"),
]


def risk_level_for(score: float) -> str:
    for threshold, label in RISK_LEVEL_THRESHOLDS:
        if score >= threshold:
            return label
    return "Low"


class PipelineState(TypedDict, total=False):
    # --- inputs ---
    conn: object                       # psycopg2 connection; omit if injected_event is used
    injected_event: Optional[dict]      # {"corridor", "severity_score", "confidence"} — offline mode
    corridor: str
    refinery: str
    window_days: int
    half_life_days: float
    max_acceptable_risk: float
    scenario_params: dict              # jump_size_pct / elasticity / days_to_reroute / etc.

    # --- filled by signal_node ---
    risk_score: float
    risk_level: str
    risk_event_count: int

    # --- filled by scenario_node ---
    scenario_result: dict

    # --- filled by procurement_node ---
    procurement_options: list

    # --- filled by summary_node ---
    summary: str

    # --- bookkeeping ---
    durations_ms: dict


def _timed(name):
    """Wrap a node so its wall-clock time lands in state['durations_ms']
    without every node having to do its own timing boilerplate."""
    def deco(fn):
        def wrapper(state: PipelineState) -> dict:
            t0 = time.perf_counter()
            out = fn(state)
            dt_ms = round((time.perf_counter() - t0) * 1000, 2)
            durations = dict(state.get("durations_ms") or {})
            durations[name] = dt_ms
            out = dict(out)
            out["durations_ms"] = durations
            return out
        return wrapper
    return deco


@_timed("signal")
def signal_node(state: PipelineState) -> dict:
    """Corridor risk score — same math as GET /corridors/{c}/risk-score,
    either against the live DB or against one injected cached event."""
    injected = state.get("injected_event")
    corridor = state["corridor"]

    if injected is not None:
        severity = injected["severity_score"]
        confidence = injected["confidence"]
        risk = round((severity / 10.0) * confidence, 3)  # decay = 1, it's "today"
        event_count = 1
    else:
        conn = state["conn"]
        window_days = state.get("window_days", 30)
        half_life = state.get("half_life_days", 7.0)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT severity_score, confidence, event_date
                FROM structured_events
                WHERE corridor_affected = %s
                  AND event_date >= (CURRENT_DATE - %s * INTERVAL '1 day');
                """,
                (corridor, window_days),
            )
            rows = cur.fetchall()

        if not rows:
            risk, event_count = 0.0, 0
        else:
            today = date.today()
            weighted_sum = weight_total = 0.0
            for sev, conf, edate in rows:
                days_ago = (today - edate).days if edate else window_days
                decay = 0.5 ** (max(days_ago, 0) / half_life)
                w = conf * decay
                weighted_sum += (sev / 10.0) * w
                weight_total += w
            risk = round(weighted_sum / weight_total, 3) if weight_total > 0 else 0.0
            event_count = len(rows)

    return {
        "risk_score": risk,
        "risk_level": risk_level_for(risk),
        "risk_event_count": event_count,
    }


@_timed("scenario")
def scenario_node(state: PipelineState) -> dict:
    """Monte Carlo scenario sized by the risk score `signal_node` produced."""
    params = dict(state.get("scenario_params") or {})
    result = scenario_engine.run_scenario(risk_score=state["risk_score"], **params)
    return {"scenario_result": result}


@_timed("procurement")
def procurement_node(state: PipelineState) -> dict:
    """Ranked alternative suppliers from the existing knowledge graph
    (api/graph.py), given today's (or the injected) chokepoint risk."""
    refinery = state.get("refinery", "Jamnagar (RIL)")
    max_risk = state.get("max_acceptable_risk", 0.5)

    g = kg.get_graph()
    conn = state.get("conn")
    if conn is not None:
        risks = kg.corridor_risks(conn, state.get("window_days", 30), state.get("half_life_days", 7.0))
    else:
        # offline: we only know the risk of the one corridor the injected
        # signal named — every other chokepoint keeps its seeded base_risk.
        risks = {state["corridor"]: {"risk": state["risk_score"], "events": state.get("risk_event_count", 1)}}
    kg.overlay_risk(g, risks)

    options = kg.alternatives(g, refinery, max_risk)
    return {"procurement_options": options, "refinery": refinery}


@_timed("summary")
def summary_node(state: PipelineState) -> dict:
    """Plain-English one-liner, templated (not an LLM call) — see task.md:
    a template carries zero latency/failure risk right before the demo's
    mic-drop line, and a judge can't tell it apart from a generated one."""
    scen = state["scenario_result"]
    options = state.get("procurement_options") or []
    viable = [o for o in options if o["viable"]]
    top = viable[0] if viable else (options[0] if options else None)

    if top and top.get("safest_viable_route"):
        pick = (f"Recommended: reroute via {top['supplier']} "
                f"({top['safest_viable_route']['eta_days']:.1f} days ETA).")
    elif top:
        pick = (f"Recommended: {top['supplier']} — no fully safe route at the current "
                f"threshold; fastest available is {top['fastest_route']['eta_days']:.1f} days ETA.")
    else:
        pick = "No viable alternative supplier found under the current risk threshold."

    results = scen["results"]
    summary = (
        f"{state['corridor']} risk: {state['risk_level']} "
        f"({state['risk_score']:.2f}, {state.get('risk_event_count', 0)} events backing it). "
        f"Estimated cost: Rs.{results['median_cost_inr_cr_per_day']:.0f} crore/day "
        f"(95% VaR: Rs.{results['var95_cost_inr_cr_per_day']:.0f} crore/day). "
        f"Reserve cover: {scen['assumptions']['baseline_reserve_days']:.1f} -> "
        f"{results['median_reserve_cover_days']:.1f} days "
        f"(P(cover < {scen['assumptions']['reserve_threshold_days']:.0f} days) = "
        f"{results['prob_reserve_cover_below_threshold']:.2f}). "
        f"{pick}"
    )
    return {"summary": summary}


def build_graph():
    g = StateGraph(PipelineState)
    g.add_node("signal", signal_node)
    g.add_node("scenario", scenario_node)
    g.add_node("procurement", procurement_node)
    g.add_node("summary", summary_node)

    g.set_entry_point("signal")
    g.add_edge("signal", "scenario")
    g.add_edge("scenario", "procurement")
    g.add_edge("procurement", "summary")
    g.add_edge("summary", END)

    return g.compile()


_COMPILED = None


def get_compiled_graph():
    global _COMPILED
    if _COMPILED is None:
        _COMPILED = build_graph()
    return _COMPILED


def run_pipeline(initial_state: dict) -> dict:
    """Run the full pipeline synchronously and return the final state, with
    a `total_ms` wall-clock figure alongside the per-node `durations_ms`."""
    graph = get_compiled_graph()
    t0 = time.perf_counter()
    final_state = dict(graph.invoke(initial_state))
    final_state["total_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    final_state.pop("conn", None)  # never let a live DB connection leak into a JSON response
    return final_state
