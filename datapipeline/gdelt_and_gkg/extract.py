"""
Deterministic rule-based GDELT event bundle -> structured risk signal extractor.

No LLM. No API calls. No ML. Python standard library only.

Usage:
  python extract.py                                   # reads event_bundles.json, writes structured_events.json
  python extract.py --input other.json --output out.json
"""

import argparse
import json
from datetime import datetime

# ---------------------------------------------------------------------------
# Reference tables
# ---------------------------------------------------------------------------


# GDELT's location_country field uses FIPS 10-4 country codes, NOT ISO 3166-1
# alpha-2. They agree for some countries here (Iran, Qatar, Djibouti, Eritrea,
# Saudi Arabia, Egypt) but diverge for others -- Oman, UAE, Kuwait, Bahrain,
# Yemen, and Sudan all have different FIPS codes than their ISO2 codes.
# Using ISO2 here silently drops most real matches into "none".
CORRIDOR_MAP = {
    "IR": "Strait of Hormuz",   # Iran (FIPS == ISO2)
    "MU": "Strait of Hormuz",   # Oman (FIPS; ISO2 is OM)
    "TC": "Persian Gulf",       # United Arab Emirates (FIPS; ISO2 is AE)
    "QA": "Persian Gulf",       # Qatar (FIPS == ISO2)
    "KU": "Persian Gulf",       # Kuwait (FIPS; ISO2 is KW)
    "BA": "Persian Gulf",       # Bahrain (FIPS; ISO2 is BH)
    "YM": "Red Sea",            # Yemen (FIPS; ISO2 is YE)
    "DJ": "Red Sea",            # Djibouti (FIPS == ISO2)
    "ER": "Red Sea",            # Eritrea (FIPS == ISO2)
    "SU": "Red Sea",            # Sudan (FIPS; ISO2 is SD)
    "SA": "Red Sea",            # Saudi Arabia (FIPS == ISO2)
    "EG": "Suez Canal",         # Egypt (FIPS == ISO2)
}

# CAMEO root codes 01-05 are the "verbal cooperation" quad class (public
# statement, appeal, intend to cooperate, consult, diplomatic cooperation) —
# used here as the deterministic stand-in for "diplomatic interaction codes".
DIPLOMATIC_CAMEO_ROOTS = {"01", "02", "03", "04", "05"}

# CAMEO fallbacks for when no GKG themes are available (the public/no-key
# fetch path has no GKG stage): 18 assault / 19 fight / 20 unconventional
# mass violence -> military_strike; 163x impose embargo-boycott-sanctions
# and 172x impose administrative sanctions -> sanction.
MILITARY_CAMEO_ROOTS = {"18", "19", "20"}
SANCTION_CAMEO_PREFIXES = ("163", "172")

DIPLOMATIC_THEME_KEYWORDS = ("DIPLOMATIC", "NEGOTIATION", "TREATY", "SUMMIT", "MEETING")

CATEGORY_LABELS = {
    "military_strike": "Military strike",
    "sanction": "Sanction",
    "maritime_incident": "Maritime incident",
    "diplomatic": "Diplomatic engagement",
    "other": "Event",
}

HIGH_GOLDSTEIN_THRESHOLD = 7.0  # |goldstein_scale| at/above this counts as "high magnitude"


# ---------------------------------------------------------------------------
# Field extractors
# ---------------------------------------------------------------------------

def extract_event_date(raw_date):
    """YYYYMMDD -> YYYY-MM-DD. Falls back to naive slicing if the value
    isn't a clean calendar date, but never raises."""
    date_str = str(raw_date).strip()
    try:
        return datetime.strptime(date_str, "%Y%m%d").strftime("%Y-%m-%d")
    except ValueError:
        if len(date_str) == 8 and date_str.isdigit():
            return f"{date_str[0:4]}-{date_str[4:6]}-{date_str[6:8]}"
        return date_str  # last resort: pass through unchanged rather than crash


def extract_actors(event):
    actors = []
    for key in ("actor1", "actor2"):
        val = event.get(key)
        if val:  # excludes None and empty string
            actors.append(val)
    return actors


def extract_corridor(location_country):
    return CORRIDOR_MAP.get(location_country, "none")


def flatten_themes(context_articles):
    themes = []
    for article in context_articles or []:
        themes.extend(article.get("themes") or [])
    return themes


def cameo_root(event_code):
    code_str = str(event_code or "").strip()
    if len(code_str) >= 2:
        return code_str[:2]
    return code_str.zfill(2)


