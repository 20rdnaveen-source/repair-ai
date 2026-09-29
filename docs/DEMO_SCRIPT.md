# REPAIR-AI: 3-minute demo script

**One-line pitch:** "REPAIR-AI is an explainable troubleshooting assistant. It calculates what a healthy circuit should read, compares it with your measurements, and runs a Fault → Reason → Verify → Repair loop. It never just guesses."

## Before you start
- `python -m repair_ai.server`, open http://127.0.0.1:8000, browser zoomed so the diagram is visible.
- Have the LED circuit selected. Optional: a real LED + 330 Ω on a breadboard with a multimeter.

## Script
| Time | Do | Say |
|---|---|---|
| 0:00 | Slide/verbal | "Fixing a dead circuit is guesswork. The same readings can come from different faults, and beginners don't know which test to do next." |
| 0:20 | Inject "R1 is open-circuit", Diagnose | "Here it reads 0 mA and 0.05 V at TP2. REPAIR-AI compares that with the healthy values, finds R1 open, shows the evidence, the repair, and highlights R1 on the drawing." |
| 1:00 | Clear. Enter only TP1 = 5, TP2 = 0. Diagnose | "With too little information it doesn't pretend. Two faults fit, so it asks for the one measurement that separates them." |
| 1:20 | Click R1 FAILED (or add the reading) | "I run the test, tell it the result, and the diagnosis updates to 100%. That is the verify step." |
| 1:50 | Enter TP0 = 0, TP1 = 5, current 20 mA, LED off | "Impossible readings. It says no single fault explains them instead of inventing one." |
| 2:10 | Netlist section: load your own circuit, inject a fault | "Not limited to presets. Describe any small DC circuit as text." |
| 2:30 | Open results/evaluation.md or the report | "Tested with 6,500 random trials per tolerance level, with part errors and meter noise: correct fault in the top three 99.3% of the time at ±5% parts, no false alarms on healthy circuits." |
| 2:50 | Close | "Next: live readings from an ESP32 and validation on real hardware." |

## Likely judge questions (honest answers)
- **Where is the AI?** Model-based diagnosis: a physics model generates hypotheses, a probabilistic ranking weighs them, and active test selection picks the next measurement. It is explainable by design. An ML classifier is on the roadmap as a second opinion, not a replacement.
- **Why not just ask an LLM?** An LLM can't compute what a circuit should read, and it hallucinates faults. Here every conclusion is backed by a calculation. An LLM could only rephrase the explanation.
- **Does it work on real hardware?** Validated on a simulator with realistic tolerances and noise so far. Hardware validation is the next step; say whether you tried the breadboard.
- **Limits?** Low-voltage DC, single fault, known circuit. Some faults are physically indistinguishable from voltage readings (two identical parallel resistors), and it says so.
- **How is it different from SPICE?** SPICE simulates a circuit you specify. REPAIR-AI runs the inverse problem: from measurements to the most likely fault, and which test to do next.
- **Is the confidence a real probability?** No, it is a relative ranking between candidate faults.
