import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle } from "lucide-react";
import TopBar from "./components/TopBar";
import OpsMap from "./components/OpsMap";
import ThreatRing from "./components/ThreatRing";
import AssumptionPanel from "./components/AssumptionPanel";
import ChokepointBoard from "./components/ChokepointBoard";
import PipelineRail from "./components/PipelineRail";
import ScenarioCard from "./components/ScenarioCard";
import ImpactCard from "./components/ImpactCard";
import ProcurementCard from "./components/ProcurementCard";
import ReactiveOverlay from "./components/ReactiveOverlay";
import { getGraph, getVessels, runPipeline } from "./api";
import { CACHED_DEMO_EVENT } from "./demoFixtures";

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
  const [mode, setMode] = useState("anticipatory");   // "anticipatory" | "reactive"
  const lastModeRef = useRef(null);       // "injected" | "live"
  const debounceRef = useRef();

  // Live map data loads immediately so the theatre is never blank.
  useEffect(() => {
    getGraph().then(setGraph).catch((e) => console.warn("graph fetch failed", e));
    getVessels().then(setVessels).catch((e) => console.warn("vessels fetch failed", e));
  }, []);

  const buildScenario = (a) => ({
    jump_size_pct: a.jumpOverrideEnabled ? a.jumpOverridePct : null,
    elasticity: a.elasticity,
    days_to_reroute: a.daysToReroute,
  });

  const runWithMode = useCallback(async (mode, a) => {
    setLoading(true);
    setError(null);
    try {
      const payload = { corridor, refinery, scenario: buildScenario(a) };
      if (mode === "injected") payload.injected_event = { ...CACHED_DEMO_EVENT, corridor };
      const out = await runPipeline(payload);
      setResult(out);
      setRunId((n) => n + 1);
      lastModeRef.current = mode;
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [corridor, refinery]);

  const handleInject = () => runWithMode("injected", assumptions);
  const handleRunLive = () => runWithMode("live", assumptions);

  const handleAssumptions = (next) => {
    setAssumptions(next);
    if (lastModeRef.current) {
      clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => runWithMode(lastModeRef.current, next), 320);
    }
  };

  // Theatre-wide threat = worst chokepoint; the ring tracks the selected corridor.
  const chokeNodes = useMemo(
    () => (graph?.nodes || []).filter((n) => n.type === "chokepoint"),
    [graph],
  );
  const theatreThreat = useMemo(
    () => chokeNodes.reduce((m, n) => Math.max(m, n.risk || 0), 0),
    [chokeNodes],
  );
  const liveCorridor = chokeNodes.find((n) => n.risk_corridor === corridor);
  const ringScore = result?.risk_score ?? liveCorridor?.risk ?? 0;
  const ringEvents = result?.risk_event_count ?? liveCorridor?.risk_events ?? null;
  const ringActive = result != null || (liveCorridor?.risk ?? 0) > 0;

  return (
    <div className="shell">
      <TopBar
        threatScore={theatreThreat}
        corridor={corridor}
        refinery={refinery}
        onCorridorChange={setCorridor}
        onRefineryChange={setRefinery}
        onInject={handleInject}
        onRunLive={handleRunLive}
        loading={loading}
        mode={mode}
        onModeChange={setMode}
      />

      <div className="stage">
        <div className="map-col">
          <OpsMap graph={graph} vessels={vessels} result={result} />
        </div>
        <div className="rail-col">
          <ThreatRing score={ringScore} eventCount={ringEvents} corridor={corridor} active={ringActive} />
          <AssumptionPanel params={assumptions} onChange={handleAssumptions} disabled={loading} />
          <ChokepointBoard graph={graph} />
        </div>
      </div>

      <PipelineRail durations={result?.durations_ms} totalMs={result?.total_ms} runId={runId} />

      <div className="analysis">
        <ScenarioCard scenario={result?.scenario_result} />
        <ImpactCard scenario={result?.scenario_result} />
        <ProcurementCard options={result?.procurement_options} refinery={refinery} />
      </div>

      <AnimatePresence>
        {mode === "reactive" && (
          <ReactiveOverlay key="reactive" onSwitch={() => setMode("anticipatory")} />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {error && (
          <motion.div className="err-toast"
            initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 12 }}>
            <AlertTriangle size={15} /> {error}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
