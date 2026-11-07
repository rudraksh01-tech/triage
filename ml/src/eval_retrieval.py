"""Does the cross-encoder rerank actually help the reply drafter?

For held-out stream tickets we know the brand's real first reply. A good
retriever should surface a past reply that says something similar. We score the
top-1 retrieved reply by cosine similarity to the real one (bge-small), and
check how often it comes from the same brand.

Proxy metric, not a human judgement, but it is the same for every method.

    python ml/src/eval_retrieval.py  -> ml/artifacts/retrieval/eval.json
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from data import ARTIFACTS, PROCESSED
from replies import RAW, clean_reply

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "api"))
from triage_api.drafts import Retriever  # noqa: E402

N = 300


def heldout() -> pd.DataFrame:
    raw = pd.read_csv(RAW, usecols=["inbound", "text", "in_response_to_tweet_id"])
    replies = raw[~raw.inbound & raw.in_response_to_tweet_id.notna()]
    replies = replies.astype({"in_response_to_tweet_id": "int64"})
    first = replies.drop_duplicates("in_response_to_tweet_id").set_index("in_response_to_tweet_id").text
    stream = pd.read_parquet(PROCESSED / "stream.parquet").sample(5000, random_state=5)
    df = stream.assign(reply=stream.id.map(first)).dropna(subset=["reply"])
    df = df.assign(reply=df.reply.map(clean_reply))
    return df[df.reply.str.len() > 20].head(N).reset_index(drop=True)


def main() -> None:
    r = Retriever(ARTIFACTS / "retrieval", threads=2)
    df = heldout()
    embed = lambda xs: np.stack(list(r.embedder.embed(xs)))  # noqa: E731
    truth = embed(df.reply.tolist())
    truth /= np.linalg.norm(truth, axis=1, keepdims=True)

    rng = np.random.default_rng(0)
    methods = {
        "random": lambda text, brand: [r.pairs.iloc[int(rng.integers(len(r.pairs)))]],
        "embedding": lambda t, b: r.search(t, b, k=1, rerank=False, brand_boost=False),
        "embedding_brand": lambda t, b: r.search(t, b, k=1, rerank=False, brand_boost=True),
        "rerank": lambda t, b: r.search(t, b, k=1, rerank=True, brand_boost=False),
        "rerank_brand": lambda t, b: r.search(t, b, k=1, rerank=True, brand_boost=True),
    }
    report = {"n": len(df)}
    for name, fn in methods.items():
        t0 = time.perf_counter()
        got = [fn(t, b)[0] for t, b in zip(df.text, df.brand)]
        ms = (time.perf_counter() - t0) / len(df) * 1000
        replies = [g.reply for g in got]
        brands = [g.brand for g in got]
        v = embed(replies)
        v /= np.linalg.norm(v, axis=1, keepdims=True)
        sims = (v * truth).sum(1)
        report[name] = {
            "reply_similarity_mean": round(float(sims.mean()), 4),
            "same_brand_at_1": round(float(np.mean([a.lower() == b.lower() for a, b in zip(brands, df.brand)])), 4),
            "ms_per_query": round(ms, 1),
        }
        print(name, report[name])
    (ARTIFACTS / "retrieval" / "eval.json").write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
