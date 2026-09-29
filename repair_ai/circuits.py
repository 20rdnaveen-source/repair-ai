"""Built-in circuits, fault injection, and the repair knowledge base."""
import copy

from .sim import OPEN, SHORT


def _r(name, a, b, val, kind="resistor"):
    return {"name": name, "type": "R", "kind": kind, "n": (a, b), "value": val}


def _v(name, a, b, val):
    return {"name": name, "type": "V", "kind": "supply", "n": (a, b), "value": val}


def _led(name, a, b):
    return {"name": name, "type": "LED", "kind": "led", "n": (a, b), "value": 0}


# TP0 = supply output, TP1 = after joint J1, TP2 = middle node.
CIRCUITS = {
    "led_resistor": {
        "title": "LED + series resistor (5 V)",
        "probes": ["TP0", "TP1", "TP2"],
        "comps": [_v("Vs", "TP0", "GND", 5.0), _r("J1", "TP0", "TP1", SHORT, "wire"),
                  _r("R1", "TP1", "TP2", 330), _led("D1", "TP2", "GND")],
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
    elif c["kind"] == "led":
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
    if k == "led":
        return {
            "open": (f"{n} (LED) is open / burnt out",
                     f"Replace {n}. Check polarity (long leg = anode toward +) and that the series resistor limits current."),
            "short": (f"{n} (LED) is shorted",
                      f"Replace {n}, then check the series resistor for overheating."),
            "reversed": (f"{n} (LED) is fitted backwards",
                         f"Power off and turn {n} around: anode (long leg) toward the resistor / positive side."),
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
    if k == "led":
        return f"Power OFF and use diode-test mode on {n}: ≈1.8–2.2 V one way, 'OL' the other way."
    return "Measure the supply output with the circuit disconnected."
