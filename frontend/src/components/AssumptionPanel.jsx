import { SlidersHorizontal } from "lucide-react";

// The "explicit and testable assumptions" panel — a judge turns a knob and
// watches the ring, distribution and cost update live (App re-runs the
// pipeline, debounced).
export default function AssumptionPanel({ params, onChange, disabled }) {
  const set = (patch) => onChange({ ...params, ...patch });

  return (
    <section className="card">
      <div className="card-head">
        <div className="title"><SlidersHorizontal size={15} /><span className="eyebrow">Assumptions</span></div>
        <span className="eyebrow">editable · live</span>
      </div>

      <div className="knobs">
        <div className="knob">
          <div className="knob-head">
            <label className="toggle">
              <input type="checkbox" checked={params.jumpOverrideEnabled}
                onChange={(e) => set({ jumpOverrideEnabled: e.target.checked })} disabled={disabled} />
              <span className="track" />
              <span className="kk">Override jump size</span>
            </label>
            <span className="kv">{params.jumpOverrideEnabled ? `${Math.round(params.jumpOverridePct * 100)}%` : "auto"}</span>
          </div>
          <input type="range" className="slider" min="0.05" max="0.6" step="0.01"
            value={params.jumpOverridePct}
            onChange={(e) => set({ jumpOverridePct: parseFloat(e.target.value) })}
            disabled={disabled || !params.jumpOverrideEnabled} />
        </div>

        <div className="knob">
          <div className="knob-head"><span className="kk">Price → economy elasticity</span><span className="kv">{params.elasticity.toFixed(1)}</span></div>
          <input type="range" className="slider" min="0.5" max="3" step="0.1"
            value={params.elasticity} onChange={(e) => set({ elasticity: parseFloat(e.target.value) })} disabled={disabled} />
        </div>

        <div className="knob">
          <div className="knob-head"><span className="kk">Days to reroute</span><span className="kv">{params.daysToReroute}d</span></div>
          <input type="range" className="slider" min="3" max="45" step="1"
            value={params.daysToReroute} onChange={(e) => set({ daysToReroute: parseInt(e.target.value, 10) })} disabled={disabled} />
        </div>
      </div>
    </section>
  );
}
