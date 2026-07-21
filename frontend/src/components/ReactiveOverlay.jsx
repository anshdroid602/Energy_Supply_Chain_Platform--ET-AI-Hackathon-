import { motion } from "framer-motion";
import { ArrowRight, Clock3 } from "lucide-react";

// What the console shows in "Reactive" mode — the old way, for contrast against
// PRAHARI's live pipeline. No data, no simulation, no recommendation until the
// disruption is already confirmed and prices have already moved: just the wait,
// and the number that wait costs.
export default function ReactiveOverlay({ onSwitch }) {
  return (
    <motion.div
      className="reactive-overlay"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.25 }}
    >
      <motion.div
        className="reactive-card"
        initial={{ opacity: 0, y: 16, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 12, scale: 0.98 }}
        transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
      >
        <div className="eyebrow" style={{ color: "var(--critical)", display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}>
          <Clock3 size={12} /> Reactive approach · the old way
        </div>

        <div className="reactive-stat">
          <span className="num">47</span>
          <span className="unit">extra days</span>
        </div>

        <p className="reactive-lede">
          McKinsey: unprepared economies take <strong>47 extra days</strong> to
          stabilise crude supply after a shock — because the response only starts
          <em> after</em> the disruption is confirmed and prices have already moved.
        </p>

        <ul className="reactive-list">
          <li>No signal detection</li>
          <li>No live simulation</li>
          <li>No procurement recommendation until it is already too late</li>
        </ul>

        <button className="btn primary" onClick={onSwitch}>
          Switch to Anticipatory <ArrowRight size={15} />
        </button>

        <div className="reactive-foot">
          PRAHARI handles the same scenario <strong>signal → recommendation in milliseconds</strong>.
        </div>
      </motion.div>
    </motion.div>
  );
}
