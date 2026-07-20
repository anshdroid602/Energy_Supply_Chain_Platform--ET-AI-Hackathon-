import { useRef } from "react";

// The "assumption panel" the plan calls out as a differentiator: a judge
// can change these and watch the scenario re-run live. Scoped to exactly 3
// knobs per task.md (down from "every parameter editable") — jump size,
// elasticity, days-to-reroute — everything else stays at its documented
// default from scenario/engine.py.
export default function AssumptionPanel({ params, onChange, disabled }) {
  const debounceRef = useRef(null);

  const update = (patch) => {
    const next = { ...params, ...patch };
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => onChange(next), 250);
  };

  return (
    <div className="panel">
      <div className="panel-header"><span>Assumptions</span></div>

      <label className="assumption-row">
        <span>
          Jump size override
          <input
            type="checkbox"
            checked={params.jumpOverrideEnabled}
            onChange={(e) => onChange({ ...params, jumpOverrideEnabled: e.target.checked })}
            disabled={disabled}
          />
        </span>
        <input
          type="range" min="0" max="0.6" step="0.01"
          value={params.jumpOverridePct}
          disabled={disabled || !params.jumpOverrideEnabled}
          onChange={(e) => update({ jumpOverridePct: parseFloat(e.target.value) })}
        />
        <span className="assumption-value">{(params.jumpOverridePct * 100).toFixed(0)}%</span>
      </label>

      <label className="assumption-row">
        <span>Elasticity</span>
        <input
          type="range" min="0.1" max="3" step="0.05"
          value={params.elasticity}
          disabled={disabled}
          onChange={(e) => update({ elasticity: parseFloat(e.target.value) })}
        />
        <span className="assumption-value">{params.elasticity.toFixed(2)}</span>
      </label>

      <label className="assumption-row">
        <span>Days to reroute</span>
        <input
          type="range" min="5" max="60" step="1"
          value={params.daysToReroute}
          disabled={disabled}
          onChange={(e) => update({ daysToReroute: parseInt(e.target.value, 10) })}
        />
        <span className="assumption-value">{params.daysToReroute}d</span>
      </label>

      <div className="assumption-note">Changes here re-run the Monte Carlo scenario live.</div>
    </div>
  );
}
