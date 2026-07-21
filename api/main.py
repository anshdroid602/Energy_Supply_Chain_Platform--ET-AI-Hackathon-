"""
The one read API in front of Postgres, for the dashboard frontend and AI
agents to consume. Covers every table the datapipeline loads: GDELT risk
events + corridor risk scores, Brent/WTI prices (daily + intraday), live
vessel positions (with sanctioned-tanker matching), OFAC sanctions, India
import bills, and pipeline freshness.

Run (from the repo root):
  uvicorn api.main:app --reload --port 8000

Docs (Swagger UI, auto-generated, agents can also read /openapi.json):
  http://localhost:8000/docs

Requires: pip install fastapi "uvicorn[standard]" psycopg2-binary python-dotenv
DATABASE_URL must be set in .env (same one the loaders use).
"""

import math
import os
from datetime import date, datetime, timezone
from typing import Literal, Optional

import psycopg2
import psycopg2.extras
import psycopg2.pool
from dotenv import load_dotenv
from fastapi import Body, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from scenario import engine as scenario_engine

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise SystemExit("Set DATABASE_URL in your .env file")

# Fixed vocabularies, kept in sync with extract.py's CORRIDOR_MAP / CATEGORY_LABELS.
# Exposed via /meta so frontend + agents know the valid filter values without
# having to query the DB or read the extraction source.
CORRIDORS = ["Strait of Hormuz", "Persian Gulf", "Red Sea", "Suez Canal", "none"]
CATEGORIES = ["military_strike", "sanction", "maritime_incident", "diplomatic", "other"]

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


# --- DB connection pool -----------------------------------------------------

pool: Optional[psycopg2.pool.SimpleConnectionPool] = None


def get_db():
    conn = pool.getconn()
    try:
        yield conn
    finally:
        pool.putconn(conn)


# --- Response models ---------------------------------------------------------

class Event(BaseModel):
    event_id: str
    event_date: Optional[date]
    actors: list[str]
    location_country: Optional[str]
    lat: Optional[float] = None    # event coordinates (GDELT ActionGeo) — for the map's evidence layer
    lon: Optional[float] = None
    corridor_affected: str
    event_category: str
    severity_score: float
    confidence: float
    summary: str


class EventList(BaseModel):
    count: int
    limit: int
    offset: int
    results: list[Event]


class CorridorSummary(BaseModel):
    corridor: str
    event_count: int
    avg_severity: Optional[float]
    max_severity: Optional[float]
    latest_event_date: Optional[date]


class RiskScore(BaseModel):
    corridor: str
    window_days: int
    half_life_days: float
    risk_score: float = Field(..., ge=0, le=1, description="0-1 confidence-and-recency-weighted severity")
    risk_level: Literal["Low", "Medium", "High", "Critical"]
    event_count_in_window: int
    low_evidence: bool = Field(False, description="True when fewer than min_events events back this score — treat the number as indicative, not conclusive")
    top_events: list[Event]


class Meta(BaseModel):
    corridors: list[str]
    event_categories: list[str]


# --- App ----------------------------------------------------------------

app = FastAPI(
    title="Crude Oil Supply Chain Risk API",
    description="Read API over GDELT-derived structured risk events for the dashboard and AI agents.",
    version="1.0.0",
)

# Hackathon-permissive CORS. Tighten allow_origins to the real frontend
# origin before this is anything but a demo.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],  # was ["GET"]; the frontend POSTs to /pipeline/run and /scenario/run
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    global pool
    pool = psycopg2.pool.SimpleConnectionPool(1, 10, DATABASE_URL)


@app.on_event("shutdown")
def shutdown():
    if pool:
        pool.closeall()


def row_to_event(row: dict) -> Event:
    return Event(
        event_id=row["event_id"],
        event_date=row["event_date"],
        actors=row["actors"] or [],
        location_country=row["location_country"],
        lat=row.get("lat"),
        lon=row.get("lon"),
        corridor_affected=row["corridor_affected"],
        event_category=row["event_category"],
        severity_score=row["severity_score"],
        confidence=row["confidence"],
        summary=row["summary"],
    )


# --- Endpoints ---------------------------------------------------------------

