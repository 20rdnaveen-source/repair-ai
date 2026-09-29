# REPAIR-AI

AI-based fault diagnosis for electronic circuits. Enter multimeter readings for a known circuit and get:
the likely fault, the evidence, the next test to run, and how to repair it.

## How it works
1. `sim.py` – DC circuit solver (nodal analysis) with an LED model.
2. `circuits.py` – built-in circuits, fault injection (open, short, drift, reversed LED, dead supply) and repair knowledge.
3. `diagnose.py` – simulates every single fault, compares with your readings, ranks by fit, flags contradictory readings, and picks the most useful next measurement.

## Run
    pip install -r requirements.txt
    python -m repair_ai.server        # web app -> http://127.0.0.1:8000
    python -m repair_ai.cli demo      # sample diagnoses
    python -m repair_ai.cli           # interactive
    python tests/test_accuracy.py     # injects all 60 single faults and checks the diagnosis

## Roadmap
- [ ] Netlist input (custom circuits)
- [ ] ML classifier trained on simulated faults
- [x] Web app + interactive test loop (standard library only)
- [ ] Schematic / photo upload (stretch)
