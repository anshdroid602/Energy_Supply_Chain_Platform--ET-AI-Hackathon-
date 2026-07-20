export default function SummaryBanner({ summary, caveat }) {
  if (!summary) {
    return (
      <div className="panel summary-banner summary-empty">
        Run the pipeline (or click "Inject Signal") to generate a recommendation.
      </div>
    );
  }
  return (
    <div className="panel summary-banner">
      <div className="summary-text">{summary}</div>
      {caveat && <div className="summary-caveat">⚠ {caveat}</div>}
    </div>
  );
}
