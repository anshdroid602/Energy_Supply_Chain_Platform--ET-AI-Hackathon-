"""The LangGraph orchestrator: wires the five agents into one chain that fires
start to finish, streaming each step.

Flow:
    risk ──(triggered?)──> scenario ──> procurement ──> reserve ──> digital_twin
       └──(below threshold)──> END

The conditional edge is the point: most teams demo disconnected widgets; this
is one pipeline where a detected signal actually drives the whole chain.

Execution engine is LangGraph when installed (the "agentic AI" the brief
rewards, and it gives per-node streaming). If langgraph isn't importable it
falls back to running the same node callables sequentially — so the demo never
depends on the graph library being present. Both paths call identical nodes.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Iterator, Optional, Tuple, TypedDict

from . import config
from .datasource import DataSource
from .llm import get_llm
from .nodes.digital_twin import make_twin_node
from .nodes.procurement import make_procurement_node
from .nodes.risk_intelligence import make_risk_node
from .nodes.scenario_modeller import make_scenario_node
from .nodes.strategic_reserve import make_reserve_node
from .schemas import (
    PipelineResult, ProcurementRecommendation, RerouteMap, ReservePlan,
    RiskAssessment, ScenarioResult,
)


class PipelineState(TypedDict, total=False):
    """Shared LangGraph state. Declaring every field (not a bare `dict`) is
    what keeps the input corridor/refinery on the state through later nodes."""
    corridor: str
    refinery: str
    risk: RiskAssessment
    scenario: ScenarioResult
    procurement: ProcurementRecommendation
    reserve: ReservePlan
    reroute: RerouteMap

# node name -> the PipelineResult field it fills
SLICE_KEY = {
    "risk": "risk",
    "scenario": "scenario",
    "procurement": "procurement",
    "reserve": "reserve",
    "digital_twin": "reroute",
}
NODE_ORDER = ["risk", "scenario", "procurement", "reserve", "digital_twin"]

HEADLINE_SYSTEM = (
    "Write ONE punchy headline (max ~30 words) a policymaker reads at a glance: "
    "corridor + risk, rupee/day impact, and the recommended buy. No markdown."
)


class Orchestrator:
    def __init__(self, ds: Optional[DataSource] = None, llm=None,
                 params: Optional[dict] = None):
        self.ds = ds or DataSource()
        self.llm = llm or get_llm()
        self.params = params or {}
        self.node_fns = {
            "risk": make_risk_node(self.ds, self.llm, self.params),
            "scenario": make_scenario_node(self.ds, self.llm, self.params),
            "procurement": make_procurement_node(self.ds, self.llm, self.params),
            "reserve": make_reserve_node(self.ds, self.llm, self.params),
            "digital_twin": make_twin_node(self.ds, self.llm, self.params),
        }
        self._final_state: dict = {}

    # --- engines ------------------------------------------------------------

    def _compile_langgraph(self):
        try:
            from langgraph.graph import END, StateGraph
        except Exception:
            return None
        sg = StateGraph(PipelineState)
        for name in NODE_ORDER:
            sg.add_node(name, self.node_fns[name])
        sg.set_entry_point("risk")
        sg.add_conditional_edges(
            "risk",
            lambda s: "fire" if s["risk"].triggered else "stop",
            {"fire": "scenario", "stop": END},
        )
        sg.add_edge("scenario", "procurement")
        sg.add_edge("procurement", "reserve")
        sg.add_edge("reserve", "digital_twin")
        sg.add_edge("digital_twin", END)
        return sg.compile()

    def iter_steps(self, corridor: str, refinery: str) -> Iterator[Tuple[str, object]]:
        """Yield (node_name, slice_object) as each agent finishes. Accumulates
        into self._final_state for assembly."""
        state = {"corridor": corridor, "refinery": refinery}
        graph = self._compile_langgraph()

        if graph is not None:
            for update in graph.stream(state, stream_mode="updates"):
                for node_name, partial in update.items():
                    if not isinstance(partial, dict):
                        continue
                    state.update(partial)
                    key = SLICE_KEY.get(node_name)
                    yield node_name, (state.get(key) if key else None)
        else:
            for name in NODE_ORDER:
                state.update(self.node_fns[name](state))
                yield name, state.get(SLICE_KEY[name])
                if name == "risk" and not state["risk"].triggered:
                    break

        self._final_state = state

    # --- assembly -----------------------------------------------------------

    def _headline(self, state: dict) -> str:
        risk = state["risk"]
        scenario = state.get("scenario")
        proc = state.get("procurement")
        if not risk.triggered:
            return (f"{risk.corridor}: {risk.risk_level} risk "
                    f"({risk.disruption_probability:.0%}) — below trigger, monitoring.")
        bits = [f"{risk.corridor} {risk.risk_level} ({risk.disruption_probability:.0%})"]
        if scenario:
            bits.append(
                f"Brent median {scenario.median_pct_change:+.0f}% / 95% VaR "
                f"{scenario.p95_var_pct:+.0f}%, ~Rs.{scenario.cost_inr_crore_per_day:.0f} cr/day, "
                f"reserve cover -> {scenario.reserve_cover_days_after:.1f}d")
        if proc and proc.top_pick:
            bits.append(proc.policymaker_summary)
        template = " | ".join(bits)
        facts = "\n".join(bits)
        return self.llm.narrate(HEADLINE_SYSTEM, facts, max_tokens=80) or template

    def _assemble(self, corridor, refinery, state, latency) -> PipelineResult:
        return PipelineResult(
            corridor=corridor,
            refinery=refinery,
            generated_at=datetime.now(timezone.utc),
            latency_seconds=round(latency, 2),
            headline=self._headline(state),
            risk=state["risk"],
            scenario=state.get("scenario"),
            procurement=state.get("procurement"),
            reserve=state.get("reserve"),
            reroute=state.get("reroute"),
        )

    def run(self, corridor: str = "Strait of Hormuz",
            refinery: Optional[str] = None) -> PipelineResult:
        refinery = refinery or config.DEFAULT_REFINERY
        start = time.time()
        for _ in self.iter_steps(corridor, refinery):
            pass
        latency = time.time() - start
        return self._assemble(corridor, refinery, self._final_state, latency)
