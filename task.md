# PRAHARI — MVP Build Plan (trimmed for time)

Revised for a tight schedule: every item below either directly hits a judged
criterion or reduces demo-day failure risk. Anything that was neither got cut.
See §3 for exactly what was removed and why, so the reasoning isn't lost if
a judge asks "what did you leave out."

## 1. Locked tech stack (updated)

| Layer | Choice | Why |
|---|---|---|
| Language | Python (single service) | Unchanged — data layer, API, graph are already Python/FastAPI. |
| API | FastAPI, extend `api/main.py` | Unchanged. |
| Database | Postgres on Neon | Unchanged, already live. |
| Event extraction (LLM) | As already coded — `hybrid_extract.py` (deterministic-first, OpenRouter free-tier for low-confidence events) | Unchanged. Not touching something that already works. |
| Agent orchestration | **LangGraph** | Kept deliberately as a skill investment even though the chain is linear — it's the one component in this project that reads as "agentic AI" on a resume/in an interview, and a 4-node linear `StateGraph` (score → scenario → procurement → summary) is not a large lift on top of endpoints that already exist. Scope discipline still applies: no conditional edges, no cycles, no multi-agent handoff — just four nodes passing a shared state dict, invoked synchronously (`graph.invoke()`), not streamed. |
| Quant engine | numpy/scipy, single-archetype jump-diffusion | Simplified from two regime-detected archetypes (persistent vs. mean-reverting) to one severity-scaled jump size. Still real, still calibrated, half the code and half the "why did you pick this branch" surface to defend live. |
| Narration | **String template, not an LLM call** | Cut the LLM-generated summary from the critical path. A judge cannot tell "Hormuz risk Critical — Rs.X crore/day, reserve cover 9.5→6.2 days, recommended: reroute via UAE/Fujairah, ETA 3 days" was templated vs. generated, but a template has zero latency variance and zero external-API failure risk sitting right before your mic-drop line. |
| Knowledge graph | networkx (already built) | Unchanged. No Neo4j. |
| Frontend | React + Vite + Leaflet | Unchanged. |
| Live-update effect | **Synchronous endpoint + scripted client-side reveal**, not real SSE | `POST /pipeline/run` runs all four steps, records each step's real duration server-side, returns one JSON payload. Frontend reveals each step timed to its real recorded duration (or a fixed cadence). Same visual effect as streaming, none of the SSE/EventSource/CORS debugging risk. |
| Deployment | Run FastAPI locally (uvicorn) on the demo laptop; frontend on Vercel | Cut Docker + NGINX entirely. You're presenting live from a laptop — containerizing for a single demo run buys nothing. If a public URL is needed for judges to poke at afterward, deploy the FastAPI app to Render/Fly's free tier as-is (no container needed for either). |
| Concurrency | `asyncio.gather` for the risk-intelligence sub-fetches only, if it's already trivial | Keep only if it falls out naturally; not worth dedicated build time now. |

## 2. What's already built (unchanged from repo audit)

- 6 data feeds live, shared Postgres, idempotent upserts, cadence-aware controller.
- GDELT hybrid extraction pipeline (deterministic + OpenRouter fallback), checkpointed.
- FastAPI read layer: events, corridor risk score (recency+confidence weighted), prices, vessels (sanction-matched), imports, sanctions, freshness.
- Knowledge graph with live risk overlay: `/graph`, `/graph/routes`, `/graph/alternatives` — this last one already *is* the ranked procurement logic.
- Tests + CI.

Nothing here changes. This plan only touches what's still unbuilt.

## 3. Cut for time (and why)

