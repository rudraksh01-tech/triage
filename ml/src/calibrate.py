"""Temperature-scale the student and pick the cascade threshold.

Routing rule: a ticket stays with the student if min(p_category, p_priority)
>= threshold, otherwise it goes to the LLM.

The threshold is chosen on the validation split, where the "LLM answer" is the
teacher label itself, so escalating is always "correct" there. That makes the
val curve a clean measure of how often the student disagrees with the teacher
on what it keeps. Gold is only used to report.

    python ml/src/calibrate.py --run full
"""
import argparse
import json

import numpy as np
from sklearn.metrics import f1_score

from data import ARTIFACTS, LABEL_DIR, TASKS, gold_frame, read_jsonl

LLMS = ["gemini-3.5-flash-lite", "gemini-3.5-flash"]


def softmax(z: np.ndarray, t: float = 1.0) -> np.ndarray:
    z = z / t
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def nll(logits, y, t) -> float:
    p = softmax(logits, t)[np.arange(len(y)), y]
    return float(-np.log(np.clip(p, 1e-12, None)).mean())


def fit_temperature(logits, y) -> float:
    grid = np.exp(np.linspace(np.log(0.3), np.log(6), 400))
    return float(grid[np.argmin([nll(logits, y, t) for t in grid])])


def ece(probs, y, bins=10) -> float:
    conf, pred = probs.max(1), probs.argmax(1)
    edges = np.linspace(0, 1, bins + 1)
    total = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf > lo) & (conf <= hi)
        if m.any():
            total += m.mean() * abs((pred[m] == y[m]).mean() - conf[m].mean())
    return float(total)


def cascade(conf, student, fallback, truth, t):
    keep = conf >= t
    pred = np.where(keep[:, None], student, fallback)
    acc = (pred == truth).mean(axis=0)
    f1 = [f1_score(truth[:, k], pred[:, k], average="macro") for k in range(truth.shape[1])]
    return float(1 - keep.mean()), acc, f1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--target", type=float, default=0.92,
                    help="min mean val agreement with the teacher")
    args = ap.parse_args()

    run = ARTIFACTS / "student" / args.run
    z = np.load(run / "logits.npz")
    tasks = list(TASKS)

    temps, report = {}, {"run": args.run, "tasks": {}}
    for k, task in enumerate(tasks):
        T = fit_temperature(z[f"val_{task}"], z["y_val"][:, k])
        temps[task] = T
        raw, cal = softmax(z[f"gold_{task}"]), softmax(z[f"gold_{task}"], T)
        report["tasks"][task] = {
            "temperature": round(T, 3),
            "gold_ece_before": round(ece(raw, z["y_gold"][:, k]), 4),
            "gold_ece_after": round(ece(cal, z["y_gold"][:, k]), 4),
        }
    print("temperatures", temps)

    def probs(split):
        return [softmax(z[f"{split}_{t}"], temps[t]) for t in tasks]

    # validation: teacher label is both truth and fallback
    pv = probs("val")
    conf_v = np.minimum(*[p.max(1) for p in pv])
    stud_v = np.stack([p.argmax(1) for p in pv], 1)
    grid = np.round(np.linspace(0, 1, 101), 2)
    val_curve = []
    for t in grid:
        esc, acc, _ = cascade(conf_v, stud_v, z["y_val"], z["y_val"], t)
        val_curve.append((t, esc, float(acc.mean())))
    ok = [(t, esc) for t, esc, a in val_curve if a >= args.target]
    threshold = min(ok, key=lambda x: x[1])[0] if ok else 1.0
    print(f"threshold {threshold} (target val agreement {args.target})")

    # gold: compare student-only, LLM-only and the cascade against the reference
    gold = gold_frame()
    truth = z["y_gold"]
    pg = probs("gold")
    conf_g = np.minimum(*[p.max(1) for p in pg])
    stud_g = np.stack([p.argmax(1) for p in pg], 1)

    report["threshold"] = threshold
    report["temperatures"] = temps
    report["gold"] = {"size": len(gold), "student_only": {}, "llm_only": {}, "curves": {}}
    report["gold"]["student_only"] = {
        t: {"accuracy": float((stud_g[:, k] == truth[:, k]).mean()),
            "macro_f1": float(f1_score(truth[:, k], stud_g[:, k], average="macro"))}
        for k, t in enumerate(tasks)}

    for llm in LLMS:
        lab = read_jsonl(LABEL_DIR / f"gold.{llm}.jsonl").set_index("id")
        missing = (~gold.id.isin(lab.index)).sum()
        if missing:
            # flash hit its 20 requests/day free limit part way through gold
            print(f"{llm}: skipped, {missing} gold tickets unlabelled")
            continue
        fb = np.stack([lab.loc[gold.id, t].map({c: i for i, c in enumerate(TASKS[t])}).to_numpy()
                       for t in tasks], 1)
        _, acc, f1 = cascade(conf_g, stud_g, fb, truth, 1.01)
        report["gold"]["llm_only"][llm] = {
            t: {"accuracy": float(acc[k]), "macro_f1": float(f1[k])} for k, t in enumerate(tasks)}
        curve = []
        for t in grid:
            esc, acc, f1 = cascade(conf_g, stud_g, fb, truth, t)
            curve.append({"threshold": float(t), "escalated": esc,
                          **{f"{task}_accuracy": float(acc[k]) for k, task in enumerate(tasks)},
                          **{f"{task}_macro_f1": float(f1[k]) for k, task in enumerate(tasks)}})
        report["gold"]["curves"][llm] = curve
        at = next(p for p in curve if p["threshold"] == threshold)
        print(f"{llm:<22} at t={threshold}: escalated {at['escalated']:.1%}  "
              f"cat acc {at['category_accuracy']:.3f}  pri acc {at['priority_accuracy']:.3f}  "
              f"| llm-only cat {report['gold']['llm_only'][llm]['category']['accuracy']:.3f}")

    so = report["gold"]["student_only"]
    print(f"student only: cat {so['category']['accuracy']:.3f}  pri {so['priority']['accuracy']:.3f}")
    print(json.dumps(report["tasks"], indent=1))
    (run / "cascade.json").write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
