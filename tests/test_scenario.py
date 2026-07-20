"""Smoke tests for the Scenario Modeller (no DB, no network — pure numpy).

Scoped per task.md: sane output ranges and runs-in-milliseconds, not
exhaustive statistical validation of the Monte Carlo itself.
"""
from scenario import engine


def test_output_shape_and_ranges():
    r = engine.run_scenario(risk_score=0.8, seed=1)

    assert set(r.keys()) == {"assumptions", "results", "distribution_sample", "caveat", "elapsed_ms"}

    res = r["results"]
    assert res["median_shock_pct"] >= 0
    assert res["var95_shock_pct"] >= res["median_shock_pct"]  # VaR is the tail, must be >= median
    assert 0 <= res["prob_reserve_cover_below_threshold"] <= 1
    assert res["median_reserve_cover_days"] > 0
    assert res["median_cost_inr_cr_per_day"] >= 0

    assert len(r["distribution_sample"]["shock_pct"]) == 19  # percentiles 5..95 step 5
    assert isinstance(r["caveat"], str) and "simplified" in r["caveat"].lower()


def test_runs_fast():
    r = engine.run_scenario(risk_score=0.8, seed=1, n_paths=10_000, horizon_days=30)
    assert r["elapsed_ms"] < 500  # generous CI margin; typically a few ms


def test_higher_risk_means_bigger_shock_and_worse_reserve_cover():
    low = engine.run_scenario(risk_score=0.1, seed=42)
    high = engine.run_scenario(risk_score=0.9, seed=42)

    assert high["results"]["median_shock_pct"] > low["results"]["median_shock_pct"]
    assert high["results"]["median_reserve_cover_days"] < low["results"]["median_reserve_cover_days"]
    assert high["results"]["median_cost_inr_cr_per_day"] > low["results"]["median_cost_inr_cr_per_day"]
    assert high["results"]["prob_reserve_cover_below_threshold"] >= low["results"]["prob_reserve_cover_below_threshold"]


def test_zero_risk_means_near_zero_jump():
    r = engine.run_scenario(risk_score=0.0, seed=1)
    assert r["assumptions"]["jump_size_pct"] == 0.0
    # only diffusion noise left, no shock — median shock should be small
    assert r["results"]["median_shock_pct"] < 0.1


def test_jump_size_override_bypasses_risk_scaling():
    r = engine.run_scenario(risk_score=0.0, jump_size_pct=0.5, seed=1)
    assert r["assumptions"]["jump_size_pct"] == 0.5
    assert r["results"]["median_shock_pct"] > 0.3  # dominated by the forced jump, not risk=0


def test_reproducible_with_seed():
    a = engine.run_scenario(risk_score=0.7, seed=99)
    b = engine.run_scenario(risk_score=0.7, seed=99)
    assert a["results"] == b["results"]


def test_assumptions_echo_every_input():
    kwargs = dict(
        risk_score=0.6, elasticity=0.9, days_to_reroute=14, brent_usd=75.0,
        baseline_reserve_days=10.0, daily_import_bbl=4_500_000.0, usd_inr=84.5,
        n_paths=2000, horizon_days=20, reserve_threshold_days=6.0, seed=5,
    )
    r = engine.run_scenario(**kwargs)
    a = r["assumptions"]
    for key, value in kwargs.items():
        if key == "risk_score":
            continue
        assert a[key] == value, f"{key} not echoed back correctly"
