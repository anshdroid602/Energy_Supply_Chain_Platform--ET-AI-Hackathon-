"""Unit tests for the agent layer.

Two halves:
  - the Monte-Carlo scenario engine (pure numpy, no DB)
  - the orchestrator end-to-end with a FAKE datasource and a DISABLED LLM, so
    the whole chain (LangGraph or sequential fallback) is exercised offline —
    no Postgres, no network, no API key needed.
"""
from agents import montecarlo
from agents.orchestrator import Orchestrator
from agents.schemas import PipelineResult
from api import graph as kg

MC = dict(corridor_share=0.4, india_daily_bbl=4.6e6)


# --- Monte-Carlo engine -----------------------------------------------------

def test_mc_output_bounds():
    r = montecarlo.simulate(80.0, "mean_reverting", seed=1, **MC)
    assert 0.0 <= r["p_cover_below_7"] <= 1.0
    assert r["reserve_cover_days_after"] <= r["reserve_cover_days_before"]
    assert r["cost_inr_crore_per_day"] >= 0.0
    assert r["cost_inr_crore_per_day_p95"] >= r["cost_inr_crore_per_day"]
    # percentiles are monotonic
    p = r["pct_change"]
    assert p["p5"] <= p["p50"] <= p["p95"]


def test_mc_is_deterministic_per_seed():
    a = montecarlo.simulate(80.0, "persistent", seed=42, **MC)
    b = montecarlo.simulate(80.0, "persistent", seed=42, **MC)
    assert a["median_pct_change"] == b["median_pct_change"]
    assert a["p95_var_pct"] == b["p95_var_pct"]


def test_persistent_jump_is_worse_than_mean_reverting():
    mr = montecarlo.simulate(80.0, "mean_reverting", seed=7, **MC)
    pr = montecarlo.simulate(80.0, "persistent", seed=7, **MC)
    # a regime-shift jump stays elevated -> larger sustained move
    assert pr["median_pct_change"] > mr["median_pct_change"]


def test_bigger_corridor_share_erodes_reserve_more():
    small = montecarlo.simulate(80.0, "persistent", corridor_share=0.1,
                                india_daily_bbl=4.6e6, seed=3)
    big = montecarlo.simulate(80.0, "persistent", corridor_share=0.6,
                              india_daily_bbl=4.6e6, seed=3)
    assert big["reserve_cover_days_after"] <= small["reserve_cover_days_after"]


# --- orchestrator (fakes) ---------------------------------------------------

class DummyLLM:
    enabled = False

    def narrate(self, *a, **k):
        return None            # force the template fallback path


class FakeDataSource:
    """Canned data so the chain runs with no Postgres/network."""
    def __init__(self, risk):
        self._risk = risk

    def corridor_risk(self, corridor, **k):
        return {
            "risk": self._risk,
            "level": "Critical" if self._risk >= 0.8 else "Low",
            "events": 84 if self._risk > 0 else 0,
            "top_events": ([{
                "event_id": "e1", "event_date": "2026-07-10", "summary": "strike",
                "severity_score": 8.0, "confidence": 0.8, "lat": 26.5, "lon": 56.5,
            }] if self._risk > 0 else []),
            "all_corridor_risks": {corridor: {"risk": self._risk, "events": 84}},
        }

    def brent_tick_change(self):
        return 0.5

    def sanctioned_vessels_in_window(self):
        return 3

    def latest_brent(self):
        return 80.0

    def india_daily_crude_bbl(self):
        return 4.6e6

    def live_graph(self, **k):
        g = kg.get_graph()
        kg.overlay_risk(g, {"Strait of Hormuz": {"risk": self._risk, "events": 84}})
        return g

    def corridor_import_share(self, g, corridor, refinery):
        return 0.4

    def close(self):
        pass


def _orch(risk):
    return Orchestrator(ds=FakeDataSource(risk), llm=DummyLLM(),
                        params={"max_risk": 0.5, "assumptions": {"n_paths": 2000}})


def test_pipeline_fires_and_reroutes_when_triggered():
    res = _orch(0.89).run("Strait of Hormuz", "Jamnagar (RIL)")
    assert isinstance(res, PipelineResult)
    assert res.risk.triggered and res.risk.risk_level == "Critical"
    assert res.scenario is not None and res.scenario.jump_type == "persistent"
    assert res.procurement is not None and res.procurement.top_pick is not None
    assert res.reserve is not None
    # Hormuz is blocked and a bypass (e.g. UAE via Fujairah) is the pick
    assert "Strait of Hormuz" in res.reroute.blocked_chokepoints
    assert res.procurement.top_pick.viable
    assert res.headline


def test_pipeline_stops_below_threshold():
    res = _orch(0.0).run("Strait of Hormuz", "Jamnagar (RIL)")
    assert not res.risk.triggered
    assert res.scenario is None
    assert res.procurement is None
    assert res.reroute is None
