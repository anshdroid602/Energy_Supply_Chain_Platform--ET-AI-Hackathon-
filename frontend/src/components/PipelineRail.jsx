import { useEffect, useState } from "react";
import { Cpu } from "lucide-react";

// The narrative spine: Signal → Scenario → Routes → Decision. Reveals each
// step paced for legibility, but the ms shown are the REAL per-node durations
// recorded server-side (durations_ms), and the total is the actual latency —
// the "signal to recommendation" hook.
const STEPS = [
  { key: "signal", label: "Signal detected" },
  { key: "scenario", label: "Scenario simulated" },
  { key: "procurement", label: "Routes ranked" },
  { key: "summary", label: "Decision ready" },
];

const paced = (ms) => Math.min(750, Math.max(280, (ms || 0) * 45));

export default function PipelineRail({ durations, totalMs, runId }) {
  const [revealed, setRevealed] = useState(durations ? STEPS.length : 0);

  useEffect(() => {
    if (!durations) { setRevealed(0); return; }
    setRevealed(0);
    const timers = [];
    let t = 0;
    STEPS.forEach((s, i) => {
      t += paced(durations[s.key]);
      timers.push(setTimeout(() => setRevealed(i + 1), t));
    });
    return () => timers.forEach(clearTimeout);
  }, [runId, durations]);

  const done = revealed >= STEPS.length;

  return (
    <div className="pipe">
      <div className="pipe-label"><Cpu size={15} color="var(--text-3)" /><span className="eyebrow">Pipeline</span></div>
      <div className="pipe-steps">
        {STEPS.map((s, i) => {
          const on = revealed > i;
          return (
            <div key={s.key} style={{ display: "flex", alignItems: "center" }}>
              {i > 0 && <span className={`pipe-conn ${on ? "on" : ""}`} />}
              <div className={`pipe-step ${on ? "on" : ""}`}>
                <span className="idx">{i + 1}</span>
                <span className="txt">{s.label}</span>
                {on && durations && <span className="ms">{durations[s.key]?.toFixed(1)}ms</span>}
              </div>
            </div>
          );
        })}
      </div>
      <div className="pipe-total">
        <span className="k">Signal → recommendation</span>
        <span className={`v ${done ? "" : "pending"}`}>
          {durations ? (done ? `${totalMs?.toFixed(1)}ms` : "…") : "—"}
        </span>
      </div>
    </div>
  );
}
