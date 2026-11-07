FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    FASTEMBED_CACHE_PATH=/opt/fastembed \
    TRIAGE_MODEL_DIR=/app/artifacts/serving \
    TRIAGE_INDEX_DIR=/app/artifacts/retrieval

WORKDIR /app
COPY api/pyproject.toml ./
RUN pip install --no-cache-dir . boto3 && pip uninstall -y triage-api

# bake the embedding + rerank models in so a cold start doesn't hit the network
RUN python -c "from fastembed import TextEmbedding; from fastembed.rerank.cross_encoder import TextCrossEncoder; \
TextEmbedding('BAAI/bge-small-en-v1.5'); TextCrossEncoder('Xenova/ms-marco-MiniLM-L-6-v2')"

COPY api/triage_api ./triage_api
# artifacts are optional in the image; set TRIAGE_ARTIFACTS_S3_URI to pull them instead
COPY ml/artifacts/serving ./artifacts/serving
COPY ml/artifacts/retrieval ./artifacts/retrieval

RUN useradd --system app && chown -R app /app /opt/fastembed
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["uvicorn", "triage_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
