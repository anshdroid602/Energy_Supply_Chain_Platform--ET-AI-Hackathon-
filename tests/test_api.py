"""API integration tests against a real Postgres.

Skipped unless DATABASE_URL_TEST is set (CI provides a postgres service;
locally: docker run -d -p 5433:5432 -e POSTGRES_PASSWORD=test -e POSTGRES_DB=energy postgres:16
then DATABASE_URL_TEST=postgresql://postgres:test@localhost:5433/energy pytest tests/test_api.py).

Seeds a tiny known dataset and asserts every endpoint family responds with
the right shape — catching schema/SELECT drift that unit tests can't.
"""
import os
from datetime import date, datetime, timedelta, timezone

import pytest

DSN = os.environ.get("DATABASE_URL_TEST")
pytestmark = pytest.mark.skipif(not DSN, reason="DATABASE_URL_TEST not set")


@pytest.fixture(scope="module")
def client():
    os.environ["DATABASE_URL"] = DSN  # must be set before api.main import
    import psycopg2

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "datapipeline", "schema.sql")) as f:
        schema = f.read()

    conn = psycopg2.connect(DSN)
    with conn, conn.cursor() as cur:
        cur.execute(schema)
        cur.execute("""
            TRUNCATE structured_events, prices, price_ticks, sanctions,
                     vessels, imports_india, ingest_runs;
        """)
        today = date.today()
        cur.execute("""
            INSERT INTO structured_events
                (event_id, event_date, actors, location_country, lat, lon,
                 corridor_affected, event_category, severity_score, confidence, summary)
            VALUES
                ('t1', %s, ARRAY['IRN'], 'IR', 26.5, 56.4,
                 'Strait of Hormuz', 'military_strike', 9.0, 0.8, 'Test strike at Hormuz.'),
                ('t2', %s, ARRAY['USA'], 'IR', NULL, NULL,
                 'Strait of Hormuz', 'sanction', 6.0, 0.6, 'Test sanction.');
        """, (today, today - timedelta(days=5)))
        cur.execute("""
            INSERT INTO prices VALUES (%s, 'BRENT', 70.5, 'EIA'), (%s, 'WTI', 66.1, 'EIA');
        """, (today, today))
        cur.execute("INSERT INTO price_ticks VALUES (%s, 'BZ=F', 71.2);",
                    (datetime.now(timezone.utc),))
        cur.execute("""
            INSERT INTO sanctions VALUES
                (1, 'TESTSHIP', 'vessel', 'IRAN-EO13846', 'Panama', 'MMSI 123456789; test');
        """)
        cur.execute("""
            INSERT INTO vessels VALUES
                (123456789, 26.6, 56.5, 12.0, 90.0, %s, 'DIFFERENT NAME'),
                (999000999, 51.0, 3.0, 10.0, 180.0, %s, 'CLEAN SHIP');
        """, (datetime.now(timezone.utc), datetime.now(timezone.utc)))
        cur.execute("""
            INSERT INTO imports_india VALUES
                (%s, 'March', 2026, 'CRUDE OIL', 'Import', 19389.1, 122986.2, 13332.1);
        """, (date(2026, 3, 1),))
        cur.execute("""
            INSERT INTO ingest_runs VALUES
                ('eia', %s, 'ok', 500, NULL),
                ('ais', %s, 'ok', 100, NULL);
        """, (datetime.now(timezone.utc),
              datetime.now(timezone.utc) - timedelta(hours=48)))
    conn.close()

    from fastapi.testclient import TestClient
    from api.main import app
    with TestClient(app) as c:  # context manager runs the startup event (pool)
        yield c


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_events_carry_coordinates(client):
    r = client.get("/events", params={"corridor": "Strait of Hormuz"}).json()
    assert r["count"] == 2
    by_id = {e["event_id"]: e for e in r["results"]}
    assert by_id["t1"]["lat"] == 26.5 and by_id["t1"]["lon"] == 56.4
    assert by_id["t2"]["lat"] is None


def test_risk_score_flags_low_evidence(client):
    r = client.get("/corridors/Strait of Hormuz/risk-score").json()
    assert 0 < r["risk_score"] <= 1
    assert r["event_count_in_window"] == 2
    assert r["low_evidence"] is True          # 2 < default min_events of 10
    r2 = client.get("/corridors/Strait of Hormuz/risk-score",
                    params={"min_events": 2}).json()
    assert r2["low_evidence"] is False


def test_sanctioned_vessel_matched_by_mmsi(client):
    ships = client.get("/vessels/sanctioned").json()
    assert [s["mmsi"] for s in ships] == [123456789]
    assert ships[0]["sanction_match"] == "mmsi"  # name differs; remarks MMSI matched


def test_prices_and_imports(client):
    latest = client.get("/prices/latest").json()
    assert {d["ticker"] for d in latest["daily"]} == {"BRENT", "WTI"}
    imports = client.get("/imports/india").json()
    assert imports[0]["value_usd_mn"] == 13332.1


def test_graph_alternatives_with_live_risk(client):
    r = client.get("/graph/alternatives").json()
    assert r["chokepoint_evidence"]["Strait of Hormuz"] == 2
    assert len(r["options"]) >= 5


def test_freshness_stale_flag(client):
    feeds = {f["feed"]: f for f in client.get("/freshness").json()["feeds"]}
    assert feeds["eia"]["stale"] is False      # just ran
    assert feeds["ais"]["stale"] is True       # 48h old vs ~1h cadence
