import asyncio
import json
import re
import time
from collections import OrderedDict, deque

import httpx


class BudgetExceeded(Exception):
    pass


class RateLimiter:
    """Sliding one-minute window. Non-blocking: callers decide what to do when full."""

    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self.calls: deque[float] = deque()
        self.lock = asyncio.Lock()

    async def try_acquire(self) -> bool:
        async with self.lock:
            now = time.monotonic()
            while self.calls and now - self.calls[0] > 60:
                self.calls.popleft()
            if len(self.calls) >= self.per_minute:
                return False
            self.calls.append(now)
            return True

    def remaining(self) -> int:
        now = time.monotonic()
        return self.per_minute - sum(1 for t in self.calls if now - t <= 60)


class LLM:
    def __init__(self, base_url: str, api_key: str, model: str, rpm: int, timeout: float):
        self.model = model
        self.limiter = RateLimiter(rpm)
        self.client = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )
        self.cache: OrderedDict[str, dict] = OrderedDict()
        self.paused_until = 0.0

    async def close(self) -> None:
        await self.client.aclose()

    def open_circuit(self, response: httpx.Response) -> None:
        # Google says how long to back off; a per-day limit means don't bother for a while
        if "per day" in response.text:
            wait = 3600.0
        else:
            hint = re.search(r"retry in ([\d.]+)s", response.text)
            wait = float(hint.group(1)) if hint else 30.0
        self.paused_until = time.monotonic() + wait

    async def chat(self, system: str, user: str, json_mode: bool = False) -> str:
        if time.monotonic() < self.paused_until:
            raise BudgetExceeded  # circuit open: provider told us to stop
        if not await self.limiter.try_acquire():
            raise BudgetExceeded
        body = {
            "model": self.model,
            "temperature": 0 if json_mode else 0.4,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        r = await self.client.post("chat/completions", json=body)
        if r.status_code in (500, 502, 503):
            # Gemini's free tier throws short 503 bursts; one quick retry clears most
            await asyncio.sleep(0.4)
            r = await self.client.post("chat/completions", json=body)
        if r.status_code == 429:
            self.open_circuit(r)
            raise BudgetExceeded
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    async def classify(self, text: str, descriptions: dict[str, dict[str, str]]) -> dict:
        if text in self.cache:
            self.cache.move_to_end(text)
            return self.cache[text]

        def block(d):
            return "\n".join(f"- {k}: {v}" for k, v in d.items())

        system = (
            "You triage a customer support tweet sent to a company. "
            "Pick exactly one category and one priority.\n\n"
            f"Categories:\n{block(descriptions['category'])}\n\n"
            f"Priorities:\n{block(descriptions['priority'])}\n\n"
            'Reply with JSON only: {"category": "...", "priority": "..."}'
        )
        out = json.loads(await self.chat(system, text, json_mode=True))
        if out.get("category") not in descriptions["category"] or \
                out.get("priority") not in descriptions["priority"]:
            raise ValueError(f"LLM returned an unknown label: {out}")
        label = {"category": out["category"], "priority": out["priority"]}

        self.cache[text] = label
        if len(self.cache) > 5000:
            self.cache.popitem(last=False)
        return label
