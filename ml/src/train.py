"""Fine-tune a small encoder with two heads (category, priority) on teacher labels.

One shared encoder, two linear heads, summed cross-entropy. Plain PyTorch loop
on purpose: it's short and every step is visible.

Default encoder is all-MiniLM-L6-v2 (23M params). DistilBERT (66M) was the
first choice but ran at ~15 s/step on a 4-core laptop CPU vs ~1.3 s for
MiniLM; --base distilbert-base-uncased still works on a GPU.

    python ml/src/train.py --name full
    python ml/src/train.py --name lora --lora
"""
import argparse
import json
import math
import time

import numpy as np
import torch
from sklearn.metrics import f1_score
from torch import nn
from transformers import AutoModel, AutoTokenizer, get_linear_schedule_with_warmup

from data import ARTIFACTS, TASKS, gold_frame, train_val

BASE = "sentence-transformers/all-MiniLM-L6-v2"
MAX_LEN = 72  # p99 of tweet token length is 71
LORA_TARGETS = {
    "distilbert": ["q_lin", "k_lin", "v_lin", "out_lin"],
    "bert": ["query", "key", "value", "attention.output.dense"],
}


class Triage(nn.Module):
    def __init__(self, encoder: nn.Module, hidden: int):
        super().__init__()
        self.encoder = encoder
        self.dropout = nn.Dropout(0.1)
        self.heads = nn.ModuleDict({t: nn.Linear(hidden, len(c)) for t, c in TASKS.items()})

    def forward(self, input_ids, attention_mask):
        h = self.encoder(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
        cls = self.dropout(h[:, 0])
        return tuple(self.heads[t](cls) for t in TASKS)


def build(base: str, lora: bool, attn: str | None = None) -> Triage:
    encoder = AutoModel.from_pretrained(base, **({"attn_implementation": attn} if attn else {}))
    hidden = getattr(encoder.config, "hidden_size", None) or encoder.config.dim
    if lora:
        from peft import LoraConfig, get_peft_model
        cfg = LoraConfig(r=8, lora_alpha=16, lora_dropout=0.1,
                         target_modules=LORA_TARGETS[encoder.config.model_type])
        encoder = get_peft_model(encoder, cfg)
    return Triage(encoder, hidden)


def batches(lengths: torch.Tensor, size: int, gen: torch.Generator) -> list[torch.Tensor]:
    # shuffle, then sort inside windows of 50 batches so each batch has
    # similar lengths and we can trim padding; batch order is shuffled again
    order = torch.randperm(len(lengths), generator=gen)
    window = size * 50
    out = []
    for s in range(0, len(order), window):
        chunk = order[s:s + window]
        chunk = chunk[lengths[chunk].argsort()]
        out += list(chunk.split(size))
    return [out[i] for i in torch.randperm(len(out), generator=gen)]


def encode(tok, texts) -> dict[str, torch.Tensor]:
    return tok(list(texts), truncation=True, max_length=MAX_LEN,
               padding="max_length", return_tensors="pt")


def targets(df) -> torch.Tensor:
    cols = [df[t].map({c: i for i, c in enumerate(cs)}).to_numpy() for t, cs in TASKS.items()]
    return torch.tensor(np.stack(cols, axis=1))


def class_weights(y: torch.Tensor, n: int) -> torch.Tensor:
    # inverse sqrt frequency: helps the rare "high" priority without
    # wrecking precision the way fully balanced weights do
    counts = torch.bincount(y, minlength=n).float().clamp(min=1)
    w = counts.rsqrt()
    return w / w.mean()


@torch.no_grad()
def predict(model, enc, batch=256) -> list[np.ndarray]:
    model.eval()
    outs = [[] for _ in TASKS]
    for s in range(0, len(enc["input_ids"]), batch):
        mask = enc["attention_mask"][s:s + batch]
        L = int(mask.sum(1).max())
        logits = model(enc["input_ids"][s:s + batch, :L], mask[:, :L])
        for k, lg in enumerate(logits):
            outs[k].append(lg.numpy())
    return [np.concatenate(o) for o in outs]


def macro_f1s(logits, y) -> dict[str, float]:
    return {t: f1_score(y[:, k].numpy(), logits[k].argmax(1), average="macro")
            for k, t in enumerate(TASKS)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--teacher", default="gemini-3.5-flash-lite")
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--lora", action="store_true")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--lr", type=float, default=None)
    ap.add_argument("--batch", type=int, default=32)
    args = ap.parse_args()
    lr = args.lr or (5e-4 if args.lora else 5e-5)

    torch.manual_seed(13)
    torch.set_num_threads(4)
    gen = torch.Generator().manual_seed(13)
    out = ARTIFACTS / "student" / args.name
    out.mkdir(parents=True, exist_ok=True)

    tok = AutoTokenizer.from_pretrained(args.base)
    tr, va = train_val(args.teacher)
    gold = gold_frame()
    X_tr, X_va, X_gold = encode(tok, tr.text), encode(tok, va.text), encode(tok, gold.text)
    y_tr, y_va, y_gold = targets(tr), targets(va), targets(gold)

    model = build(args.base, args.lora)
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    print(f"{args.name}: {trainable:,} / {total:,} params trainable, lr {lr}")

    losses = [nn.CrossEntropyLoss(weight=class_weights(y_tr[:, k], len(c)))
              for k, c in enumerate(TASKS.values())]
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],
                            lr=lr, weight_decay=0.01)
    steps_per_epoch = math.ceil(len(tr) / args.batch)
    total_steps = steps_per_epoch * args.epochs
    sched = get_linear_schedule_with_warmup(opt, int(0.06 * total_steps), total_steps)

    best, history, t0, step = -1.0, [], time.time(), 0
    for epoch in range(args.epochs):
        model.train()
        for idx in batches(X_tr["attention_mask"].sum(1), args.batch, gen):
            mask = X_tr["attention_mask"][idx]
            L = int(mask.sum(1).max())
            logits = model(X_tr["input_ids"][idx, :L], mask[:, :L])
            loss = sum(fn(lg, y_tr[idx, k]) for k, (fn, lg) in enumerate(zip(losses, logits)))
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            step += 1
            if step % 50 == 0:
                rate = (time.time() - t0) / step
                print(f"epoch {epoch + 1} step {step}/{total_steps} loss {loss.item():.3f} "
                      f"eta {rate * (total_steps - step) / 60:.0f}m", flush=True)

        f1 = macro_f1s(predict(model, X_va), y_va)
        mean_f1 = float(np.mean(list(f1.values())))
        history.append({"epoch": epoch + 1, "val_macro_f1": f1,
                        "minutes": round((time.time() - t0) / 60, 1)})
        print(f"epoch {epoch + 1} val macro-F1 {f1}", flush=True)
        if mean_f1 > best:
            best = mean_f1
            torch.save(model.state_dict(), out / "model.pt")

    model.load_state_dict(torch.load(out / "model.pt"))
    val_logits, gold_logits = predict(model, X_va), predict(model, X_gold)
    np.savez(out / "logits.npz",
             **{f"val_{t}": val_logits[k] for k, t in enumerate(TASKS)},
             **{f"gold_{t}": gold_logits[k] for k, t in enumerate(TASKS)},
             y_val=y_va.numpy(), y_gold=y_gold.numpy())

    gold_f1 = macro_f1s(gold_logits, y_gold)
    gold_acc = {t: float((gold_logits[k].argmax(1) == y_gold[:, k].numpy()).mean())
                for k, t in enumerate(TASKS)}
    tok.save_pretrained(out / "tokenizer")
    meta = {"name": args.name, "base": args.base, "lora": args.lora, "lr": lr,
            "epochs": args.epochs, "max_len": MAX_LEN, "teacher": args.teacher,
            "trainable_params": trainable, "total_params": total,
            "history": history, "gold_macro_f1": gold_f1, "gold_accuracy": gold_acc,
            "train_minutes": round((time.time() - t0) / 60, 1), "labels": TASKS}
    (out / "meta.json").write_text(json.dumps(meta, indent=2))
    print("gold macro-F1", gold_f1, "accuracy", gold_acc)


if __name__ == "__main__":
    main()
