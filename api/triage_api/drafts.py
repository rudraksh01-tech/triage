from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from fastembed import TextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder

EMBED_MODEL = "BAAI/bge-small-en-v1.5"
RERANK_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"


@dataclass
class Example:
    brand: str
    ticket: str
    reply: str
    similarity: float
    rerank_score: float | None


class Retriever:
    """Bi-encoder recall over past tickets, cross-encoder rerank of the shortlist."""

    def __init__(self, index_dir: Path, threads: int = 1):
        self.pairs = pd.read_parquet(index_dir / "pairs.parquet")
        self.vectors = np.load(index_dir / "vectors.npy").astype(np.float32)
        self.threads = threads
        self.embedder = TextEmbedding(EMBED_MODEL, threads=threads)
        self._reranker: TextCrossEncoder | None = None

    @property
    def reranker(self) -> TextCrossEncoder:
        # loaded on first use only; the default path doesn't rerank
        if self._reranker is None:
            self._reranker = TextCrossEncoder(RERANK_MODEL, threads=self.threads)
        return self._reranker

    def recall(self, text: str, k: int = 30) -> tuple[list[int], np.ndarray]:
        q = next(iter(self.embedder.query_embed(text)))
        q = q / np.linalg.norm(q)
        sims = self.vectors @ q
        top = np.argpartition(-sims, k)[:k]
        return sorted(top.tolist(), key=lambda i: -sims[i]), sims

    def search(self, text: str, brand: str | None, k: int = 3,
               rerank: bool = False, brand_boost: bool = True) -> list[Example]:
        """Top-k past tickets. Reranking is off by default: on the held-out eval it
        didn't beat plain embedding search (see ml/src/eval_retrieval.py)."""
        idx, sims = self.recall(text)
        candidates = self.pairs.iloc[idx]
        same = [bool(brand) and b.lower() == brand.lower() for b in candidates.brand]
        if rerank:
            # rerank on the past ticket; the reply text adds noise ("please DM us")
            scores = list(self.reranker.rerank(text, candidates.text.tolist()))
            base, boost = scores, 0.5  # cross-encoder logits
        else:
            scores = [None] * len(idx)
            base, boost = [float(sims[i]) for i in idx], 0.05  # cosine
        if not brand_boost:
            boost = 0.0
        order = sorted(range(len(idx)), key=lambda j: -(base[j] + boost * same[j]))
        out = []
        for j in order[:k]:
            row = candidates.iloc[j]
            out.append(Example(brand=row.brand, ticket=row.text, reply=row.reply,
                               similarity=float(sims[idx[j]]),
                               rerank_score=None if scores[j] is None else float(scores[j])))
        return out


DRAFT_SYSTEM = """You write the first public reply from a company's support account on Twitter.
Rules:
- Under 280 characters. Plain text, no hashtags, no emoji.
- Be specific to what the customer said. Never promise refunds or outcomes you can't know.
- If account details are needed, ask them to send a DM. Never ask for passwords or card numbers in public.
- Match the tone of the example replies from real agents, but don't copy them."""


def draft_prompt(text: str, brand: str, examples: list[Example]) -> str:
    shots = "\n\n".join(f"Customer: {e.ticket}\n@{e.brand}: {e.reply}" for e in examples)
    return f"Similar past tickets and how agents replied:\n\n{shots}\n\n---\nReply as @{brand} to:\n{text}"
