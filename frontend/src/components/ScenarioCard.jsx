import { Area, AreaChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Sigma } from "lucide-react";
import { fmt, fmtPct } from "../utils";

const PCTS = Array.from({ length: 19 }, (_, i) => 5 + i * 5); // 5..95

function TipBox({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: "var(--surface-3)", border: "1px solid var(--border)", borderRadius: 8, padding: "6px 9px", fontFamily: "var(--font-mono)", fontSize: 11 }}>
      <div style={{ color: "var(--text-3)" }}>p{label}</div>
      <div style={{ color: "var(--text)" }}>{fmt(payload[0].value, 1)} days cover</div>
    </div>
  );
}

export default function ScenarioCard({ scenario }) {
  if (!scenario) {
    return (
      <section className="card">
        <div className="card-head"><div className="title"><Sigma size={15} /><span className="eyebrow">Scenario · Monte Carlo</span></div></div>
        <div className="empty"><Sigma size={26} /><div className="t">No simulation yet</div><div className="s">Inject a signal to run 10,000 paths</div></div>
      </section>
    );
  }

  const { results, assumptions, distribution_sample, elapsed_ms } = scenario;
  const data = distribution_sample.reserve_cover_days.map((days, i) => ({ pct: PCTS[i], days }));
  const threshold = assumptions.reserve_threshold_days;

  return (
    <section className="card">
      <div className="card-head">
        <div className="title"><Sigma size={15} /><span className="eyebrow">Scenario · Monte Carlo</span></div>
        <span className="chip mono">{assumptions.n_paths.toLocaleString()} paths · {fmt(elapsed_ms, 0)}ms</span>
      </div>

      <div className="metrics" style={{ marginBottom: 10 }}>
        <div className="metric"><div className="v amber">{fmtPct(results.median_shock_pct, 0)}</div><div className="k">Median Brent shock</div></div>
        <div className="metric"><div className="v crit">{fmtPct(results.var95_shock_pct, 0)}</div><div className="k">95% VaR shock</div></div>
      </div>

      <div style={{ flex: 1, minHeight: 96 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 4, right: 6, left: -22, bottom: -6 }}>
            <defs>
              <linearGradient id="coverGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#45c4b0" stopOpacity={0.42} />
                <stop offset="100%" stopColor="#45c4b0" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <XAxis dataKey="pct" tick={{ fontSize: 9, fill: "#5e6b78", fontFamily: "var(--font-mono)" }} tickLine={false} axisLine={false} unit="" />
            <YAxis tick={{ fontSize: 9, fill: "#5e6b78", fontFamily: "var(--font-mono)" }} width={30} tickLine={false} axisLine={false} />
            <Tooltip content={<TipBox />} cursor={{ stroke: "#2c3846" }} />
            <ReferenceLine y={threshold} stroke="#f04452" strokeDasharray="4 4" strokeWidth={1.2} />
            <Area type="monotone" dataKey="days" stroke="#45c4b0" fill="url(#coverGrad)" strokeWidth={2} isAnimationActive animationDuration={800} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <div className="chart-cap">Reserve cover (days) across the simulated distribution · red line = {threshold}-day floor</div>
    </section>
  );
}
