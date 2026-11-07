"""Carve the ticket pool into gold / train / stream.

gold   - hand-checked test set, never used for training or threshold tuning
train  - teacher-labelled, split later into train/val
stream - unlabelled, replayed into the live inbox demo
"""
import html
from pathlib import Path

import pandas as pd

PROCESSED = Path("ml/data/processed")
GOLD_SIZE = 400
TRAIN_SIZE = 20_000
SEED = 13


def main() -> None:
    pool = pd.read_parquet(PROCESSED / "tickets.parquet")
    # decoded here rather than in prepare.py so the sampled ticket set stays fixed
    pool["text"] = pool.text.map(html.unescape)

    # gold is spread across brands so no single company dominates the test set
    per_brand = max(1, GOLD_SIZE // pool.brand.nunique() + 1)
    gold = (pool.sample(frac=1, random_state=SEED)
                .groupby("brand").head(per_brand)
                .sample(GOLD_SIZE, random_state=SEED))

    rest = pool.drop(gold.index)
    train = rest.sample(TRAIN_SIZE, random_state=SEED)
    stream = rest.drop(train.index)

    for name, part in [("gold", gold), ("train", train), ("stream", stream)]:
        part.reset_index(drop=True).to_parquet(PROCESSED / f"{name}.parquet", index=False)
        print(f"{name:<6} {len(part):>7,}  brands={part.brand.nunique()}")


if __name__ == "__main__":
    main()
