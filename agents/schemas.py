"""The agent -> frontend contract.

This is the single JSON shape the React + Leaflet dashboard renders and the
one contract the whole team agreed still matters. Every agent node fills in
one slice of PipelineResult; the orchestrator assembles and streams it.

Design rules:
  - Every quantitative field is deterministic and produced by code, not the
    LLM. LLMs only fill the free-text `*reasoning` / `*_summary` fields.
  - Everything a judge might question carries its evidence or assumptions
    alongside it (the brief's "explicit and testable" requirement).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# --- shared -----------------------------------------------------------------

class Evidence(BaseModel):
    """One line under the disruption gauge: what the score is built on."""
    label: str                      # "news sentiment ↑", "sanctions flag", ...
    detail: str                     # human-readable specifics
    source: str                     # "GDELT" | "OFAC" | "yfinance/EIA" | "AISStream"
    value: Optional[float] = None   # optional numeric for a mini-chart


class EventRef(BaseModel):
    """A single GDELT risk event, plotted as an evidence dot on the map."""
    event_id: str
    event_date: Optional[str] = None
    summary: str
    severity_score: float
    confidence: float
    lat: Optional[float] = None
    lon: Optional[float] = None


# --- agent 1: Risk Intelligence ---------------------------------------------

class RiskAssessment(BaseModel):
    corridor: str
    disruption_probability: float = Field(..., ge=0, le=1)
    risk_level: str                 # Low | Medium | High | Critical
    triggered: bool                 # crossed DISRUPTION_THRESHOLD -> fire the chain
    threshold: float
    event_count: int
    low_evidence: bool = False
    evidence: list[Evidence] = []
    top_events: list[EventRef] = []
    reasoning: str = ""             # LLM narrative (or template fallback)


# --- agent 2: Scenario Modeller ---------------------------------------------

class Percentiles(BaseModel):
    p5: float
    p25: float
    p50: float
    p75: float
    p95: float


class ScenarioResult(BaseModel):
    n_paths: int
    horizon_days: int
    jump_type: str                  # mean_reverting | persistent
    jump_type_label: str
    brent_spot_usd: float
    # price impact distribution (terminal % change vs spot)
    median_pct_change: float
    p95_var_pct: float = Field(..., description="95% VaR: the upside tail of the Brent move")
    pct_change: Percentiles
    brent_usd: Percentiles          # absolute $ level distribution at horizon
    # economic cascade (SIMPLIFIED — stated honestly)
    reserve_cover_days_before: float
    reserve_cover_days_after: float
    p_cover_below_7: float = Field(..., ge=0, le=1)
    cost_inr_crore_per_day: float   # median extra import bill
    cost_inr_crore_per_day_p95: float
    assumptions: dict               # every knob used, echoed back for the panel
    caveat: str                     # the honest weak-link disclaimer
    reasoning: str = ""


# --- agent 3: Procurement Orchestrator --------------------------------------

class ProcurementOption(BaseModel):
    supplier: str
    grade: Optional[str] = None
    grade_name: Optional[str] = None
    grade_fit: bool
    import_share_pct: Optional[float] = None
    viable: bool
    blocked_reason: Optional[str] = None
    eta_days: Optional[float] = None
    path: list[str] = []            # node ids for the reroute line
    path_risk: Optional[float] = None
    cost_delta_usd_per_bbl: Optional[float] = None
    rank: int


class ProcurementRecommendation(BaseModel):
    refinery: str
    max_risk: float
    chokepoint_risk: dict           # chokepoint id -> live risk
    options: list[ProcurementOption]
    top_pick: Optional[ProcurementOption] = None
    reasoning: str = ""
    policymaker_summary: str = ""   # the concrete "Buy X via Y, +$Z/bbl, ETA N days" line


# --- agent 4: Strategic Reserve ---------------------------------------------

class ReservePlan(BaseModel):
    reserve_cover_days: float
    daily_gap_kbd: float            # lost imports, thousand bbl/day
    drawdown_kbd: float             # SPR draw to cover the gap
    buffer_days: float              # how long reserves last at this drawdown
    replenishment_window_days: float
    rule: str                       # the plain explainable rule applied
    reasoning: str = ""


# --- agent 5: Supply-Chain Digital Twin -------------------------------------

class MapNode(BaseModel):
    id: str
    type: str
    lat: float
    lon: float
    risk: Optional[float] = None


class RerouteMap(BaseModel):
    refinery: str
    from_supplier: Optional[str] = None
    blocked_chokepoints: list[str] = []     # drawn red / crossed out
    active_path: list[MapNode] = []         # the recommended reroute, in order
    waypoints: list[list[float]] = []       # [[lat, lon], ...] incl. sea-lane points
    note: str = ""


# --- the whole thing --------------------------------------------------------

class PipelineResult(BaseModel):
    corridor: str
    refinery: str
    generated_at: datetime
    latency_seconds: float
    headline: str = ""              # one-line policymaker brief for the top of the screen
    risk: RiskAssessment
    scenario: Optional[ScenarioResult] = None
    procurement: Optional[ProcurementRecommendation] = None
    reserve: Optional[ReservePlan] = None
    reroute: Optional[RerouteMap] = None
