import httpx
import pytest

from triage_api.llm import LLM, BudgetExceeded

DAILY = '{"error": {"code": 429, "message": "Generate content requests per day limit exceeded on Free Tier"}}'
MINUTE = '{"error": {"code": 429, "message": "per minute limit exceeded. Please retry in 7.5s."}}'


def make_llm(body: str) -> tuple[LLM, list]:
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, text=body)

    llm = LLM("https://example.test/", "k", "m", rpm=100, timeout=5)
    llm.client = httpx.AsyncClient(base_url="https://example.test/", transport=httpx.MockTransport(handler))
    return llm, calls


async def test_daily_limit_stops_calls_for_an_hour():
    llm, calls = make_llm(DAILY)
    for _ in range(5):
        with pytest.raises(BudgetExceeded):
            await llm.chat("s", "u")
    assert len(calls) == 1  # only the first call reached the provider
    assert llm.paused_until - __import__("time").monotonic() > 3000


async def test_minute_limit_uses_the_providers_hint():
    llm, _ = make_llm(MINUTE)
    with pytest.raises(BudgetExceeded):
        await llm.chat("s", "u")
    wait = llm.paused_until - __import__("time").monotonic()
    assert 5 < wait <= 7.5