@app.get("/health")
def health(conn=Depends(get_db)):
    with conn.cursor() as cur:
        cur.execute("SELECT 1;")
        cur.fetchone()
    return {"status": "ok"}


@app.get("/meta", response_model=Meta)
def meta():
    """Valid filter values for corridor_affected and event_category, so
    frontend/agents don't have to guess or query the DB to discover them."""
    return Meta(corridors=CORRIDORS, event_categories=CATEGORIES)


@app.get("/events", response_model=EventList)
def list_events(
    conn=Depends(get_db),
    corridor: Optional[str] = Query(None, description="Filter by corridor_affected, e.g. 'Strait of Hormuz'"),
    category: Optional[str] = Query(None, description="Filter by event_category"),
    country: Optional[str] = Query(None, description="Filter by location_country (FIPS code)"),
    actor: Optional[str] = Query(None, description="Filter events where this actor code appears (e.g. 'IRN')"),
    min_severity: Optional[float] = Query(None, ge=0, le=10),
    max_severity: Optional[float] = Query(None, ge=0, le=10),
    min_confidence: Optional[float] = Query(None, ge=0, le=1),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    sort: Literal["severity_desc", "date_desc", "date_asc"] = "date_desc",
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    where = []
    params: list = []

    if corridor:
        where.append("corridor_affected = %s")
        params.append(corridor)
    if category:
        where.append("event_category = %s")
        params.append(category)
    if country:
        where.append("location_country = %s")
        params.append(country)
    if actor:
        where.append("%s = ANY(actors)")
        params.append(actor)
    if min_severity is not None:
        where.append("severity_score >= %s")
        params.append(min_severity)
    if max_severity is not None:
        where.append("severity_score <= %s")
        params.append(max_severity)
    if min_confidence is not None:
        where.append("confidence >= %s")
        params.append(min_confidence)
    if start_date:
        where.append("event_date >= %s")
        params.append(start_date)
    if end_date:
        where.append("event_date <= %s")
        params.append(end_date)

    where_clause = f"WHERE {' AND '.join(where)}" if where else ""

    order_by = {
        "severity_desc": "severity_score DESC",
        "date_desc": "event_date DESC NULLS LAST",
        "date_asc": "event_date ASC NULLS LAST",
    }[sort]

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(f"SELECT count(*) AS n FROM structured_events {where_clause};", params)
        total = cur.fetchone()["n"]

        cur.execute(
            f"""
            SELECT event_id, event_date, actors, location_country, lat, lon, corridor_affected,
                   event_category, severity_score, confidence, summary
            FROM structured_events
            {where_clause}
            ORDER BY {order_by}
            LIMIT %s OFFSET %s;
            """,
            params + [limit, offset],
        )
        rows = cur.fetchall()

    return EventList(
        count=total,
        limit=limit,
        offset=offset,
        results=[row_to_event(r) for r in rows],
    )


@app.get("/events/{event_id}", response_model=Event)
def get_event(event_id: str, conn=Depends(get_db)):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT event_id, event_date, actors, location_country, lat, lon, corridor_affected,
                   event_category, severity_score, confidence, summary
            FROM structured_events WHERE event_id = %s;
            """,
            (event_id,),
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"event_id '{event_id}' not found")
    return row_to_event(row)


@app.get("/corridors", response_model=list[CorridorSummary])
def corridor_summaries(conn=Depends(get_db)):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT corridor_affected AS corridor,
                   count(*) AS event_count,
                   avg(severity_score) AS avg_severity,
                   max(severity_score) AS max_severity,
                   max(event_date) AS latest_event_date
            FROM structured_events
            GROUP BY corridor_affected
            ORDER BY avg_severity DESC NULLS LAST;
            """
        )
        rows = cur.fetchall()

    return [
        CorridorSummary(
            corridor=r["corridor"],
            event_count=r["event_count"],
            avg_severity=round(r["avg_severity"], 2) if r["avg_severity"] is not None else None,
            max_severity=r["max_severity"],
            latest_event_date=r["latest_event_date"],
        )
        for r in rows
    ]


