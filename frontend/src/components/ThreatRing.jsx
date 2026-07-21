import { motion } from "framer-motion";
import { ShieldAlert } from "lucide-react";
import CountUp from "./CountUp";
import { riskColor, riskLevel } from "../utils";

const TICKS = 48;
const R = 72;
const C = 2 * Math.PI * R;

// The signature widget: a segmented radar bezel + an animated confidence arc.
// The disruption probability IS the corridor risk score (auditable), counted
// up and read out at the centre.
export default function ThreatRing({ score, eventCount, corridor, active }) {
  const s = active && score != null ? score : 0;
  const color = riskColor(s);
  const level = riskLevel(s);

  return (
    <section className="card ring-card">
      <div className="card-head" style={{ alignSelf: "stretch" }}>
        <div className="title"><ShieldAlert size={15} /><span className="eyebrow">Disruption probability</span></div>
        <span className="chip mono">{corridor}</span>
      </div>

      <div className="ring-wrap">
        <svg width="190" height="190" viewBox="0 0 190 190">
          <defs>
            <radialGradient id="ringGlow" cx="50%" cy="50%" r="50%">
              <stop offset="55%" stopColor={color} stopOpacity="0" />
              <stop offset="100%" stopColor={color} stopOpacity="0.12" />
            </radialGradient>
          </defs>
          <circle cx="95" cy="95" r="80" fill="url(#ringGlow)" />

          {/* segmented bezel */}
          {Array.from({ length: TICKS }).map((_, i) => {
            const a = (i / TICKS) * 2 * Math.PI;
            const on = i / TICKS < s;
            const x1 = 95 + 82 * Math.cos(a), y1 = 95 + 82 * Math.sin(a);
            const x2 = 95 + 75 * Math.cos(a), y2 = 95 + 75 * Math.sin(a);
            return (
              <line key={i} x1={x1} y1={y1} x2={x2} y2={y2}
                stroke={on ? color : "#232d3a"} strokeWidth="2.2" strokeLinecap="round"
                opacity={on ? 1 : 0.7} />
            );
          })}

          {/* track + animated arc */}
          <circle cx="95" cy="95" r={R} fill="none" stroke="#1b2431" strokeWidth="7" />
          <motion.circle
            cx="95" cy="95" r={R} fill="none" stroke={color} strokeWidth="7" strokeLinecap="round"
            strokeDasharray={C}
            initial={{ strokeDashoffset: C }}
            animate={{ strokeDashoffset: C * (1 - s) }}
            transition={{ duration: 1.1, ease: [0.16, 1, 0.3, 1] }}
            style={{ filter: `drop-shadow(0 0 6px ${color}66)` }}
          />
        </svg>

        <div className="ring-center">
          <div className="ring-val" style={{ color }}>
            <CountUp value={s * 100} decimals={0} /><span className="pct">%</span>
          </div>
          <div className="ring-lvl" style={{ color }}>{level}</div>
          <div className="ring-cap">recency · confidence weighted</div>
        </div>
      </div>

      <div className="ring-foot">
        <div className="m">
          <div className="v">{active && eventCount != null ? eventCount : "—"}</div>
          <div className="k">Events backing</div>
        </div>
        <div className="m">
          <div className="v" style={{ color: s >= 0.5 ? color : "var(--text)" }}>{active ? (s >= 0.5 ? "ARMED" : "CLEAR") : "IDLE"}</div>
          <div className="k">Detector</div>
        </div>
      </div>
    </section>
  );
}
