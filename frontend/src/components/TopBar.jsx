import { useEffect, useState } from "react";
import { Activity, Radio, Zap } from "lucide-react";
import { riskClass, riskLevel } from "../utils";
import { CORRIDORS, REFINERIES } from "../demoFixtures";

function Clock() {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  const time = now.toLocaleTimeString("en-GB", { timeZone: "Asia/Kolkata", hour12: false });
  const day = now.toLocaleDateString("en-GB", { timeZone: "Asia/Kolkata", day: "2-digit", month: "short" });
  return (
    <div className="meta-block">
      <span className="k">{day} · IST</span>
      <span className="v">{time}</span>
    </div>
  );
}

function SentinelMark() {
  return (
    <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <path d="M12 2 4 5v6c0 5 3.4 8.5 8 11 4.6-2.5 8-6 8-11V5l-8-3Z" />
      <circle cx="12" cy="10.5" r="2.4" fill="currentColor" stroke="none" />
    </svg>
  );
}

export default function TopBar({
  threatScore, corridor, refinery, onCorridorChange, onRefineryChange,
  onInject, onRunLive, loading,
}) {
  const level = riskLevel(threatScore ?? 0);
  return (
    <header className="topbar">
      <div className="brand">
        <span className="brand-mark"><SentinelMark /></span>
        <div>
          <div className="brand-name">PRAHARI</div>
          <div className="brand-sub">India · Energy Supply-Chain Sentinel</div>
        </div>
      </div>

      <div className={`threat-pill ${riskClass(threatScore ?? 0)}`}>
        <Activity size={15} />
        <div style={{ display: "flex", flexDirection: "column" }}>
          <span className="lab">Theatre threat</span>
          <span className="lvl">{level}</span>
        </div>
      </div>

      <div className="topbar-spacer" />

      <div className="topbar-meta">
        <div className="meta-block">
          <span className="k"><span className="dot live" style={{ display: "inline-block", marginRight: 6 }} />Status</span>
          <span className="v" style={{ fontSize: 13 }}>OPERATIONAL</span>
        </div>
        <Clock />
      </div>

      <div className="topbar-actions">
        <label className="select-wrap">
          <select className="select" value={corridor} onChange={(e) => onCorridorChange(e.target.value)} aria-label="Corridor">
            {CORRIDORS.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
        <label className="select-wrap">
          <select className="select" value={refinery} onChange={(e) => onRefineryChange(e.target.value)} aria-label="Refinery">
            {REFINERIES.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </label>
        <button className="btn ghost" onClick={onRunLive} disabled={loading}>
          <Radio size={15} /> Run live
        </button>
        <button className="btn primary" onClick={onInject} disabled={loading}>
          <Zap size={15} /> {loading ? "Running…" : "Inject signal"}
        </button>
      </div>
    </header>
  );
}
