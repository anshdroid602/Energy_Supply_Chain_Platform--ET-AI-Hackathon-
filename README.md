# PRAHARI — an energy supply-chain sentinel for India's oil

**Team f20230436 · PS 2: AI-Driven Energy Supply Chain Resilience for Import-Dependent Economies · ET AI Hackathon**

PRAHARI watches the world for trouble that could choke off India's oil supply. The moment something looks dangerous near a chokepoint like the Strait of Hormuz, it works out what the trouble costs India (in rupees, and in days of reserve left) and tells the people who buy crude what to buy instead and how to ship it. "Prahari" means watchman.

Our pitch in one line: **47 days versus 47 seconds.** McKinsey found an unprepared economy loses about 47 extra days recovering from an oil shock. India imports ~88% of its crude, ~40% of it through Hormuz, with only ~9.5 days of reserve cover. PRAHARI turns a detected signal into a costed, mapped recommendation in about 20 milliseconds.

New here? Read **[SUBMISSION.md](SUBMISSION.md)** for the story, **[TECHNICAL_OVERVIEW.md](TECHNICAL_OVERVIEW.md)** for how it's built, and **[DEMO_GUIDE.md](DEMO_GUIDE.md)** to run it.

## What it does, end to end

When a threat appears, one pass through the pipeline does four things:

1. **Reads the risk** — weighs recent news for a corridor by severity and recency into a single 0–1 score.
2. **Simulates the damage** — 10,000 Monte Carlo price paths, turned into the likely and worst-case price jump, how far the reserve falls, and the cost per day.
3. **Finds the way out** — a knowledge graph of India's real supply chain returns which suppliers can still deliver while avoiding the dangerous chokepoints, ranked by speed and safety.
4. **Writes the answer** — one plain line a decision-maker reads in five seconds, and a reroute drawn on the map.

The guiding rule: **every number is computed and can be checked; a language model is only used to read news text, never to invent a figure.**

## Architecture

```
  six public feeds        loaders            shared Postgres        read API          dashboard
  EIA  yfinance  OFAC  ─►  one script  ─►     (Neon, single    ─►   FastAPI     ─►    React +
  AIS  PPAC  GDELT         per source         source of truth)      api/main.py       Leaflet
                              ▲                     │
                    controller.py                   ├─ scenario model   (scenario/engine.py, numpy Monte Carlo)
              (cadence loop / GitHub Actions)       ├─ knowledge graph  (api/graph.py, live risk overlay)
                                                    └─ agent pipeline   (agents/graph.py, LangGraph)
```

Nothing talks to the outside sources except the loaders. The map, the model, and the agents all read the same database, so no two parts of the system can disagree about the data.

## Quick start

```bash
git clone https://github.com/anshdroid602/Energy_Supply_Chain_Platform--ET-AI-Hackathon-
cd Energy_Supply_Chain_Platform--ET-AI-Hackathon-
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # paste the team DATABASE_URL + free API keys

# backend + frontend together
./run_dev.sh
```

Then open http://localhost:5173 and click **Inject signal**. That button runs the whole pipeline on a cached real event with no database and no internet, so it works even if the network drops. To load fresh data first: `python3 -m datapipeline.controller --force`. Backend docs live at http://localhost:8000/docs.

## The pieces

- **Data layer** (`datapipeline/`) — six feeds, one small loader each, upserting into one Postgres. A controller reruns each on its natural cadence.
- **Read API** (`api/main.py`) — one FastAPI layer over every table, plus the scenario and pipeline endpoints.
- **Knowledge graph** (`api/graph.py`) — India's real crude supply chain with live chokepoint risk; answers "who can still reach this refinery, and how fast."
- **Scenario model** (`scenario/engine.py`) — a mean-reverting jump-diffusion, 10,000 vectorised numpy paths in a few milliseconds.
- **Agent pipeline** (`agents/graph.py`) — signal → scenario → procurement → summary, wired with LangGraph and timed per step.
- **Dashboard** (`frontend/`) — a one-screen React + Leaflet console: live map, risk dial, chokepoint watch, simulation chart, cost in rupees and days, ranked suppliers, and an assumptions panel you can change on the spot.

## The feeds

| Feed | Folder | Table | Key needed | Natural cadence |
|---|---|---|---|---|
| EIA daily Brent/WTI spot | `datapipeline/eia/` | `prices` | free EIA key | daily |
| yfinance intraday ticks | `datapipeline/market_prices/` | `price_ticks` | none | ~10 min |
| OFAC SDN sanctions | `datapipeline/ofac/` | `sanctions` | none | daily |
| AISStream live ships | `datapipeline/ais/` | `vessels` | free AISStream key | ~10 min snapshots |
| PPAC India imports | `datapipeline/ppac/` | `imports_india` | none (CSV committed) | monthly |
| GDELT news → risk signals | `datapipeline/gdelt_and_gkg/` | `structured_events` | none (public mode) | ~4 h |

Every loader is idempotent (upserts), so rerunning anything is always safe.

## The API

| Endpoint | What |
|---|---|
| `GET /events`, `/events/{id}`, `/meta` | filtered GDELT risk events, each with lat/lon for the map |
| `GET /corridors`, `/corridors/{c}/risk-score` | per-corridor stats + a 0–1 recency/confidence-weighted risk score |
| `GET /prices/daily`, `/prices/ticks`, `/prices/latest` | EIA daily + yfinance intraday |
| `GET /vessels/latest`, `/vessels/sanctioned` | latest AIS position per ship, flagged against OFAC vessels |
| `GET /imports/india` | PPAC monthly quantity/value series |
| `GET /graph`, `/graph/routes`, `/graph/alternatives` | the supply-chain graph with live risk; ranked supplier options |
| `POST /scenario/run` | the Monte Carlo scenario for a given risk score |
| `POST /pipeline/run` | the full signal → scenario → procurement → summary pipeline in one call |
| `GET /freshness`, `/health` | per-feed staleness and liveness |

## Tests and CI

```bash
pytest tests/ -q
```

36 tests pass plus a gated DB-integration suite, run on every push through GitHub Actions. Loaders also validate at runtime: crude prices outside $1–500/bbl are rejected, and a truncated OFAC download fails loudly instead of loading a partial list.

## Honest data caveats (read before demoing)

- **The data is real but not a live stream.** Each feed refreshes on its own schedule; for a demo, run the controller first so the numbers are current.
- **AISStream free tier barely covers the Persian Gulf.** The live ship dots sit on well-covered lanes to prove the pipeline is real; the Hormuz story is told with geography, sanctioned tankers, and the news signal, which are all real data we do have.
- **Rule of the project: real-but-cached beats fabricated. We never invent a number.**

## Tech stack

Python + FastAPI, Postgres on Neon, numpy (Monte Carlo), networkx (knowledge graph), LangGraph (agent chain), React + Vite + Leaflet (dashboard), GitHub Actions (CI + scheduled refresh). A language model reads the news; nothing else depends on it. Everything runs on free tiers.

## Team

Team **f20230436** — Ansh Sharma (lead), Harsh Vardhan, Aditya Nitin Jagtap, Abhijay Pansari.
