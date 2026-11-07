"""Build the ticket pool from raw TWCS.

A "ticket" is a customer's opening tweet that a brand account replied to.
Output: ml/data/processed/tickets.parquet (id, brand, created_at, text).
"""
import re
from pathlib import Path

import pandas as pd

RAW = Path("ml/data/raw/twcs.csv")
OUT = Path("ml/data/processed/tickets.parquet")

PER_BRAND_CAP = 1500
MIN_BRAND_TICKETS = 300
SEED = 13

URL = re.compile(r"https?://\S+")
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")
PHONE = re.compile(r"(?<!\w)\+?\d[\d\s-]{7,}\d(?!\w)")
USER_ID = re.compile(r"@\d+\b")  # TWCS replaces customer handles with numeric ids
LONG_NUM = re.compile(r"\b\d{9,}\b")  # account / order numbers
SPACES = re.compile(r"\s+")


def clean(text: str) -> str:
    text = text.replace("�", "'")
    text = URL.sub("<url>", text)
    text = EMAIL.sub("<email>", text)
    text = PHONE.sub("<phone>", text)
    text = LONG_NUM.sub("<num>", text)
    text = USER_ID.sub("@user", text)
    return SPACES.sub(" ", text).strip()


def mostly_ascii(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and sum(c.isascii() for c in letters) / len(letters) > 0.9


def main() -> None:
    df = pd.read_csv(RAW, dtype={"author_id": str})

    openers = df[df.inbound & df.in_response_to_tweet_id.isna()]

    replies = df.loc[~df.inbound & df.in_response_to_tweet_id.notna(),
                     ["author_id", "in_response_to_tweet_id"]]
    replies = replies.astype({"in_response_to_tweet_id": "int64"})
    first_reply = replies.drop_duplicates("in_response_to_tweet_id")
    brand_of = first_reply.set_index("in_response_to_tweet_id").author_id

    t = openers.assign(brand=openers.tweet_id.map(brand_of)).dropna(subset=["brand"])
    t = t.assign(text=t.text.map(clean))
    t = t[t.text.map(mostly_ascii)]

    # strip handles to measure whether there is an actual message left
    body = t.text.str.replace(r"@\w+", "", regex=True).str.strip()
    keep = (body.str.len() >= 15) & ~body.str.lower().duplicated()
    t = t[keep]

    counts = t.brand.value_counts()
    t = t[t.brand.isin(counts[counts >= MIN_BRAND_TICKETS].index)]

    t = t.sample(frac=1, random_state=SEED).groupby("brand").head(PER_BRAND_CAP)

    t = t.assign(created_at=pd.to_datetime(t.created_at, format="%a %b %d %H:%M:%S %z %Y"))
    out = (t.rename(columns={"tweet_id": "id"})[["id", "brand", "created_at", "text"]]
             .sample(frac=1, random_state=SEED)
             .reset_index(drop=True))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)
    print(f"{len(out):,} tickets from {out.brand.nunique()} brands -> {OUT}")
    print(out.brand.value_counts().describe().round(0).to_string())


if __name__ == "__main__":
    main()
