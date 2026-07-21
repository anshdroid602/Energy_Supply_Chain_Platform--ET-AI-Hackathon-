"""CLI runner for the agent pipeline.

Run from the repo root (platform/), same root uvicorn/pytest use:

  python3 -m agents.run                                  # Hormuz -> Jamnagar
  python3 -m agents.run --corridor "Red Sea"
  python3 -m agents.run --refinery "Paradip (IOCL)" --json
  python3 -m agents.run --stream                         # print each agent as it finishes

Prints a readable console summary by default, or the full PipelineResult JSON
with --json (that JSON is exactly what the frontend consumes).
"""
from __future__ import annotations

import argparse
import json

from . import config
from .orchestrator import Orchestrator


def _print_human(result):
    r = result
    print("\n" + "=" * 68)
    print(f"  {r.headline}")
    print("=" * 68)
    print(f"corridor={r.corridor}  refinery={r.refinery}  latency={r.latency_seconds}s")

    print(f"\n[1] Risk Intelligence — {r.risk.risk_level} "
          f"P(disruption)={r.risk.disruption_probability:.0%} "
          f"triggered={r.risk.triggered}")
    for e in r.risk.evidence:
        print(f"      • {e.label}: {e.detail}")
    print(f"      {r.risk.reasoning}")

    if r.scenario:
        s = r.scenario
        print(f"\n[2] Scenario Modeller — {s.jump_type_label}")
        print(f"      Brent median {s.median_pct_change:+.1f}%  95% VaR {s.p95_var_pct:+.1f}%  "
              f"(spot ${s.brent_spot_usd})")
        print(f"      reserve cover {s.reserve_cover_days_before}->{s.reserve_cover_days_after}d  "
              f"P(cover<7d)={s.p_cover_below_7}")
        print(f"      extra bill ~Rs.{s.cost_inr_crore_per_day} cr/day "
              f"(95%: Rs.{s.cost_inr_crore_per_day_p95} cr/day)")
        print(f"      {s.reasoning}")
        print(f"      caveat: {s.caveat}")

    if r.procurement:
        p = r.procurement
        print(f"\n[3] Procurement — refinery={p.refinery} max_risk={p.max_risk}")
        for o in p.options:
            flag = "✓" if o.viable else "✗"
            eta = f"{o.eta_days:.0f}d" if o.eta_days is not None else "n/a"
            print(f"      {flag} #{o.rank} {o.supplier:<16} grade={o.grade or '-':<6} "
                  f"ETA={eta:<5} +${o.cost_delta_usd_per_bbl}/bbl  "
                  f"risk={o.path_risk if o.path_risk is not None else '-'}"
                  + ("" if o.viable else f"  ({o.blocked_reason})"))
        print(f"      >> {p.policymaker_summary}")

    if r.reserve:
        rv = r.reserve
        print(f"\n[4] Strategic Reserve — gap {rv.daily_gap_kbd} kb/d, "
              f"buffer {rv.buffer_days}d vs reroute {rv.replenishment_window_days}d")
        print(f"      {rv.reasoning}")

    if r.reroute:
        rr = r.reroute
        path = " -> ".join(n.id for n in rr.active_path) or "none"
        print(f"\n[5] Digital Twin — reroute: {path}")
        print(f"      blocked: {', '.join(rr.blocked_chokepoints) or 'none'}  "
              f"({len(rr.waypoints)} map waypoints)")
    print()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corridor", default="Strait of Hormuz")
    ap.add_argument("--refinery", default=config.DEFAULT_REFINERY)
    ap.add_argument("--json", action="store_true", help="print full PipelineResult JSON")
    ap.add_argument("--stream", action="store_true", help="print each agent step as it completes")
    args = ap.parse_args()

    orch = Orchestrator()

    if args.stream:
        for step_name, slice_obj in orch.iter_steps(args.corridor, args.refinery):
            payload = slice_obj.model_dump(mode="json") if slice_obj is not None else None
            print(f"\n### {step_name}")
            print(json.dumps(payload, indent=2, default=str))
        return

    result = orch.run(args.corridor, args.refinery)
    if args.json:
        print(result.model_dump_json(indent=2))
    else:
        _print_human(result)


if __name__ == "__main__":
    main()
