from google.cloud import bigquery
import google.auth

PROJECT_ID = "project-21508f3b-5710-4110-999"

credentials, _ = google.auth.default()

print("=" * 50)
print("Authentication")
print("=" * 50)
print(f"Project: {PROJECT_ID}")
print(f"Credentials Type: {type(credentials).__name__}")

client = bigquery.Client(
    project=PROJECT_ID,
    credentials=credentials
)

QUERY = """
SELECT
  GlobalEventID,
  EventCode
FROM `gdelt-bq.gdeltv2.events`
LIMIT 500
"""

job_config = bigquery.QueryJobConfig(
    dry_run=True,
    use_query_cache=False
)

job = client.query(QUERY, job_config=job_config)

bytes_processed = job.total_bytes_processed

print("\nBytes processed:", f"{bytes_processed:,}")
print("GB:", bytes_processed / (1024**3))
print("Estimated Cost ($6.25/TB): $", bytes_processed / (1024**4) * 6.25)