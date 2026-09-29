"""Tests for the circuit graph and topology (Phases 1-2). Run: python tests/test_core.py"""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from repair_ai.circuits import CIRCUITS, build
from repair_ai.core.components import Component, GraphError
from repair_ai.core.graph import CircuitGraph
from repair_ai.core.topology import analyze
from repair_ai.diagnose import diagnose
from repair_ai.sim import solve


def raises(fn, *a, **kw):
    try:
        fn(*a, **kw)
    except GraphError:
        return True
    return False


def led_graph():
    g = CircuitGraph("demo")
    g.add_component("Vs", "supply", ["TP0", "GND"], 5)
    g.add_component("J1", "wire", ["TP0", "TP1"])
    g.add_component("R1", "resistor", ["TP1", "TP2"], 330)
    g.add_component("D1", "led", ["TP2", "GND"])
    return g


# ---- graph construction ---------------------------------------------------
def test_graph_construction():
    g = led_graph()
    assert g.nodes == ["GND", "TP0", "TP1", "TP2"]
    assert g.components["R1"].terminals == {"a": "TP1", "b": "TP2"}
    assert g.components["D1"].terminals == {"anode": "TP2", "cathode": "GND"}
    assert sorted(g.attachments("TP2")) == [("D1", "anode"), ("R1", "b")]
    assert g.check() == []
    g.add_component("R9", "resistor", ["X", "Y"], 100)      # a piece that touches nothing else
    assert "circuit is in separate, unconnected pieces" in g.check()


def test_graph_rejects_bad_input():
    g = led_graph()
    assert raises(g.add_component, "R1", "resistor", ["A", "B"], 100)          # duplicate name
    assert raises(g.add_component, "R9", "resistor", ["A"], 100)               # wrong node count
    assert raises(g.add_component, "R9", "resistor", ["A", "B"], -5)           # bad value
    assert raises(g.add_component, "R9", "resistor", ["A", "B"], float("nan"))
    assert raises(g.add_component, "X1", "capacitor", ["A", "B"], 1)           # unsupported kind
    assert raises(g.add_component, "R9", "resistor", ["I", "B"], 100)          # reserved node name
    assert raises(g.add_component, "D9", "led", ["A", "B"], 5)                 # led has no value
    assert raises(g.add_component, "R9", "resistor", ["A", "B"], 100, confidence=1.5)
    assert raises(g.add_component, "Q9", "bjt", ["A", "B", "C"], None, gain=3) # unsupported parameter
    assert raises(g.remove, "NOPE")
    assert CircuitGraph().check() == ["no voltage source", "nothing is connected to GND"]


def test_json_roundtrip_is_json_safe():
    g = led_graph()
    g.mark_ambiguous("crossing_wires", ["W1", "W2"], "cross at (10, 20)")
    text = g.to_json()
    d = json.loads(text)                                  # must be plain JSON
    assert d["components"][2]["terminals"] == {"a": "TP1", "b": "TP2"}
    g2 = CircuitGraph.from_json(text)
    assert g2.to_dict() == g.to_dict()


# ---- bridge to the existing simulator (nothing may change for old circuits) --
def test_all_builtin_circuits_roundtrip_and_simulate_identically():
    for cid, spec in CIRCUITS.items():
        g = CircuitGraph.from_sim_components(build(cid), cid)
        assert g.to_sim_components() == build(cid), cid
        assert solve(g.to_sim_components()) == solve(build(cid)), cid


def test_graph_to_physics_known_values():
    r = solve(led_graph().to_sim_components())
    assert abs(r["I"] - 0.00895) < 2e-4               # 5 V, 330 ohm, LED ~2 V -> about 9 mA
    assert 1.9 < r["V"]["TP2"] < 2.15 and r["led"]["D1"]


def test_netlist_text_to_graph_to_diagnosis_input():
    g = CircuitGraph.from_netlist_text("V1 TP0 GND 9\nJ1 TP0 TP1\nR1 TP1 TP2 4.7k\nR2 TP2 GND 3.3k")
    assert g.components["R1"].value == 4700 and g.components["J1"].kind == "wire"
    assert g.components["R2"].nodes == ("TP2", "GND")


# ---- topology --------------------------------------------------------------
def test_series_led_and_resistor():
    t = analyze(led_graph())
    assert t.series == [["R1", "D1"]] and t.parallel == [] and t.branches == []
    assert not t.has_ambiguity
    assert t.net_of["TP0"] == t.net_of["TP1"]             # wire collapsed into one net


