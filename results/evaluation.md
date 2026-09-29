# REPAIR-AI evaluation

Monte-Carlo test: 100 random trials for every fault (and the healthy circuit) in every circuit, seed 1.
The engine only knows the **nominal** circuit; the simulated 'real' circuit has random part errors and meter noise.
Single-fault assumption. Ideal simulator, not hardware: treat these numbers as a benchmark of the method.

Metrics: **Top-1** = the first suggestion is the true fault. **Top-1 (equiv.)** = the first suggestion is the true fault or a fault that gives identical readings (e.g. two identical parallel resistors). **Top-3** = the true fault is in the first three.

## Accuracy vs component tolerance (all circuits)

| Resistor tolerance | Trials | Top-1 | Top-1 (equiv.) | Top-3 | Healthy false-alarm | Fault missed as healthy | 'No fit' warnings |
|---|---|---|---|---|---|---|---|
| ±0% | 6500 | 96.9% | 100.0% | 100.0% | 0.0% | 0.0% | 0.0% |
| ±1% | 6500 | 90.8% | 100.0% | 100.0% | 0.0% | 0.0% | 0.6% |
| ±5% | 6500 | 89.6% | 98.6% | 99.3% | 0.0% | 0.5% | 3.1% |
| ±10% | 6500 | 87.7% | 96.2% | 98.3% | 9.2% | 0.7% | 7.3% |

## Per circuit at ±5% parts

| Circuit | Top-1 | Top-1 (equiv.) | Top-3 | False alarm |
|---|---|---|---|---|
| LED + series resistor (5 V) | 90.8% | 100.0% | 100.0% | 0.0% |
| Diode + resistor (5 V, 1k, silicon diode) | 90.5% | 100.0% | 100.0% | 0.0% |
| NPN transistor switch (5 V, Rb 10k, Rc 1k) | 95.9% | 95.9% | 97.9% | 0.0% |
| Voltage divider (9 V, 10k / 10k) | 100.0% | 100.0% | 100.0% | 0.0% |
| Series-parallel network (12 V, 1k + 2.2k || 2.2k) | 74.4% | 98.1% | 99.1% | 0.0% |

## Most common confusions at ±5% parts

| Circuit | True fault | Diagnosed as | Count |
|---|---|---|---|
| resistor_network | R3 short | R2 short | 100 |
| resistor_network | R3 open | R2 open | 91 |
| diode_resistor | D1 open | D1 reversed | 56 |
| resistor_network | R2 high | R3 high | 55 |
| led_resistor | D1 open | D1 reversed | 54 |
| diode_resistor | D1 reversed | D1 open | 48 |
| led_resistor | D1 reversed | D1 open | 47 |
| resistor_network | R3 low | R2 low | 46 |
| resistor_network | R2 low | R3 low | 44 |
| resistor_network | R3 high | R2 high | 43 |