| Cut | Reason |
|---|---|
| Dual jump-diffusion archetypes (regime detector) | One calibrated, severity-scaled jump does the same demo job with half the code and half the defense surface. |
| LLM-generated narration on the critical path | Replaced with a template. Removes an external API call (latency + failure risk) from the exact moment the demo needs to land. |
| Real SSE streaming | Replaced with one synchronous call + client-side scripted reveal using real recorded step durations. Same visual effect, none of the streaming infra risk. |
| Docker + NGINX | Presenting live from a laptop; containerizing adds build time for zero demo-day benefit. Direct `uvicorn` + Vercel is enough. |
| Strategic Reserve Agent | Was already marked stretch — now fully cut, not attempted. |
| CVaR-optimal procurement mix | Say it in the pitch ("we pick the mix robust across 10,000 crises"), never build it — this was always the plan's own advice. |
| Neo4j migration | Was never going to be built for the demo; not even mentioned as stretch now — networkx is final. |
| Full assumption panel (every parameter editable) | Scoped down to 3 knobs: jump size / price elasticity / days-to-reroute. Still satisfies "assumptions are explicit and testable," far less UI to build and test. |
| Reactive-vs-anticipatory toggle | Kept, but demoted to last-priority frontend polish — cut first if the frontend runs short on time. |
| Exhaustive unit tests on new code | Scoped to smoke tests only (does it run, are outputs in sane ranges) — not full coverage, given the existing repo's test culture is on the data layer, not this new code. |

## 4. MVP build plan — phased

### Phase 1 — Scenario Modeller — ✅ DONE
- [x] `scenario/engine.py`: single mean-reverting jump-diffusion for Brent, jump size scaled by triggering corridor's risk score (not regime-detected).
- [x] Calibrated against one historical anchor (2022 Ukraine invasion, ~$90→$130 sustained, ~44%) as the ceiling for a max-severity shock — **flagged in the module docstring as approximate; cross-check against real `prices` table history before the live demo.**
- [x] ~10,000-path vectorized Monte Carlo: price → import bill → reserve-cover days → cost/day.
- [x] Output: median shock %, 95% VaR shock %, median/VaR reserve-cover days, P(reserve cover < threshold), median/VaR cost in INR crore/day, plus an explicit `caveat` string on the cascade being a simplified elasticity.
- [x] `POST /scenario/run` in `api/main.py` — pure computation, no DB dependency, fully typed request/response models.
- [x] Smoke tests (`tests/test_scenario.py`, 7 tests): output ranges, monotonicity with risk, seed-reproducibility, assumption echo-back, runs in single-digit ms.

### Phase 2 — LangGraph pipeline — ✅ DONE
- [x] `agents/graph.py`: linear `StateGraph`, four nodes, one shared state dict, no branching —
  1. **signal**: computes corridor risk in-process (same recency/confidence-weighted formula as `/corridors/{c}/risk-score`, run directly against Postgres rather than an HTTP self-call) — or, in injected mode, from one cached event.
  2. **scenario**: calls `scenario.engine.run_scenario` with that risk.
  3. **procurement**: overlays live risk onto the existing knowledge graph and calls `api.graph.alternatives`.
  4. **summary**: fills the one-line template from the state dict.
- [x] Each node's wall-clock duration recorded in `durations_ms`, plus overall `total_ms` — what the frontend's latency timer will read.
- [x] `POST /pipeline/run` — `graph.invoke()` synchronously, no SSE.
- [x] "Inject signal" mode: pass `injected_event` instead of hitting the DB at all — verified the DB connection pool is never touched on this path (not just unused-but-required; genuinely optional).
- [x] Smoke tests (`tests/test_pipeline.py`, 7 tests): all four nodes fire and are timed, no DB connection leaks into the JSON response, risk-formula correctness, summary content, procurement ranking order, low-vs-high severity sanity check.
- Full suite: `pytest tests/` → 36 passed, 7 skipped (the DB-integration suite, correctly gated on `DATABASE_URL_TEST` not being set here).

**Two follow-ups before the live demo (need real DB/data access, not just code):**
- [ ] Pull actual Brent prices around a real historical shock from the `prices` table and confirm/adjust `MAX_JUMP_PCT` in `scenario/engine.py` against it.
- [ ] Replace the placeholder cached-event fixture used for "inject signal" with a real captured high-severity event from `structured_events` — update it in **both** `tests/test_pipeline.py`/`frontend/src/demoFixtures.js` (currently the same documented placeholder in both places — swap before rehearsing the demo, not before).

