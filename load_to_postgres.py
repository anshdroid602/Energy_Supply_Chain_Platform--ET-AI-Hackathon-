"""
Load structured_events.json into Postgres.

Creates the table if it doesn't exist, then upserts every event by event_id
(so re-running this after new batches finish doesn't create duplicates or
choke on events you've already loaded).

Usage:
  python load_to_postgres.py
  python load_to_postgres.py --input structured_events.json --dsn "postgresql://user:pass@localhost:5432/dbname"

Requires: pip install psycopg2-binary python-dotenv
Set DATABASE_URL in your .env, or pass --dsn explicitly.
"""

import argparse
import json
import os

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS structured_events (
    event_id            TEXT PRIMARY KEY,
    event_date          DATE,
    actors              TEXT[],
    location_country    TEXT,
    corridor_affected   TEXT,
    event_category      TEXT,
    severity_score      REAL,
    confidence          REAL,
    summary             TEXT,
    loaded_at           TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_structured_events_corridor
    ON structured_events (corridor_affected);
CREATE INDEX IF NOT EXISTS idx_structured_events_date
    ON structured_events (event_date);
CREATE INDEX IF NOT EXISTS idx_structured_events_severity
    ON structured_events (severity_score DESC);
"""

UPSERT_SQL = """
INSERT INTO structured_events (
    event_id, event_date, actors, location_country,
    corridor_affected, event_category, severity_score, confidence, summary
)
VALUES %s
ON CONFLICT (event_id) DO UPDATE SET
    event_date        = EXCLUDED.event_date,
    actors             = EXCLUDED.actors,
    location_country   = EXCLUDED.location_country,
    corridor_affected  = EXCLUDED.corridor_affected,
    event_category     = EXCLUDED.event_category,
    severity_score     = EXCLUDED.severity_score,
    confidence         = EXCLUDED.confidence,
    summary            = EXCLUDED.summary,
    loaded_at          = now();
"""


def to_row(event):
    return (
        event.get("event_id"),
        event.get("event_date") or None,   # already YYYY-MM-DD, Postgres parses it directly
        event.get("actors") or [],
        event.get("location_country"),
        event.get("corridor_affected"),
        event.get("event_category"),
        event.get("severity_score"),
        event.get("confidence"),
        event.get("summary"),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="structured_events.json")
    parser.add_argument("--dsn", default=os.getenv("DATABASE_URL"),
                         help="Postgres connection string. Defaults to DATABASE_URL from .env")
    args = parser.parse_args()

    if not args.dsn:
        raise SystemExit("No DSN found. Set DATABASE_URL in .env or pass --dsn.")

    with open(args.input) as f:
        events = json.load(f)

    rows = [to_row(e) for e in events]

    conn = psycopg2.connect(args.dsn)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(CREATE_TABLE_SQL)
                psycopg2.extras.execute_values(cur, UPSERT_SQL, rows)
        print(f"Upserted {len(rows)} events into structured_events")

        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM structured_events;")
            total = cur.fetchone()[0]
            cur.execute("""
                SELECT corridor_affected, count(*), round(avg(severity_score)::numeric, 2)
                FROM structured_events
                GROUP BY corridor_affected
                ORDER BY count(*) DESC;
            """)
            breakdown = cur.fetchall()

        print(f"Total rows in table: {total}")
        print("\nBy corridor:")
        for corridor, count, avg_severity in breakdown:
            print(f"  {corridor:20s} {count:5d} events   avg severity {avg_severity}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()