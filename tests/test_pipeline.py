"""Smoke tests for the LangGraph pipeline (no DB, no network).

Uses the 'injected_event' offline path deliberately — this is the same path
the demo's 'inject signal' button and cached-event fallback use, so testing
it here doubles as a check that the demo-safe route actually works without
a live database. DB-backed tests belong with test_api.py's
DATABASE_URL_TEST-gated suite, not here.
"""
from agents.graph import run_pipeline

# Mirrors frontend/src/demoFixtures.js's CACHED_DEMO_EVENT. Run
# `python scripts/capture_demo_event.py --write` against the real DB to
# replace both copies with a real captured event instead of editing by hand.
# DEMO_EVENT_START
CACHED_EVENT = {
    "corridor": "Strait of Hormuz",
    "severity_score": 9.4,
    "confidence": 0.75,
}
# DEMO_EVENT_END


def _run(**overrides):
    state = {
        "injected_event": CACHED_EVENT,
        "corridor": "Strait of Hormuz",
        "refinery": "Jamnagar (RIL)",
        "scenario_params": {"seed": 42},
    }
    state.update(overrides)
    return run_pipeline(state)


def test_pipeline_runs_fully_offline():
    out = _run()
    for key in ("risk_score", "risk_level", "risk_event_count",
                "scenario_result", "procurement_options", "summary",
                "durations_ms", "total_ms"):
        assert key in out, f"missing '{key}' in pipeline output"


def test_all_four_nodes_recorded_their_timing():
    out = _run()
    assert set(out["durations_ms"].keys()) == {"signal", "scenario", "procurement", "summary"}
    assert out["total_ms"] >= 0


def test_no_db_connection_leaks_into_output():
    out = _run()
    assert "conn" not in out


def test_risk_score_matches_injected_event_formula():
    # decay = 1 for a same-day cached signal -> risk = severity/10 * confidence.
    # Derived from CACHED_EVENT itself (not hardcoded) so this test stays
    # correct after CACHED_EVENT is swapped for a real captured event.
    out = _run()
    expected = round((CACHED_EVENT["severity_score"] / 10.0) * CACHED_EVENT["confidence"], 3)
    assert out["risk_score"] == expected
    assert out["risk_event_count"] == 1


def test_summary_mentions_corridor_and_a_number():
    out = _run()
    assert "Strait of Hormuz" in out["summary"]
    assert "crore/day" in out["summary"]


def test_procurement_options_present_and_ranked():
    out = _run()
    options = out["procurement_options"]
    assert len(options) > 0
    # viable options (if any) must sort ahead of non-viable ones
    viable_flags = [o["viable"] for o in options]
    assert viable_flags == sorted(viable_flags, reverse=True)


def test_low_vs_high_severity_changes_the_recommendation_inputs():
    calm = _run(injected_event={"corridor": "Strait of Hormuz", "severity_score": 1.0, "confidence": 0.5})
    crisis = _run(injected_event={"corridor": "Strait of Hormuz", "severity_score": 9.5, "confidence": 0.9})

    assert crisis["risk_score"] > calm["risk_score"]
    assert (crisis["scenario_result"]["results"]["median_cost_inr_cr_per_day"]
            > calm["scenario_result"]["results"]["median_cost_inr_cr_per_day"])
