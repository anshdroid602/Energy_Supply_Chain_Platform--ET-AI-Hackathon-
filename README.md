# Energy Supply Chain Platform — Data Layer

Everything that gets real-world data into the shared Postgres (Neon) and back
out again: 6 feeds → loaders → one database → one read API. Agents, the
scenario model, and the frontend all build on top of this.

```
                 ┌──────────────────────── datapipeline/ ───────────────────────┐
 EIA API ────────► eia/loader.py ──────────► prices            ┐
 yfinance ───────► market_prices/loader.py ► price_ticks       │
 OFAC SDN csv ───► ofac/loader.py ─────────► sanctions         │   shared Neon
 AISStream ws ───► ais/loader.py ──────────► vessels           ├──  Postgres
 PPAC csv ───────► ppac/loader.py ─────────► imports_india     │  (DATABASE_URL)
 GDELT dumps/BQ ─► gdelt_and_gkg/ pipeline ► structured_events ┘
                 └──────────────▲───────────────────────────────────────────────┘
                                │ reruns on cadence, prunes stale AIS
                          datapipeline/controller.py       api/main.py (FastAPI)
                    (laptop loop or GitHub Actions)         ▲ frontend + agents
```

## Quick start (teammates)

```bash
git clone <this repo> && cd <repo>
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # paste the team DATABASE_URL + your free keys

python3 -m datapipeline.init_db   # create all tables (idempotent)
python3 -m datapipeline.controller --force     # load every feed right now
uvicorn api.main:app --reload --port 8000
open http://localhost:8000/docs
```

If you only consume data, you don't need any API keys — just `DATABASE_URL`
(query Postgres directly) or hit the API someone else is hosting.

## The feeds

| Feed | Folder | Table | Key needed | Natural cadence |
|---|---|---|---|---|
| EIA daily Brent/WTI spot | `datapipeline/eia/` | `prices` | free EIA key | daily |
| yfinance intraday ticks | `datapipeline/market_prices/` | `price_ticks` | none | ~10 min |
| OFAC SDN sanctions | `datapipeline/ofac/` | `sanctions` | none | daily |
| AISStream live ships | `datapipeline/ais/` | `vessels` | free AISStream key | ~10 min snapshots |
| PPAC India imports | `datapipeline/ppac/` | `imports_india` | none (CSV committed) | monthly |
| GDELT news → risk signals | `datapipeline/gdelt_and_gkg/` | `structured_events` | none (public mode) | ~4 h |

Every loader is idempotent (upserts) — rerunning anything is always safe.

## The controller (`datapipeline/controller.py`)

One entry point that runs whatever is due, based on per-feed cadences stored
in the `ingest_runs` table (so any machine — laptop, cron, GitHub Actions —
can pick up where the last run left off):

```bash
python3 -m datapipeline.controller                 # run whatever is due, exit
python3 -m datapipeline.controller --force         # ignore cadences, run everything
python3 -m datapipeline.controller --only ais      # just one feed (repeatable)
python3 -m datapipeline.controller --loop 300      # demo-laptop mode: rerun every 5 min
```

Sliding-window policy: GDELT always fetches a rolling `GDELT_WINDOW_DAYS`
(default 30) window ending today; AIS positions older than
`VESSEL_RETENTION_HOURS` (default 48) are deleted. **Nothing else is ever
deleted** — price/import/event history is what the scenario model calibrates
on, and the risk score already down-weights old events by recency.

## Auto-refresh in the cloud (GitHub Actions)

`.github/workflows/refresh.yml` runs the controller every 30 minutes so Neon
stays fresh with no laptop involved. To activate it, a repo admin adds three
Actions secrets — `DATABASE_URL`, `EIA_API_KEY`, `AISSTREAM_API_KEY` — under
*Settings → Secrets and variables → Actions*, and the workflow must be on the
default branch. Trigger it manually once from the Actions tab to verify.

GitHub cron is best-effort (minutes late sometimes) — good for freshness, but
the on-stage "live" element should be `datapipeline/controller.py --loop` on the demo
laptop.

## The API (`api/main.py`)

Single FastAPI read layer over all tables — interactive docs at `/docs`,
machine-readable schema for agents at `/openapi.json`.

| Endpoint | What |
|---|---|
| `GET /events`, `/events/{id}`, `/meta` | filtered GDELT risk events |
| `GET /corridors`, `/corridors/{c}/risk-score` | per-corridor stats + 0–1 recency/confidence-weighted risk score |
| `GET /prices/daily`, `/prices/ticks`, `/prices/latest` | EIA daily + yfinance intraday |
| `GET /vessels/latest`, `/vessels/sanctioned` | latest AIS position per ship, flagged against OFAC vessel names |
| `GET /imports/india` | PPAC monthly quantity/value series |
| `GET /sanctions/vessels` | the OFAC vessel registry |
| `GET /graph` | the full supply-chain knowledge graph (nodes carry lat/lon for the map) with live chokepoint risk |
| `GET /graph/routes?supplier=X&refinery=Y` | every route between a supplier and a refinery, with ETA + per-chokepoint risk |
| `GET /graph/alternatives?refinery=Y&max_risk=0.5` | ranked supplier options given today's risk — the Procurement agent's input |
| `GET /freshness` | last run per feed + row counts (the "data as of" panel) |
| `GET /health` | liveness |

## Knowledge graph (`api/graph.py` + `api/graph_seed.json`)

A small directed graph of India's real crude supply chain:
`supplier → export port → chokepoint(s) → Indian port → refinery`
(~32 nodes, ~48 edges — 7 suppliers, 5 chokepoints, 5 refineries, all real
infrastructure including the Hormuz bypasses: Saudi's East-West pipeline to
Yanbu, UAE's ADCOP pipeline to Fujairah, Russia's ESPO to Kozmino).

The skeleton is static (curated seed file, approximate voyage days and FY25
import shares). The **risk is live**: each chokepoint pulls the same
recency/confidence-weighted risk score as `/corridors/{c}/risk-score` from
`structured_events` at query time. So when GDELT news turns Hormuz critical,
`/graph/alternatives` automatically stops routing through it and returns the
ranked fallback suppliers with ETAs — which is exactly what the Procurement
agent recommends and what the reroute map draws. Read-only and derived;
never written to, never synced.

## GDELT pipeline specifics

See `datapipeline/gdelt_and_gkg/README.md`. Short version: the pipeline is
`fetch → merge → extract → load`, with two interchangeable fetch sources —
`--source public` (default; free GDELT daily dumps, no account, events only)
and `--source bigquery` (needs GCP credentials; adds the mentions join + GKG
theme context, now on partitioned tables with a rolling date window). The
extract stage is deterministic by default, with optional LLM review
(`--extractor hybrid`).

## Known data caveats (read before demoing)

- **AISStream free tier has ~zero coverage over the Persian Gulf / Indian
  Ocean.** The default box is the English Channel (dense coverage) to prove
  the pipeline is live with real ships. The Hormuz map layer is built from
  choke-point geography + OFAC vessels + GDELT signal — real data we do have.
- **GDELT public mode has no GKG themes**, so event categorisation falls back
  to CAMEO event codes and confidences run lower. BigQuery mode enriches it.
- **PPAC is a committed CSV** (data.gov.in blocks scraping); refresh it by
  downloading the new monthly sheet to `datapipeline/ppac/data/ppac.csv`.
- Rule from the plan: real-but-cached beats fabricated. Never invent numbers.
