"""Monte-Carlo evaluation of the diagnosis engine under realistic imperfections.

    python -m repair_ai.evaluate [--trials 20] [--seed 1]

For every circuit and every single fault (plus the healthy circuit) it builds a "real" circuit whose
parts differ from the nominal model (resistor tolerance, LED/diode drop, transistor gain, supply error),
"measures" it with meter noise, and asks the engine (which only knows the NOMINAL circuit) to diagnose it.
Writes results/evaluation.md and results/confusion_5pct.csv.
"""
import argparse
import copy
import csv
import os
import random
from collections import Counter, defaultdict

from .circuits import CIRCUITS, apply_fault, build, faults_of
from .diagnose import diagnose, predict
from .sim import LED_VF

TOLS = [0.0, 0.01, 0.05, 0.10]       # resistor tolerance levels; 0.05 = 5 % parts
OUT = os.path.join(os.path.dirname(__file__), "..", "results")


def perturb(comps, rng, s):
    """A 'real-world' version of the nominal circuit. s = tolerance / 5 %."""
    out = copy.deepcopy(comps)
    for c in out:
        if c["kind"] == "resistor":
            c["value"] *= 1 + rng.uniform(-0.05, 0.05) * s
        elif c["kind"] == "supply":
            c["value"] *= 1 + rng.uniform(-0.02, 0.02) * s
        elif c["kind"] in ("led", "diode"):
            c["vf"] = c.get("vf", LED_VF) + rng.uniform(-0.15, 0.15) * s
        elif c["kind"] == "bjt":
            c["beta"] *= 1 + rng.uniform(-0.3, 0.3) * min(s, 3)
    return out


def measure(reading, rng, s):
    out = {}
    for k, v in reading.items():
        if k == "LED":
            out[k] = v
        elif k == "I":
            out[k] = v + rng.gauss(0, s * (0.01 * abs(v) + 5e-6))
        else:
            out[k] = v + rng.gauss(0, s * (0.005 * abs(v) + 0.005))
    return out


def label(comp, mode):
    return "healthy" if comp is None else f"{comp} {mode}"


def signature(reading):
    return tuple((k, reading[k] if k == "LED" else round(reading[k], 2)) for k in sorted(reading))


def run(tol, trials, seed):
    rng, s = random.Random(seed), tol / 0.05
    per, conf = {}, Counter()
    for cid, spec in CIRCUITS.items():
        if cid == "custom":
            continue
        nominal, probes = build(cid), spec["probes"]
        has_led = any(c["kind"] == "led" for c in nominal)
        hyps = [(None, "healthy")] + faults_of(nominal)
        sig = {h: signature(predict(nominal if h[0] is None else apply_fault(nominal, *h), probes, has_led))
               for h in hyps}
        c = Counter()
        for h in hyps:
            for _ in range(trials):
                real = perturb(nominal, rng, s)
                rd = measure(predict(real if h[0] is None else apply_fault(real, *h), probes, has_led), rng, s)
                res = diagnose(cid, rd)
                cands = [(x["component"], x["mode"]) for x in res["candidates"]]
                c["n"] += 1
                c["top1"] += cands[0] == h
                c["top1_eq"] += sig[cands[0]] == sig[h]     # equal to truth OR indistinguishable from it
                c["top3"] += h in cands[:3]
                c["abstain"] += res["status"] == "inconsistent"
                if h[0] is None:
                    c["healthy_n"] += 1
                    c["false_alarm"] += res["status"] != "no_fault"
                else:
                    c["fault_n"] += 1
                    c["missed"] += res["status"] == "no_fault"
                conf[(cid, label(*h), label(*cands[0]))] += 1
        per[cid] = c
    return per, conf


def pct(a, b):
    return f"{100 * a / b:.1f}%" if b else "-"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=20, help="random trials per fault")
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    md = ["# REPAIR-AI evaluation", "",
          f"Monte-Carlo test: {a.trials} random trials for every fault (and the healthy circuit) in every circuit, seed {a.seed}.",
          "The engine only knows the **nominal** circuit; the simulated 'real' circuit has random part errors and meter noise.",
          "Single-fault assumption. Ideal simulator, not hardware: treat these numbers as a benchmark of the method.", "",
          "Metrics: **Top-1** = the first suggestion is the true fault. **Top-1 (equiv.)** = the first suggestion is the true fault "
          "or a fault that gives identical readings (e.g. two identical parallel resistors). **Top-3** = the true fault is in the first three.", "",
          "## Accuracy vs component tolerance (all circuits)", "",
          "| Resistor tolerance | Trials | Top-1 | Top-1 (equiv.) | Top-3 | Healthy false-alarm | Fault missed as healthy | 'No fit' warnings |",
          "|---|---|---|---|---|---|---|---|"]
    detail = None
    for tol in TOLS:
        per, conf = run(tol, a.trials, a.seed)
        t = sum(per.values(), Counter())
        md.append(f"| ±{tol * 100:g}% | {t['n']} | {pct(t['top1'], t['n'])} | {pct(t['top1_eq'], t['n'])} | "
                  f"{pct(t['top3'], t['n'])} | {pct(t['false_alarm'], t['healthy_n'])} | "
                  f"{pct(t['missed'], t['fault_n'])} | {pct(t['abstain'], t['n'])} |")
        print(f"tol ±{tol * 100:g}%: top-1 {pct(t['top1'], t['n'])}, equiv {pct(t['top1_eq'], t['n'])}, top-3 {pct(t['top3'], t['n'])}")
        if abs(tol - 0.05) < 1e-9:
            detail = (per, conf)
    per, conf = detail
    md += ["", "## Per circuit at ±5% parts", "", "| Circuit | Top-1 | Top-1 (equiv.) | Top-3 | False alarm |", "|---|---|---|---|---|"]
    for cid, c in per.items():
        md.append(f"| {CIRCUITS[cid]['title']} | {pct(c['top1'], c['n'])} | {pct(c['top1_eq'], c['n'])} | "
                  f"{pct(c['top3'], c['n'])} | {pct(c['false_alarm'], c['healthy_n'])} |")
    wrong = [(n, k) for k, n in conf.items() if k[1] != k[2]]
    wrong.sort(reverse=True)
    md += ["", "## Most common confusions at ±5% parts", "", "| Circuit | True fault | Diagnosed as | Count |", "|---|---|---|---|"]
    md += [f"| {k[0]} | {k[1]} | {k[2]} | {n} |" for n, k in wrong[:10]]
    open(os.path.join(OUT, "evaluation.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")

    rows = defaultdict(Counter)
    for (cid, t, p), n in conf.items():
        rows[f"{cid}: {t}"][f"{cid}: {p}"] += n
    cols = sorted({c for r in rows.values() for c in r})
    with open(os.path.join(OUT, "confusion_5pct.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["true \\ diagnosed"] + cols)
        for r in sorted(rows):
            w.writerow([r] + [rows[r][c] for c in cols])
    print("wrote results/evaluation.md and results/confusion_5pct.csv")


if __name__ == "__main__":
    main()
