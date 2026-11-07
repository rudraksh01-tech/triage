import asyncio
import logging
import time
from collections import Counter
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .artifacts import sync_from_s3
from .batcher import MicroBatcher
from .drafts import DRAFT_SYSTEM, Retriever, draft_prompt
from .llm import LLM, BudgetExceeded
from .settings import get_settings
from .student import Student

log = logging.getLogger("triage")


class TicketIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    brand: str | None = Field(default=None, max_length=64)


class BatchIn(BaseModel):
    tickets: list[TicketIn] = Field(min_length=1, max_length=64)


class Classified(BaseModel):
    category: str
    priority: str
    confidence: float
    route: str  # "model" | "llm" | "deferred" (wanted the LLM, budget said no)
    model_ms: float
    llm_ms: float | None = None
    student: dict[str, str]
    probs: dict[str, dict[str, float]]


class Stats:
    def __init__(self):
        self.routes: Counter[str] = Counter()
        self.started = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    if s.artifacts_s3_uri:
        await asyncio.to_thread(sync_from_s3, s.artifacts_s3_uri, s.artifacts_cache)
        s.model_dir, s.index_dir = s.artifacts_cache / "serving", s.artifacts_cache / "retrieval"
    app.state.student = Student(s.model_dir, s.threads)
    app.state.llm = LLM(s.llm_base_url, s.llm_api_key, s.llm_model, s.llm_rpm, s.llm_timeout_s)
    app.state.retriever = None
    if (s.index_dir / "vectors.npy").exists():
        app.state.retriever = await asyncio.to_thread(Retriever, s.index_dir, s.threads)
    app.state.stats = Stats()
    app.state.batcher = None
    if s.max_batch > 1:
        app.state.batcher = MicroBatcher(app.state.student.predict, s.max_batch, s.max_wait_ms / 1000)
        app.state.batcher.start()
    yield
    if app.state.batcher:
        await app.state.batcher.stop()
    await app.state.llm.close()


app = FastAPI(title="Triage", version="1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins,
                   allow_methods=["GET", "POST"], allow_headers=["content-type"])


async def route(student: Student, llm: LLM, text: str, pred, model_ms: float) -> Classified:
    base = dict(confidence=round(pred.confidence, 4), model_ms=round(model_ms, 2),
                student={"category": pred.category, "priority": pred.priority}, probs=pred.probs)
    if pred.confidence >= student.threshold:
        return Classified(category=pred.category, priority=pred.priority, route="model", **base)

    t0 = time.perf_counter()
    try:
        label = await llm.classify(text, student.descriptions)
    except BudgetExceeded:
        return Classified(category=pred.category, priority=pred.priority, route="deferred", **base)
    except (httpx.HTTPError, ValueError) as e:
        log.warning("llm fallback failed: %s", e)
        return Classified(category=pred.category, priority=pred.priority, route="deferred", **base)
    return Classified(**label, route="llm", llm_ms=round((time.perf_counter() - t0) * 1000, 1), **base)


@app.get("/health")
async def health():
    st = app.state
    return {"ok": True, "model": st.student.base, "threshold": st.student.threshold,
            "retrieval": st.retriever is not None,
            "llm_budget_left": st.llm.limiter.remaining(),
            "routes": dict(st.stats.routes),
            "mean_batch": round(st.batcher.items / st.batcher.batches, 2)
            if getattr(st, "batcher", None) and st.batcher.batches else None}


@app.post("/v1/classify", response_model=Classified)
async def classify(ticket: TicketIn):
    st = app.state
    t0 = time.perf_counter()
    batcher = getattr(st, "batcher", None)
    if batcher:
        pred = await batcher.submit(ticket.text)
    else:
        [pred] = await asyncio.to_thread(st.student.predict, [ticket.text])
    out = await route(st.student, st.llm, ticket.text, pred, (time.perf_counter() - t0) * 1000)
    st.stats.routes[out.route] += 1
    return out


@app.post("/v1/classify/batch", response_model=list[Classified])
async def classify_batch(batch: BatchIn):
    st = app.state
    texts = [t.text for t in batch.tickets]
    t0 = time.perf_counter()
    preds = await asyncio.to_thread(st.student.predict, texts)
    per = (time.perf_counter() - t0) * 1000 / len(texts)
    outs = await asyncio.gather(*(route(st.student, st.llm, t, p, per) for t, p in zip(texts, preds)))
    st.stats.routes.update(o.route for o in outs)
    return outs


class DraftOut(BaseModel):
    draft: str | None
    examples: list[dict]
    reason: str | None = None


@app.post("/v1/draft", response_model=DraftOut)
async def draft(ticket: TicketIn):
    st = app.state
    if st.retriever is None:
        raise HTTPException(503, "retrieval index not loaded")
    brand = ticket.brand or "support"
    examples = await asyncio.to_thread(st.retriever.search, ticket.text, ticket.brand)
    ex = [e.__dict__ for e in examples]
    try:
        text = await st.llm.chat(DRAFT_SYSTEM, draft_prompt(ticket.text, brand, examples))
    except BudgetExceeded:
        return DraftOut(draft=None, examples=ex, reason="LLM budget for this minute is used up")
    except httpx.HTTPError as e:
        log.warning("draft failed: %s", e)
        return DraftOut(draft=None, examples=ex, reason="LLM unavailable")
    return DraftOut(draft=text.strip()[:400], examples=ex)
