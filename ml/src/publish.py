"""Collect measured results for the web app.

Writes:
  web/src/data/results.json         numbers behind the /metrics page
  web/src/data/sample-tickets.json  80 gold tickets run through the real cascade,
                                    shown when no live gateway is connected

    python ml/src/publish.py --run full --lora-run lora
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import pandas as pd

from data import ARTIFACTS, PROCESSED, gold_frame

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "api"))
from triage_api.llm import LLM, BudgetExceeded  # noqa: E402
from triage_api.settings import get_settings  # noqa: E402
from triage_api.student import Student  # noqa: E402

WEB_DATA = ROOT / "web/src/data"
SAMPLE_SIZE = 80


def load(path: Path) -> dict | None:
    return json.loads(path.read_text()) if path.exists() else None


def student_summary(run: str) -> dict | None:
    meta = load(ARTIFACTS / "student" / run / "meta.json")
    if not meta:
        return None
    return {k: meta[k] for k in ("base", "lora", "trainable_params", "total_params", "train_minutes",
                                 "epochs", "gold_macro_f1", "gold_accuracy", "history")}


async def build_sample(student: Student) -> list[dict]:
    s = get_settings()
    llm = LLM(s.llm_base_url, s.llm_api_key, s.llm_model, rpm=s.llm_rpm, timeout=s.llm_timeout_s)
    keep = gold_frame().id  # skips the non-English tickets left out of gold
    gold = pd.read_parquet(PROCESSED / "gold.parquet")
    gold = gold[gold.id.isin(keep)].sample(SAMPLE_SIZE, random_state=11)

    out, t_start = [], int(time.time() * 1000)
    for k, row in enumerate(gold.itertuples()):
        t0 = time.perf_counter()
        [p] = student.predict([row.text])
        model_ms = (time.perf_counter() - t0) * 1000
        cat, pri, route, llm_ms = p.category, p.priority, "model", None
        if p.confidence < student.threshold:
            t1 = time.perf_counter()
            try:
                label = await llm.classify(row.text, student.descriptions)
                cat, pri, route = label["category"], label["priority"], "llm"
                llm_ms = (time.perf_counter() - t1) * 1000
            except BudgetExceeded:
                route = "deferred"
            # stay under the free-tier rate limit
            await asyncio.sleep(4.5)
        received = t_start - (SAMPLE_SIZE - k) * 23_000
        out.append({
            "id": str(row.id), "brand": row.brand, "text": row.text,
            "receivedAt": received, "doneAt": received + int(model_ms + (llm_ms or 0)), "burst": False,
            "category": cat, "priority": pri, "confidence": round(p.confidence, 4), "route": route,
            "modelMs": round(model_ms, 2), "llmMs": None if llm_ms is None else round(llm_ms, 1),
            "student": {"category": p.category, "priority": p.priority},
            "probs": {t: {k2: round(v, 4) for k2, v in d.items()} for t, d in p.probs.items()},
        })
    await llm.close()
    return out[::-1]  # newest first


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--lora-run", default=None)
    ap.add_argument("--skip-sample", action="store_true")
    args = ap.parse_args()

    cascade = load(ARTIFACTS / "student" / args.run / "cascade.json")
    tickets = pd.read_parquet(PROCESSED / "tickets.parquet", columns=["brand"])
    results = {
        "threshold": cascade["threshold"],
        "data": {
            "tickets": len(tickets), "brands": int(tickets.brand.nunique()),
            "gold": len(gold_frame()), "train": 18_000, "val": 2_000,
            "teacher": "gemini-3.5-flash-lite",
        },
        "baseline": load(ARTIFACTS / "baseline" / "report.json"),
        "students": {"full": student_summary(args.run)},
        "calibration": cascade["tasks"],
        "cascade": cascade["gold"],
        "export": load(ARTIFACTS / "serving" / "export_report.json"),
        "retrieval": load(ARTIFACTS / "retrieval" / "eval.json"),
        "loadtest": load(ROOT / "loadtest" / "results.json"),
    }
    if args.lora_run:
        results["students"]["lora"] = student_summary(args.lora_run)
        lora_cascade = load(ARTIFACTS / "student" / args.lora_run / "cascade.json")
        if lora_cascade:
            results["students"]["lora"]["student_only"] = lora_cascade["gold"]["student_only"]
    results["students"]["full"]["student_only"] = cascade["gold"]["student_only"]

    WEB_DATA.mkdir(parents=True, exist_ok=True)
    (WEB_DATA / "results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    print("wrote results.json")

    if not args.skip_sample:
        student = Student(ARTIFACTS / "serving")
        sample = asyncio.run(build_sample(student))
        (WEB_DATA / "sample-tickets.json").write_text(json.dumps(sample, indent=1, ensure_ascii=False), encoding="utf-8")
        routes = pd.Series([t["route"] for t in sample]).value_counts().to_dict()
        print(f"wrote {len(sample)} sample tickets {routes}")


if __name__ == "__main__":
    main()
