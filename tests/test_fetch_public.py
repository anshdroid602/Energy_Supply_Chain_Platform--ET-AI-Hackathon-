"""Tests the GDELT daily-dump parser against a synthetic file, so a silent
column shift in the real format (parsed by position) is caught in CI."""
import io
from datetime import date, timedelta

import fetch_public


def synthetic_row(event_id="1001", sqldate=None, actor1="IRN", actor2="USA",
                  event_code="190", goldstein="-10.0", mentions="12",
                  tone="-4.5", geo_country="IR", lat="26.5", lon="56.4"):
    """One 58-column GDELT 1.0 export row with our columns in the right slots."""
    sqldate = sqldate or (date.today() - timedelta(days=1)).strftime("%Y%m%d")
    cols = [""] * 58
    cols[0] = event_id
    cols[1] = sqldate
    cols[7] = actor1
    cols[17] = actor2
    cols[26] = event_code
    cols[30] = goldstein
    cols[31] = mentions
    cols[34] = tone
    cols[51] = geo_country
    cols[53] = lat
    cols[54] = lon
    return "\t".join(cols)


def parse(rows):
    return fetch_public.parse_day_csv(io.StringIO("\n".join(rows)))


def test_parses_matching_event():
    df = parse([synthetic_row()])
    assert len(df) == 1
    row = df.iloc[0]
    assert row["Actor1CountryCode"] == "IRN"
    assert row["GoldsteinScale"] == -10.0
    assert row["ActionGeo_CountryCode"] == "IR"
    assert row["ActionGeo_Lat"] == 26.5 and row["ActionGeo_Long"] == 56.4


def test_filters_apply():
    old = (date.today() - timedelta(days=fetch_public.WINDOW_DAYS + 30)).strftime("%Y%m%d")
    df = parse([
        synthetic_row(event_id="1"),
        synthetic_row(event_id="2", actor1="FRA", actor2="DEU"),   # wrong actors
        synthetic_row(event_id="3", goldstein="2.0"),              # not conflictual
        synthetic_row(event_id="4", sqldate=old),                  # re-reported old event
    ])
    assert list(df["GlobalEventID"]) == ["1"]


def test_missing_coords_become_nan_not_crash():
    df = parse([synthetic_row(lat="", lon="")])
    assert len(df) == 1
    assert df.iloc[0]["ActionGeo_Lat"] != df.iloc[0]["ActionGeo_Lat"]  # NaN
