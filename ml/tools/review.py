"""Blind hand-labelling for the gold set.

    python ml/tools/review.py      -> http://localhost:8765

Teacher labels are deliberately hidden so they can't anchor the human label.
Every answer is written to ml/data/labels/gold.human.jsonl immediately.
"""
import json
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from taxonomy import CATEGORIES, PRIORITIES  # noqa: E402

GOLD = Path("ml/data/processed/gold.parquet")
OUT = Path("ml/data/labels/gold.human.jsonl")
PAGE = Path(__file__).with_name("review.html")
PORT = 8765


def load_done() -> dict[int, dict]:
    done = {}
    if OUT.exists():
        for line in OUT.open(encoding="utf-8"):
            row = json.loads(line)
            done[row["id"]] = row  # last write wins, so re-labelling works
    return done


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/":
            self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/data":
            gold = pd.read_parquet(GOLD)
            payload = {
                "tickets": [{"id": int(r.id), "brand": r.brand, "text": r.text}
                            for r in gold.itertuples()],
                "categories": CATEGORIES,
                "priorities": PRIORITIES,
                "done": list(load_done().values()),
            }
            self._send(200, json.dumps(payload).encode(), "application/json")
        else:
            self._send(404, b"", "text/plain")

    def do_POST(self) -> None:
        if self.path != "/label":
            return self._send(404, b"", "text/plain")
        row = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        ok = row.get("skip") or (row.get("category") in CATEGORIES
                                 and row.get("priority") in PRIORITIES)
        if not isinstance(row.get("id"), int) or not ok:
            return self._send(400, b"bad label", "text/plain")
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with OUT.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        self._send(204, b"", "text/plain")

    def log_message(self, *args) -> None:
        pass


if __name__ == "__main__":
    print(f"reviewing at http://localhost:{PORT}  (ctrl+c to stop)")
    webbrowser.open(f"http://localhost:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
