"""Command line: `python -m repair_ai.cli` (interactive) or `python -m repair_ai.cli demo`."""
import sys
 
from .circuits import CIRCUITS
from .diagnose import diagnose
 
 
def report(result):
    print(f"\nCircuit: {result['circuit']}")
    for w in result["warnings"]:
        print(f"⚠  {w}")
    for i, c in enumerate(result["candidates"], 1):
        conf = f" ({c['confidence']:.0%})" if c["confidence"] is not None else " (closest match)"
        print(f"\n{i}. {c['title']}{conf}")
        for e in c["evidence"]:
            print(f"   evidence: {e}")
        print(f"   fix: {c['repair']}")
    print(f"\nNext test: {result['next_test']['text']}\n")
 
 
DEMOS = [
    ("led_resistor", {"TP1": 5.0, "TP2": 0.05, "I": 0.0, "LED": "off"}),   # R1 open
    ("led_resistor", {"TP1": 5.0, "TP2": 0.0}),                            # ambiguous, partial readings
    ("led_resistor", {"TP1": 5.0, "TP2": 0.0, "LED": "off", "I": 0.02}),   # the note's contradictory example
    ("voltage_divider", {"TP0": 9.0, "TP2": 0.82}),
]
 
 
def ask(prompt):
    try:
        return input(prompt).strip()
    except EOFError:
        return ""
 
 
def interactive():
    ids = list(CIRCUITS)
    for i, cid in enumerate(ids, 1):
        print(f"{i}. {CIRCUITS[cid]['title']}")
    cid = ids[int(ask("Choose circuit number: ") or 1) - 1]
    print("Enter readings (press Enter to skip a field).")
    readings = {}
    for tp in CIRCUITS[cid]["probes"]:
        v = ask(f"  V at {tp} (volts): ")
        if v:
            readings[tp] = float(v)
    i = ask("  Supply current (mA): ")
    if i:
        readings["I"] = float(i) / 1000
    if any(c["type"] == "LED" for c in CIRCUITS[cid]["comps"]):
        led = ask("  LED on/off: ").lower()
        if led in ("on", "off"):
            readings["LED"] = led
    report(diagnose(cid, readings))
 
 
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "demo":
        for cid, rd in DEMOS:
            print("=" * 60, f"\nReadings: {rd}")
            report(diagnose(cid, rd))
    else:
        interactive()
 