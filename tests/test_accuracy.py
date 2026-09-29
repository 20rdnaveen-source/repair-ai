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


if __name__ == "__main__":
    test_all_single_faults(); test_contradictory_readings_are_flagged(); test_healthy_circuit()
    print("all tests passed")
