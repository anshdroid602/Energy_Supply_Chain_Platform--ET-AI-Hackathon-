"""Unit tests for the deterministic extraction rules (no network, no DB)."""
import extract


def make_event(**overrides):
    event = {
        "event_id": "1",
        "event_date": "20260701",
        "event_code": "190",
        "actor1": "IRN",
        "actor2": "USA",
        "goldstein_scale": -10.0,
        "num_mentions": 5,
        "avg_tone": -5.0,
        "location_country": "IR",
        "action_lat": None,
        "action_lon": None,
        "context_articles": [],
    }
    event.update(overrides)
    return event


# --- corridor: geofence first, country fallback -----------------------------

def test_corridor_geofence_hormuz():
    assert extract.extract_corridor("IR", 26.5, 56.4) == "Strait of Hormuz"


def test_corridor_geofence_beats_country():
    # coordinates in the Red Sea, country code Saudi -> geofence wins (same
    # here, but e.g. an Egypt-coded event at Hormuz coords must map to Hormuz)
    assert extract.extract_corridor("EG", 26.5, 56.4) == "Strait of Hormuz"


def test_corridor_country_fallback_without_coords():
    assert extract.extract_corridor("IR", None, None) == "Strait of Hormuz"
    assert extract.extract_corridor("EG", None, None) == "Suez Canal"


def test_corridor_inland_coords_fall_back_to_country():
    # Tehran is outside every box -> falls back to Iran -> Hormuz
    assert extract.extract_corridor("IR", 35.7, 51.4) == "Strait of Hormuz"


def test_corridor_unknown():
    assert extract.extract_corridor("US", 38.9, -77.0) == "none"
    assert extract.extract_corridor(None, None, None) == "none"


# --- category: themes first, CAMEO fallback ----------------------------------

def test_category_theme_beats_cameo():
    event = make_event(event_code="036")  # diplomatic CAMEO
    assert extract.extract_event_category(event, ["SANCTIONS_X"]) == "sanction"


def test_category_cameo_military_fallback():
    for code in ("180", "190", "202"):
        assert extract.extract_event_category(make_event(event_code=code), []) == "military_strike"


def test_category_cameo_sanction_fallback():
    for code in ("163", "1631", "172"):
        assert extract.extract_event_category(make_event(event_code=code), []) == "sanction"


def test_category_diplomatic_and_other():
    assert extract.extract_event_category(make_event(event_code="036"), []) == "diplomatic"
    assert extract.extract_event_category(make_event(event_code="100"), []) == "other"


# --- scores stay in bounds ----------------------------------------------------

def test_severity_bounds():
    hi = extract.extract_severity_score(make_event(goldstein_scale=-10, num_mentions=9999, avg_tone=-100))
    lo = extract.extract_severity_score(make_event(goldstein_scale=0, num_mentions=0, avg_tone=0))
    assert 0.0 <= lo <= hi <= 10.0


def test_confidence_bounds():
    c = extract.extract_confidence(make_event(), [])
    assert 0.0 <= c <= 1.0


# --- full record shape ---------------------------------------------------------

def test_process_event_has_all_fields():
    out = extract.process_event(make_event(action_lat=26.5, action_lon=56.4))
    assert out["corridor_affected"] == "Strait of Hormuz"
    assert out["lat"] == 26.5 and out["lon"] == 56.4
    assert out["event_date"] == "2026-07-01"


def test_safe_process_event_never_raises():
    out = extract.safe_process_event(None, 0)
    assert out["event_category"] == "other" and out["confidence"] == 0.0
