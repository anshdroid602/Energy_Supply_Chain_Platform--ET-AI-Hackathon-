"""GDELT events via BigQuery -> gdelt_events_with_mentions.csv.

Requires Google Cloud credentials (gcloud auth / service account) — if you
don't have them, use fetch_public.py instead (same output, no key).

Uses the DATE-PARTITIONED mirror tables (events_partitioned / eventmentions_partitioned)
with a _PARTITIONTIME filter: the raw gdeltv2.events / gkg tables are NOT
partitioned, so querying them scans the full multi-hundred-GB column history
on every run and burns the 1TB/month BigQuery free tier in a handful of runs.

Env knobs (all optional):
  GCP_PROJECT           BigQuery billing project, default the team project
  GDELT_WINDOW_DAYS     rolling window size, default 30
  GDELT_ACTORS          comma-separated CAMEO codes, default IRN,SAU,ARE,YEM,USA,RUS
  GDELT_MAX_GOLDSTEIN   keep events with GoldsteinScale <= this, default -5
"""
import os
from datetime import date, timedelta

from google.cloud import bigquery

PROJECT = os.environ.get("GCP_PROJECT", "project-21508f3b-5710-4110-999")
WINDOW_DAYS = int(os.environ.get("GDELT_WINDOW_DAYS", "30"))
ACTORS = sorted(set((os.environ.get("GDELT_ACTORS") or "IRN,SAU,ARE,YEM,USA,RUS").split(",")))
MAX_GOLDSTEIN = float(os.environ.get("GDELT_MAX_GOLDSTEIN", "-5"))

client = bigquery.Client(project=PROJECT)

end = date.today()
start = end - timedelta(days=WINDOW_DAYS)
start_sqldate = int(start.strftime("%Y%m%d"))
end_sqldate = int(end.strftime("%Y%m%d"))
actor_list = ",".join(f"'{a}'" for a in ACTORS)

QUERY = f"""
WITH filtered_events AS (
  SELECT
    GlobalEventID,
    EventCode,
    Actor1CountryCode,
    Actor2CountryCode,
    GoldsteinScale,
    NumMentions,
    AvgTone,
    ActionGeo_CountryCode,
    ActionGeo_Lat,
    ActionGeo_Long,
    SQLDATE
  FROM `gdelt-bq.gdeltv2.events_partitioned`
  WHERE
    _PARTITIONTIME >= TIMESTAMP('{start.isoformat()}')
    AND (Actor1CountryCode IN ({actor_list})
     OR Actor2CountryCode IN ({actor_list}))
    AND SQLDATE >= {start_sqldate}
    AND SQLDATE <= {end_sqldate}
    AND GoldsteinScale <= {MAX_GOLDSTEIN}
),

mention_agg AS (
  SELECT
    GLOBALEVENTID AS GlobalEventID,
    AVG(MentionDocTone) AS avg_mention_tone,
    COUNT(*) AS mention_count,
    MAX(Confidence) AS max_confidence
  FROM `gdelt-bq.gdeltv2.eventmentions_partitioned`
  WHERE _PARTITIONTIME >= TIMESTAMP('{start.isoformat()}')
    AND Confidence > 50
  GROUP BY GLOBALEVENTID
)

SELECT
  e.*,
  m.avg_mention_tone,
  m.mention_count,
  m.max_confidence
FROM filtered_events e
LEFT JOIN mention_agg m
  ON e.GlobalEventID = m.GlobalEventID
ORDER BY e.GoldsteinScale ASC
LIMIT 500
"""

events_df = client.query(QUERY).to_dataframe()

print(f"Window: {start} .. {end}")
print(events_df.head(10))
print(f"Rows returned: {len(events_df)}")
print(f"Rows with mention data: {events_df['mention_count'].notna().sum()}")

events_df.to_csv("gdelt_events_with_mentions.csv", index=False)
print("Saved to gdelt_events_with_mentions.csv")
