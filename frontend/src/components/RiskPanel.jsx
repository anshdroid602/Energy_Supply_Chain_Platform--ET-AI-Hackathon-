import { CORRIDORS } from "../demoFixtures";
import { riskColor, riskLevel, fmt } from "../utils";

export default function RiskPanel({ corridor, onCorridorChange, riskScore, eventCount }) {
  const score = riskScore ?? 0;
  const pct = Math.round(Math.min(Math.max(score, 0), 1) * 100);

  return (
    <div className="panel">
      <div className="panel-header">
        <span>Corridor Risk</span>
        <select value={corridor} onChange={(e) => onCorridorChange(e.target.value)}>
          {CORRIDORS.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>
      <div className="gauge-track">
        <div
          className="gauge-fill"
          style={{ width: `${pct}%`, background: riskColor(score) }}
        />
      </div>
      <div className="gauge-labels">
        <span className="gauge-level" style={{ color: riskColor(score) }}>
          {riskLevel(score)}
        </span>
        <span className="gauge-score">{fmt(score, 2)} · {eventCount ?? 0} events</span>
      </div>
    </div>
  );
}
