// Shared formatting + the single source of truth for what "Critical" vs "Low"
// looks like across the ring, map, board and chips. Risk thresholds mirror
// RISK_LEVEL_THRESHOLDS in api/main.py exactly.

export function riskLevel(score) {
  if (score >= 0.8) return "Critical";
  if (score >= 0.6) return "High";
  if (score >= 0.35) return "Medium";
  return "Low";
}

// premium risk palette (not the garish default reds/yellows)
export function riskColor(score) {
  if (score >= 0.8) return "#f04452";
  if (score >= 0.6) return "#f2913d";
  if (score >= 0.35) return "#e7b84b";
  return "#3fb27f";
}

export function riskClass(score) {
  if (score >= 0.8) return "crit";
  if (score >= 0.6) return "high";
  if (score >= 0.35) return "med";
  return "safe";
}

export function nodeColor(type) {
  switch (type) {
    case "supplier": return "#6a9bd8";
    case "export_port": return "#45c4b0";
    case "import_port": return "#b98bd6";
    case "refinery": return "#3fb27f";
    case "chokepoint": return "#f04452";
    default: return "#5e6b78";
  }
}

export function fmt(n, digits = 1) {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return Number(n).toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

export function fmtInt(n) { return fmt(n, 0); }
export function fmtPct(frac, digits = 1) { return `${fmt(frac * 100, digits)}%`; }
