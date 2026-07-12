"""Unit tests for the knowledge graph (no network, no DB — fake risks)."""
from api import graph as kg


def live_graph(risks):
    g = kg.get_graph()
    kg.overlay_risk(g, {c: {"risk": r, "events": 100} for c, r in risks.items()})
    return g


def test_graph_builds():
    g = kg.get_graph()
    assert g.number_of_nodes() > 25 and g.number_of_edges() > 40
    types = {d["type"] for _, d in g.nodes(data=True)}
    assert types == {"supplier", "export_port", "chokepoint", "import_port", "refinery"}


def test_hormuz_crisis_blocks_iraq_but_not_uae():
    g = live_graph({"Strait of Hormuz": 0.9})
    opts = {o["supplier"]: o for o in kg.alternatives(g, "Jamnagar (RIL)", max_risk=0.5)}

    assert not opts["Iraq"]["viable"]          # no Hormuz bypass exists
    assert not opts["Kuwait"]["viable"]
    assert opts["UAE"]["viable"]               # Fujairah pipeline bypass
    assert "Fujairah" in opts["UAE"]["safest_viable_route"]["path"]
    assert opts["Saudi Arabia"]["viable"]      # Yanbu / Red Sea bypass
    assert "Yanbu" in opts["Saudi Arabia"]["safest_viable_route"]["path"]


def test_calm_world_everyone_viable():
    g = live_graph({})
    opts = kg.alternatives(g, "Jamnagar (RIL)", max_risk=0.5)
    assert all(o["viable"] for o in opts)
    # calm ranking is by ETA: a Gulf supplier must be first
    assert opts[0]["supplier"] in {"UAE", "Saudi Arabia", "Iraq", "Kuwait"}


def test_path_risk_combines_chokepoints():
    g = live_graph({"Suez Canal": 0.5, "Red Sea": 0.5})
    routes = kg.routes(g, "Russia", "Vadinar (Nayara)")
    suez_route = next(r for r in routes if "Suez Canal" in r["path"])
    # 1 - (1-0.5)(1-0.5) = 0.75
    assert abs(suez_route["path_risk"] - 0.75) < 0.001


def test_russia_reaches_east_coast_via_pacific():
    g = live_graph({"Strait of Hormuz": 0.9, "Red Sea": 0.9})
    opts = {o["supplier"]: o for o in kg.alternatives(g, "Paradip (IOCL)", max_risk=0.5)}
    assert opts["Russia"]["viable"]
    assert "Strait of Malacca" in opts["Russia"]["safest_viable_route"]["path"]


def test_as_dict_is_json_shaped():
    g = live_graph({"Strait of Hormuz": 0.7})
    d = kg.as_dict(g)
    hormuz = next(n for n in d["nodes"] if n["id"] == "Strait of Hormuz")
    assert hormuz["risk"] == 0.7 and hormuz["risk_events"] == 100
