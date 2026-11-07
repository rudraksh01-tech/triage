"""Embed past tickets for reply retrieval.

    python ml/src/index.py  -> ml/artifacts/retrieval/{vectors.npy, pairs.parquet}
"""
import time

import numpy as np
import pandas as pd
from fastembed import TextEmbedding

from data import ARTIFACTS, PROCESSED

EMBED_MODEL = "BAAI/bge-small-en-v1.5"
OUT = ARTIFACTS / "retrieval"


def main() -> None:
    pairs = pd.read_parquet(PROCESSED / "replies.parquet")
    model = TextEmbedding(EMBED_MODEL, threads=2)

    t0 = time.time()
    vecs = np.stack(list(model.embed(pairs.text.tolist(), batch_size=128)))
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    print(f"embedded {len(vecs):,} in {time.time() - t0:.0f}s, dim {vecs.shape[1]}")

    OUT.mkdir(parents=True, exist_ok=True)
    np.save(OUT / "vectors.npy", vecs.astype(np.float16))  # halves size, recall unchanged
    pairs.to_parquet(OUT / "pairs.parquet", index=False)


if __name__ == "__main__":
    main()
