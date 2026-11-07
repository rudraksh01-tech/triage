import json
from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split

from taxonomy import LABELS, PRIORITY_LEVELS

PROCESSED = Path("ml/data/processed")
LABEL_DIR = Path("ml/data/labels")
ARTIFACTS = Path("ml/artifacts")
TASKS = {"category": LABELS, "priority": PRIORITY_LEVELS}
SEED = 13


def read_jsonl(path: Path) -> pd.DataFrame:
    rows = [json.loads(line) for line in path.open(encoding="utf-8")]
    return pd.DataFrame(rows).drop_duplicates("id", keep="last")


def gold_frame(reference: str = "reference") -> pd.DataFrame:
    ref = read_jsonl(LABEL_DIR / f"gold.{reference}.jsonl")
    if "skip" in ref:
        ref = ref[ref.skip.isna() | (ref.skip == False)]  # noqa: E712
    text = pd.read_parquet(PROCESSED / "gold.parquet")[["id", "text"]]
    return ref[["id", *TASKS]].merge(text, on="id").reset_index(drop=True)


def train_val(teacher: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    labels = read_jsonl(LABEL_DIR / f"train.{teacher}.jsonl")
    df = pd.read_parquet(PROCESSED / "train.parquet").merge(labels, on="id")
    tr, va = train_test_split(df, test_size=0.1, random_state=SEED, stratify=df.category)
    return tr.reset_index(drop=True), va.reset_index(drop=True)