@app.get("/corridors/{corridor}/risk-score", response_model=RiskScore)
def corridor_risk_score(
    corridor: str,
    conn=Depends(get_db),
    window_days: int = Query(30, ge=1, le=365, description="Only consider events within this many days of today"),
    half_life_days: float = Query(7.0, gt=0, description="Recency decay half-life: an event this many days old counts half as much"),
    top_n: int = Query(5, ge=0, le=50, description="How many top-contributing events to return alongside the score"),
    min_events: int = Query(10, ge=1, description="Below this many events the score is flagged low_evidence"),
):
    """
    Deterministic risk score for a corridor: confidence- and recency-weighted
    mean of severity_score/10 over events in the last `window_days`.

    risk_score = sum(severity_i/10 * confidence_i * decay_i) / sum(confidence_i * decay_i)
    decay_i = 0.5 ** (days_ago_i / half_life_days)

    A corridor with zero events in the window returns risk_score 0.0 / "Low"
    rather than erroring, since "no recent signal" is itself informative for
    a caller (dashboard or agent) polling this endpoint.
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT event_id, event_date, actors, location_country, lat, lon, corridor_affected,
                   event_category, severity_score, confidence, summary
            FROM structured_events
            WHERE corridor_affected = %s
              AND event_date >= (CURRENT_DATE - %s * INTERVAL '1 day')
            ORDER BY event_date DESC;
            """,
            (corridor, window_days),
        )
        rows = cur.fetchall()

    if not rows:
        return RiskScore(
            corridor=corridor,
            window_days=window_days,
            half_life_days=half_life_days,
            risk_score=0.0,
            risk_level="Low",
            event_count_in_window=0,
            low_evidence=True,
            top_events=[],
        )

    today = date.today()
    weighted_sum = 0.0
    weight_total = 0.0
    scored_rows = []

    for r in rows:
        days_ago = (today - r["event_date"]).days if r["event_date"] else window_days
        decay = 0.5 ** (max(days_ago, 0) / half_life_days)
        weight = r["confidence"] * decay
        weighted_sum += (r["severity_score"] / 10.0) * weight
        weight_total += weight
        scored_rows.append((weight, r))

    risk_score = round(weighted_sum / weight_total, 3) if weight_total > 0 else 0.0
    scored_rows.sort(key=lambda pair: pair[0], reverse=True)
    top_events = [row_to_event(r) for _, r in scored_rows[:top_n]]

    return RiskScore(
        corridor=corridor,
        window_days=window_days,
        half_life_days=half_life_days,
        risk_score=risk_score,
        risk_level=risk_level_for(risk_score),
        event_count_in_window=len(rows),
        low_evidence=len(rows) < min_events,
        top_events=top_events,
    )


# ============================================================================
# Market data, vessels, imports, sanctions, freshness — the rest of the
# datapipeline tables, so this stays the single API in front of Postgres.
# ============================================================================

class DailyPrice(BaseModel):
    day: date
    ticker: str          # 'BRENT' | 'WTI'
    usd: float
    source: str


class PriceTick(BaseModel):
    ts: datetime
    ticker: str          # 'BZ=F' | 'CL=F'
    usd: float


class VesselPosition(BaseModel):
    mmsi: int
    lat: Optional[float]
    lon: Optional[float]
    sog: Optional[float]
    cog: Optional[float]
    ts: datetime
    name: Optional[str]
    sanctioned: bool
    # 'mmsi' = OFAC remarks contain this exact MMSI (strong evidence);
    # 'name' = ship name equals an SDN vessel name (weak — names repeat);
    # None = no match.
    sanction_match: Optional[str]


class IndiaImportRow(BaseModel):
    period: Optional[date]
    product: str
    trade: str
    quantity_tmt: Optional[float]
    value_inr_cr: Optional[float]
    value_usd_mn: Optional[float]


class SanctionedVessel(BaseModel):
    ent_num: int
    name: Optional[str]
    program: Optional[str]
    vessel_flag: Optional[str]
    remarks: Optional[str]


class FeedFreshness(BaseModel):
    feed: str
    last_run: Optional[datetime]
    last_status: Optional[str]
    last_rows: Optional[int]
    note: Optional[str]
    stale: bool = Field(False, description="True when the feed hasn't run successfully within ~2x its expected cadence")


