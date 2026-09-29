"""Component model for the circuit graph.

A Component is one electrical part with named terminals wired to nodes.
Kinds match the existing simulator ("resistor", "wire", "led", "diode",
"supply", "bjt") so a graph converts to the simulator's dicts without loss.
"""
import math
import re
from dataclasses import dataclass, field


class GraphError(ValueError):
    """Bad component or graph input."""


TERMINALS = {
    "resistor": ("a", "b"),
    "wire": ("a", "b"),
    "led": ("anode", "cathode"),
    "diode": ("anode", "cathode"),
    "supply": ("plus", "minus"),
    "bjt": ("base", "collector", "emitter"),        # NPN, same order as the netlist "Q" line
}
POLARIZED = {"led", "diode", "supply"}              # terminal order matters
LOADS = {"resistor", "led", "diode"}                # two-terminal parts eligible for series/parallel
ALLOWED_PARAMS = {"led": {"vf"}, "diode": {"vf"}, "bjt": {"beta"}}

_NODE = re.compile(r"[A-Z0-9_]{1,8}")
_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,15}")
RESERVED_NODES = {"I", "LED"}                       # used as reading keys by the diagnosis engine


def norm_node(tok):
    """Normalise a node name (same rules as the netlist parser)."""
    if not isinstance(tok, str):
        raise GraphError(f"node name must be text, got {tok!r}")
    n = tok.strip().upper()
    if n in ("GND", "0"):
        return "GND"
    if not _NODE.fullmatch(n) or n in RESERVED_NODES:
        raise GraphError(f"bad node name {tok!r} (letters/digits/_, max 8, not 'I' or 'LED')")
    return n


def _number(x, what, minimum_exclusive=None, minimum=None):
    try:
        v = float(x)
    except (TypeError, ValueError):
        raise GraphError(f"{what} must be a number, got {x!r}")
    if not math.isfinite(v):
        raise GraphError(f"{what} must be finite")
    if minimum_exclusive is not None and v <= minimum_exclusive:
        raise GraphError(f"{what} must be greater than {minimum_exclusive:g}")
    if minimum is not None and v < minimum:
        raise GraphError(f"{what} must be at least {minimum:g}")
    return v


@dataclass
class Component:
    name: str
    kind: str
    nodes: tuple
    value: float = None                  # resistor: ohms, supply: volts, others: None
    params: dict = field(default_factory=dict)      # led/diode: vf, bjt: beta
    confidence: float = 1.0              # detection confidence (1.0 = user-entered / certain)
    warnings: list = field(default_factory=list)

    def __post_init__(self):
        self.name = str(self.name).strip()          # case is kept: presets use names like 'Vs'
        if not _NAME.fullmatch(self.name):
            raise GraphError(f"bad component name {self.name!r}")
        self.kind = str(self.kind).strip().lower()
        if self.kind not in TERMINALS:
            raise GraphError(f"unknown kind {self.kind!r} (supported: {', '.join(TERMINALS)})")
        self.nodes = tuple(norm_node(n) for n in self.nodes)
        if len(self.nodes) != len(TERMINALS[self.kind]):
            raise GraphError(f"{self.name}: a {self.kind} needs {len(TERMINALS[self.kind])} nodes, got {len(self.nodes)}")
        if self.kind == "resistor":
            self.value = _number(self.value, f"{self.name} resistance", minimum_exclusive=0)
        elif self.kind == "supply":
            self.value = _number(self.value, f"{self.name} voltage", minimum=0)
        elif self.value is not None:
            raise GraphError(f"{self.name}: a {self.kind} has no value")
        bad = set(self.params) - ALLOWED_PARAMS.get(self.kind, set())
        if bad:
            raise GraphError(f"{self.name}: unsupported parameter(s) {sorted(bad)} for a {self.kind}")
        self.params = {k: _number(v, f"{self.name} {k}", minimum_exclusive=0) for k, v in self.params.items()}
        self.confidence = _number(self.confidence, f"{self.name} confidence", minimum=0)
        if self.confidence > 1:
            raise GraphError(f"{self.name}: confidence must be between 0 and 1")
        self.warnings = [str(w) for w in self.warnings]

    @property
    def terminals(self):
        """{terminal name: node}"""
        return dict(zip(TERMINALS[self.kind], self.nodes))

    def to_dict(self):
        return {"name": self.name, "kind": self.kind, "nodes": list(self.nodes),
                "terminals": self.terminals, "value": self.value, "params": dict(self.params),
                "confidence": self.confidence, "warnings": list(self.warnings)}

    @classmethod
    def from_dict(cls, d):
        try:
            return cls(d["name"], d["kind"], tuple(d["nodes"]), d.get("value"), dict(d.get("params") or {}),
                       d.get("confidence", 1.0), list(d.get("warnings") or []))
        except KeyError as e:
            raise GraphError(f"component is missing field {e}")
