"""Fault diagnosis: compare readings with what each single fault would produce.
 
Readings dict keys: "TP0", "TP1", "TP2" (volts), "I" (amps from supply), "LED" ("on"/"off").
Any subset may be given.
"""
import math
from itertools import combinations
 
from .circuits import CIRCUITS, apply_fault, build, describe, faults_of, physical_test
from .sim import solve
 
CONSISTENT = 1.5     # a reading "fits" if it is within 1.5 tolerances of the prediction
 
 
def predict(comps, probes, has_led=None):
    """Simulate; LED state is reported whenever the healthy circuit has an LED
    (a burnt-out/shorted LED simply reads 'off')."""
    r = solve(comps)
    out = {p: r["V"].get(p, 0.0) for p in probes}
    out["I"] = r["I"]
    if has_led is None:
        has_led = any(c["kind"] == "led" for c in comps)
    if has_led:
        out["LED"] = "on" if any(r["led"].values()) else "off"
    return out
 
 
def _err(key, meas, pred, ref_i):
    """How many 'tolerances' meas is away from pred."""
    if key == "LED":
        return 0.0 if meas == pred else 3.0
    if key == "I":
        tol = 0.1 * abs(pred) + 0.02 * abs(ref_i) + 1e-6
    else:
        tol = 0.1 + 0.05 * abs(pred)
    return abs(meas - pred) / tol
 
 
def _show(key, val):
    if key == "LED":
        return str(val)
    return f"{val * 1000:.2f} mA" if key == "I" else f"{val:.2f} V"
 
 
def _check_factor(row, checks):
    """Component checks: 'fail' keeps hypotheses on that part, 'pass' rules them out."""
    f = 1.0
    for comp, res in checks.items():
        if res == "fail":
            f *= 1.0 if row["comp"] == comp else 0.02
        elif row["comp"] == comp:
            f *= 0.02
    return f
 
 
def diagnose(circuit_id, readings, checks=None):
    checks = checks or {}
    base = build(circuit_id)
    probes = CIRCUITS[circuit_id]["probes"]
    has_led = any(c["kind"] == "led" for c in base)
    ref = predict(base, probes)
    readings = {k.upper() if k.upper() != "LED" else "LED": v for k, v in readings.items()}
    keys = [k for k in readings if k in ref]
    if not keys:
        raise ValueError(f"Give at least one reading from {sorted(ref)}")
    ref_i = ref["I"]
 
    spec = CIRCUITS[circuit_id]
    if "_hyp" not in spec:          # nominal predictions for every hypothesis, computed once per circuit
        spec["_hyp"] = [(cn, m, predict(base if cn is None else apply_fault(base, cn, m), probes, has_led))
                        for cn, m in [(None, "healthy")] + faults_of(base)]
    rows = []
    for comp_name, mode, pred in spec["_hyp"]:
        errs = {k: _err(k, readings[k], pred[k], ref_i) for k in keys}
        rows.append({"comp": comp_name, "mode": mode, "pred": pred, "errs": errs,
                     "sse": sum(e * e for e in errs.values()), "worst": max(errs.values())})
    rows.sort(key=lambda r: r["sse"])
 
    fits = [r for r in rows if r["worst"] <= CONSISTENT]
    warnings = []
    if fits:
        w = [math.exp(-0.5 * r["sse"]) * _check_factor(r, checks) for r in fits]
        for r, wi in zip(fits, w):
            r["conf"] = wi / sum(w)
        fits.sort(key=lambda r: -r["conf"])
        shown = fits
    else:
        shown = rows[:3]
        for r in shown:
            r["conf"] = None
        bad = [f"{k} = {_show(k, readings[k])}" for k, e in shown[0]["errs"].items() if e > CONSISTENT]
        warnings.append("No single fault explains ALL readings. Contradicting readings: " + ", ".join(bad) +
                        ". Re-check probe contact/ground and the meter range; there may be more than one fault.")
 
    comps_by_name = {c["name"]: c for c in base}
    cands = []
    for r in shown[:4]:
        if r["comp"] is None:
            title, repair = "Circuit looks healthy", "No fault indicated by these readings."
        else:
            title, repair = describe(comps_by_name[r["comp"]], r["mode"])
        evidence = []
        for k in keys:
            if _err(k, readings[k], ref[k], ref_i) > 1:
                evidence.append(f"{k}: measured {_show(k, readings[k])}, healthy circuit gives "
                                f"{_show(k, ref[k])}; with this fault expect {_show(k, r['pred'][k])}")
        cands.append({"component": r["comp"], "mode": r["mode"], "title": title, "confidence": r["conf"],
                      "evidence": evidence or ["All readings match the healthy circuit."], "repair": repair})
 
    table = [{"key": k, "expected": _show(k, ref[k]),
              "observed": _show(k, readings[k]) if k in readings else "-",
              "ok": None if k not in readings else bool(_err(k, readings[k], ref[k], ref_i) <= 1)} for k in ref]
    status = "inconsistent" if not fits else ("no_fault" if shown[0]["comp"] is None else "fault")
    return {"circuit": CIRCUITS[circuit_id]["title"], "status": status, "consistent": bool(fits),
            "table": table, "candidates": cands, "checks": checks, "warnings": warnings,
            "next_test": _next_test(shown, ref, ref_i, keys, comps_by_name, checks)}
 
 
def _next_test(shown, ref, ref_i, keys, comps_by_name, checks):
    lead = shown[0]
    if lead["comp"] is None:
        return {"type": "none", "text": "Readings look normal: no fault to chase. If the circuit still misbehaves, add more readings."}
    if checks.get(lead["comp"]) == "fail" and (lead["conf"] or 0) > 0.6:
        return {"type": "done", "text": f"Confirmed: {lead['comp']} failed its check. Apply the repair above, then re-measure."}
    top = [r for r in shown[:3] if (r["conf"] or 0) > 0.02 or r["conf"] is None]
    if len(top) >= 2:
        best_k, best_spread = None, 0.0
        for k in (k for k in ref if k not in keys):
            spread = max(_err(k, a["pred"][k], b["pred"][k], ref_i) for a, b in combinations(top, 2))
            if spread > best_spread:
                best_k, best_spread = k, spread
        if best_k and best_spread >= 2:
            what = {"I": "the supply current", "LED": "whether the LED is lit"}.get(best_k, f"the voltage at {best_k}")
            parts = [f"{'healthy' if r['comp'] is None else r['comp'] + ' ' + r['mode']}: {_show(best_k, r['pred'][best_k])}"
                     for r in top]
            return {"type": "measure", "key": best_k, "text": f"Measure {what}. Expected: " + "; ".join(parts) + "."}
    target = next((r for r in shown if r["comp"] and r["comp"] not in checks), lead)
    return {"type": "check", "component": target["comp"],
            "text": physical_test(comps_by_name[target["comp"]], target["mode"])}
 