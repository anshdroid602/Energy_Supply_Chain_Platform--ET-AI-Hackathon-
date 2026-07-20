export default function ProcurementTable({ options }) {
  if (!options || options.length === 0) {
    return <div className="panel">Procurement options will appear here after a run.</div>;
  }

  return (
    <div className="panel">
      <div className="panel-header"><span>Procurement — Ranked Alternatives</span></div>
      <table className="proc-table">
        <thead>
          <tr>
            <th>Supplier</th>
            <th>Grade fit</th>
            <th>Import share</th>
            <th>Route</th>
            <th>ETA</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {options.map((o, i) => {
            const route = o.safest_viable_route || o.fastest_route;
            return (
              <tr key={o.supplier} className={i === 0 && o.viable ? "row-top-pick" : ""}>
                <td>{o.supplier}{i === 0 && o.viable && <span className="badge">TOP PICK</span>}</td>
                <td>{o.grade_fit ? "✓" : "✗"}</td>
                <td>{o.import_share_pct != null ? `${o.import_share_pct}%` : "—"}</td>
                <td className="route-path">{route ? route.path.join(" → ") : "—"}</td>
                <td>{route ? `${route.eta_days.toFixed(1)}d` : "—"}</td>
                <td className={o.viable ? "status-viable" : "status-blocked"}>
                  {o.viable ? "Viable" : (o.blocked_reason || "Blocked")}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