### Phase 3 — Frontend — ✅ DONE (MVP scope)
- [x] Vite + React single screen (`frontend/`): Leaflet map (`MapView` — graph nodes/edges + vessels, color-coded by risk/type, no default-icon asset issues since it's all `CircleMarker`), risk gauge (`RiskPanel`), scenario distribution chart (`ScenarioPanel`, recharts), ranked supplier table (`ProcurementTable`), one-line summary (`SummaryBanner`), latency readout (`PipelineSteps`).
- [x] Scripted reveal of the 4 pipeline steps (`PipelineSteps.jsx`) — paced for legibility (clamped 300-900ms per step) but shows the *real* recorded `durations_ms`/`total_ms` from `/pipeline/run` alongside, so nothing is faked, only the pacing.
- [x] 3-knob assumption panel (`AssumptionPanel.jsx`: jump size override, elasticity, days-to-reroute), debounced, re-runs the full pipeline live on change.
- [x] "Inject Signal" button wired to `/pipeline/run` with a cached placeholder event (`demoFixtures.js` — **swap for a real captured event before the demo**, same follow-up as Phase 2). "Run on Live Data" button also included for when a real DB is connected.
- [x] Reactive/anticipatory toggle (`ModeToggle.jsx` + `ReactiveOverlay.jsx`) — added back in once everything ahead of it was done; "Reactive" mode dims the dashboard behind the McKinsey 47-day contrast line, "Anticipatory" is the live pipeline.

Verified: `npm run build` compiles cleanly (no errors, 634 modules); confirmed a live end-to-end HTTP round trip (`/pipeline/run` with `injected_event`) against a running instance of the actual FastAPI app returns the full correct payload the frontend consumes — same DB-independence property as the backend smoke tests.

### Phase 3.5 — Tooling to close out the two blocking follow-ups
Rather than leave "verify against real data" as manual work, both follow-ups
now have a script — run once against the real DB and done:
- [x] `scripts/capture_demo_event.py` — queries `structured_events` for the best real high-severity/high-confidence event (optionally scoped to one corridor), prints it, and with `--write` patches the cached-event fixture in **both** `frontend/src/demoFixtures.js` and `tests/test_pipeline.py` in place (marked with `DEMO_EVENT_START`/`END` comments so the patch is exact, not fuzzy-matched).
- [x] `scripts/calibrate_jump_size.py` — queries the real `prices` table around a historical shock window (default: 2022 Ukraine invasion), computes the actual % move, compares it to `MAX_JUMP_PCT` in `scenario/engine.py`, and with `--write` patches the constant in place.
- [x] Both scripts' file-patching logic verified end-to-end against the real repo files with synthetic input, then reverted back to the documented placeholders (no fabricated numbers left in the repo — only real DB output should ever get written via `--write`).
- [x] `run_dev.sh` — one command to start the FastAPI app and the Vite dev server together (checks for `.env`/`.venv`/`node_modules` first, Ctrl+C stops both).

**What's left before the real demo now is purely running two commands against the live DB, not writing any more code:**
```
python scripts/capture_demo_event.py --write
python scripts/calibrate_jump_size.py --write
```

### Phase 4 — Demo prep (non-negotiable, do not skip for more features)
- [ ] Confirm one cached real event runs the full pipeline end to end and looks good, as the guaranteed fallback.
- [ ] Record the backup demo video.
- [ ] Rehearse the 90-second script against the real running system.

## 5. Order of work

Same logic as before, just a shorter list: Scenario Modeller first (zero dependencies, biggest gap), LangGraph pipeline second (a thin wrapper over endpoints that already exist, so the framework overhead is small), frontend third, demo prep last and protected — nothing above this line is worth building at the expense of a rehearsed, reliable demo.
