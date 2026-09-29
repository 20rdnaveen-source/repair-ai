"""Graph -> text netlist -> simulator / diagnosis (Phase 3).

The graph is turned into the project's own netlist text and parsed by the
existing repair_ai.netlist parser, so a graph obeys exactly the same limits as a
hand-typed netlist (max parts, max voltage). Nothing here guesses: a graph the
netlist cannot represent exactly is rejected with a clear message.
"""
from .. import netlist as _netlist
from ..circuits import CIRCUITS
from ..diagnose import diagnose, predict
from .components import GraphError
from .graph import CircuitGraph
from .topology import analyze

_PRESETS = frozenset(k for k in CIRCUITS if k != "custom")     # never overwritten
_PREFIX = {"resistor": "R", "supply": "V", "led": "D", "diode": "D", "bjt": "Q", "wire": "JW"}
_DIODE_VF, _BJT_BETA = 0.7, 100


def _num(v, what):
    """Write a number the netlist parser reads back to exactly the same value."""
    for mult, suffix in ((1e6, "M"), (1e3, "k")):
        if v >= mult:
            s = f"{v / mult:.9f}".rstrip("0").rstrip(".")
            if float(s) * mult == v:
                return s + suffix
    s = f"{v:.9f}".rstrip("0").rstrip(".")
    if not s or float(s) != v:
        raise GraphError(f"{what} {v!r} cannot be written as a netlist number")
    return s


def to_netlist_text(graph):
    """Netlist text for a graph. Raises GraphError if the graph is not representable."""
    lines = []
    for c in graph.components.values():
        if c.name[0].upper() not in _PREFIX[c.kind]:
            raise GraphError(f"{c.name}: a {c.kind} must have a name starting with "
                             f"{' or '.join(_PREFIX[c.kind])} (for example {_PREFIX[c.kind][0]}1)")
        a = " ".join(c.nodes)
        if c.kind == "resistor":
            lines.append(f"{c.name} {a} {_num(c.value, c.name + ' resistance')}")
        elif c.kind == "supply":
            if c.value <= 0:
                raise GraphError(f"{c.name}: a 0 V supply cannot be written as a netlist (use a value above 0)")
            lines.append(f"{c.name} {a} {_num(c.value, c.name + ' voltage')}")
        elif c.kind == "wire":
            lines.append(f"{c.name} {a}")
        elif c.kind == "led":
            if "vf" in c.params:
                raise GraphError(f"{c.name}: the netlist cannot store a custom LED forward voltage")
            lines.append(f"{c.name} {a} LED")
        elif c.kind == "diode":
            if c.params.get("vf", _DIODE_VF) != _DIODE_VF:
                raise GraphError(f"{c.name}: the netlist cannot store a custom diode forward voltage")
            lines.append(f"{c.name} {a} DIODE")
        else:
            beta = c.params.get("beta", _BJT_BETA)
            lines.append(f"{c.name} {a} NPN" + ("" if beta == _BJT_BETA else " " + _num(beta, c.name + " beta")))
    return "\n".join(lines) + "\n"


def blocking_issues(graph):
    """Problems a person must resolve before this graph is used for diagnosis."""
    issues = list(graph.check())
    issues += [f"unresolved {a['type']}: {', '.join(a['items'])}" + (f" ({a['note']})" if a["note"] else "")
               for a in graph.ambiguities]
    issues += [a["note"] for a in analyze(graph).ambiguities if a["type"] == "low_confidence"]
    return issues


def register_graph(graph, circuit_id="graph", title=None, force=False):
    """Make the graph available to diagnose() under circuit_id. Returns the id.

    force=True skips the review check (blocking_issues) once a person has confirmed the graph.
    """
    if circuit_id in _PRESETS or circuit_id == "custom":
        raise GraphError(f"circuit id {circuit_id!r} is reserved; choose another")
    issues = [] if force else blocking_issues(graph)
    if issues:
        raise GraphError("graph needs review before diagnosis: " + "; ".join(issues))
    comps = _netlist.parse(to_netlist_text(graph))             # applies the netlist's own limits
    for parsed, original in zip(comps, graph.components):
        parsed["name"] = original                              # the parser upper-cases names; keep the graph's
    probes = sorted({n for c in comps for n in c["n"]} - {"GND"})
    CIRCUITS[circuit_id] = {"title": title or graph.name, "probes": probes, "comps": comps}
    return circuit_id


def expected_readings(graph):
    """Physics prediction for a healthy graph: {node: volts, "I": amps, "LED": "on"/"off"}."""
    comps = graph.to_sim_components()
    probes = sorted({n for c in comps for n in c["n"]} - {"GND"})
    out = predict(comps, probes, any(c["kind"] == "led" for c in comps))
    return {k: (v if isinstance(v, str) else float(v)) for k, v in out.items()}


def diagnose_graph(graph, readings, checks=None, circuit_id="graph", force=False):
    """Register the graph and run the existing diagnosis engine on it."""
    return diagnose(register_graph(graph, circuit_id, force=force), readings, checks)
