// The "reactive vs anticipatory" contrast from the plan's "5 details judges
// remember" list — purely cosmetic, no backend dependency, cheap to build.
// Was demoted to lowest priority in task.md and cut first if time ran short;
// added back now that everything ahead of it is done.
export default function ModeToggle({ mode, onChange }) {
  return (
    <div className="mode-toggle">
      <button
        className={mode === "reactive" ? "mode-btn mode-active" : "mode-btn"}
        onClick={() => onChange("reactive")}
      >
        Reactive (old way)
      </button>
      <button
        className={mode === "anticipatory" ? "mode-btn mode-active" : "mode-btn"}
        onClick={() => onChange("anticipatory")}
      >
        Anticipatory (PRAHARI)
      </button>
    </div>
  );
}