# Expected max age per feed (~2x the controller cadence) — used only to set
# the `stale` flag so the dashboard can show 'overdue' without knowing
# controller internals.
FEED_MAX_AGE_HOURS = {
    "eia": 44.0,
    "market_prices": 1.0,
    "ofac": 44.0,
    "ppac": 26 * 24.0,   # monthly data, refreshed daily-ish is plenty
    "ais": 1.0,
    "gdelt": 9.0,
}


@app.get("/prices/daily", response_model=list[DailyPrice])
def daily_prices(
    conn=Depends(get_db),
    ticker: Optional[Literal["BRENT", "WTI"]] = Query(None),
    days: int = Query(365, ge=1, le=5000, description="How far back from the latest day on record"),
):
    """Official EIA daily spot prices — the citable series the scenario model
    calibrates on."""
    where = ["day >= (SELECT max(day) FROM prices) - %s * INTERVAL '1 day'"]
    params: list = [days]
    if ticker:
        where.append("ticker = %s")
        params.append(ticker)
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            f"SELECT day, ticker, usd, source FROM prices WHERE {' AND '.join(where)} ORDER BY day;",
            params,
        )
        return [DailyPrice(**r) for r in cur.fetchall()]


@app.get("/prices/ticks", response_model=list[PriceTick])
def price_ticks(
    conn=Depends(get_db),
    ticker: Optional[Literal["BZ=F", "CL=F"]] = Query(None),
    hours: int = Query(24, ge=1, le=24 * 14, description="How far back from the latest tick on record"),
):
    """Intraday yfinance ticks — the live 'Brent tick-up' evidence line."""
    where = ["ts >= (SELECT max(ts) FROM price_ticks) - %s * INTERVAL '1 hour'"]
    params: list = [hours]
    if ticker:
        where.append("ticker = %s")
        params.append(ticker)
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            f"SELECT ts, ticker, usd FROM price_ticks WHERE {' AND '.join(where)} ORDER BY ts;",
            params,
        )
        return [PriceTick(**r) for r in cur.fetchall()]


@app.get("/prices/latest")
def latest_prices(conn=Depends(get_db)):
    """Latest daily close per EIA ticker and latest intraday tick per futures
    ticker, in one call — what a dashboard header needs."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (ticker) day, ticker, usd, source
            FROM prices ORDER BY ticker, day DESC;
            """
        )
        daily = cur.fetchall()
        cur.execute(
            """
            SELECT DISTINCT ON (ticker) ts, ticker, usd
            FROM price_ticks ORDER BY ticker, ts DESC;
            """
        )
        ticks = cur.fetchall()
    return {"daily": daily, "intraday": ticks}


VESSEL_LATEST_SQL = """
SELECT DISTINCT ON (v.mmsi)
       v.mmsi, v.lat, v.lon, v.sog, v.cog, v.ts, v.name,
       (s.ent_num IS NOT NULL) AS sanctioned,
       CASE
         WHEN s.remarks LIKE '%%MMSI ' || v.mmsi::text || '%%' THEN 'mmsi'
         WHEN s.ent_num IS NOT NULL THEN 'name'
       END AS sanction_match
FROM vessels v
LEFT JOIN sanctions s
  ON lower(s.sdn_type) = 'vessel'
 AND (   (s.remarks IS NOT NULL AND s.remarks LIKE '%%MMSI ' || v.mmsi::text || '%%')
      OR (s.name IS NOT NULL AND v.name IS NOT NULL
          AND upper(trim(v.name)) = upper(trim(s.name))) )
{extra_where}
ORDER BY v.mmsi, v.ts DESC,
         (s.remarks LIKE '%%MMSI ' || v.mmsi::text || '%%') DESC NULLS LAST
LIMIT %s;
"""


