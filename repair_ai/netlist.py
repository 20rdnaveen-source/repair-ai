"""Text netlist -> circuit. One component per line, '#' starts a comment.

    V1 TP0 GND 5           voltage source (+ node, - node, volts)     name starts with V
    J1 TP0 TP1             wire / solder joint                        name starts with J or W
    R1 TP1 TP2 330         resistor (values: 330, 4.7k, 1M)           name starts with R
    D1 TP2 GND LED         diode: anode, cathode, LED or DIODE        name starts with D
    Q1 TPB TPC GND NPN     NPN transistor: base, collector, emitter   name starts with Q  (optional beta)

Ground is GND (or 0). Every other node becomes a test point you can measure.
The supply current reading 'I' is the current out of the first V source.
"""
import re

from .circuits import CIRCUITS, SHORT, _bjt, _diode, _led, _r, _v

MAX_PARTS, MAX_VOLTS = 25, 50.0
_NUM = re.compile(r"^([0-9]*\.?[0-9]+)\s*([kKM]?)\s*(?:Ω|ohms?|V|v)?$")


class NetlistError(ValueError):
    pass


def _value(tok, ln, what):
    m = _NUM.match(tok)
    if not m:
        raise NetlistError(f"line {ln}: cannot read {what} '{tok}' (examples: 330, 4.7k, 1M)")
    v = float(m.group(1)) * {"": 1, "k": 1e3, "K": 1e3, "M": 1e6}[m.group(2)]
    if v <= 0:
        raise NetlistError(f"line {ln}: {what} must be greater than 0")
    return v


def _node(tok, ln):
    n = tok.upper()
    if n in ("GND", "0"):
        return "GND"
    if not re.fullmatch(r"[A-Z0-9_]{1,8}", n) or n in ("I", "LED"):
        raise NetlistError(f"line {ln}: bad node name '{tok}' (use letters/digits, max 8, not 'I' or 'LED')")
    return n


def parse(text):
    comps, names = [], set()
    for ln, raw in enumerate(text.splitlines(), 1):
        t = raw.split("#")[0].split()
        if not t:
            continue
        name, kind = t[0].upper(), t[0][0].upper()
        if name in names:
            raise NetlistError(f"line {ln}: duplicate component name {name}")
        names.add(name)
        need = {"V": 4, "R": 4, "J": 3, "W": 3, "D": 3, "Q": 4}.get(kind)
        if need is None:
            raise NetlistError(f"line {ln}: unknown component '{t[0]}' (supported: V, R, J/W, D, Q)")
        if len(t) < need + (0 if kind not in "VR" else 0):
            raise NetlistError(f"line {ln}: {name} needs more fields")
        if kind == "V":
            v = _value(t[3], ln, "voltage")
            if v > MAX_VOLTS:
                raise NetlistError(f"line {ln}: low-voltage DC only (max {MAX_VOLTS:g} V)")
            comps.append(_v(name, _node(t[1], ln), _node(t[2], ln), v))
        elif kind == "R":
            comps.append(_r(name, _node(t[1], ln), _node(t[2], ln), _value(t[3], ln, "resistance")))
        elif kind in "JW":
            comps.append(_r(name, _node(t[1], ln), _node(t[2], ln), SHORT, "wire"))
        elif kind == "D":
            a, k = _node(t[1], ln), _node(t[2], ln)
            comps.append(_led(name, a, k) if len(t) > 3 and t[3].upper() == "LED" else _diode(name, a, k))
        else:
            if len(t) > 4 and t[4].upper() != "NPN":
                raise NetlistError(f"line {ln}: only NPN transistors are supported")
            beta = _value(t[5], ln, "beta") if len(t) > 5 else 100
            comps.append(_bjt(name, _node(t[1], ln), _node(t[2], ln), _node(t[3], ln), beta))
    if len(comps) > MAX_PARTS:
        raise NetlistError(f"too many parts (max {MAX_PARTS})")
    if not any(c["kind"] == "supply" for c in comps):
        raise NetlistError("add at least one voltage source, e.g. 'V1 TP0 GND 5'")
    if len(comps) < 2:
        raise NetlistError("add at least one more component")
    if not any("GND" in c["n"] for c in comps):
        raise NetlistError("no component is connected to GND")
    return comps


def register(text):
    """Parse a netlist and make it available as circuit id 'custom'."""
    comps = parse(text)
    probes = sorted({n for c in comps for n in c["n"]} - {"GND"})
    CIRCUITS["custom"] = {"title": "Custom circuit (from netlist)", "probes": probes, "comps": comps}
    return "custom"
