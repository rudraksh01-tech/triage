"""Open-loop load test for /v1/classify.

Requests are fired on a fixed schedule (constant arrival rate) instead of
"send the next one when the last returns", so a slow server shows up as
latency instead of quietly lowering the request rate.

LLM escalation is turned off for the run (TRIAGE_LLM_RPM=0 on the server)
so this measures the service, not Google's free tier.

    python loadtest/run.py --url http://127.0.0.1:8000
"""
import argparse
import asyncio
import json
import random
import statistics
import time
from pathlib import Path

import httpx
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = [("steady", 20, 30), ("busy", 50, 30), ("outage spike", 100, 20), ("overload", 200, 15)]  # name, req/s, seconds


async def scenario(client, texts, name, rps, seconds) -> dict:
    lat, failed = [], 0
    interval = 1 / rps
    start = time.perf_counter()

    async def one(text):
        nonlocal failed
        t0 = time.perf_counter()
        try:
            r = await client.post("/v1/classify", json={"text": text})
            r.raise_for_status()
            lat.append((time.perf_counter() - t0) * 1000)
        except httpx.HTTPError:
            failed += 1

    tasks = []
    for i in range(int(rps * seconds)):
        delay = start + i * interval - time.perf_counter()
        if delay > 0:
            await asyncio.sleep(delay)
        tasks.append(asyncio.create_task(one(random.choice(texts))))
    await asyncio.gather(*tasks)
    elapsed = time.perf_counter() - start

    lat.sort()
    q = lambda p: lat[min(len(lat) - 1, int(p * len(lat)))] if lat else 0  # noqa: E731
    out = {"name": name, "rps": len(tasks) / elapsed, "requests": len(tasks), "failed": failed,
           "p50_ms": round(statistics.median(lat), 1) if lat else 0,
           "p95_ms": round(q(0.95), 1), "p99_ms": round(q(0.99), 1)}
    print(out)
    return out


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--variant", default="batched", help="label for this server config")
    args = ap.parse_args()

    texts = pd.read_parquet(ROOT / "ml/data/processed/stream.parquet").text.sample(2000, random_state=3).tolist()
    limits = httpx.Limits(max_connections=200, max_keepalive_connections=200)
    async with httpx.AsyncClient(base_url=args.url, timeout=30, limits=limits) as client:
        await client.post("/v1/classify", json={"text": "warm up"})
        results = [await scenario(client, texts, *s) for s in SCENARIOS]

    out = ROOT / "loadtest/results.json"
    data = json.loads(out.read_text()) if out.exists() else {}
    data.setdefault("runs", {})[args.variant] = results
    data["machine"] = "2-core laptop CPU, load generator on the same machine"
    out.write_text(json.dumps(data, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