@app.get("/vessels/latest", response_model=list[VesselPosition])
def latest_vessels(
    conn=Depends(get_db),
    limit: int = Query(1000, ge=1, le=10000),
):
    """Latest known position per vessel, each flagged if its AIS ship name
    matches an OFAC-sanctioned vessel. This powers the live map layer."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(VESSEL_LATEST_SQL.format(extra_where=""), (limit,))
        return [VesselPosition(**r) for r in cur.fetchall()]


@app.get("/vessels/sanctioned", response_model=list[VesselPosition])
def sanctioned_vessels_live(
    conn=Depends(get_db),
    limit: int = Query(1000, ge=1, le=10000),
):
    """Only the vessels currently in the AIS window whose name matches an
    OFAC SDN vessel entry — the 'sanctions flag' evidence line on the map."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(VESSEL_LATEST_SQL.format(extra_where="WHERE s.ent_num IS NOT NULL"), (limit,))
        return [VesselPosition(**r) for r in cur.fetchall()]


@app.get("/imports/india", response_model=list[IndiaImportRow])
def india_imports(
    conn=Depends(get_db),
    product: str = Query("CRUDE OIL", description="e.g. 'CRUDE OIL', 'LPG', 'NET IMPORT'"),
    trade: Literal["Import", "Export"] = Query("Import"),
):
    """PPAC monthly quantity + value series — the rupees-and-days grounding
    for the impact model (import bill, reserve-cover maths)."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT period, product, trade, quantity_tmt, value_inr_cr, value_usd_mn
            FROM imports_india
            WHERE upper(product) = upper(%s) AND trade = %s AND period IS NOT NULL
            ORDER BY period;
            """,
            (product, trade),
        )
        return [IndiaImportRow(**r) for r in cur.fetchall()]


@app.get("/sanctions/vessels", response_model=list[SanctionedVessel])
def sanctioned_vessel_registry(
    conn=Depends(get_db),
    search: Optional[str] = Query(None, description="Case-insensitive substring match on vessel name"),
    limit: int = Query(100, ge=1, le=5000),
):
    """The OFAC SDN vessel registry itself (not joined to AIS)."""
    where = ["lower(sdn_type) = 'vessel'"]
    params: list = []
    if search:
        where.append("name ILIKE %s")
        params.append(f"%{search}%")
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            f"""
            SELECT ent_num, name, program, vessel_flag, remarks
            FROM sanctions WHERE {' AND '.join(where)}
            ORDER BY name LIMIT %s;
            """,
            params + [limit],
        )
        return [SanctionedVessel(**r) for r in cur.fetchall()]


# ============================================================================
# Knowledge graph: supplier -> port -> chokepoint -> import port -> refinery,
# with live corridor risk overlaid from structured_events (see api/graph.py).
# ============================================================================

from api import graph as kg  # noqa: E402  (import placed with its endpoints)


def _live_graph(conn, window_days: int, half_life_days: float):
    g = kg.get_graph()
    kg.overlay_risk(g, kg.corridor_risks(conn, window_days, half_life_days))
    return g


@app.get("/graph")
def full_graph(
    conn=Depends(get_db),
    window_days: int = Query(30, ge=1, le=365),
    half_life_days: float = Query(7.0, gt=0),
):
    """The whole supply-chain graph with live chokepoint risk — nodes carry
    lat/lon so the frontend can draw this straight onto the Leaflet map."""
    g = _live_graph(conn, window_days, half_life_days)
    return kg.as_dict(g)


@app.get("/graph/routes")
def graph_routes(
    conn=Depends(get_db),
    supplier: str = Query(..., description="e.g. 'Russia', 'Iraq', 'Saudi Arabia'"),
    refinery: str = Query("Jamnagar (RIL)", description="e.g. 'Jamnagar (RIL)', 'Paradip (IOCL)'"),
    window_days: int = Query(30, ge=1, le=365),
    half_life_days: float = Query(7.0, gt=0),
):
    """Every way this supplier's crude can reach this refinery, with ETA and
    per-chokepoint risk, fastest first."""
    g = _live_graph(conn, window_days, half_life_days)
    result = kg.routes(g, supplier, refinery)
    if result is None:
        raise HTTPException(status_code=404, detail="unknown supplier or refinery id — see /graph for valid ids")
    return {"supplier": supplier, "refinery": refinery, "routes": result}


