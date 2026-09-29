"""Tiny DC circuit solver (modified nodal analysis) with a piecewise-linear LED.

Components are plain dicts:
  {"name": "R1", "type": "R",   "kind": "resistor", "n": ("TP1", "TP2"), "value": 330}
  {"name": "Vs", "type": "V",   "kind": "supply",   "n": ("TP0", "GND"), "value": 5}
  {"name": "D1", "type": "LED", "kind": "led",      "n": ("TP2", "GND")}   # anode, cathode
"""
import numpy as np

GMIN = 1e-7      # ~10 Mohm to ground on every node: models a multimeter probe
OPEN = 1e9       # ohms: broken connection
SHORT = 0.05     # ohms: shorted part
LED_VF, LED_RS, LED_LIT = 2.0, 5.0, 0.5e-3   # forward drop, series R, "visibly lit" current


def solve(comps):
    """Return {"V": {node: volts}, "I": supply current (A), "led": {name: lit?}}."""
    nodes = sorted({n for c in comps for n in c["n"]} - {"GND"})
    idx = {n: i for i, n in enumerate(nodes)}
    sources = [c for c in comps if c["type"] == "V"]
    N, M = len(nodes), len(sources)
    led_on = {c["name"]: True for c in comps if c["type"] == "LED"}

    for _ in range(30):                      # iterate LED on/off state until stable
        A = np.zeros((N + M, N + M))
        b = np.zeros(N + M)

        def stamp(p, q, g):
            ip, iq = idx.get(p), idx.get(q)
            if ip is not None:
                A[ip, ip] += g
            if iq is not None:
                A[iq, iq] += g
            if ip is not None and iq is not None:
                A[ip, iq] -= g
                A[iq, ip] -= g

        for i in range(N):
            A[i, i] += GMIN
        for c in comps:
            p, q = c["n"]
            if c["type"] == "R":
                stamp(p, q, 1.0 / max(c["value"], 1e-3))
            elif c["type"] == "LED":
                if led_on[c["name"]]:
                    g = 1.0 / LED_RS
                    stamp(p, q, g)
                    if p in idx:
                        b[idx[p]] += g * LED_VF
                    if q in idx:
                        b[idx[q]] -= g * LED_VF
                else:
                    stamp(p, q, 1e-12)
        for k, c in enumerate(sources):
            p, q = c["n"]
            if p in idx:
                A[idx[p], N + k] += 1
                A[N + k, idx[p]] += 1
            if q in idx:
                A[idx[q], N + k] -= 1
                A[N + k, idx[q]] -= 1
            b[N + k] = c["value"]

        x = np.linalg.solve(A, b)
        volt = {n: x[idx[n]] for n in nodes}
        volt["GND"] = 0.0

        changed = False
        for c in comps:
            if c["type"] != "LED":
                continue
            vd = volt[c["n"][0]] - volt[c["n"][1]]
            if led_on[c["name"]] and (vd - LED_VF) / LED_RS < 0:
                led_on[c["name"]], changed = False, True
            elif not led_on[c["name"]] and vd > LED_VF:
                led_on[c["name"]], changed = True, True
        if not changed:
            break

    lit = {}
    for c in comps:
        if c["type"] == "LED":
            vd = volt[c["n"][0]] - volt[c["n"][1]]
            lit[c["name"]] = led_on[c["name"]] and (vd - LED_VF) / LED_RS > LED_LIT
    return {"V": volt, "I": -x[N] if M else 0.0, "led": lit}
