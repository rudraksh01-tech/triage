"""Pair each train ticket with the brand's first public reply.

These pairs back the reply drafter: for a new ticket we retrieve similar past
tickets and show the model how the brand actually answered them. Only the
train split is used so gold/stream tickets never see their own answer.

    python ml/src/replies.py   -> ml/data/processed/replies.parquet
"""
import html
import re

import pandas as pd

from data import PROCESSED

RAW = "ml/data/raw/twcs.csv"
SIGNOFF = re.compile(r"\s*(\^|-|–)\s*\w{1,4}\s*$")  # "^JB", "-Sam" style initials
HANDLE = re.compile(r"@\w+")
URL = re.compile(r"https?://\S+")


def clean_reply(text: str) -> str:
    text = html.unescape(text)
    text = URL.sub("<url>", text)
    text = HANDLE.sub("", text)
    text = SIGNOFF.sub("", text)
    return " ".join(text.split())


def main() -> None:
    raw = pd.read_csv(RAW, usecols=["inbound", "text", "in_response_to_tweet_id"])
    replies = raw[~raw.inbound & raw.in_response_to_tweet_id.notna()]
    replies = replies.astype({"in_response_to_tweet_id": "int64"})
    first = replies.drop_duplicates("in_response_to_tweet_id").set_index("in_response_to_tweet_id").text

    train = pd.read_parquet(PROCESSED / "train.parquet")
    out = train.assign(reply=train.id.map(first)).dropna(subset=["reply"])
    out = out.assign(reply=out.reply.map(clean_reply))
    # "please DM us" answers are useless as examples of tone or content on their own,
    # but they are the honest majority, so keep them and let the reranker decide
    out = out[out.reply.str.len() > 20][["id", "brand", "text", "reply"]]
    out.to_parquet(PROCESSED / "replies.parquet", index=False)
    print(f"{len(out):,} ticket/reply pairs")
    for r in out.sample(5, random_state=1).itertuples():
        print(f"\n[{r.brand}] {r.text[:120]}\n  -> {r.reply[:160]}")


if __name__ == "__main__":
    main()
