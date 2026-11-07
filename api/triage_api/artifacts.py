"""Fetch model artifacts from S3 at startup when TRIAGE_ARTIFACTS_S3_URI is set.

Keeps the image small and lets a new model ship by uploading files instead of
rebuilding. Locally the artifacts are just read from ml/artifacts.
"""
import logging
from pathlib import Path
from urllib.parse import urlparse

log = logging.getLogger("triage")


def sync_from_s3(uri: str, dest: Path) -> None:
    import boto3  # only needed in this mode

    parsed = urlparse(uri)
    bucket, prefix = parsed.netloc, parsed.path.lstrip("/").rstrip("/") + "/"
    s3 = boto3.client("s3")
    n = 0
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            target = dest / obj["Key"][len(prefix):]
            if target.exists() and target.stat().st_size == obj["Size"]:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            s3.download_file(bucket, obj["Key"], str(target))
            n += 1
    log.info("synced %d files from %s", n, uri)
