# Model card: Triage ticket classifier

A small text classifier that labels a customer support message with a **category** and a
**priority**, and reports how confident it is so that unsure cases can be sent to an LLM.

| | |
|---|---|
| Architecture | `sentence-transformers/all-MiniLM-L6-v2` encoder, 6 layers, 384 hidden size, with two linear heads |
| Parameters | 22.7 M (all trained); a LoRA variant trains 151,691 |
| Input | One message, up to 72 tokens (covers 99% of tweets), English |
| Output | Probabilities over 8 categories and 3 priorities, temperature-calibrated |
| Served as | ONNX, int8 dynamic quantization, 23 MB, ~8 ms per message on one CPU thread |
| Trained on | 18,000 tweets labelled by Gemini 3.5 Flash-Lite; 2,000 held for validation |
| Evaluated on | 384 tweets labelled separately by a stronger LLM, never used for training or tuning |
| Code | `ml/src/train.py`, `calibrate.py`, `export.py` |

## Intended use

Routing and prioritising inbound customer messages for a support team, as the first stage of a
cascade: accept the label when the calibrated confidence is at least 0.65, otherwise ask a stronger
model or a person.

It is **not** meant to make decisions on its own about refunds, account actions or anything that
affects a customer without review. Low-confidence outputs are expected to be wrong about 43% of
the time; that is what the confidence score is for.

## Labels

| Category | Covers |
|---|---|
| billing | charges, refunds, payments, invoices, pricing, promo codes |
| delivery | orders, shipping, parcels, food delivery, late, missing or wrong items |
| account | login, password, locked or hacked accounts, subscription changes, cancellation |
| technical | app or website bugs, device faults, outages, network and signal |
| travel | flights, trains, bookings, delays, cancellations, baggage, seats |
| service | complaints about staff, stores, wait times or the general experience |
| question | how-to or information requests with no problem reported |
| other | praise, jokes, spam, chatter, "sent you a DM", anything not actionable |

| Priority | Means |
|---|---|
| high | money lost or stuck, locked out, safety risk, stranded traveller, service fully down |
| medium | a real problem that needs a reply, nothing on fire |
| low | questions, feedback, praise, chatter |

## Training

- **Data.** Customers' opening tweets that a company replied to, from the public
  [Customer Support on Twitter](https://www.kaggle.com/datasets/thoughtvector/customer-support-on-twitter)
  dataset (2017). Phone numbers, emails, links and long account numbers masked; capped at 1,500 per
  company so a few large brands don't dominate.
- **Labels.** Gemini 3.5 Flash-Lite, temperature 0, 50 tweets per request, with the label definitions
  above in the prompt. Agreement with the evaluation labels: 81.0% category, 75.5% priority.
- **Objective.** Sum of two cross-entropy losses. Priority uses inverse-square-root class weights
  because "high" is rare.
- **Optimisation.** AdamW, learning rate 5e-5 (5e-4 for LoRA), weight decay 0.01, 6% linear warm-up,
  3 epochs, batch 32, gradient clipping at 1.0. Batches group tweets of similar length and trim padding.
- **Selection.** The epoch with the best mean validation macro-F1 (epoch 3).
- **Hardware.** A 2-core laptop CPU, no GPU. About 35 minutes per run when the machine isn't asleep.

## Evaluation

On 384 held-out tweets. Category accuracy **71.1%** (macro-F1 0.709); priority accuracy **68.8%**
(macro-F1 0.656). With the cascade at threshold 0.65: **80.7% / 75.0%**, with 43% of messages sent to
the LLM.

**Per category**

| Category | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| technical | 0.80 | 0.83 | 0.81 | 71 |
| billing | 0.75 | 0.77 | 0.76 | 35 |
| question | 0.78 | 0.73 | 0.75 | 62 |
| delivery | 0.61 | 0.91 | 0.73 | 22 |
| account | 0.62 | 0.75 | 0.68 | 28 |
| travel | 0.53 | 0.95 | 0.68 | 22 |
| other | 0.71 | 0.58 | 0.64 | 64 |
| service | 0.75 | 0.54 | 0.63 | 80 |

**Per priority**

| Priority | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| low | 0.89 | 0.69 | 0.78 | 180 |
| medium | 0.67 | 0.64 | 0.66 | 168 |
| high | 0.38 | 0.89 | 0.53 | 36 |

**Calibration.** One temperature per head (1.19 category, 1.29 priority), fitted on validation.
Expected calibration error on the evaluation set: 0.108 → 0.066 (category), 0.126 → 0.077 (priority).
When the model's confidence is at least 0.65 it is right 81.4% of the time on category and 78.6% on
priority; below 0.65, 57.3% and 55.5%.

## What it gets wrong, and why

- **It over-flags urgency.** "High" has 89% recall but 38% precision: it catches nearly every urgent
  message and raises many false alarms. The teacher called 22% of training tweets high priority; the
  evaluation labels call 9% high. The student learned the teacher's caution. For routing, missing an
  urgent ticket is worse than a false alarm, so this direction of error is the safer one.
- **"Travel" and "delivery" absorb questions.** Recall is above 0.9 but precision is 0.53–0.61. The
  teacher labelled *"is my 9:31 to Manchester running?"* as travel; the evaluation labels call it a
  question. This is a disagreement about definitions as much as a model error.
- **"Service" vs "other" is the most common confusion** (20 of 111 category errors). A vague rant
  like *"worst customer service ever"* sits on the boundary of both definitions.

## Limitations

- Evaluation labels come from an LLM, not people. They are a strong independent reference, not
  ground truth.
- The student can't be better than its teacher on what the teacher gets systematically wrong.
- English only; non-English tweets were excluded from evaluation. 2017 data, mostly US and UK brands.
- Short-text model: anything past 72 tokens is cut off.
- The calibration and cascade numbers were measured on the PyTorch model; the served int8 model picks
  the same label 97% of the time.

## Data and privacy

Public tweets, with customer handles already replaced by numeric ids in the source dataset. Phone
numbers, email addresses, URLs and long digit strings were masked before training. The dataset is
CC BY-NC-SA 4.0, so the derived labels and model weights are for non-commercial use.
