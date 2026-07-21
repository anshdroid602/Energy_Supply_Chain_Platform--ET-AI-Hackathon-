# Agent orchestration layer

The intelligence layer on top of the data platform: five agents wired into one
LangGraph chain that fires from a detected signal to a **costed, mapped
procurement recommendation** — signal → recommendation in seconds.

```
 Risk Intelligence ──(disruption ≥ threshold?)──► Scenario Modeller ──► Procurement
        │                                                                     │
        └──(below threshold: stop, monitor)──► END        Strategic Reserve ◄─┘
                                                                   │
                                                          Supply-Chain Digital Twin ──► END
```

Everything reads the shared Postgres **in-process** (no HTTP hop) via
`datasource.py`, which reuses `api/graph.py`. It does **not** need the FastAPI
server running.

## The one rule: numbers are code, prose is the LLM

Every quantitative field is computed deterministically (SQL + numpy + the
knowledge graph). The LLM (**Cerebras `gpt-oss-120b`** by default) only writes
the `*reasoning` / `headline` narrative. Consequences:

- **Auditable** — the disruption probability, the VaR, the ETA, the cost are
  all reproducible and testable (the brief's "explicit and testable").
- **Resilient** — with no LLM key, or Cerebras throttled/down, each narration
  falls back to a templated sentence and the pipeline still completes. Calls
  are bounded (timeout + no retry) so a rate-limited free tier can't blow the
  47-second clock. Measured ~6–7s end-to-end.

## Run it

From the repo root (`platform/`), same root uvicorn/pytest use:

```bash
pip install -r requirements.txt
python3 -m agents.run                              # Hormuz → Jamnagar, human summary
python3 -m agents.run --corridor "Red Sea"
python3 -m agents.run --json                       # full PipelineResult JSON (the frontend contract)
python3 -m agents.run --stream                     # print each agent as it finishes
```

Over HTTP (endpoints are mounted on the main API):

```bash
python3 -m uvicorn api.main:app --port 8000
curl "http://127.0.0.1:8000/pipeline/run?corridor=Strait%20of%20Hormuz"
curl -N "http://127.0.0.1:8000/pipeline/stream?corridor=Strait%20of%20Hormuz"   # SSE, one event per agent
```

## The five agents

| # | Agent | File | What it produces | LLM? |
|---|-------|------|------------------|------|
| 1 | Risk Intelligence | `nodes/risk_intelligence.py` | live disruption probability (= corridor risk score) + evidence lines (news/Brent/sanctions) + trigger | narrate |
| 2 | Scenario Modeller | `nodes/scenario_modeller.py` + `montecarlo.py` | mean-reverting jump-diffusion, 10k MC → Brent median/VaR, reserve cover, P(cover<7d), ₹cr/day | narrate |
| 3 | Procurement | `nodes/procurement.py` | ranked alternative suppliers/routes (viable safe route, grade fit, ETA, cost delta); concrete "buy X via Y" | narrate |
| 4 | Strategic Reserve | `nodes/strategic_reserve.py` | drawdown vs the daily gap, buffer days vs reroute ETA | narrate |
| 5 | Digital Twin | `nodes/digital_twin.py` | reroute geometry (real node coords + sea-lane waypoints), blocked chokepoints | none (geometry) |

The scenario detector picks the jump archetype by severity: a **Critical**
corridor (≥0.8) gets the *persistent* regime-shift jump (cf. 1990 Gulf War /
2022 Ukraine); otherwise the *mean-reverting* partial jump (cf. 2019 Abqaiq).

## The contract

`schemas.py` defines `PipelineResult` — the single JSON shape the React +
Leaflet dashboard renders and `/pipeline/*` returns. Sub-objects per agent:
`RiskAssessment`, `ScenarioResult`, `ProcurementRecommendation`, `ReservePlan`,
`RerouteMap`, plus a top-level `headline` and `latency_seconds`.

## The assumption panel

Every knob a judge might turn lives in `config.py` (`ASSUMPTIONS`,
`JUMP_ARCHETYPES`, `DISRUPTION_THRESHOLD`) and is echoed back in
`ScenarioResult.assumptions`, so the frontend can expose them as live editable
inputs. All env-overridable. The economic cascade (price → supply → reserve →
cost) is a **simplified elasticity and says so** in `ScenarioResult.caveat` —
we report intervals, not false precision.

## LLM provider

Provider-agnostic through the OpenAI-compatible SDK (`llm.py`). Default
Cerebras; switch with `LLM_PROVIDER` (cerebras | openrouter | groq | openai)
and `LLM_MODEL`. See `config.PROVIDERS`.

## Config knobs (env)

| Var | Default | Meaning |
|---|---|---|
| `LLM_PROVIDER` / `LLM_MODEL` | cerebras / gpt-oss-120b | narration model |
| `CEREBRAS_API_KEY` | — | free key from cerebras.ai |
| `DISRUPTION_THRESHOLD` | 0.5 | fire the chain at/above this |
| `LLM_TIMEOUT_S` | 10 | per-call ceiling before template fallback |
| `MC_PATHS` / `MC_HORIZON_DAYS` | 10000 / 30 | Monte Carlo size/horizon |
| `USD_INR`, `RESERVE_COVER_DAYS`, `SUPPLY_PRICE_COUPLING`, … | see `config.ASSUMPTIONS` | cascade assumptions |

## Notes / caveats

- Disruption probability **is** the corridor risk score (recency/confidence-
  weighted severity from `structured_events`) — kept identical to
  `/corridors/{c}/risk-score` so the number is one source of truth.
- Cost delta is a transparent **freight + grade proxy**, not a traded
  differential — labeled as such.
- `datasource.py` degrades gracefully if the live DB predates the
  `structured_events.lat/lon` columns (evidence dots just lack coordinates);
  run `python3 -m datapipeline.init_db` to apply that additive migration.
