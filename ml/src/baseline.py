"""TF-IDF + logistic regression baseline.

Trains on teacher labels, reports on the gold set. Also scores each teacher
against the gold reference, since that number is roughly the ceiling for a
student trained on its labels.

    python ml/src/baseline.py --teacher gemini-3.5-flash-lite
"""
import argparse
import json
import time

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.pipeline import FeatureUnion, Pipeline

from data import ARTIFACTS, LABEL_DIR, TASKS, gold_frame, read_jsonl, train_val

OUT = ARTIFACTS / "baseline"


def make_model() -> Pipeline:
    features = FeatureUnion([
        ("word", TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)),
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=3,
                                 sublinear_tf=True, max_features=200_000)),
    ])
    clf = LogisticRegression(C=4.0, max_iter=2000, class_weight="balanced")
    return Pipeline([("tfidf", features), ("clf", clf)])


def score(y_true, y_pred) -> dict:
    return {"accuracy": round(accuracy_score(y_true, y_pred), 4),
            "macro_f1": round(f1_score(y_true, y_pred, average="macro"), 4)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher", required=True)
    ap.add_argument("--gold", default="reference", help="gold labels to score against: reference or human")
    args = ap.parse_args()

    gold = gold_frame(args.gold)
    print(f"gold: {len(gold)} tickets, reference = {args.gold}\n")

    report = {"teacher": args.teacher, "reference": args.gold,
              "gold_size": len(gold), "teachers_vs_reference": {}}
    for path in sorted(LABEL_DIR.glob("gold.*.jsonl")):
        name = path.stem.removeprefix("gold.")
        if name in ("human", "reference"):
            continue
        t = read_jsonl(path).merge(gold, on="id", suffixes=("_t", ""))
        report["teachers_vs_reference"][name] = {
            task: score(t[task], t[f"{task}_t"]) for task in TASKS}
        print(f"teacher {name:<24}", report["teachers_vs_reference"][name])

    tr, va = train_val(args.teacher)
    print(f"\ntrain {len(tr):,}  val {len(va):,}")

    OUT.mkdir(parents=True, exist_ok=True)
    report["student"] = {}
    for task in TASKS:
        model = make_model().fit(tr.text, tr[task])

        t0 = time.perf_counter()
        pred = model.predict(gold.text)
        ms = (time.perf_counter() - t0) / len(gold) * 1000

        report["student"][task] = {
            "val": score(va[task], model.predict(va.text)),
            "gold": score(gold[task], pred),
            "ms_per_ticket": round(ms, 3),
        }
        print(f"\n== {task}  {report['student'][task]}")
        print(classification_report(gold[task], pred, digits=3, zero_division=0))

        proba = model.predict_proba(gold.text).max(axis=1)
        right = pred == gold[task].to_numpy()
        print(f"confidence when right {np.mean(proba[right]):.3f} "
              f"| when wrong {np.mean(proba[~right]):.3f}")

        joblib.dump(model, OUT / f"{task}.joblib")

    (OUT / "report.json").write_text(json.dumps(report, indent=2))
    print(f"\nsaved to {OUT}")


if __name__ == "__main__":
    main()
