// What the dashboard shows in "Reactive" mode — the old way, for contrast
// against PRAHARI's live pipeline. No data, no simulation, no
// recommendation: just a wait.
export default function ReactiveOverlay() {
  return (
    <div className="reactive-overlay">
      <div className="reactive-card">
        <div className="reactive-title">Reactive approach</div>
        <p>
          No signal detection. No live simulation. No procurement recommendation
          until the disruption is already confirmed and prices have already moved —
          then the response process starts.
        </p>
        <p className="reactive-stat">McKinsey: unprepared economies take <strong>47 extra days</strong> to
          stabilise supply after a shock.</p>
        <p className="reactive-cta">Switch to <strong>Anticipatory (PRAHARI)</strong> to see the same
          scenario handled signal-to-recommendation in milliseconds.</p>
      </div>
    </div>
  );
}
