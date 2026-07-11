"""EIA v2 -> prices table.  Official daily Brent (RBRTE) & WTI (RWTC) spot.

Run from the repo root:  python3 -m datapipeline.eia.loader
"""
import os

import requests

from datapipeline.common.db import upsert

SERIES = {"RBRTE": "BRENT", "RWTC": "WTI"}
URL = "https://api.eia.gov/v2/petroleum/pri/spt/data/"


def fetch():
    key = os.environ.get("EIA_API_KEY")
    if not key:
        raise SystemExit("EIA_API_KEY not set in .env  (free key: https://www.eia.gov/opendata/)")
    params = [
        ("api_key", key),
        ("frequency", "daily"),
        ("data[0]", "value"),
        ("facets[series][]", "RBRTE"),
        ("facets[series][]", "RWTC"),
        ("sort[0][column]", "period"),
        ("sort[0][direction]", "desc"),
        ("length", "500"),
    ]
    r = requests.get(URL, params=params, timeout=30)
    r.raise_for_status()
    return r.json()["response"]["data"]


def main():
    rows = [
        (d["period"], SERIES.get(d["series"], d["series"]), d["value"], "EIA")
        for d in fetch() if d.get("value") is not None
    ]
    upsert("prices", ["day", "ticker", "usd", "source"], rows, conflict=["day", "ticker", "source"])
    print(f"EIA: loaded {len(rows)} price rows")
    return len(rows)


if __name__ == "__main__":
    main()
