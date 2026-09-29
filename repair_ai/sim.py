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
BJT_VBE, BJT_RBE, BJT_VSAT, BJT_RCE = 0.7, 50.0, 0.2, 2.0   # NPN: B-E drop/resistance, C-E saturation
 
 
def solve(comps):
    """Return {"V": {node: volts}, "I": supply current (A), "led": {name: lit?}}."""
    nodes = sorted({n for c in comps for n in c["n"]} - {"GND"})
    idx = {n: i for i, n in enumerate(nodes)}
    sources = [c for c in comps if c["type"] == "V"]
    N, M = len(nodes), len(sources)
    led_on = {c["name"]: True for c in comps if c["type"] == "LED"}
    bjt = {c["name"]: "act" for c in comps if c["type"] == "BJT"}    # cut / act / sat
 
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
        def add(row, col, val):
            if row in idx and col in idx:
                A[idx[row], idx[col]] += val
 
        def inject(node, val):
            if node in idx:
                b[idx[node]] += val
 
        def on(p, q, g, vf):          # conducting branch: g*(Vp - Vq - vf)
            stamp(p, q, g)
            inject(p, g * vf)
            inject(q, -g * vf)
 
        for c in comps:
            if c["type"] == "BJT":
                B, C, E = c["n"]
                force = c.get("force")
                mode = "cut" if force == "cut" else "ces" if force == "ces" else bjt[c["name"]]
                beta = 0 if force == "noc" else c.get("beta", 100)
                g = 1.0 / BJT_RBE
                if mode == "cut":
                    stamp(B, E, 1e-12)
                    stamp(C, E, 1e-12)
                    continue
                on(B, E, g, BJT_VBE)
                if mode == "act" and beta:
                    gm = beta * g          # Ic = gm * (Vb - Ve - Vbe), flowing C -> E
                    add(C, B, gm); add(C, E, -gm); add(E, B, -gm); add(E, E, gm)
                    inject(C, gm * BJT_VBE)
                    inject(E, -gm * BJT_VBE)
                elif mode == "sat":
                    on(C, E, 1.0 / BJT_RCE, BJT_VSAT)
                elif mode == "ces":
                    stamp(C, E, 1.0 / SHORT)
                continue
            p, q = c["n"]
            if c["type"] == "R":
                stamp(p, q, 1.0 / max(c["value"], 1e-3))
            elif c["type"] == "LED":
                if led_on[c["name"]]:
                    on(p, q, 1.0 / LED_RS, c.get("vf", LED_VF))
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
            if c["type"] == "LED":
                vf = c.get("vf", LED_VF)
                vd = volt[c["n"][0]] - volt[c["n"][1]]
                if led_on[c["name"]] and (vd - vf) / LED_RS < 0:
                    led_on[c["name"]], changed = False, True
                elif not led_on[c["name"]] and vd > vf:
                    led_on[c["name"]], changed = True, True
            elif c["type"] == "BJT" and c.get("force") not in ("cut", "ces"):
                B, C, E = c["n"]
                vbe, vce = volt[B] - volt[E], volt[C] - volt[E]
                ib = (vbe - BJT_VBE) / BJT_RBE
                beta = 0 if c.get("force") == "noc" else c.get("beta", 100)
                s0, new = bjt[c["name"]], bjt[c["name"]]
                if s0 == "cut" and vbe > BJT_VBE:
                    new = "act"
                elif s0 == "act":
                    new = "cut" if ib < 0 else "sat" if (beta and vce < BJT_VSAT) else "act"
                elif s0 == "sat":
                    new = "cut" if ib <= 0 else "act" if (vce - BJT_VSAT) / BJT_RCE > beta * ib else "sat"
                if new != s0:
                    bjt[c["name"]], changed = new, True
        if not changed:
            break
 
    lit = {}
    for c in comps:
        if c["type"] == "LED":
            vd = volt[c["n"][0]] - volt[c["n"][1]]
            lit[c["name"]] = led_on[c["name"]] and (vd - c.get("vf", LED_VF)) / LED_RS > LED_LIT
    return {"V": volt, "I": -x[N] if M else 0.0, "led": lit}
 