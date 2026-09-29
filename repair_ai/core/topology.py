"""Series / parallel / branch detection from graph connectivity only.

No AI and no guessing. Rules:
  * Wires are collapsed first: nodes joined by a wire are one electrical net.
  * Series:   two load parts (resistor/LED/diode) meet at a net that has exactly
              two part terminals attached, so nothing else branches off there.
  * Parallel: load parts whose terminals sit on the same two nets.
  * Branch:   a net with three or more part terminals attached.
Anything undecidable is reported as an ambiguity instead of being guessed.
"""
from dataclasses import dataclass, field

from .components import LOADS, POLARIZED


@dataclass
class Topology:
    net_of: dict = field(default_factory=dict)      # node -> net name (after collapsing wires)
    series: list = field(default_factory=list)      # [[part names in order]]
    parallel: list = field(default_factory=list)    # [[part names]]
    branches: list = field(default_factory=list)    # [{"net": ..., "components": [...]}]
    ambiguities: list = field(default_factory=list)   # [{"type", "items", "note"}]

    @property
    def has_ambiguity(self):
        return bool(self.ambiguities)

    def relationships(self):
        rel = [{"type": "series", "components": s} for s in self.series]
        rel += [{"type": "parallel", "components": p} for p in self.parallel]
        rel += [{"type": "branch", "net": b["net"], "components": b["components"]} for b in self.branches]
        return rel

    def to_dict(self):
        return {"nets": dict(self.net_of), "series": [list(s) for s in self.series],
                "parallel": [list(p) for p in self.parallel],
                "branches": [{"net": b["net"], "components": list(b["components"])} for b in self.branches],
                "relationships": self.relationships(),
                "ambiguities": [dict(a, items=list(a["items"])) for a in self.ambiguities]}


def _collapse_wires(graph):
    parent = {n: n for n in graph.nodes}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for c in graph.components.values():
        if c.kind == "wire":
            parent[find(c.nodes[1])] = find(c.nodes[0])
    groups = {}
    for n in parent:
        groups.setdefault(find(n), []).append(n)
    net_of = {}
    for members in groups.values():
        name = "GND" if "GND" in members else min(members)
        for m in members:
            net_of[m] = name
    return net_of


def analyze(graph, low_confidence=0.6):
    order = {name: i for i, name in enumerate(graph.components)}
    net_of = _collapse_wires(graph)
    topo = Topology(net_of=net_of)
    amb = topo.ambiguities

    active = {}                                     # non-wire parts with their nets
    for c in graph.components.values():
        if c.kind == "wire":
            continue
        nets = tuple(net_of[n] for n in c.nodes)
        if len(nets) == 2 and nets[0] == nets[1]:
            amb.append({"type": "shorted_by_wire", "items": [c.name],
                        "note": f"both ends of {c.name} are joined by wire(s), so it carries no current"})
            continue
        active[c.name] = (c, nets)

    at = {}                                         # net -> [part names] (one entry per terminal)
    for name, (c, nets) in active.items():
        for n in nets:
            at.setdefault(n, []).append(name)

    # ---- series: nets with exactly two terminals attached, both load parts
    link = {}                                       # part -> set of neighbours in a chain
    for net, parts in at.items():
        if len(parts) == 2 and parts[0] != parts[1] and all(active[p][0].kind in LOADS for p in parts):
            a, b = parts
            link.setdefault(a, set()).add(b)
            link.setdefault(b, set()).add(a)
    seen = set()
    for start in sorted(link, key=order.get):
        if start in seen:
            continue
        group, stack = set(), [start]
        while stack:
            p = stack.pop()
            if p not in group:
                group.add(p)
                stack.extend(link[p])
        seen |= group
        ends = sorted((p for p in group if len(link[p]) < 2), key=order.get)
        chain, cur = [], (ends[0] if ends else min(group, key=order.get))
        while cur is not None:
            chain.append(cur)
            cur = next((q for q in sorted(link[cur], key=order.get) if q not in chain), None)
        topo.series.append(chain)
    topo.series.sort(key=lambda s: order[s[0]])

    # ---- parallel: load parts on the same pair of nets
    pairs = {}
    for name, (c, nets) in active.items():
        if c.kind in LOADS:
            pairs.setdefault(frozenset(nets), []).append(name)
    for names in pairs.values():
        if len(names) < 2:
            continue
        names.sort(key=order.get)
        topo.parallel.append(names)
        polar = {active[n][1][0] for n in names if active[n][0].kind in POLARIZED}
        if len(polar) > 1:
            amb.append({"type": "antiparallel", "items": list(names),
                        "note": "polarised parts face opposite ways between the same nets; check orientation"})
    topo.parallel.sort(key=lambda p: order[p[0]])

    # ---- branches and dangling nets
    for net, parts in sorted(at.items()):
        uniq = sorted(set(parts), key=order.get)
        if len(parts) >= 3:
            topo.branches.append({"net": net, "components": uniq})
        elif len(parts) == 1:
            amb.append({"type": "dangling", "items": [net, parts[0]],
                        "note": f"net {net} touches only {parts[0]}: open connection or missing part"})

    # ---- uncertain detections and graph-level ambiguities (e.g. crossing wires)
    for c in graph.components.values():
        if c.confidence < low_confidence:
            amb.append({"type": "low_confidence", "items": [c.name],
                        "note": f"{c.name} detected with confidence {c.confidence:.2f}; please confirm"})
    for a in graph.ambiguities:
        amb.append(dict(a, items=list(a["items"])))
    return topo
