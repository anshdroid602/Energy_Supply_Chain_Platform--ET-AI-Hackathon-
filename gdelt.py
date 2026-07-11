from google.cloud import bigquery
import pandas as pd

client = bigquery.Client(project="project-21508f3b-5710-4110-999")

QUERY = """
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
    SQLDATE
  FROM `gdelt-bq.gdeltv2.events`
  WHERE
    (Actor1CountryCode IN ('IRN','SAU','ARE','YEM','USA','RUS')
     OR Actor2CountryCode IN ('IRN','SAU','ARE','YEM','USA','RUS'))
    AND SQLDATE >= 20260601
    AND SQLDATE <= 20260710
    AND GoldsteinScale <= -5
),

mention_agg AS (
  SELECT
    GLOBALEVENTID AS GlobalEventID,
    AVG(MentionDocTone) AS avg_mention_tone,
    COUNT(*) AS mention_count,
    MAX(Confidence) AS max_confidence
  FROM `gdelt-bq.gdeltv2.eventmentions`
  WHERE Confidence > 50
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

print(events_df.head(10))
print(f"Rows returned: {len(events_df)}")
print(f"Rows with mention data: {events_df['mention_count'].notna().sum()}")

events_df.to_csv("gdelt_events_with_mentions.csv", index=False)
print("Saved to gdelt_events_with_mentions.csv")