@app.get("/graph/alternatives")
def graph_alternatives(
    conn=Depends(get_db),
    refinery: str = Query("Jamnagar (RIL)"),
    max_risk: float = Query(0.5, ge=0, le=1, description="A route is viable only if every chokepoint on it is below this risk"),
    window_days: int = Query(30, ge=1, le=365),
    half_life_days: float = Query(7.0, gt=0),
):
    """The procurement question: ranked supplier options for this refinery
    given TODAY'S chokepoint risk — fastest acceptably-safe route per
    supplier, with grade fit and import share, viable options first. This is
    what the Procurement agent reasons over and what the reroute map draws."""
    g = _live_graph(conn, window_days, half_life_days)
    if refinery not in g:
        raise HTTPException(status_code=404, detail="unknown refinery id — see /graph for valid ids")
    return {
        "refinery": refinery,
        "max_risk": max_risk,
        "chokepoint_risk": {n: d.get("risk", 0.0) for n, d in g.nodes(data=True)
                            if d.get("type") == "chokepoint"},
        "chokepoint_evidence": {n: d.get("risk_events", 0) for n, d in g.nodes(data=True)
                                if d.get("type") == "chokepoint"},
        "options": kg.alternatives(g, refinery, max_risk),
    }


# ============================================================================
# Scenario Modeller: signal-triggered, mean-reverting jump-diffusion Monte
# Carlo (scenario/engine.py). Pure computation, no DB dependency, so it's
# independently testable and independently fast (~10k paths in a few ms).
# ============================================================================

class ScenarioRequest(BaseModel):
    risk_score: float = Field(..., ge=0, le=1, description="Corridor risk score, e.g. from /corridors/{c}/risk-score")
    jump_size_pct: Optional[float] = Field(None, description="Override the risk-scaled jump size directly (assumption panel knob)")
    elasticity: float = Field(1.2, gt=0, description="Reserve-cover disruption elasticity (assumption panel knob) — simplified linear proxy, see 'caveat' in the response")
    days_to_reroute: int = Field(21, gt=0, description="Mean-reversion half-life in days (assumption panel knob)")
    brent_usd: float = Field(82.0, gt=0, description="Baseline Brent price before the shock")
    baseline_reserve_days: float = Field(9.5, gt=0, description="India's strategic reserve cover before the shock (PPAC figure)")
    daily_import_bbl: float = Field(5_000_000.0, gt=0, description="India's approximate daily crude import volume")
    usd_inr: float = Field(83.0, gt=0)
    n_paths: int = Field(10_000, ge=100, le=100_000)
    horizon_days: int = Field(30, ge=1, le=365)
    reserve_threshold_days: float = Field(7.0, gt=0, description="Reserve-cover threshold for P(cover < threshold)")
    seed: Optional[int] = Field(None, description="Set for reproducible output (used by tests/demo replay)")


class ScenarioAssumptionsOut(BaseModel):
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


class ScenarioResultsOut(BaseModel):
    median_shock_pct: float
    var95_shock_pct: float
    median_reserve_cover_days: float
    var95_reserve_cover_days: float
    prob_reserve_cover_below_threshold: float
    median_cost_inr_cr_per_day: float
    var95_cost_inr_cr_per_day: float


class ScenarioDistributionOut(BaseModel):
    shock_pct: list[float]
    reserve_cover_days: list[float]


class ScenarioResponse(BaseModel):
    assumptions: ScenarioAssumptionsOut
    results: ScenarioResultsOut
    distribution_sample: ScenarioDistributionOut
    caveat: str
    elapsed_ms: float


@app.post("/scenario/run", response_model=ScenarioResponse)
def scenario_run(req: ScenarioRequest = Body(...)):
    """Run the Monte Carlo scenario for a given corridor risk score. Every
    input is an explicit, editable assumption (the frontend's 3-knob panel
    maps to jump_size_pct / elasticity / days_to_reroute) — nothing here is
    a hidden constant. See scenario/engine.py for the model itself."""
    return scenario_engine.run_scenario(**req.model_dump())


# ============================================================================
# Pipeline: the LangGraph orchestration over everything above — signal ->
# scenario -> procurement -> summary, one synchronous call (agents/graph.py).
# ============================================================================

from agents import graph as agent_pipeline  # noqa: E402  (import placed with its endpoint)


