import { useCallback, useEffect, useRef, useState } from "react";
import Header from "./components/Header";
import MapView from "./components/MapView";
import RiskPanel from "./components/RiskPanel";
import SummaryBanner from "./components/SummaryBanner";
import ScenarioPanel from "./components/ScenarioPanel";
import ProcurementTable from "./components/ProcurementTable";
import AssumptionPanel from "./components/AssumptionPanel";
import PipelineSteps from "./components/PipelineSteps";
import ReactiveOverlay from "./components/ReactiveOverlay";
import { getGraph, getVessels, runPipeline } from "./api";
import { CACHED_DEMO_EVENT } from "./demoFixtures";
import "./App.css";

const DEFAULT_ASSUMPTIONS = {
  jumpOverrideEnabled: false,
  jumpOverridePct: 0.3,
  elasticity: 1.2,
  daysToReroute: 21,
};

export default function App() {
  const [graph, setGraph] = useState(null);
  const [vessels, setVessels] = useState([]);
  const [corridor, setCorridor] = useState("Strait of Hormuz");
  const [refinery, setRefinery] = useState("Jamnagar (RIL)");
  const [assumptions, setAssumptions] = useState(DEFAULT_ASSUMPTIONS);
  const [result, setResult] = useState(null);
  const [runId, setRunId] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [viewMode, setViewMode] = useState("anticipatory"); // "anticipatory" | "reactive" — cosmetic contrast toggle
  const lastModeRef = useRef(null); // "injected" | "live" — which pipeline input source was last used

  // Best-effort map data — the demo's core story (pipeline result) never
  // blocks on this, so failures here are logged, not surfaced as an error.
  useEffect(() => {
    getGraph().then(setGraph).catch((e) => console.warn("graph fetch failed", e));
    getVessels().then(setVessels).catch((e) => console.warn("vessels fetch failed", e));
  }, []);

  const scenarioParams = useCallback(() => ({
    jump_size_pct: assumptions.jumpOverrideEnabled ? assumptions.jumpOverridePct : null,
    elasticity: assumptions.elasticity,
    days_to_reroute: assumptions.daysToReroute,
  }), [assumptions]);

  const runWithMode = useCallback(async (mode) => {
    setLoading(true);
    setError(null);
    try {
      const payload = {
        corridor,
        refinery,
        scenario: scenarioParams(),
      };
      if (mode === "injected") payload.injected_event = CACHED_DEMO_EVENT;

      const out = await runPipeline(payload);
      setResult(out);
      setRunId((n) => n + 1);
      lastModeRef.current = mode;
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [corridor, refinery, scenarioParams]);

  const handleInjectSignal = () => runWithMode("injected");
  const handleRunLive = () => runWithMode("live");

  const handleAssumptionsChange = (next) => {
    setAssumptions(next);
    if (lastModeRef.current) runWithMode(lastModeRef.current);
  };

  return (
    <div className="app-shell">
      <Header
        refinery={refinery}
        onRefineryChange={setRefinery}
        onInjectSignal={handleInjectSignal}
        onRunLive={handleRunLive}
        loading={loading}
        error={error}
        mode={viewMode}
        onModeChange={setViewMode}
      />

      {viewMode === "reactive" ? (
        <ReactiveOverlay />
      ) : (
        <>
          <PipelineSteps durations={result?.durations_ms} totalMs={result?.total_ms} runId={runId} />

          <div className="main-grid">
            <div className="map-col">
              <MapView graph={graph} vessels={vessels} />
            </div>

            <div className="side-col">
              <RiskPanel
                corridor={corridor}
                onCorridorChange={setCorridor}
                riskScore={result?.risk_score}
                eventCount={result?.risk_event_count}
              />
              <SummaryBanner summary={result?.summary} caveat={result?.scenario_result?.caveat} />
              <ScenarioPanel scenario={result?.scenario_result} />
              <AssumptionPanel params={assumptions} onChange={handleAssumptionsChange} disabled={loading} />
            </div>
          </div>

          <ProcurementTable options={result?.procurement_options} />
        </>
      )}
    </div>
  );
}
