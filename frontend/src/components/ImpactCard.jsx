import { IndianRupee } from "lucide-react";
import CountUp from "./CountUp";
import { fmt, fmtPct, riskColor } from "../utils";

// The Business-Impact card: everything in rupees and days, the way a
// policymaker reads it. Median cost is the headline; reserve cover shows how
// close the country runs to the floor.
export default function ImpactCard({ scenario }) {
  if (!scenario) {
    return (
      <section className="card">
        <div className="card-head"><div className="title"><IndianRupee size={15} /><span className="eyebrow">Business impact</span></div></div>
        <div className="empty"><IndianRupee size={26} /><div className="t">No impact yet</div><div className="s">Runs when a signal fires</div></div>
      </section>
    );
  }

  const { results, assumptions } = scenario;
  const before = assumptions.baseline_reserve_days;
  const after = results.median_reserve_cover_days;
  const threshold = assumptions.reserve_threshold_days;
  const maxDays = Math.max(before, 12);
  const fillColor = after < threshold ? "#f04452" : after < before ? "#f2913d" : "#3fb27f";
  const pBreach = results.prob_reserve_cover_below_threshold;

  return (
    <section className="card">
      <div className="card-head">
        <div className="title"><IndianRupee size={15} /><span className="eyebrow">Business impact</span></div>
        <span className="chip crit mono">P(cover&lt;{threshold}d) {fmt(pBreach * 100, 0)}%</span>
      </div>

      <div className="impact-hero">
        <div>
          <span className="v">₹<CountUp value={results.median_cost_inr_cr_per_day} decimals={0} /></span>
          <span className="u"> cr/day</span>
        </div>
        <div className="k">Median added import bill</div>
      </div>

      <div className="metrics" style={{ marginBottom: 14 }}>
        <div className="metric"><div className="v">₹{fmt(results.var95_cost_inr_cr_per_day, 0)}<span style={{ fontSize: 12, color: "var(--text-3)" }}> cr</span></div><div className="k">95% VaR cost/day</div></div>
        <div className="metric"><div className="v amber">{fmtPct(results.median_shock_pct, 0)}</div><div className="k">Brent, median path</div></div>
      </div>

      <div className="reserve-bar-wrap">
        <div className="reserve-track">
          <div className="reserve-fill" style={{ width: `${(after / maxDays) * 100}%`, background: fillColor }} />
          <div className="reserve-thresh" style={{ left: `${(threshold / maxDays) * 100}%` }} />
        </div>
        <div className="reserve-legend">
          <span>Reserve cover <b style={{ color: "var(--text-2)" }}>{fmt(before, 1)}d</b> → <b style={{ color: fillColor }}>{fmt(after, 1)}d</b></span>
          <span>floor {threshold}d</span>
        </div>
      </div>
    </section>
  );
}
