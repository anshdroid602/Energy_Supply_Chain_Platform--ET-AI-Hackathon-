// PLACEHOLDER cached event for the "Inject Signal" demo button.
//
// task.md flags this explicitly as a pre-demo follow-up: swap this for a
// real, high-severity event pulled from the live `structured_events` table
// (same shape: corridor / severity_score / confidence) before rehearsing
// the actual pitch. Keeping a placeholder here means the frontend is fully
// wireable and testable right now without needing DB access.
//
// Run `python scripts/capture_demo_event.py --write` against the real DB to
// replace the block below automatically (it also updates
// tests/test_pipeline.py's copy) instead of editing this by hand.
// DEMO_EVENT_START
export const CACHED_DEMO_EVENT = {
  corridor: "Strait of Hormuz",
  severity_score: 8.5,
  confidence: 0.8,
};
// DEMO_EVENT_END

export const CORRIDORS = [
  "Strait of Hormuz",
  "Persian Gulf",
  "Red Sea",
  "Suez Canal",
];

export const REFINERIES = [
  "Jamnagar (RIL)",
  "Vadinar (Nayara)",
  "Panipat (IOCL)",
  "Paradip (IOCL)",
  "Kochi (BPCL)",
];
