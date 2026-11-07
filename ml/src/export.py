"""Export a trained student to ONNX, quantize to int8, check parity and speed.

    python ml/src/export.py --run full   -> ml/artifacts/serving/

The serving folder is everything the API needs: model.onnx, tokenizer/,
config.json (labels, temperatures, threshold).
"""
import argparse
import json
import shutil
import statistics
import time

import numpy as np
import onnx
import onnxruntime as ort
import torch
from onnxruntime.quantization import QuantType, quantize_dynamic
from transformers import AutoTokenizer

from data import ARTIFACTS, TASKS, gold_frame
from taxonomy import CATEGORIES, PRIORITIES
from train import build

SERVING = ARTIFACTS / "serving"


class Exportable(torch.nn.Module):
    def __init__(self, model):
        super().__init__()
        self.model = model

    def forward(self, input_ids, attention_mask):
        return self.model(input_ids, attention_mask)


def bench(fn, texts, tok, max_len, n=200) -> dict:
    times = []
    for text in texts[:n]:
        enc = tok(text, truncation=True, max_length=max_len, return_tensors="np")
        t0 = time.perf_counter()
        fn(enc["input_ids"].astype(np.int64), enc["attention_mask"].astype(np.int64))
        times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    return {"p50_ms": round(statistics.median(times), 2), "p95_ms": round(times[int(0.95 * len(times))], 2)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    args = ap.parse_args()

    run = ARTIFACTS / "student" / args.run
    meta = json.loads((run / "meta.json").read_text())
    cascade = json.loads((run / "cascade.json").read_text())

    torch.set_num_threads(1)
    model = build(meta["base"], meta["lora"], attn="eager")
    model.load_state_dict(torch.load(run / "model.pt"))
    if meta["lora"]:
        model.encoder = model.encoder.merge_and_unload()
    model.eval()

    SERVING.mkdir(parents=True, exist_ok=True)
    fp32, int8 = SERVING / "model.fp32.onnx", SERVING / "model.onnx"
    # the dummy batch must contain padding: with an all-ones mask the tracer
    # constant-folds the masking branch away and the exported graph ignores
    # attention_mask (caught by the parity check below: 92% agreement in fp32)
    ids = torch.randint(1000, 5000, (2, 16))
    mask = torch.ones(2, 16, dtype=torch.long)
    mask[1, 9:] = 0
    dummy = (ids, mask)
    # dynamo exporter: the legacy tracer baked the dummy's sequence length into
    # the mask arithmetic, so padded batches of any other length came out wrong
    batch, seq = torch.export.Dim("batch", max=256), torch.export.Dim("seq", max=512)
    torch.onnx.export(
        Exportable(model), dummy, fp32,
        input_names=["input_ids", "attention_mask"],
        output_names=list(TASKS),
        dynamic_shapes={"input_ids": {0: batch, 1: seq}, "attention_mask": {0: batch, 1: seq}},
        opset_version=18, dynamo=True, external_data=False,
    )
    # the dynamo exporter leaves value_info that onnx shape inference then
    # contradicts; drop it and let the quantizer re-infer
    graph = onnx.load(fp32)
    del graph.graph.value_info[:]
    onnx.save(graph, fp32)
    quantize_dynamic(fp32, int8, weight_type=QuantType.QInt8, per_channel=True)

    tok = AutoTokenizer.from_pretrained(run / "tokenizer")
    shutil.copytree(run / "tokenizer", SERVING / "tokenizer", dirs_exist_ok=True)

    gold = gold_frame()
    enc = tok(gold.text.tolist(), truncation=True, max_length=meta["max_len"],
              padding=True, return_tensors="np")
    feeds = {"input_ids": enc["input_ids"].astype(np.int64),
             "attention_mask": enc["attention_mask"].astype(np.int64)}

    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 1
    sessions = {name: ort.InferenceSession(str(p), opts, providers=["CPUExecutionProvider"])
                for name, p in [("onnx_fp32", fp32), ("onnx_int8", int8)]}
    with torch.no_grad():
        ref = [o.numpy() for o in model(torch.tensor(feeds["input_ids"]),
                                        torch.tensor(feeds["attention_mask"]))]

    report = {"run": args.run, "size_mb": {}, "agreement_with_torch": {}, "latency": {}}
    report["size_mb"]["onnx_fp32"] = round(fp32.stat().st_size / 1e6, 1)
    report["size_mb"]["onnx_int8"] = round(int8.stat().st_size / 1e6, 1)
    truth = {t: gold[t].map({c: i for i, c in enumerate(cs)}).to_numpy() for t, cs in TASKS.items()}
    report["gold_accuracy"] = {"torch_fp32": {
        t: float((ref[k].argmax(1) == truth[t]).mean()) for k, t in enumerate(TASKS)}}
    for name, sess in sessions.items():
        out = sess.run(None, feeds)
        report["agreement_with_torch"][name] = {
            t: float((out[k].argmax(1) == ref[k].argmax(1)).mean()) for k, t in enumerate(TASKS)}
        report["gold_accuracy"][name] = {
            t: float((out[k].argmax(1) == truth[t]).mean()) for k, t in enumerate(TASKS)}

    texts = gold.text.tolist()
    with torch.no_grad():
        report["latency"]["torch_fp32"] = bench(
            lambda i, m: model(torch.from_numpy(i), torch.from_numpy(m)), texts, tok, meta["max_len"])
    for name, sess in sessions.items():
        report["latency"][name] = bench(
            lambda i, m, s=sess: s.run(None, {"input_ids": i, "attention_mask": m}),
            texts, tok, meta["max_len"])

    fp32.unlink()  # only the int8 model ships
    config = {"run": args.run, "base": meta["base"], "max_len": meta["max_len"],
              "labels": TASKS,
              "descriptions": {"category": CATEGORIES, "priority": PRIORITIES},
              "temperatures": cascade["temperatures"],
              "threshold": cascade["threshold"]}
    (SERVING / "config.json").write_text(json.dumps(config, indent=1))
    (SERVING / "export_report.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
