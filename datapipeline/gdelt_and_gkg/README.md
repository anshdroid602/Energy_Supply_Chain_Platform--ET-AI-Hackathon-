# GDELT + GKG pipeline

GDELT events → structured risk signals → the `structured_events` table.
(The read API moved to the repo root: `api/main.py` — one FastAPI over ALL
tables, run with `uvicorn api.main:app` from the repo root.)

## Quick start

```bash
python3 run_pipeline.py                    # public GDELT dumps, no keys needed
python3 run_pipeline.py --source bigquery  # richer data, needs GCP credentials
```

## Architecture

```
fetch_public.py  (or gdelt.py + gkg.py)  →  merge.py  →  extract.py  →  load_to_postgres.py
(raw events [+ GKG])           (event_bundles.json)  (structured_events.json)   (Postgres)
```

Each stage is a standalone script, independently runnable for debugging.
`run_pipeline.py` chains them together; it does not replace them.

| Stage | Script | Reads | Writes |
|---|---|---|---|
| 1 | `fetch_public.py` (default, no key)<br>OR `gdelt.py` + `gkg.py` (BigQuery, GCP creds) | GDELT public daily dumps / BigQuery partitioned tables | `gdelt_events_with_mentions.csv` (+ `gdelt_gkg_events.csv` on the BigQuery path) |
| 2 | `merge.py` | the CSV(s) above — GKG file optional | `event_bundles.json` |
| 3 | `extract.py` (deterministic)<br>`extract_events.py` (LLM)<br>`hybrid_extract.py` (both) | `event_bundles.json` | `structured_events.json` |
| 4 | `load_to_postgres.py` | `structured_events.json` | `structured_events` table |

All fetch windows are **rolling** (today back `GDELT_WINDOW_DAYS` days,
default 30) — no more hardcoded dates. Filters are env-tunable:
`GDELT_ACTORS`, `GDELT_MAX_GOLDSTEIN`, `GCP_PROJECT`.

The BigQuery scripts now query the **partitioned** mirror tables
(`events_partitioned` / `eventmentions_partitioned` / `gkg_partitioned`)
with a `_PARTITIONTIME` filter — the raw tables are unpartitioned, so the old
queries scanned the full multi-hundred-GB history every run and would have
burned the 1TB/month free tier in a handful of runs.

On the public path there is no GKG context, so `extract.py` falls back to
CAMEO event codes for categorisation (18/19/20 → military_strike,
163x/172x → sanction) and confidence scores run lower. That's expected.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pandas openai requests python-dotenv psycopg2-binary fastapi "uvicorn[standard]"
```

`.env`:
```
OPENROUTER_API_KEY=...      # only needed for extract_events.py / hybrid_extract.py
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres
```

Local Postgres via Docker:
```bash
docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:16
```

## Running the pipeline

One command, full run:
```bash
python3 run_pipeline.py
```

Common variations:
```bash
python3 run_pipeline.py --source bigquery          # GCP-credentialed fetch (mentions + GKG)
python3 run_pipeline.py --extractor hybrid        # hybrid_extract.py instead of extract.py
python3 run_pipeline.py --extractor llm           # extract_events.py instead
python3 run_pipeline.py --from merge               # CSVs already fetched, skip to merge.py
python3 run_pipeline.py --only extract             # rerun just the extraction stage
python3 run_pipeline.py --skip fetch               # skip any combination
```

If a stage fails, `run_pipeline.py` stops immediately and prints which
`--from <stage>` command resumes from there. Note it does not know about a
stage's own internal checkpointing (e.g. `extract_events.py` resumes its own
batches via `checkpoint.json` regardless of the orchestrator) — that logic
lives inside the stage and still works, the orchestrator's resume message is
just a coarser, stage-level one.

Or run any stage standalone for debugging:
```bash
python3 gdelt.py
python3 gkg.py
python3 merge.py
python3 extract.py            # or hybrid_extract.py / extract_events.py
python3 load_to_postgres.py
```

## Extraction stage: three options

| Script | Speed | Cost | Use when |
|---|---|---|---|
| `extract.py` | instant | free | rules alone can classify most events — the default |
| `extract_events.py` | slow (free-tier rate limits) | free (OpenRouter free models) | you want every event LLM-reviewed |
| `hybrid_extract.py` | fast | free | deterministic pass first; only low-confidence/`other` events go to the LLM |

`hybrid_extract.py` is the recommended default once your event volume grows —
it prints a split (e.g. `deterministic: 460, LLM-reviewed: 40`) so you can see
how much of the dataset the rules alone are handling. If nearly everything
gets flagged, that's a signal to tighten `extract.py`'s rules rather than lean
harder on the LLM.

`extract_events.py` and `hybrid_extract.py` auto-discover which OpenRouter
models are currently free (rather than hardcoding model names that rotate),
retry on 429/502/503, and checkpoint after every batch — safe to Ctrl+C and
resume later.

## API

Moved to the repo root as `api/main.py` — one FastAPI in front of Postgres
covering ALL tables (events + risk scores + prices + vessels + imports +
sanctions + freshness). Run from the repo root:

```bash
uvicorn api.main:app --reload --port 8000
```

Endpoint list and details: root `README.md`. The risk-score formula is
unchanged — confidence- and recency-weighted mean severity, tunable via
`window_days` and `half_life_days` query params:
```
risk_score = Σ(severity_i/10 × confidence_i × decay_i) / Σ(confidence_i × decay_i)
decay_i = 0.5 ^ (days_ago_i / half_life_days)
```

## Important gotcha: FIPS vs ISO2 country codes

GDELT's `location_country` / `ActionGeo_CountryCode` field uses **FIPS 10-4**
country codes, not ISO 3166-1 alpha-2. They agree for some countries but
diverge for several relevant to this project:

| Country | ISO2 | FIPS (what GDELT actually sends) |
|---|---|---|
| Oman | OM | MU |
| UAE | AE | TC |
| Kuwait | KW | KU |
| Bahrain | BH | BA |
| Yemen | YE | YM |
| Sudan | SD | SU |

`extract.py`'s `CORRIDOR_MAP` is keyed on FIPS codes — if you add corridor
countries, look up the FIPS code, not ISO2.

Actor fields (`Actor1CountryCode`/`Actor2CountryCode`) use CAMEO 3-letter
codes instead (e.g. `IRN`, `USA`) — a third, separate scheme from both ISO2
and FIPS. Don't cross-reference actor codes against `CORRIDOR_MAP`.

## Files not committed

`event_bundles.json`, `structured_events*.json`, `failed_bundles*.json`,
`checkpoint.json`, `free_models_cache.json`, `*.csv`, `.env`, and
`__pycache__/` are gitignored — they're either regenerable pipeline output or
machine-specific state. Regenerate with `python3 run_pipeline.py` after
pulling.

## Utilities

`tokenlimit.py` — token-length helper used when tuning `BATCH_SIZE` in
`extract_events.py`/`hybrid_extract.py` against OpenRouter's per-request
limits. *(Flag me if this description is off — I'm inferring from the name.)*