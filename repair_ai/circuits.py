"""Built-in circuits, fault injection, and the repair knowledge base."""
import copy
 
from .sim import OPEN, SHORT
 
 
def _r(name, a, b, val, kind="resistor"):
    return {"name": name, "type": "R", "kind": kind, "n": (a, b), "value": val}
 
 
def _v(name, a, b, val):
    return {"name": name, "type": "V", "kind": "supply", "n": (a, b), "value": val}
 
 
def _led(name, a, b):
    return {"name": name, "type": "LED", "kind": "led", "n": (a, b), "value": 0}
 
 
def _diode(name, a, b, vf=0.7):
    return {"name": name, "type": "LED", "kind": "diode", "n": (a, b), "value": 0, "vf": vf}
 
 
def _bjt(name, b, c, e, beta=100):
    return {"name": name, "type": "BJT", "kind": "bjt", "n": (b, c, e), "value": 0, "beta": beta}
 
 
# TP0 = supply output, TP1 = after joint J1, TP2 = middle node.
CIRCUITS = {
    "led_resistor": {
        "title": "LED + series resistor (5 V)",
        "probes": ["TP0", "TP1", "TP2"],
        "comps": [_v("Vs", "TP0", "GND", 5.0), _r("J1", "TP0", "TP1", SHORT, "wire"),
                  _r("R1", "TP1", "TP2", 330), _led("D1", "TP2", "GND")],
    },
    "diode_resistor": {
        "title": "Diode + resistor (5 V, 1k, silicon diode)",
        "probes": ["TP0", "TP1", "TP2"],
        "comps": [_v("Vs", "TP0", "GND", 5.0), _r("J1", "TP0", "TP1", SHORT, "wire"),
                  _r("R1", "TP1", "TP2", 1_000), _diode("D1", "TP2", "GND")],
    },
    "bjt_switch": {
        "title": "NPN transistor switch (5 V, Rb 10k, Rc 1k)",
        "probes": ["TP0", "TPB", "TPC"],     # supply, base, collector
        "comps": [_v("Vs", "TP0", "GND", 5.0), _r("Rb", "TP0", "TPB", 10_000),
                  _r("Rc", "TP0", "TPC", 1_000), _bjt("Q1", "TPB", "TPC", "GND")],
    },
    "voltage_divider": {
        "title": "Voltage divider (9 V, 10k / 10k)",
        "probes": ["TP0", "TP1", "TP2"],
        "comps": [_v("Vs", "TP0", "GND", 9.0), _r("J1", "TP0", "TP1", SHORT, "wire"),
                  _r("R1", "TP1", "TP2", 10_000), _r("R2", "TP2", "GND", 10_000)],
    },
    "resistor_network": {
        "title": "Series-parallel network (12 V, 1k + 2.2k || 2.2k)",
        "probes": ["TP0", "TP1", "TP2"],
        "comps": [_v("Vs", "TP0", "GND", 12.0), _r("J1", "TP0", "TP1", SHORT, "wire"),
                  _r("R1", "TP1", "TP2", 1_000), _r("R2", "TP2", "GND", 2_200),
                  _r("R3", "TP2", "GND", 2_200)],
    },
}
 
MODES = {
    "resistor": ["open", "short", "high", "low"],
    "wire": ["open"],
    "led": ["open", "short", "reversed"],
    "diode": ["open", "short", "reversed"],
    "bjt": ["open_base", "open_collector", "ce_short", "low_gain"],
    "supply": ["dead", "low"],
}
 
 
def build(circuit_id):
    return copy.deepcopy(CIRCUITS[circuit_id]["comps"])
 
 
def faults_of(comps):
    """All single faults as (component_name, mode)."""
    return [(c["name"], m) for c in comps for m in MODES[c["kind"]]]
 
 
