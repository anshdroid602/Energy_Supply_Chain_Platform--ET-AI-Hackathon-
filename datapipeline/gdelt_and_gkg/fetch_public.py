"""GDELT public daily dumps -> gdelt_events_with_mentions.csv. NO key, NO GCP.

Alternative to gdelt.py (BigQuery) that anyone can run: downloads GDELT 1.0
daily event files (http://data.gdeltproject.org/events/YYYYMMDD.export.CSV.zip),
applies the same filters as gdelt.py's BigQuery query (actor countries,
Goldstein <= threshold, rolling date window), and writes a CSV with the exact
columns merge.py expects.

Differences vs the BigQuery path (documented, not hidden):
  - no eventmentions join -> mention_count / avg_mention_tone / max_confidence
    are empty (merge.py and extract.py already handle nulls there)
  - no GKG context either -> run with merge.py's missing-GKG fallback, where
    extract.py falls back to CAMEO-code categorisation instead of themes

Env knobs (all optional):
  GDELT_WINDOW_DAYS     rolling window size, default 30
  GDELT_ACTORS          comma-separated CAMEO codes, default IRN,SAU,ARE,YEM,USA,RUS
  GDELT_MAX_GOLDSTEIN   keep events with GoldsteinScale <= this, default -5
  GDELT_MAX_EVENTS      keep the N most severe events overall, default 500
                        (matches the BigQuery query's LIMIT; the daily dumps
                        match ~7k events/day, far too many to LLM-review)
"""
import io
import os
import zipfile
from datetime import date, timedelta

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Retry transient failures — this runs unattended in CI, where one network
# blip would otherwise silently drop a whole day of events.
SESSION = requests.Session()
SESSION.mount("http://", HTTPAdapter(max_retries=Retry(
    total=3, backoff_factor=2.0, status_forcelist=(429, 500, 502, 503, 504))))

BASE_URL = "http://data.gdeltproject.org/events/{d}.export.CSV.zip"
OUTPUT = "gdelt_events_with_mentions.csv"

WINDOW_DAYS = int(os.environ.get("GDELT_WINDOW_DAYS", "30"))
ACTORS = set((os.environ.get("GDELT_ACTORS") or "IRN,SAU,ARE,YEM,USA,RUS").split(","))
MAX_GOLDSTEIN = float(os.environ.get("GDELT_MAX_GOLDSTEIN", "-5"))
MAX_EVENTS = int(os.environ.get("GDELT_MAX_EVENTS", "500"))

# GDELT 1.0 daily export column positions (58 tab-separated fields, no header).
COL = {
    "GlobalEventID": 0,
    "SQLDATE": 1,
    "Actor1CountryCode": 7,
    "Actor2CountryCode": 17,
    "EventCode": 26,
    "GoldsteinScale": 30,
    "NumMentions": 31,
    "AvgTone": 34,
    "ActionGeo_CountryCode": 51,
    "ActionGeo_Lat": 53,
    "ActionGeo_Long": 54,
}


def parse_day_csv(f):
    """Parse one daily export file-object into a filtered DataFrame.
    Split out from fetch_day so tests can feed it synthetic data."""
    df = pd.read_csv(
        f, sep="\t", header=None, dtype=str,
        usecols=list(COL.values()), na_filter=False,
        quoting=3,  # csv.QUOTE_NONE — raw GDELT text contains stray quotes
    )
    df.columns = [name for name, _ in sorted(COL.items(), key=lambda kv: kv[1])]

    for col in ("GoldsteinScale", "NumMentions", "AvgTone", "SQLDATE",
                "ActionGeo_Lat", "ActionGeo_Long"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Daily files are keyed by report date and can re-report much older
    # events; keep SQLDATE inside the window like the BigQuery query does.
    start_sqldate = int((date.today() - timedelta(days=WINDOW_DAYS)).strftime("%Y%m%d"))
    keep = (
        (df["Actor1CountryCode"].isin(ACTORS) | df["Actor2CountryCode"].isin(ACTORS))
        & (df["GoldsteinScale"] <= MAX_GOLDSTEIN)
        & (df["SQLDATE"] >= start_sqldate)
    )
    return df[keep].copy()


def fetch_day(d):
    """Download one daily file; returns a filtered DataFrame or None on 404."""
    url = BASE_URL.format(d=d.strftime("%Y%m%d"))
    r = SESSION.get(url, timeout=120)
    if r.status_code == 404:
        return None  # file not published yet (today/very recent) — fine
    r.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        with z.open(z.namelist()[0]) as f:
            return parse_day_csv(f)


def main():
    end = date.today()
    start = end - timedelta(days=WINDOW_DAYS)
    print(f"GDELT public dumps: {start} .. {end}  "
          f"(actors={sorted(ACTORS)}, goldstein<={MAX_GOLDSTEIN})")

    frames = []
    d = start
    while d <= end:
        try:
            day_df = fetch_day(d)
        except Exception as e:
            print(f"  {d}: FAILED ({e}) — skipping day")
            day_df = None
        if day_df is not None:
            print(f"  {d}: {len(day_df)} matching events")
            frames.append(day_df)
        d += timedelta(days=1)

    if not frames:
        raise SystemExit("No GDELT daily files could be fetched — check connectivity.")

    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates(subset="GlobalEventID", keep="last")

    # Cap volume like the BigQuery LIMIT — the dumps match thousands of
    # events per day, which would swamp merge/extract and make LLM review
    # impossible on free tiers. Capped PER DAY (most severe first) rather
    # than overall: Goldstein scores tie at -10 constantly, so a global
    # top-N collapses onto a single day and the recency-decayed risk score
    # loses its timeline.
    per_day = max(1, MAX_EVENTS // max(1, df["SQLDATE"].nunique()))
    df = (df.sort_values(["GoldsteinScale", "NumMentions"], ascending=[True, False])
            .groupby("SQLDATE", group_keys=False)
            .head(per_day))

    # Columns merge.py expects; the mentions-join columns stay empty here.
    df["avg_mention_tone"] = None
    df["mention_count"] = None
    df["max_confidence"] = None
    out_cols = ["GlobalEventID", "EventCode", "Actor1CountryCode", "Actor2CountryCode",
                "GoldsteinScale", "NumMentions", "AvgTone", "ActionGeo_CountryCode",
                "ActionGeo_Lat", "ActionGeo_Long",
                "SQLDATE", "avg_mention_tone", "mention_count", "max_confidence"]
    df = df.sort_values("GoldsteinScale")[out_cols]

    df.to_csv(OUTPUT, index=False)
    print(f"Saved {len(df)} events to {OUTPUT}")


if __name__ == "__main__":
    main()
