// Shared formatting/color helpers — kept in one place so the map, gauge,
// and chart all agree on what "Critical" vs "Low" looks like.

// Mirrors RISK_LEVEL_THRESHOLDS in api/main.py exactly.
export function riskLevel(score) {
  if (score >= 0.8) return "Critical";
  if (score >= 0.6) return "High";
  if (score >= 0.35) return "Medium";
  return "Low";
}

export function riskColor(score) {
  if (score >= 0.8) return "#e53935"; // red
  if (score >= 0.6) return "#fb8c00"; // orange
  if (score >= 0.35) return "#fdd835"; // yellow
  return "#43a047"; // green
}

export function nodeColor(type) {
  switch (type) {
    case "supplier": return "#42a5f5";
    case "export_port": return "#26c6da";
    case "import_port": return "#ab47bc";
    case "refinery": return "#66bb6a";
    default: return "#9e9e9e";
  }
}

export function fmt(n, digits = 1) {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return Number(n).toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

export function fmtCrore(n) {
  return `Rs.${fmt(n, 0)} cr/day`;
}

export function fmtPct(n) {
  return `${fmt(n * 100, 1)}%`;
}
