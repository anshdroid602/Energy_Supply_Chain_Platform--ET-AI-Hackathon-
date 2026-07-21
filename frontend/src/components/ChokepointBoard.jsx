import { motion } from "framer-motion";
import { Waves } from "lucide-react";
import { riskClass, riskColor, riskLevel } from "../utils";

// The live watchlist: every maritime chokepoint with its recency/confidence-
// weighted risk, sorted worst-first — a real ops board driven by graph data.
export default function ChokepointBoard({ graph }) {
  const chokepoints = (graph?.nodes || [])
    .filter((n) => n.type === "chokepoint")
    .map((n) => ({ id: n.id, risk: n.risk || 0, events: n.risk_events || 0 }))
    .sort((a, b) => b.risk - a.risk);

  return (
    <section className="card board">
      <div className="card-head">
        <div className="title"><Waves size={15} /><span className="eyebrow">Chokepoint watch</span></div>
        <span className="eyebrow">{chokepoints.length} tracked</span>
      </div>
      <div className="board-list">
        {chokepoints.map((c, i) => {
          const color = riskColor(c.risk);
          return (
            <motion.div key={c.id} className="choke-row"
              initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.05, duration: 0.35 }}>
              <div className="choke-name">
                <span className="glyph" style={{ background: color }} />
                {c.id}
              </div>
              <div className="choke-val" style={{ color }}>{c.risk.toFixed(2)}</div>
              <div className="choke-bar">
                <motion.span style={{ background: color }}
                  initial={{ width: 0 }} animate={{ width: `${c.risk * 100}%` }}
                  transition={{ delay: i * 0.05 + 0.1, duration: 0.7, ease: [0.16, 1, 0.3, 1] }} />
              </div>
              <div className="choke-meta">{riskLevel(c.risk)} · {c.events} events · 30d window</div>
            </motion.div>
          );
        })}
      </div>
    </section>
  );
}
