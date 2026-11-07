import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer


@dataclass
class Prediction:
    category: str
    priority: str
    confidence: float  # min of the two calibrated top probabilities
    probs: dict[str, dict[str, float]]


class Student:
    """int8 ONNX encoder with two heads, temperature-calibrated."""

    def __init__(self, model_dir: Path, threads: int = 1):
        cfg = json.loads((model_dir / "config.json").read_text())
        self.labels: dict[str, list[str]] = cfg["labels"]
        self.descriptions: dict[str, dict[str, str]] = cfg["descriptions"]
        self.temps: dict[str, float] = cfg["temperatures"]
        self.threshold: float = cfg["threshold"]
        self.base: str = cfg["base"]

        self.tok = Tokenizer.from_file(str(model_dir / "tokenizer" / "tokenizer.json"))
        self.tok.enable_truncation(cfg["max_len"])
        self.tok.enable_padding(pad_id=self.tok.token_to_id("[PAD]") or 0)

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = threads
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(str(model_dir / "model.onnx"), opts,
                                            providers=["CPUExecutionProvider"])

    def predict(self, texts: list[str]) -> list[Prediction]:
        enc = self.tok.encode_batch(texts)
        ids = np.array([e.ids for e in enc], dtype=np.int64)
        mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
        outputs = self.session.run(None, {"input_ids": ids, "attention_mask": mask})

        probs = {}
        for task, logits in zip(self.labels, outputs):
            z = logits / self.temps[task]
            z = z - z.max(axis=1, keepdims=True)
            e = np.exp(z)
            probs[task] = e / e.sum(axis=1, keepdims=True)

        preds = []
        for i in range(len(texts)):
            per_task = {t: dict(zip(self.labels[t], map(float, probs[t][i]))) for t in self.labels}
            top = {t: max(p, key=p.get) for t, p in per_task.items()}
            preds.append(Prediction(
                category=top["category"],
                priority=top["priority"],
                confidence=min(per_task[t][top[t]] for t in per_task),
                probs=per_task,
            ))
        return preds
