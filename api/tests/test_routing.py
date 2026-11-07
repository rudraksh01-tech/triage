import httpx
import pytest
from fastapi.testclient import TestClient

from triage_api.llm import BudgetExceeded, RateLimiter
from triage_api.main import Stats, app
from triage_api.student import Prediction

DESCRIPTIONS = {
    "category": {"billing": "", "technical": "", "other": ""},
    "priority": {"high": "", "medium": "", "low": ""},
}


class FakeStudent:
    threshold = 0.8
    base = "fake"
    descriptions = DESCRIPTIONS

    def __init__(self, confidence: float):
        self.confidence = confidence

    def predict(self, texts):
        return [
            Prediction(
                category="billing",
                priority="medium",
                confidence=self.confidence,
                probs={"category": {"billing": self.confidence}, "priority": {"medium": self.confidence}},
            )
            for _ in texts
        ]


class FakeLLM:
    def __init__(self, behaviour="ok"):
        self.behaviour = behaviour
        self.calls = 0
        self.limiter = RateLimiter(10)

    async def classify(self, text, descriptions):
        self.calls += 1
        if self.behaviour == "budget":
            raise BudgetExceeded
        if self.behaviour == "error":
            raise httpx.ConnectError("down")
        return {"category": "technical", "priority": "high"}


@pytest.fixture
def client():
    def make(confidence=0.95, llm="ok"):
        app.state.student = FakeStudent(confidence)
        app.state.llm = FakeLLM(llm)
        app.state.retriever = None
        app.state.stats = Stats()
        return TestClient(app)  # no `with`: skips lifespan, so no model files needed

    return make


def test_confident_ticket_stays_with_model(client):
    c = client(confidence=0.95)
    r = c.post("/v1/classify", json={"text": "charged twice"})
    assert r.status_code == 200
    body = r.json()
    assert body["route"] == "model"
    assert body["category"] == "billing"
    assert app.state.llm.calls == 0


def test_low_confidence_escalates_and_llm_label_wins(client):
    c = client(confidence=0.4)
    body = c.post("/v1/classify", json={"text": "app keeps crashing"}).json()
    assert body["route"] == "llm"
    assert (body["category"], body["priority"]) == ("technical", "high")
    assert body["student"] == {"category": "billing", "priority": "medium"}
    assert body["llm_ms"] is not None


@pytest.mark.parametrize("failure", ["budget", "error"])
def test_llm_unavailable_keeps_student_label(client, failure):
    c = client(confidence=0.4, llm=failure)
    body = c.post("/v1/classify", json={"text": "?"}).json()
    assert body["route"] == "deferred"
    assert body["category"] == "billing"


def test_threshold_is_inclusive(client):
    c = client(confidence=0.8)
    assert c.post("/v1/classify", json={"text": "x"}).json()["route"] == "model"


def test_batch_routes_each_ticket(client):
    c = client(confidence=0.4)
    r = c.post("/v1/classify/batch", json={"tickets": [{"text": "a"}, {"text": "b"}]})
    assert [t["route"] for t in r.json()] == ["llm", "llm"]
    assert app.state.stats.routes["llm"] == 2


@pytest.mark.parametrize("payload", [{"text": ""}, {"text": "x" * 1001}, {}])
def test_rejects_bad_input(client, payload):
    assert client().post("/v1/classify", json=payload).status_code == 422


def test_draft_without_index_is_503(client):
    assert client().post("/v1/draft", json={"text": "hi"}).status_code == 503


async def test_rate_limiter_window():
    lim = RateLimiter(2)
    assert await lim.try_acquire()
    assert await lim.try_acquire()
    assert not await lim.try_acquire()
    assert lim.remaining() == 0