def test_series_chain_is_ordered_along_the_path():
    g = CircuitGraph.from_netlist_text("V1 TP0 GND 9\nJ1 TP0 TP1\nR1 TP1 TP2 4.7k\nR2 TP2 TP3 2.2k\nR3 TP3 GND 3.3k")
    assert analyze(g).series == [["R1", "R2", "R3"]]
    g2 = CircuitGraph()                                   # same chain, parts added in scrambled order
    g2.add_component("V1", "supply", ["A", "GND"], 5)
    g2.add_component("R3", "resistor", ["C", "GND"], 100)
    g2.add_component("R1", "resistor", ["A", "B"], 100)
    g2.add_component("R2", "resistor", ["B", "C"], 100)
    assert sorted(analyze(g2).series[0]) == ["R1", "R2", "R3"] and len(analyze(g2).series[0]) == 3


def test_parallel_and_branch():
    t = analyze(CircuitGraph.from_sim_components(build("resistor_network")))
    assert t.parallel == [["R2", "R3"]]
    assert [b["net"] for b in t.branches] == ["GND", "TP2"]
    assert t.series == []                                 # R1 is NOT series: TP2 branches
    tp2 = next(b for b in t.branches if b["net"] == "TP2")
    assert tp2["components"] == ["R1", "R2", "R3"]


def test_branch_at_supply_fanout():
    t = analyze(CircuitGraph.from_sim_components(build("bjt_switch")))
    assert [b["net"] for b in t.branches] == ["TP0"] and t.series == [] and t.parallel == []


def test_wire_collapse_makes_parallel_across_different_node_names():
    g = CircuitGraph()
    g.add_component("V1", "supply", ["A", "GND"], 5)
    g.add_component("R1", "resistor", ["A", "B"], 100)
    g.add_component("R2", "resistor", ["A", "C"], 100)
    g.add_component("W1", "wire", ["B", "C"])              # joins B and C
    g.add_component("R3", "resistor", ["B", "GND"], 100)
    t = analyze(g)
    assert t.parallel == [["R1", "R2"]]
    assert t.series == [] and [b["net"] for b in t.branches] == ["A", "B"]


def test_ambiguous_crossing_wires_are_reported_not_connected():
    g = led_graph()
    g.mark_ambiguous("crossing_wires", ["W1", "W2"], "wires cross; connection unknown")
    t = analyze(g)
    assert t.has_ambiguity
    assert {"type": "crossing_wires", "items": ["W1", "W2"], "note": "wires cross; connection unknown"} in t.ambiguities
    assert t.series == [["R1", "D1"]]                      # graph is unchanged: no automatic connection


def test_other_ambiguities():
    g = CircuitGraph()
    g.add_component("V1", "supply", ["A", "GND"], 5)
    g.add_component("R1", "resistor", ["A", "B"], 100, confidence=0.4)     # low detection confidence
    g.add_component("R2", "resistor", ["B", "B2"], 100)
    g.add_component("W1", "wire", ["B", "B2"])                              # R2 shorted by wire
    g.add_component("D1", "led", ["B", "GND"])
    g.add_component("D2", "led", ["GND", "B"])                              # opposite polarity
    types = {a["type"] for a in analyze(g).ambiguities}
    assert {"low_confidence", "shorted_by_wire", "antiparallel"} <= types
    h = CircuitGraph()
    h.add_component("V1", "supply", ["A", "GND"], 5)
    h.add_component("R1", "resistor", ["A", "B"], 100)                      # B goes nowhere
    d = [a for a in analyze(h).ambiguities if a["type"] == "dangling"]
    assert d and d[0]["items"] == ["B", "R1"]


def test_topology_output_is_json_safe_and_has_relationships():
    d = analyze(led_graph()).to_dict()
    json.dumps(d)
    assert {"type": "series", "components": ["R1", "D1"]} in d["relationships"]


def test_existing_diagnosis_still_works_on_a_graph_circuit():
    from repair_ai.netlist import register
    cid = register("V1 TP0 GND 5\nJ1 TP0 TP1\nR1 TP1 TP2 330\nD1 TP2 GND LED")
    assert diagnose(cid, {"TP1": 5.0, "TP2": 2.04, "I": 0.009})["status"] == "no_fault"
    CIRCUITS.pop("custom", None)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"{len(tests)} core tests passed")