class InjectedEventIn(BaseModel):
    corridor: str = Field(..., description="Must match a corridor id, e.g. 'Strait of Hormuz'")
    severity_score: float = Field(..., ge=0, le=10)
    confidence: float = Field(..., ge=0, le=1)


class ScenarioParamsIn(BaseModel):
    jump_size_pct: Optional[float] = None
    elasticity: float = 1.2
    days_to_reroute: int = 21
    brent_usd: float = 82.0
    baseline_reserve_days: float = 9.5
    daily_import_bbl: float = 5_000_000.0
    usd_inr: float = 83.0
    n_paths: int = 10_000
    horizon_days: int = 30
    reserve_threshold_days: float = 7.0
    seed: Optional[int] = None


class PipelineRequest(BaseModel):
    corridor: str = "Strait of Hormuz"
    refinery: str = "Jamnagar (RIL)"
    window_days: int = 30
    half_life_days: float = 7.0
    max_acceptable_risk: float = Field(0.5, ge=0, le=1)
    scenario: ScenarioParamsIn = ScenarioParamsIn()
    injected_event: Optional[InjectedEventIn] = Field(
        None,
        description="Replay a cached event instead of querying live data — the 'inject signal' "
                    "demo button, and the guaranteed fallback if the DB or live news isn't cooperating.",
    )


@app.post("/pipeline/run")
def pipeline_run(req: PipelineRequest = Body(...)):
    """Run the full signal -> scenario -> procurement -> summary pipeline in
    one call. Returns the final state: risk score, the Monte Carlo scenario
    (same shape as /scenario/run), ranked procurement options (same shape as
    /graph/alternatives), the templated one-line summary, and per-step
    wall-clock durations (`durations_ms`, `total_ms`) — this is what the
    frontend's live latency timer reads.

    No `Depends(get_db)` on the signature deliberately: when `injected_event`
    is given, this handler never touches the database pool at all, so the
    'inject signal' demo path is genuinely independent of the DB being
    reachable, not just of live news existing.

    Not a response_model on purpose, matching /graph/alternatives above:
    the procurement options' shape is owned by api/graph.py, not duplicated
    here.
    """
    initial_state: dict = {
        "corridor": req.corridor,
        "refinery": req.refinery,
        "window_days": req.window_days,
        "half_life_days": req.half_life_days,
        "max_acceptable_risk": req.max_acceptable_risk,
        "scenario_params": req.scenario.model_dump(exclude_none=True),
    }

    if req.injected_event is not None:
        initial_state["injected_event"] = req.injected_event.model_dump()
        return agent_pipeline.run_pipeline(initial_state)

    conn = pool.getconn()
    try:
        initial_state["conn"] = conn
        return agent_pipeline.run_pipeline(initial_state)
    finally:
        pool.putconn(conn)


@app.get("/freshness")
def freshness(conn=Depends(get_db)):
    """When each feed last loaded (from ingest_runs) plus live row counts —
    lets the dashboard show 'data as of' per source, and lets anyone verify
    the pipeline is actually running."""
    now = datetime.now(timezone.utc)
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT feed, last_run, last_status, last_rows, note FROM ingest_runs ORDER BY feed;")
        runs = []
        for r in cur.fetchall():
            max_age = FEED_MAX_AGE_HOURS.get(r["feed"])
            age_h = (now - r["last_run"]).total_seconds() / 3600 if r["last_run"] else None
            stale = bool(
                r["last_status"] != "ok"
                or age_h is None
                or (max_age is not None and age_h > max_age)
            )
            runs.append(FeedFreshness(**r, stale=stale))
        cur.execute(
            """
            SELECT 'prices' AS t, count(*) AS n FROM prices
            UNION ALL SELECT 'price_ticks', count(*) FROM price_ticks
            UNION ALL SELECT 'sanctions', count(*) FROM sanctions
            UNION ALL SELECT 'vessels', count(*) FROM vessels
            UNION ALL SELECT 'imports_india', count(*) FROM imports_india
            UNION ALL SELECT 'structured_events', count(*) FROM structured_events;
            """
        )
        counts = {r["t"]: r["n"] for r in cur.fetchall()}
    return {"feeds": runs, "table_counts": counts}