def apply_fault(comps, name, mode):
    comps = copy.deepcopy(comps)
    c = next(c for c in comps if c["name"] == name)
    if c["kind"] in ("resistor", "wire"):
        c["value"] = {"open": OPEN, "short": SHORT,
                      "high": c["value"] * 10, "low": c["value"] / 10}[mode]
    elif c["kind"] == "bjt":
        if mode == "low_gain":
            c["beta"] = 5
        else:
            c["force"] = {"open_base": "cut", "open_collector": "noc", "ce_short": "ces"}[mode]
    elif c["kind"] in ("led", "diode"):
        if mode == "reversed":
            c["n"] = (c["n"][1], c["n"][0])
        else:
            c["type"], c["value"] = "R", OPEN if mode == "open" else SHORT
    elif c["kind"] == "supply":
        c["value"] = 0.0 if mode == "dead" else c["value"] * 0.5
    return comps
 
 
def _fmt(ohms):
    return f"{ohms / 1000:g} kΩ" if ohms >= 1000 else f"{ohms:g} Ω"
 
 
def describe(comp, mode):
    """(title, how-to-repair) for a fault, given the ORIGINAL component dict."""
    n, k = comp["name"], comp["kind"]
    if k == "resistor":
        v = _fmt(comp["value"])
        return {
            "open": (f"{n} is open-circuit (burnt or broken)",
                     f"Power off. Measure {n} out of circuit (should be ≈{v}). Replace it with the same "
                     f"value and power rating. If it burnt, find out why before powering on again."),
            "short": (f"{n} is shorted",
                      f"Power off. Look for a solder bridge or stray wire across {n}. If none, replace {n} ({v})."),
            "high": (f"{n} value is far too high (≈10× nominal)",
                     f"Wrong part or drifted resistor: check the colour code, then replace {n} with {v}."),
            "low": (f"{n} value is far too low (≈1/10 nominal)",
                    f"Wrong part or damaged resistor: check the colour code, then replace {n} with {v}."),
        }[mode]
    if k == "wire":
        return (f"{n} is an open joint / broken wire",
                f"Power off. Reflow the solder joint or replace the jumper/track at {n}. "
                f"Confirm end-to-end continuity before powering on.")
    if k in ("led", "diode"):
        w = "LED" if k == "led" else "diode"
        return {
            "open": (f"{n} ({w}) is open / burnt out",
                     f"Replace {n}. Check polarity (anode toward +) and that the series resistor limits current."),
            "short": (f"{n} ({w}) is shorted",
                      f"Replace {n}, then check the series resistor for overheating."),
            "reversed": (f"{n} ({w}) is fitted backwards",
                         f"Power off and turn {n} around: anode (band-free end / long leg) toward the resistor / positive side."),
        }[mode]
    if k == "bjt":
        return {
            "open_base": (f"{n} base is open (bad joint or dead transistor)",
                          f"Power off. Check the base joint and Rb, then test {n}'s base-emitter junction in diode mode (≈0.6–0.7 V one way). Replace {n} if it reads open."),
            "open_collector": (f"{n} collector path is open",
                               f"Power off. Check the collector joint and Rc, then test {n} in diode mode. Replace {n} if the collector junction is open."),
            "ce_short": (f"{n} is shorted collector-to-emitter",
                         f"Power off and replace {n}; check that the load current and supply did not exceed its rating."),
            "low_gain": (f"{n} has very low gain (damaged or wrong part)",
                         f"Replace {n} with the correct part (check the part number and pin-out: E-B-C order)."),
        }[mode]
    return {
        "dead": ("Supply is dead (0 V)",
                 "Check battery / adapter, fuse, switch and connector. Measure the supply output with the circuit disconnected."),
        "low": ("Supply voltage is low (≈50 %)",
                "Charge or replace the battery, check the adapter rating, and look for something loading the supply."),
    }[mode]
 
 
def physical_test(comp, mode):
    """A power-off check that confirms the suspected fault."""
    n, k = comp["name"], comp["kind"]
    if k == "resistor":
        return f"Power OFF, lift one leg of {n} and measure its resistance (expected {_fmt(comp['value'])})."
    if k == "wire":
        return f"Power OFF and check continuity across {n} (the meter should beep)."
    if k in ("led", "diode"):
        return f"Power OFF and use diode-test mode on {n}: forward drop one way, 'OL' the other way."
    if k == "bjt":
        return f"Power OFF and use diode-test mode on {n}: base-emitter and base-collector ≈0.6–0.7 V one way, 'OL' the other; collector-emitter 'OL' both ways."
    return "Measure the supply output with the circuit disconnected."
 