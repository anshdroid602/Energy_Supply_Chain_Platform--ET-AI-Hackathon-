import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from "recharts";
import { fmt, fmtCrore, fmtPct } from "../utils";

const PERCENTILES = Array.from({ length: 19 }, (_, i) => 5 + i * 5); // 5..95 step 5

export default function ScenarioPanel({ scenario }) {
  if (!scenario) {
    return <div className="panel">Scenario distribution will appear here after a run.</div>;
  }

  const { results, assumptions, distribution_sample, caveat, elapsed_ms } = scenario;
  const chartData = distribution_sample.reserve_cover_days.map((days, i) => ({
    pct: PERCENTILES[i],
    days,
  }));

  return (
    <div className="panel">
      <div className="panel-header"><span>Scenario — Monte Carlo ({assumptions.n_paths.toLocaleString()} paths, {elapsed_ms}ms)</span></div>

      <div className="stat-grid">
        <Stat label="Median shock" value={fmtPct(results.median_shock_pct)} />
        <Stat label="95% VaR shock" value={fmtPct(results.var95_shock_pct)} />
        <Stat label="Median cost" value={fmtCrore(results.median_cost_inr_cr_per_day)} />
        <Stat label="P(cover < threshold)" value={fmt(results.prob_reserve_cover_below_threshold * 100, 0) + "%"} />
      </div>

      <div style={{ height: 130, marginTop: 8 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
            <defs>
              <linearGradient id="coverGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#42a5f5" stopOpacity={0.5} />
                <stop offset="100%" stopColor="#42a5f5" stopOpacity={0.05} />
              </linearGradient>
            </defs>
            <XAxis dataKey="pct" tick={{ fontSize: 10, fill: "#90a4ae" }} unit="%" />
            <YAxis tick={{ fontSize: 10, fill: "#90a4ae" }} width={30} />
            <Tooltip
              contentStyle={{ background: "#12202e", border: "1px solid #2c3e50", fontSize: 12 }}
              formatter={(v) => [`${fmt(v, 1)} days`, "Reserve cover"]}
              labelFormatter={(l) => `${l}th percentile`}
            />
            <ReferenceLine y={assumptions.reserve_threshold_days} stroke="#e53935" strokeDasharray="4 4" />
            <Area type="monotone" dataKey="days" stroke="#42a5f5" fill="url(#coverGrad)" strokeWidth={2} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <div className="chart-caption">Reserve cover (days) across the simulated distribution — dashed line = {assumptions.reserve_threshold_days}-day threshold</div>

      {caveat && <div className="summary-caveat" style={{ marginTop: 8 }}>⚠ {caveat}</div>}
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div className="stat">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}
