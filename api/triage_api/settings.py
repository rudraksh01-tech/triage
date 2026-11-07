from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TRIAGE_", env_file=(ROOT / ".env", ".env"), extra="ignore")

    model_dir: Path = ROOT / "ml/artifacts/serving"
    index_dir: Path = ROOT / "ml/artifacts/retrieval"
    # s3://bucket/prefix containing serving/ and retrieval/; overrides the local dirs
    artifacts_s3_uri: str | None = None
    artifacts_cache: Path = Path("/tmp/triage-artifacts")

    llm_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    llm_api_key: str = ""
    llm_model: str = "gemini-3.5-flash-lite"
    llm_timeout_s: float = 20.0
    # free tier allows 15 requests/min; keep a little headroom for drafts
    llm_rpm: int = 12

    threads: int = 1
    # dynamic batching for /v1/classify. Off by default: on a 2-core CPU it
    # lowered peak throughput (62 vs 84 req/s) because per-request HTTP overhead,
    # not the model, is the bottleneck, and one batch at a time used fewer cores.
    # Worth turning on with a GPU or more cores; see loadtest/results.json.
    max_batch: int = 1
    max_wait_ms: float = 3.0
    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if not s.llm_api_key:
        # reuse the labelling key from the repo .env when running locally
        import os
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
        s.llm_api_key = os.environ.get("LABEL_API_KEY", "")
    return s
