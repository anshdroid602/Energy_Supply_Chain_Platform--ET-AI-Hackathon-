"""GDELT GKG via BigQuery -> gdelt_gkg_events.csv.

Requires Google Cloud credentials. Optional stage: merge.py works without
this file (events get empty context and extract.py falls back to CAMEO-code
categorisation), so the public/no-key pipeline simply skips it.

Uses the DATE-PARTITIONED gkg_partitioned table — the raw gdeltv2.gkg table
is NOT partitioned and a single themes query against it can scan terabytes,
blowing the BigQuery free tier in one run.

Env knobs (all optional):
  GCP_PROJECT          BigQuery billing project, default the team project
  GDELT_WINDOW_DAYS    rolling window size, default 30
"""
import os
from datetime import date, timedelta

from google.cloud import bigquery

PROJECT = os.environ.get("GCP_PROJECT", "project-21508f3b-5710-4110-999")
WINDOW_DAYS = int(os.environ.get("GDELT_WINDOW_DAYS", "30"))

client = bigquery.Client(project=PROJECT)

end = date.today()
start = end - timedelta(days=WINDOW_DAYS)
start_gkgdate = int(start.strftime("%Y%m%d") + "000000")
end_gkgdate = int(end.strftime("%Y%m%d") + "235959")

GKG_QUERY = f"""
SELECT
  DATE,
  SourceCommonName,
  DocumentIdentifier,
  V2Themes AS Themes,
  V2Locations AS Locations,
  V2Persons AS Persons,
  V2Organizations AS Organizations,
  V2Tone AS Tone
FROM `gdelt-bq.gdeltv2.gkg_partitioned`
WHERE
  _PARTITIONTIME >= TIMESTAMP('{start.isoformat()}')
  AND (V2Themes LIKE '%ENV_OIL%'
   OR V2Themes LIKE '%ECON_OILPRICE%'
   OR V2Themes LIKE '%SANCTION%'
   OR V2Themes LIKE '%STRAIT_HORMUZ%'
   OR V2Themes LIKE '%MARITIME%'
   OR V2Themes LIKE '%MILITARY%'
   OR V2Themes LIKE '%ENERGY_SECURITY%')
  AND DATE >= {start_gkgdate}
  AND DATE <= {end_gkgdate}
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY CAST(DATE AS STRING)
  ORDER BY FARM_FINGERPRINT(DocumentIdentifier)
) <= 25
"""

gkg_df = client.query(GKG_QUERY).to_dataframe()

print(f"Window: {start} .. {end}")
print(gkg_df.head(10))
print(f"Rows returned: {len(gkg_df)}")
print(f"Unique days covered: {gkg_df['DATE'].astype(str).str[:8].nunique()}")

all_themes = gkg_df['Themes'].dropna().str.split(';').explode().str.split(',').str[0]
print("\nTop 30 themes:")
print(all_themes.value_counts().head(30))

gkg_df.to_csv("gdelt_gkg_events.csv", index=False)
print("\nSaved to gdelt_gkg_events.csv")
