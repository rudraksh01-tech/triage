# API reference

FastAPI service in `api/`. Interactive docs at `http://localhost:8000/docs` when it's running.

## `POST /v1/classify`

Label one ticket.

```bash
curl -s localhost:8000/v1/classify \
  -H 'content-type: application/json' \
  -d '{"text": "I was charged twice for my order and still no refund", "brand": "AmazonHelp"}'
```

```json
{
  "category": "billing",
  "priority": "high",
  "confidence": 0.8238,
  "route": "model",
  "model_ms": 2.7,
  "llm_ms": null,
  "student": { "category": "billing", "priority": "high" },
  "probs": {
    "category": { "billing": 0.97, "delivery": 0.02, "account": 0.0, "...": "5 more" },
    "priority": { "high": 0.82, "medium": 0.16, "low": 0.02 }
  }
}
```

(A real response from the served model, trimmed to the top category probabilities.)

| Field | Meaning |
|---|---|
| `category`, `priority` | The final label |
| `confidence` | The weaker of the two calibrated top probabilities |
| `route` | `model`: accepted as is. `llm`: the LLM was asked and its label is final. `deferred`: the LLM was needed but unavailable, so the model's label was kept |
| `model_ms`, `llm_ms` | Time spent in each |
| `student` | What the small model said, even when the LLM overruled it |
| `probs` | Calibrated probabilities for every label |

Request body: `text` (1–1,000 characters, required), `brand` (optional, up to 64 characters).
Invalid input returns `422`.

## `POST /v1/classify/batch`

Up to 64 tickets in one call; one model run for all of them, then each is routed on its own.

```json
{ "tickets": [ { "text": "app keeps crashing" }, { "text": "where is my parcel" } ] }
```

Returns a list in the same order, each shaped like the single response.

## `POST /v1/draft`

Draft a first public reply. Retrieves the three most similar past tickets (favouring the same
company) and gives them, with the real agents' replies, to the LLM as examples.

```bash
curl -s localhost:8000/v1/draft \
  -H 'content-type: application/json' \
  -d '{"text": "ordered a phone 5 days ago, tracking says delivered but nothing here", "brand": "AmazonHelp"}'
```

```json
{
  "draft": "We are sorry to hear your phone hasn't arrived. Have you checked around your porch or with neighbors to see if it was left nearby? Please send us a DM with your order details so we can look into this for you.",
  "examples": [
    {
      "brand": "AmazonHelp",
      "ticket": "@AmazonHelp its says that my product has delivere but i haven't received it ye",
      "reply": "I'm sorry for this wait. Do you have a Safe Space designated for your deliveries?",
      "similarity": 0.832,
      "rerank_score": null
    }
  ],
  "reason": null
}
```

When the LLM is unavailable, `draft` is `null`, `reason` says why, and `examples` are still returned.
Returns `503` if the retrieval index isn't loaded.

## `GET /health`

```json
{
  "ok": true,
  "model": "sentence-transformers/all-MiniLM-L6-v2",
  "threshold": 0.65,
  "retrieval": true,
  "llm_budget_left": 0,
  "routes": { "model": 444, "llm": 10, "deferred": 361 },
  "mean_batch": null
}
```

`routes` counts tickets since the process started. The numbers above are from a real demo session
on the day the LLM's free daily quota ran out, which is why so many are `deferred`.

## Configuration

Environment variables, all prefixed `TRIAGE_`. A `.env` at the repository root is read automatically.

| Variable | Default | Meaning |
|---|---|---|
| `TRIAGE_LLM_API_KEY` | – | Gemini API key (free at Google AI Studio) |
| `TRIAGE_LLM_MODEL` | `gemini-3.5-flash-lite` | Any model on the OpenAI-compatible endpoint |
| `TRIAGE_LLM_BASE_URL` | Gemini's OpenAI endpoint | Point at Groq or any other OpenAI-compatible API |
| `TRIAGE_LLM_RPM` | `12` | LLM calls allowed per minute; `0` turns escalation off |
| `TRIAGE_LLM_TIMEOUT_S` | `20` | Per-call timeout |
| `TRIAGE_MODEL_DIR` | `ml/artifacts/serving` | ONNX model, tokenizer and calibration config |
| `TRIAGE_INDEX_DIR` | `ml/artifacts/retrieval` | Reply-retrieval index; drafting is off if missing |
| `TRIAGE_ARTIFACTS_S3_URI` | – | `s3://bucket/prefix` to download both folders at startup |
| `TRIAGE_THREADS` | `1` | ONNX threads per request |
| `TRIAGE_MAX_BATCH` | `1` | Micro-batch size; above 1 turns batching on |
| `TRIAGE_MAX_WAIT_MS` | `3` | How long a batch waits to fill |
| `TRIAGE_CORS_ORIGINS` | `["http://localhost:3000"]` | Websites allowed to call the API |

Realtime service (`realtime/`):

| Variable | Default | Meaning |
|---|---|---|
| `REDIS_URL` | `redis://127.0.0.1:6379` | Redis for the queue and pub/sub |
| `TRIAGE_API_URL` | `http://127.0.0.1:8000` | Where the worker sends tickets |
| `PORT` | `8080` | Gateway port (`/ws`, `/health`, `/burst`) |
| `REPLAY_RATE` | `0.5` | Tickets per second in normal replay |
| `BURST_SIZE` | `300` | Tickets per simulated outage |
| `BURST_COOLDOWN_MS` | `60000` | Minimum time between outages |
| `WORKER_CONCURRENCY` | `8` | Jobs processed in parallel |
| `ALLOWED_ORIGINS` | `http://localhost:3000` | Comma-separated origins allowed on the WebSocket |

Web app (`web/`): `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_REALTIME_URL`. Without them it runs on the
bundled sample tickets.
