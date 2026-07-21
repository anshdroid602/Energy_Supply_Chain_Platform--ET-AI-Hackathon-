"""In-process data access for the agents.

Reads the shared Postgres directly and reuses the existing knowledge-graph
module (api.graph) — no HTTP hop to the read API, so the whole agent chain
runs in-process and self-contained (it does NOT need the FastAPI server up).
Postgres stays the single source of truth; this only reads.

Run context: `agents` and `api` are sibling top-level packages under
platform/, so `from api import graph` resolves when run from the repo root
(the same root uvicorn/pytest use).
"""
from __future__ import annotations

from typing import Optional

import psycopg2
import psycopg2.extras

from api import graph as kg

from . import config

# Mirror of api.main.RISK_LEVEL_THRESHOLDS (kept tiny to avoid importing the
# whole FastAPI app just for this mapping).
_RISK_LEVELS = [(0.8, "Critical"), (0.6, "High"), (0.35, "Medium"), (0.0, "Low")]


def risk_level_for(score: float) -> str:
    for threshold, label in _RISK_LEVELS:
        if score >= threshold:
            return label
    return "Low"


class DataSource:
    def __init__(self, database_url: Optional[str] = None):
        url = database_url or config.DATABASE_URL
        if not url:
            raise SystemExit("DATABASE_URL not set (put it in platform/.env)")
        self.conn = psycopg2.connect(url)
        self.conn.autocommit = True
        self._se_cols = self._table_columns("structured_events")

    def _table_columns(self, table: str) -> set:
        rows = self._rows(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s;",
            (table,),
        )
        return {r["column_name"] for r in rows}

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _rows(self, sql: str, params: tuple = ()) -> list:
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    # --- risk / news --------------------------------------------------------

    def corridor_risk(self, corridor: str,
                      window_days: Optional[int] = None,
                      half_life_days: Optional[float] = None) -> dict:
        """Confidence- and recency-weighted risk (0-1) for one corridor, plus
        its top contributing events. Same formula as /corridors/{c}/risk-score."""
        window_days = window_days or config.WINDOW_DAYS
        half_life_days = half_life_days or config.HALF_LIFE_DAYS
        all_risks = kg.corridor_risks(self.conn, window_days, half_life_days)
        entry = all_risks.get(corridor, {"risk": 0.0, "events": 0})
        # Older Neon deployments predate the lat/lon columns the committed
        # schema declares; degrade gracefully (evidence dots just lack coords)
        # rather than 500 like the current API does.
        coord_cols = ("lat, lon" if {"lat", "lon"} <= self._se_cols
                      else "NULL::float AS lat, NULL::float AS lon")
        top = self._rows(
            f"""
            SELECT event_id, event_date, summary, severity_score, confidence, {coord_cols}
            FROM structured_events
            WHERE corridor_affected = %s
              AND event_date >= (CURRENT_DATE - %s * INTERVAL '1 day')
            ORDER BY severity_score * confidence DESC NULLS LAST
            LIMIT 5;
            """,
            (corridor, window_days),
        )
        return {
            "risk": entry["risk"],
            "level": risk_level_for(entry["risk"]),
            "events": entry["events"],
            "top_events": top,
            "all_corridor_risks": all_risks,
        }

    # --- prices -------------------------------------------------------------

    def latest_brent(self) -> float:
        rows = self._rows(
            "SELECT usd FROM prices WHERE ticker = 'BRENT' ORDER BY day DESC LIMIT 1;"
        )
        if rows:
            return float(rows[0]["usd"])
        rows = self._rows(
            "SELECT usd FROM price_ticks WHERE ticker = 'BZ=F' ORDER BY ts DESC LIMIT 1;"
        )
        return float(rows[0]["usd"]) if rows else 80.0  # last-resort default

    def brent_tick_change(self) -> Optional[float]:
        """Latest intraday Brent tick minus the previous one (the 'tick-up'
        evidence line). None if we don't have two ticks."""
        rows = self._rows(
            "SELECT usd FROM price_ticks WHERE ticker = 'BZ=F' ORDER BY ts DESC LIMIT 2;"
        )
        if len(rows) < 2:
            return None
        return round(float(rows[0]["usd"]) - float(rows[1]["usd"]), 2)

    # --- imports (PPAC) -----------------------------------------------------

    def india_daily_crude_bbl(self) -> float:
        """India's crude imports in barrels/day from the latest PPAC month;
        falls back to the config anchor if PPAC has no crude import row."""
        rows = self._rows(
            """
            SELECT quantity_tmt
            FROM imports_india
            WHERE upper(product) = 'CRUDE OIL' AND trade = 'Import'
              AND period IS NOT NULL AND quantity_tmt IS NOT NULL
            ORDER BY period DESC LIMIT 1;
            """
        )
        if rows and rows[0]["quantity_tmt"]:
            tmt = float(rows[0]["quantity_tmt"])          # thousand tonnes / month
            barrels = tmt * 1000.0 * config.ASSUMPTIONS["bbl_per_tonne"]
            return barrels / 30.4                          # -> barrels/day
        return config.ASSUMPTIONS["india_crude_kbd"] * 1000.0

    # --- vessels / sanctions ------------------------------------------------

    def sanctioned_vessels_in_window(self) -> int:
        rows = self._rows(
            """
            SELECT count(DISTINCT v.mmsi) AS n
            FROM vessels v
            JOIN sanctions s ON lower(s.sdn_type) = 'vessel'
             AND ( (s.remarks IS NOT NULL AND s.remarks LIKE '%%MMSI ' || v.mmsi::text || '%%')
                OR (s.name IS NOT NULL AND v.name IS NOT NULL
                    AND upper(trim(v.name)) = upper(trim(s.name))) );
            """
        )
        return int(rows[0]["n"]) if rows else 0

    # --- knowledge graph (live risk overlaid) -------------------------------

    def live_graph(self, window_days: Optional[int] = None,
                   half_life_days: Optional[float] = None):
        window_days = window_days or config.WINDOW_DAYS
        half_life_days = half_life_days or config.HALF_LIFE_DAYS
        g = kg.get_graph()
        kg.overlay_risk(g, kg.corridor_risks(self.conn, window_days, half_life_days))
        return g

    def corridor_import_share(self, g, corridor: str, refinery: str) -> float:
        """Fraction of India's crude (by import share) whose fastest route to
        this refinery crosses the corridor's chokepoint — derived live from
        the graph. Falls back to the config anchor if it can't be resolved."""
        chokepoint = config.CORRIDOR_TO_CHOKEPOINT.get(corridor)
        fallback = config.CORRIDOR_SHARE_FALLBACK.get(corridor, 0.3)
        if not chokepoint or chokepoint not in g or refinery not in g:
            return fallback
        suppliers = [n for n, d in g.nodes(data=True) if d.get("type") == "supplier"]
        total, dependent = 0.0, 0.0
        for s in suppliers:
            rts = kg.routes(g, s, refinery) or []
            if not rts:
                continue
            share = g.nodes[s].get("share_pct") or 0.0
            total += share
            if any(c["id"] == chokepoint for c in rts[0]["chokepoints"]):
                dependent += share
        return round(dependent / total, 3) if total > 0 else fallback
