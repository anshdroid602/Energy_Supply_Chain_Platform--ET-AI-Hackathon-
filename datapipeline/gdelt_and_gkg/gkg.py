from google.cloud import bigquery
import pandas as pd

client = bigquery.Client(project="project-21508f3b-5710-4110-999")

GKG_QUERY = """
SELECT
  DATE,
  SourceCommonName,
  DocumentIdentifier,
  V2Themes AS Themes,
  V2Locations AS Locations,
  V2Persons AS Persons,
  V2Organizations AS Organizations,
  V2Tone AS Tone
FROM `gdelt-bq.gdeltv2.gkg`
WHERE
  (V2Themes LIKE '%ENV_OIL%'
   OR V2Themes LIKE '%ECON_OILPRICE%'
   OR V2Themes LIKE '%SANCTION%'
   OR V2Themes LIKE '%STRAIT_HORMUZ%'
   OR V2Themes LIKE '%MARITIME%'
   OR V2Themes LIKE '%MILITARY%'
   OR V2Themes LIKE '%ENERGY_SECURITY%')
  AND DATE >= 20260601000000
  AND DATE <= 20260710235959
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY CAST(DATE AS STRING) 
  ORDER BY FARM_FINGERPRINT(DocumentIdentifier)
) <= 25
"""

gkg_df = client.query(GKG_QUERY).to_dataframe()

print(gkg_df.head(10))
print(f"Rows returned: {len(gkg_df)}")
print(f"Unique days covered: {gkg_df['DATE'].astype(str).str[:8].nunique()}")

all_themes = gkg_df['Themes'].dropna().str.split(';').explode().str.split(',').str[0]
print("\nTop 30 themes:")
print(all_themes.value_counts().head(30))

gkg_df.to_csv("gdelt_gkg_events.csv", index=False)
print("\nSaved to gdelt_gkg_events.csv")