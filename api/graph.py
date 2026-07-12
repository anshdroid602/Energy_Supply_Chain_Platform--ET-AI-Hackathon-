"""Knowledge graph over India's crude supply chain.

Structure (static, from graph_seed.json — real ports/pipelines/chokepoints):

    supplier -> export_port -> chokepoint(s) -> import_port -> refinery

Risk (live, from Postgres at query time): each chokepoint node maps to a
corridor in structured_events via its `risk_corridor` attribute and gets the
same confidence- and recency-weighted risk score the /corridors/{c}/risk-score
endpoint computes — so the graph's danger levels move with the news.

The graph is READ-ONLY and DERIVED: rebuilt from the seed on first use,
risk re-overlaid per request. It is never written to and never synced —
Postgres stays the single source of truth.

Why this exists: "which suppliers can still reach which refinery, avoiding
the risky chokepoints, and how long does each option take" is a path query.
This module answers it; the Procurement agent and the digital-twin map both
consume the answers.
"""
import json
import os

import networkx as nx

SEED_PATH = os.path.join(os.path.dirname(__file__), "graph_seed.json")

# Mirrors the /corridors/{corridor}/risk-score formula (window 30d, half-life
# 7d) in one SQL aggregate:
#   risk = sum(sev/10 * conf * 0.5^(age/half_life)) / sum(conf * 0.5^(age/half_life))
CORRIDOR_RISK_SQL = """
SELECT corridor_affected,
       SUM(severity_score / 10.0 * confidence * POWER(0.5, GREATEST(CURRENT_DATE - event_date, 0) / %s))
     / NULLIF(SUM(confidence * POWER(0.5, GREATEST(CURRENT_DATE - event_date, 0) / %s)), 0) AS risk,
       COUNT(*) AS n_events
FROM structured_events
WHERE event_date >= (CURRENT_DATE - %s * INTERVAL '1 day')
GROUP BY corridor_affected;
"""

_G = None


def get_graph():
    """Build once per process; node risk attributes are refreshed per request."""
    global _G
    if _G is None:
        with open(SEED_PATH) as f:
            seed = json.load(f)
        g = nx.DiGraph()
        for n in seed["nodes"]:
            g.add_node(n["id"], **{k: v for k, v in n.items() if k != "id"})
        for e in seed["edges"]:
            g.add_edge(e["from"], e["to"],
                       days=e.get("days", 0), note=e.get("note"))
        _G = g
    return _G


def corridor_risks(conn, window_days=30, half_life_days=7.0):
    """corridor -> {'risk': 0-1, 'events': n} for corridors with events."""
    with conn.cursor() as cur:
        cur.execute(CORRIDOR_RISK_SQL, (half_life_days, half_life_days, window_days))
        return {row[0]: {"risk": round(float(row[1]), 3), "events": int(row[2])}
                for row in cur.fetchall() if row[1] is not None}


def overlay_risk(g, risks):
    """Write the live corridor risk (and how many events back it) onto each
    chokepoint node. risk_events lets consumers judge evidence strength —
    a 0.9 from 3 events is not the same as a 0.9 from 300."""
    for _, data in g.nodes(data=True):
        if data.get("type") == "chokepoint":
            corridor = data.get("risk_corridor")
            entry = risks.get(corridor) if corridor else None
            data["risk"] = entry["risk"] if entry else data.get("base_risk", 0.0)
            data["risk_events"] = entry["events"] if entry else 0


def path_metrics(g, path):
    """ETA + risk breakdown for one route. Path risk is the probability at
    least one chokepoint on the way disrupts: 1 - prod(1 - risk_i)."""
    eta = sum(g[u][v].get("days", 0) for u, v in zip(path, path[1:]))
    chokepoints = [{"id": n, "risk": round(g.nodes[n].get("risk", 0.0), 3)}
                   for n in path if g.nodes[n].get("type") == "chokepoint"]
    survive = 1.0
    for c in chokepoints:
        survive *= (1.0 - c["risk"])
    return {
        "path": path,
        "eta_days": round(eta, 1),
        "chokepoints": chokepoints,
        "path_risk": round(1.0 - survive, 3),
    }


def routes(g, supplier, refinery, max_hops=7):
    """Every distinct way supplier's crude can reach the refinery, with
    metrics, fastest first."""
    if supplier not in g or refinery not in g:
        return None
    found = [path_metrics(g, p)
             for p in nx.all_simple_paths(g, supplier, refinery, cutoff=max_hops)]
    return sorted(found, key=lambda r: r["eta_days"])


def alternatives(g, refinery, max_risk=0.5):
    """The Procurement agent's core question: for each supplier, what is the
    fastest route and the fastest ACCEPTABLY-SAFE route (every chokepoint
    below max_risk) to this refinery — plus grade fit and import share.

    Ranked: viable suppliers first (safe route exists + grade fits), then by
    the safe route's ETA. All inputs to the ranking are returned so an agent
    (or a judge) can audit it.
    """
    accepts = set(g.nodes[refinery].get("accepts", []))
    suppliers = [n for n, d in g.nodes(data=True) if d.get("type") == "supplier"]

    results = []
    for s in suppliers:
        all_routes = routes(g, s, refinery) or []
        if not all_routes:
            continue
        safe = [r for r in all_routes
                if all(c["risk"] < max_risk for c in r["chokepoints"])]
        node = g.nodes[s]
        grade_fit = node.get("grade") in accepts
        results.append({
            "supplier": s,
            "grade": node.get("grade"),
            "grade_name": node.get("grade_name"),
            "grade_fit": grade_fit,
            "import_share_pct": node.get("share_pct"),
            "fastest_route": all_routes[0],
            "safest_viable_route": safe[0] if safe else None,
            "viable": bool(safe) and grade_fit,
            "blocked_reason": None if safe else
                f"every route crosses a chokepoint at/above risk {max_risk}",
        })

    results.sort(key=lambda r: (not r["viable"],
                                r["safest_viable_route"]["eta_days"]
                                if r["safest_viable_route"] else 999))
    return results


def as_dict(g):
    """Whole graph as JSON-friendly nodes+edges (with live risk already
    overlaid) — what the Leaflet map renders directly."""
    return {
        "nodes": [{"id": n, **d} for n, d in g.nodes(data=True)],
        "edges": [{"from": u, "to": v, **d} for u, v, d in g.edges(data=True)],
    }
