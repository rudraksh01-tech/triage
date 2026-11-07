import pandas as pd

df = pd.read_csv("ml/data/raw/twcs.csv", dtype={"author_id": str})
print("rows", len(df))

first = df[df.inbound & df.in_response_to_tweet_id.isna()].copy()
print("customer openers", len(first))

# which brand replied to the opener
replies = df[~df.inbound][["tweet_id", "author_id", "in_response_to_tweet_id"]]
replies = replies.dropna(subset=["in_response_to_tweet_id"])
replies["in_response_to_tweet_id"] = replies.in_response_to_tweet_id.astype("int64")
brand = replies.drop_duplicates("in_response_to_tweet_id").set_index("in_response_to_tweet_id").author_id
first["brand"] = first.tweet_id.map(brand)
print("openers with a brand reply", first.brand.notna().sum())
print(first.brand.value_counts().head(30).to_string())

first["len"] = first.text.str.len()
print(first.len.describe().round(1).to_string())
for t in first.dropna(subset=["brand"]).sample(15, random_state=7).text:
    print("-", t[:200].replace("\n", " "))
