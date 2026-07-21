// The "reactive vs anticipatory" contrast — one of the plan's "5 details judges
// remember", and the on-screen embodiment of the 47-days-vs-milliseconds hook.
// A compact segmented control living in the TopBar; flipping to "Reactive"
// dims the live console behind ReactiveOverlay. Purely cosmetic, no backend.
export default function ModeToggle({ mode, onChange }) {
  return (
    <div className="mode-toggle" role="tablist" aria-label="Response mode">
      <button
        role="tab"
        aria-selected={mode === "reactive"}
        className={`mode-seg ${mode === "reactive" ? "on reactive" : ""}`}
        onClick={() => onChange("reactive")}
      >
        Reactive
      </button>
      <button
        role="tab"
        aria-selected={mode === "anticipatory"}
        className={`mode-seg ${mode === "anticipatory" ? "on anticipatory" : ""}`}
        onClick={() => onChange("anticipatory")}
      >
        Anticipatory
      </button>
    </div>
  );
}
