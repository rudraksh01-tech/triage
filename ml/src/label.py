"""Label tickets with an LLM teacher.

Resumable: results are appended to ml/data/labels/<split>.jsonl and finished
ids are skipped on the next run, so it's safe to stop and restart (free tiers
run out of quota mid-way all the time).

    python ml/src/label.py gold
    python ml/src/label.py train --limit 2000
"""
import argparse
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
from taxonomy import CATEGORIES, PRIORITIES  # noqa: E402

PROCESSED = Path("ml/data/processed")
LABELS = Path("ml/data/labels")
RETRY_IN = re.compile(r"retry in ([\d.]+)s")

SYSTEM = f"""You triage customer support tweets sent to companies.
For each tweet pick exactly one category and one priority.

Categories:
{chr(10).join(f"- {k}: {v}" for k, v in CATEGORIES.items())}

Priorities:
{chr(10).join(f"- {k}: {v}" for k, v in PRIORITIES.items())}

The company handle is in the tweet. Judge only what the customer wrote.
Reply with JSON only: {{"labels": [{{"i": 1, "category": "...", "priority": "..."}}, ...]}}
One entry per tweet, same order, same numbering."""


def build_prompt(texts: list[str]) -> str:
    return "\n".join(f"{i}. {t}" for i, t in enumerate(texts, 1))


def parse(content: str, n: int) -> list[dict]:
    rows = json.loads(content)["labels"]
    by_i = {int(r["i"]): r for r in rows}
    out = []
    for i in range(1, n + 1):
        r = by_i[i]
        if r["category"] not in CATEGORIES or r["priority"] not in PRIORITIES:
            raise ValueError(f"bad label {r}")
        out.append({"category": r["category"], "priority": r["priority"]})
    return out


class Teacher:
    def __init__(self, model: str | None = None) -> None:
        load_dotenv(Path(".env"))
        self.model = model or os.environ["LABEL_MODEL"]
        self.reasoning = os.environ.get("LABEL_REASONING")
        self.client = httpx.Client(
            base_url=os.environ["LABEL_BASE_URL"].rstrip("/") + "/",
            headers={"Authorization": f"Bearer {os.environ['LABEL_API_KEY']}"},
            timeout=180,
        )

    def label(self, texts: list[str]) -> list[dict]:
        body = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": build_prompt(texts)},
            ],
        }
        if self.reasoning:
            body["reasoning_effort"] = self.reasoning
        for attempt in range(12):
            try:
                r = self.client.post("chat/completions", json=body)
            except httpx.TimeoutException:
                print("  timeout, retrying", flush=True)
                continue
            if r.status_code == 429 or r.status_code >= 500:
                hint = RETRY_IN.search(r.text)
                wait = float(hint.group(1)) + 1 if hint else min(60, 5 * 2 ** attempt)
                print(f"  {r.status_code}, waiting {wait:.0f}s", flush=True)
                time.sleep(wait)
                continue
            if r.is_error:
                raise RuntimeError(f"{r.status_code}: {r.text[:300]}")
            try:
                return parse(r.json()["choices"][0]["message"]["content"], len(texts))
            except (KeyError, ValueError, json.JSONDecodeError) as e:
                print(f"  unparseable batch ({e}), retrying", flush=True)
        raise RuntimeError("teacher kept failing on this batch")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("split", choices=["gold", "train"])
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--model", default=None, help="override LABEL_MODEL")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--batch", type=int, default=20)
    args = ap.parse_args()

    teacher = Teacher(args.model)
    df = pd.read_parquet(PROCESSED / f"{args.split}.parquet")
    LABELS.mkdir(parents=True, exist_ok=True)
    out_path = LABELS / f"{args.split}.{teacher.model}.jsonl"

    done = set()
    if out_path.exists():
        done = {json.loads(line)["id"] for line in out_path.open(encoding="utf-8")}
    todo = df[~df.id.isin(done)]
    if args.limit:
        todo = todo.head(args.limit)
    print(f"{teacher.model}: {len(done):,} done, {len(todo):,} to go")

    chunks = [todo.iloc[s:s + args.batch] for s in range(0, len(todo), args.batch)]
    lock = threading.Lock()
    finished = len(done)

    def run(chunk: pd.DataFrame) -> None:
        nonlocal finished
        try:
            labels = teacher.label(chunk.text.tolist())
        except RuntimeError as e:
            # leave it for the next run instead of killing the whole job
            print(f"  gave up on a batch: {e}", flush=True)
            return
        with lock:
            for tid, lab in zip(chunk.id, labels):
                f.write(json.dumps({"id": int(tid), **lab, "teacher": teacher.model}) + "\n")
            f.flush()
            finished += len(chunk)
            print(f"{finished:,}/{len(df):,}", flush=True)

    with out_path.open("a", encoding="utf-8") as f, \
            ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(run, chunks))


if __name__ == "__main__":
    main()
