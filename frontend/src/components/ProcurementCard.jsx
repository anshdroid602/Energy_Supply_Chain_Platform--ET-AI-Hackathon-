import { CheckCircle2, Ship, XCircle } from "lucide-react";
import { fmt } from "../utils";

function routeOf(o) { return o.safest_viable_route || o.fastest_route || null; }

export default function ProcurementCard({ options, refinery }) {
  if (!options || options.length === 0) {
    return (
      <section className="card">
        <div className="card-head"><div className="title"><Ship size={15} /><span className="eyebrow">Procurement · ranked sources</span></div></div>
        <div className="empty"><Ship size={26} /><div className="t">No recommendation yet</div><div className="s">The reroute shortlist appears after a run</div></div>
      </section>
    );
  }

  const top = options.find((o) => o.viable) || options[0];
  const topRoute = routeOf(top);

  return (
    <section className="card">
      <div className="card-head">
        <div className="title"><Ship size={15} /><span className="eyebrow">Procurement · ranked sources</span></div>
        <span className="eyebrow">→ {refinery}</span>
      </div>

      {top && topRoute && (
        <div className="proc-top">
          <div className="lead">
            <div className="who">{top.supplier} <span className="chip safe mono">TOP PICK</span></div>
            <div className="route">{topRoute.path.join("  ›  ")}</div>
          </div>
          <div className="eta">
            <div className="v">{fmt(topRoute.eta_days, 0)}d</div>
            <div className="k">ETA · {top.grade_name || top.grade}</div>
          </div>
        </div>
      )}

      <div className="proc-scroll">
        <table className="proc-table">
          <thead>
            <tr>
              <th>Source</th><th>Grade</th><th className="num">Share</th><th className="num">ETA</th><th className="num">Status</th>
            </tr>
          </thead>
          <tbody>
            {options.map((o) => {
              const r = routeOf(o);
              return (
                <tr key={o.supplier} className={o.viable ? "" : "proc-blocked"}>
                  <td className="sup">{o.supplier}</td>
                  <td className="grade">{o.grade_name || o.grade || "—"}</td>
                  <td className="num etacell">{o.import_share_pct != null ? `${o.import_share_pct}%` : "—"}</td>
                  <td className="num etacell">{r ? `${fmt(r.eta_days, 0)}d` : "—"}</td>
                  <td className="num">
                    {o.viable
                      ? <span className="stat-chip ok"><CheckCircle2 size={11} style={{ verticalAlign: -2 }} /> Viable</span>
                      : <span className="stat-chip no"><XCircle size={11} style={{ verticalAlign: -2 }} /> Blocked</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
