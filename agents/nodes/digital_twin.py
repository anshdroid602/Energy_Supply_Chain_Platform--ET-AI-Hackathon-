"""Agent 5 — Supply-Chain Digital Twin (demo layer).

Draws the recommended reroute: supplier -> export port -> chokepoint(s) ->
Indian port -> refinery, using the real node coordinates from the graph, plus
a few hardcoded sea-lane waypoints so long ocean legs bow through open water
instead of drawing a straight line across land. Blocked (high-risk)
chokepoints are returned so the map can cross them out. Pure geometry, no LLM.
"""
from __future__ import annotations

from ..schemas import MapNode, RerouteMap

# A few mid-ocean waypoints so a straight polyline between two graph nodes
# doesn't cut across land. Keyed on an (a, b) ordered pair of node ids; the
# listed [lat, lon] points are inserted between them. Sea lanes, not roads.
SEA_LANES = {
    ("Cape of Good Hope", "Sikka/Vadinar (Gujarat)"): [[-15.0, 55.0], [10.0, 62.0]],
    ("Cape of Good Hope", "Paradip Port"): [[-10.0, 60.0], [5.0, 80.0]],
    ("Bonny Terminal (Nigeria)", "Cape of Good Hope"): [[-15.0, 5.0]],
    ("US Gulf (Houston)", "Cape of Good Hope"): [[0.0, -25.0], [-25.0, 0.0]],
}


def _waypoints_for_path(g, path):
    """Node coords with sea-lane waypoints spliced into long ocean legs."""
    wp = []
    for a, b in zip(path, path[1:]):
        da = g.nodes[a]
        if da.get("lat") is not None and da.get("lon") is not None:
            wp.append([da["lat"], da["lon"]])
        wp.extend(SEA_LANES.get((a, b), []))
    last = g.nodes[path[-1]]
    if last.get("lat") is not None and last.get("lon") is not None:
        wp.append([last["lat"], last["lon"]])
    return wp


def make_twin_node(ds, llm, params):
    max_risk = params.get("max_risk", 0.5)

    def node(state):
        refinery = state["refinery"]
        proc = state.get("procurement")
        g = ds.live_graph()

        blocked = [n for n, d in g.nodes(data=True)
                   if d.get("type") == "chokepoint" and d.get("risk", 0.0) >= max_risk]

        top = proc.top_pick if proc else None
        active_nodes, waypoints = [], []
        if top and top.path:
            for nid in top.path:
                d = g.nodes[nid]
                if d.get("lat") is not None and d.get("lon") is not None:
                    active_nodes.append(MapNode(
                        id=nid, type=d.get("type", "unknown"),
                        lat=d["lat"], lon=d["lon"], risk=d.get("risk"),
                    ))
            waypoints = _waypoints_for_path(g, top.path)

        if top:
            avoided = ", ".join(blocked) if blocked else "no blocked chokepoint"
            note = f"Reroute crude from {top.supplier} to {refinery}, avoiding {avoided}."
        else:
            note = f"No viable reroute to {refinery} under the current risk threshold."

        return {"reroute": RerouteMap(
            refinery=refinery,
            from_supplier=top.supplier if top else None,
            blocked_chokepoints=blocked,
            active_path=active_nodes,
            waypoints=waypoints,
            note=note,
        )}

    return node
