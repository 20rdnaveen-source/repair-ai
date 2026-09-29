# REPAIR-AI
 
![tests](https://github.com/20rdnaveen-source/repair-ai/actions/workflows/tests.yml/badge.svg)
 
**Explainable fault diagnosis and guided troubleshooting for low-voltage DC electronic circuits.**
 
Enter multimeter readings for a circuit. REPAIR-AI tells you whether it is healthy, which fault is most likely, *why*, which test to run next, and how to repair it. It does not guess: the answer comes from circuit physics, not from a language model.
 
> Diagnostic loop: **Fault → Reason → Verify → Repair**
 
## Features
- **Model-based diagnosis.** Simulates the circuit under every possible single fault (open, short, wrong value, reversed diode, dead supply, transistor faults) and ranks the faults that explain your readings.
- **Explainable output.** Expected vs observed table, evidence per fault, relative confidence, repair steps.
- **Guided test loop.** If several faults fit, it picks the measurement that best separates them and asks for it. Pass/fail component checks update the diagnosis.
- **Honest.** Says "no fault" for healthy circuits, and warns when readings contradict each other instead of inventing a fault.
- **Your own circuits.** Describe a circuit as a text netlist (V, R, wire/joint, diode/LED, NPN transistor).
- **Web app** with circuit diagram, live fault injection for demos, and a printable diagnostic report.
- **Benchmarked** with a Monte-Carlo evaluation under component tolerance and meter noise.
## How it works
```
Circuit (preset or netlist)
        │
        ▼
  DC solver (nodal analysis)  ──►  predicted readings for: healthy + every single fault
        │
        ▼
  compare with measured readings  ──►  rank faults, flag contradictions
        │
        ▼
  next most informative test  ◄──  user enters test result  ──►  update ranking
        │
        ▼
  report: fault, evidence, repair
```
 
## Run
    pip install -r requirements.txt
    python -m repair_ai.server        # web app -> http://127.0.0.1:8000
    python -m repair_ai.cli demo      # sample diagnoses in the terminal
    python -m repair_ai.evaluate      # Monte-Carlo benchmark -> results/evaluation.md
    python tests/test_accuracy.py     # all tests
 
## Circuits
Built in: LED + resistor, diode + resistor, voltage divider, series-parallel resistors, NPN transistor switch (60 single-fault scenarios).
Custom netlist (one part per line):
 
    V1 TP0 GND 9         # supply (+ node, - node, volts)
    J1 TP0 TP1           # wire / solder joint
    R1 TP1 TP2 4.7k      # resistor
    D1 TP2 GND LED       # diode (LED or DIODE)
    Q1 TPB TPC GND NPN   # NPN transistor: base, collector, emitter
 
## Results (simulated benchmark)
6,500 random trials per tolerance level. The engine knows only the nominal circuit; the simulated "real" circuit has random resistor, diode, gain and supply errors plus meter noise.
 
| Resistor tolerance | Top-1 | Top-1 (equiv.) | Top-3 | Healthy false alarm |
|---|---|---|---|---|
| ±1% | 90.8% | 100.0% | 100.0% | 0.0% |
| ±5% | 89.6% | 98.6% | 99.3% | 0.0% |
| ±10% | 87.7% | 96.2% | 98.3% | 9.2% |
 
*Top-1 (equiv.)* counts faults that give identical readings as correct (for example two identical parallel resistors: no measurement can tell them apart). Full tables and confusions: [`results/evaluation.md`](results/evaluation.md).
 
## Limitations
- Low-voltage **DC** only; single-fault assumption.
- Results come from an ideal simulator, not real hardware yet.
- Confidence is a relative ranking between candidate faults, not a calibrated probability.
- The circuit must be known (preset or netlist). It does not discover unknown circuits or read photos.
- At ±10% parts the "healthy" band is too tight (9.2% false alarms).
## Project structure
```
repair_ai/  sim.py (solver) · circuits.py (presets, faults, repair knowledge) · diagnose.py (engine)
            netlist.py · evaluate.py · server.py · cli.py · static/index.html (UI)
tests/      test_accuracy.py        results/   evaluation.md, confusion_5pct.csv
docs/       DEMO_SCRIPT.md
```
 
## Roadmap
- [x] Simulator, diagnosis engine, interactive test loop
- [x] Web app, circuit diagram, printable report
- [x] Netlist input
- [x] Tolerance / noise evaluation
- [ ] Multi-fault diagnosis
- [ ] Live measurements from ESP32/Arduino, validation on a real breadboard
- [ ] ML classifier compared against the physics engine
- [ ] More parts (op-amp, Zener, MOSFET)
 