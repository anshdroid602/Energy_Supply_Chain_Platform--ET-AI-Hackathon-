import { REFINERIES } from "../demoFixtures";
import ModeToggle from "./ModeToggle";

export default function Header({ refinery, onRefineryChange, onInjectSignal, onRunLive, loading, error, mode, onModeChange }) {
  return (
    <header className="app-header">
      <div className="brand">
        <span className="brand-title">PRAHARI</span>
        <span className="brand-tagline">Signal → Recommendation</span>
      </div>

      <ModeToggle mode={mode} onChange={onModeChange} />

      <div className="header-controls">
        <label className="header-select">
          Refinery
          <select value={refinery} onChange={(e) => onRefineryChange(e.target.value)}>
            {REFINERIES.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </label>

        <button className="btn btn-primary" onClick={onInjectSignal} disabled={loading || mode === "reactive"}>
          {loading ? "Running…" : "Inject Signal"}
        </button>
        <button className="btn btn-secondary" onClick={onRunLive} disabled={loading || mode === "reactive"}>
          Run on Live Data
        </button>
      </div>

      {error && <div className="header-error">{error}</div>}
    </header>
  );
}
