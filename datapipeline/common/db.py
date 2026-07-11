"""Shared DB helpers: one connection string, upsert, and ingest-run bookkeeping."""
import os
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import execute_values

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DB_URL = os.environ.get("DATABASE_URL", "postgresql://app:app@localhost:5432/energy")


def connect():
    return psycopg2.connect(DB_URL)


def upsert(table, cols, rows, conflict=None):
    """Insert rows; on primary-key clash, skip (so re-running is safe)."""
    if not rows:
        return
    sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES %s"
    if conflict:
        sql += f" ON CONFLICT ({','.join(conflict)}) DO NOTHING"
    with connect() as conn, conn.cursor() as cur:
        execute_values(cur, sql, rows)
        conn.commit()


def record_run(feed, status, rows=0, note=None):
    """Log a loader run into ingest_runs (drives the controller's cadence
    gating and the API's /freshness endpoint)."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ingest_runs (feed, last_run, last_status, last_rows, note)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (feed) DO UPDATE SET
                last_run = EXCLUDED.last_run,
                last_status = EXCLUDED.last_status,
                last_rows = EXCLUDED.last_rows,
                note = EXCLUDED.note;
            """,
            (feed, datetime.now(timezone.utc), status, rows, note),
        )
        conn.commit()


def minutes_since_last_run(feed):
    """Minutes since the feed last ran successfully, or None if it never has."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT last_run FROM ingest_runs WHERE feed = %s AND last_status = 'ok';",
            (feed,),
        )
        row = cur.fetchone()
    if not row or not row[0]:
        return None
    return (datetime.now(timezone.utc) - row[0]).total_seconds() / 60.0


def prune_vessels(retention_hours=48):
    """The one table where old rows are genuinely obsolete: stale AIS
    position reports. Price/import/sanction/event history is kept — the
    scenario model calibrates on it and the risk score already down-weights
    old events by recency."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM vessels WHERE ts < now() - %s * INTERVAL '1 hour';",
            (retention_hours,),
        )
        deleted = cur.rowcount
        conn.commit()
    return deleted
