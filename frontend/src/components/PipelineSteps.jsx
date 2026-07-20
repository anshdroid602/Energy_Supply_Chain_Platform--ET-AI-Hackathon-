import { useEffect, useState } from "react";

// Scripted reveal of the 4 LangGraph pipeline steps, paced for legibility on
// stage rather than for realism — see task.md: real SSE was cut, so this
// takes one synchronous /pipeline/run response (with real per-step
// durations_ms already recorded server-side) and reveals each step with a
// short, clamped delay. The real recorded ms is shown alongside each step,
// so nothing here is faked — only the pacing of the reveal is scripted.
const STEPS = [
  { key: "signal", label: "Signal detected" },
  { key: "scenario", label: "Scenario computed" },
  { key: "procurement", label: "Routes ranked" },
  { key: "summary", label: "Recommendation ready" },
];

function pacedDelayMs(realMs) {
  return Math.min(900, Math.max(300, (realMs || 0) * 40));
}

export default function PipelineSteps({ durations, totalMs, runId }) {
  const [revealed, setRevealed] = useState(0);

  useEffect(() => {
    if (!durations) {
      setRevealed(0);
      return;
    }
    setRevealed(0);
    const timers = [];
    let cumulative = 0;
    STEPS.forEach(({ key }, idx) => {
      cumulative += pacedDelayMs(durations[key]);
      timers.push(setTimeout(() => setRevealed(idx + 1), cumulative));
    });
    return () => timers.forEach(clearTimeout);
  }, [runId, durations]);

  return (
    <div className="pipeline-steps">
      {STEPS.map((s, i) => {
        const done = revealed > i;
        return (
          <div key={s.key} className={`step-chip ${done ? "step-done" : "step-pending"}`}>
            <span className="step-dot" />
            <span className="step-label">{s.label}</span>
            {done && durations && (
              <span className="step-ms">{durations[s.key]?.toFixed(2)}ms</span>
            )}
          </div>
        );
      })}
      {durations && (
        <div className={`total-ms ${revealed >= STEPS.length ? "total-ms-final" : ""}`}>
          {revealed >= STEPS.length ? `Signal → recommendation: ${totalMs?.toFixed(1)}ms` : "…"}
        </div>
      )}
    </div>
  );
}
