"""Injects every single fault into every circuit, 'measures' it with noise, and checks the diagnosis."""
import os, random, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
 
from repair_ai.circuits import CIRCUITS, apply_fault, build, faults_of
from repair_ai.diagnose import diagnose, predict
 
 
def noisy(reading, rng):
    return {k: (v if k == "LED" else v * (1 + rng.uniform(-0.02, 0.02))) for k, v in reading.items()}
 
 
def test_all_single_faults():
    rng = random.Random(1)
    total = top1 = in_set = 0
    for cid, spec in CIRCUITS.items():
        base = build(cid)
        for comp, mode in faults_of(base):
            readings = noisy(predict(apply_fault(base, comp, mode), spec["probes"], any(c["kind"] == "led" for c in base)), rng)
            res = diagnose(cid, readings)
            total += 1
            in_set += any(c["component"] == comp and c["mode"] == mode for c in res["candidates"])
            top1 += (res["candidates"][0]["component"], res["candidates"][0]["mode"]) == (comp, mode)
    print(f"{total} faults: true fault in candidate list {in_set}/{total}, ranked first {top1}/{total}")
    assert in_set == total
 
 
def test_contradictory_readings_are_flagged():
    res = diagnose("led_resistor", {"TP1": 5.0, "TP2": 0.0, "LED": "off", "I": 0.02})
    assert not res["consistent"] and res["warnings"]
 
 
def test_healthy_circuit():
    res = diagnose("voltage_divider", {"TP0": 9.0, "TP2": 4.5})
    assert res["candidates"][0]["component"] is None
 
 
def test_check_loop():
    r = {"TP1": 5.0, "TP2": 0.0}                       # ambiguous: R1 open or D1 short
    first = diagnose("led_resistor", r)
    assert first["next_test"]["type"] in ("measure", "check")
    fail = diagnose("led_resistor", r, {"R1": "fail"})
    assert fail["candidates"][0]["component"] == "R1" and fail["candidates"][0]["confidence"] > 0.9
    ok = diagnose("led_resistor", r, {"R1": "pass"})
    assert ok["candidates"][0]["component"] == "D1"
 
 
def test_netlist():
    from repair_ai.netlist import NetlistError, register
    cid = register("V1 TP0 GND 9\nJ1 TP0 TP1\nR1 TP1 TP2 4.7k\nR2 TP2 TP3 2.2k\nR3 TP3 GND 3.3k")
    base = build(cid)
    assert len(faults_of(base)) == 1 * 2 + 1 + 3 * 4
    rd = predict(apply_fault(base, "R2", "open"), CIRCUITS[cid]["probes"], False)
    assert diagnose(cid, rd)["candidates"][0]["component"] == "R2"
    for bad in ("R1 A B", "X1 A B 5", "V1 A GND 500\nR1 A GND 1k", "R1 A GND 1k", "V1 A GND 5\nD1 A GND\nD1 A GND"):
        try:
            register(bad); assert False, bad
        except NetlistError:
            pass
    CIRCUITS.pop("custom", None)
 
 
def test_evaluation_runs():
    from repair_ai.evaluate import run
    per, _ = run(0.05, 2, 1)
    n = sum(c["n"] for c in per.values())
    assert n > 100 and sum(c["top3"] for c in per.values()) / n > 0.9
 
 
def test_server_api():
    import json, threading, urllib.request
    from http.server import ThreadingHTTPServer
    from repair_ai.server import Handler
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    post = lambda u, b: json.load(urllib.request.urlopen(urllib.request.Request(
        base + u, json.dumps(b).encode(), {"Content-Type": "application/json"})))
    assert b"REPAIR-AI" in urllib.request.urlopen(base + "/").read()
    info = json.load(urllib.request.urlopen(base + "/api/circuits"))
    assert len(info) == 5 and info[0]["faults"]
    rd = post("/api/inject", {"circuit": "led_resistor", "component": "R1", "mode": "open"})
    res = post("/api/diagnose", {"circuit": "led_resistor", "readings": rd})
    assert res["status"] == "fault" and res["candidates"][0]["component"] == "R1"
    healthy = post("/api/diagnose", {"circuit": "led_resistor", "readings": post("/api/inject", {"circuit": "led_resistor"})})
    assert healthy["status"] == "no_fault"
    srv.shutdown()
 
 
if __name__ == "__main__":
    test_all_single_faults(); test_contradictory_readings_are_flagged(); test_healthy_circuit(); test_check_loop(); test_netlist(); test_evaluation_runs(); test_server_api()
    print("all tests passed")
 