def extract_event_category(event, all_themes):
    if any("SANCTIONS" in t for t in all_themes):
        return "sanction"

    if any("MARITIME_INCIDENT" in t for t in all_themes):
        return "maritime_incident"

    if any(("MILITARY" in t or "ARMEDCONFLICT" in t) for t in all_themes):
        return "military_strike"

    # No theme match (or no GKG context at all): fall back to the CAMEO
    # event code, which every GDELT event carries.
    code_str = str(event.get("event_code") or "").strip()
    if code_str.startswith(SANCTION_CAMEO_PREFIXES):
        return "sanction"
    if cameo_root(event.get("event_code")) in MILITARY_CAMEO_ROOTS:
        return "military_strike"

    is_diplomatic_code = cameo_root(event.get("event_code")) in DIPLOMATIC_CAMEO_ROOTS
    is_diplomatic_theme = any(
        keyword in t for t in all_themes for keyword in DIPLOMATIC_THEME_KEYWORDS
    )
    if is_diplomatic_code or is_diplomatic_theme:
        return "diplomatic"

    return "other"


def extract_severity_score(event):
    goldstein = event.get("goldstein_scale") or 0.0
    num_mentions = event.get("num_mentions") or 0
    avg_tone = event.get("avg_tone") or 0.0

    severity = (
        0.55 * abs(goldstein)
        + 0.25 * min(num_mentions, 10)
        + 0.20 * abs(avg_tone)
    )
    severity = max(0.0, min(10.0, severity))
    return round(severity, 1)


def extract_confidence(event, context_articles):
    goldstein = event.get("goldstein_scale") or 0.0
    actors_complete = bool(event.get("actor1")) and bool(event.get("actor2"))
    num_articles = len(context_articles or [])

    theme_sets = [set(a.get("themes") or []) for a in (context_articles or [])]
    articles_agree = False
    if num_articles > 1:
        for i in range(len(theme_sets)):
            for j in range(i + 1, len(theme_sets)):
                if theme_sets[i] & theme_sets[j]:
                    articles_agree = True
                    break
            if articles_agree:
                break

    confidence = 0.5
    if num_articles > 1:
        confidence += 0.10          # more than one context article exists
    if articles_agree:
        confidence += 0.15          # multiple articles agree on themes
    if abs(goldstein) >= HIGH_GOLDSTEIN_THRESHOLD:
        confidence += 0.15          # Goldstein magnitude is high
    if actors_complete:
        confidence += 0.10          # actor information is complete

    confidence = max(0.0, min(1.0, confidence))
    return round(confidence, 2)


def extract_summary(category, actors, location_country):
    label = CATEGORY_LABELS.get(category, "Event")
    who = " and ".join(actors) if actors else "unspecified actors"
    where = location_country if location_country else "an unspecified location"
    return f"{label} involving {who} in {where}."


# ---------------------------------------------------------------------------
# Per-event pipeline
# ---------------------------------------------------------------------------

def process_event(event):
    context_articles = event.get("context_articles") or []
    all_themes = flatten_themes(context_articles)

    actors = extract_actors(event)
    location_country = event.get("location_country")
    category = extract_event_category(event, all_themes)

    return {
        "event_id": event.get("event_id"),
        "event_date": extract_event_date(event.get("event_date")),
        "actors": actors,
        "location_country": location_country,
        "corridor_affected": extract_corridor(location_country),
        "event_category": category,
        "severity_score": extract_severity_score(event),
        "confidence": extract_confidence(event, context_articles),
        "summary": extract_summary(category, actors, location_country),
    }


def safe_process_event(event, index):
    """Never let one malformed event stop the whole run. On failure, still
    emit a schema-valid object so every input event produces exactly one
    output object as required."""
    try:
        return process_event(event)
    except Exception as e:
        print(f"  warning: event at index {index} failed ({e}); emitting fallback record")
        return {
            "event_id": event.get("event_id") if isinstance(event, dict) else None,
            "event_date": extract_event_date(event.get("event_date")) if isinstance(event, dict) else "",
            "actors": [],
            "location_country": event.get("location_country") if isinstance(event, dict) else None,
            "corridor_affected": "none",
            "event_category": "other",
            "severity_score": 0.0,
            "confidence": 0.0,
            "summary": "Event with incomplete data.",
        }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="event_bundles.json")
    parser.add_argument("--output", default="structured_events.json")
    args = parser.parse_args()

    with open(args.input) as f:
        bundles = json.load(f)

    results = [safe_process_event(event, i) for i, event in enumerate(bundles)]

    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Processed {len(results)} / {len(bundles)} events")
    print(f"Saved {args.output}")

    if results:
        print("\nSample output:\n")
        print(json.dumps(results[0], indent=2))


if __name__ == "__main__":
    main()