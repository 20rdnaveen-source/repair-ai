"""Circuit graph: components wired to named nodes. Pure data, no AI.

The graph is the single source of truth for connectivity. Vision, manual entry
and netlists all produce a CircuitGraph; topology and the simulator read it.
"""
import json

from .components import Component, GraphError


class CircuitGraph:
    def __init__(self, name="circuit"):
        self.name = name
        self.components = {}          # name -> Component, in insertion order
        self.ambiguities = []         # connections we could not decide (e.g. crossing wires)

    # ---- building -------------------------------------------------------
    def add(self, comp):
        if comp.name.upper() in {n.upper() for n in self.components}:
            raise GraphError(f"duplicate component name {comp.name}")
        self.components[comp.name] = comp
        return comp

    def add_component(self, name, kind, nodes, value=None, confidence=1.0, **params):
        return self.add(Component(name, kind, tuple(nodes), value, params, confidence))

    def remove(self, name):
        found = next((n for n in self.components if n.upper() == name.upper()), None)
        if found is None:
            raise GraphError(f"no component {name}")
        del self.components[found]

    def mark_ambiguous(self, kind, items, note=""):
        """Record something the graph could not decide, e.g. two wires that cross
        but may not be connected. Crossing wires are never connected automatically."""
        self.ambiguities.append({"type": str(kind), "items": [str(i) for i in items], "note": str(note)})

    # ---- queries --------------------------------------------------------
    @property
    def nodes(self):
        return sorted({n for c in self.components.values() for n in c.nodes})

    def attachments(self, node):
        """[(component name, terminal name)] touching this node."""
        node = node.upper() if node != "0" else "GND"
        return [(c.name, t) for c in self.components.values() for t, n in c.terminals.items() if n == node]

    def check(self):
        """Structural problems that make the graph unusable for simulation."""
        issues = []
        if not any(c.kind == "supply" for c in self.components.values()):
            issues.append("no voltage source")
        if "GND" not in self.nodes:
            issues.append("nothing is connected to GND")
        parent = {n: n for n in self.nodes}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        for c in self.components.values():
            for n in c.nodes[1:]:
                parent[find(n)] = find(c.nodes[0])
        if len({find(n) for n in parent}) > 1:
            issues.append("circuit is in separate, unconnected pieces")
        return issues

    # ---- JSON-safe serialisation ---------------------------------------
    def to_dict(self):
        return {"name": self.name, "nodes": self.nodes,
                "components": [c.to_dict() for c in self.components.values()],
                "ambiguities": [dict(a, items=list(a["items"])) for a in self.ambiguities]}

    @classmethod
    def from_dict(cls, d):
        g = cls(d.get("name", "circuit"))
        for cd in d.get("components", []):
            g.add(Component.from_dict(cd))
        for a in d.get("ambiguities", []):
            g.mark_ambiguous(a.get("type", "unknown"), a.get("items", []), a.get("note", ""))
        return g

    def to_json(self, **kw):
        return json.dumps(self.to_dict(), **kw)

    @classmethod
    def from_json(cls, text):
        return cls.from_dict(json.loads(text))

    # ---- bridge to the existing simulator / netlist ---------------------
    def to_sim_components(self):
        """Component dicts in exactly the format repair_ai.sim / diagnose expect."""
        from ..circuits import _bjt, _diode, _led, _r, _v
        from ..sim import SHORT
        out = []
        for c in self.components.values():
            a = c.nodes
            if c.kind == "resistor":
                out.append(_r(c.name, a[0], a[1], c.value))
            elif c.kind == "wire":
                out.append(_r(c.name, a[0], a[1], SHORT, "wire"))
            elif c.kind == "supply":
                out.append(_v(c.name, a[0], a[1], c.value))
            elif c.kind == "led":
                d = _led(c.name, a[0], a[1])
                if "vf" in c.params:
                    d["vf"] = c.params["vf"]
                out.append(d)
            elif c.kind == "diode":
                out.append(_diode(c.name, a[0], a[1], c.params.get("vf", 0.7)))
            else:
                out.append(_bjt(c.name, a[0], a[1], a[2], c.params.get("beta", 100)))
        return out

    @classmethod
    def from_sim_components(cls, comps, name="circuit"):
        """Build a graph from the simulator's component dicts (healthy circuits)."""
        g = cls(name)
        for d in comps:
            kind, params = d["kind"], {}
            if kind in ("led", "diode") and "vf" in d:
                params["vf"] = d["vf"]
            if kind == "bjt":
                params["beta"] = d.get("beta", 100)
            value = d["value"] if kind in ("resistor", "supply") else None
            g.add(Component(d["name"], kind, tuple(d["n"]), value, params))
        return g

    @classmethod
    def from_netlist_text(cls, text, name="circuit"):
        """Parse the project's text netlist (repair_ai.netlist syntax) into a graph."""
        from ..netlist import parse
        return cls.from_sim_components(parse(text), name)
