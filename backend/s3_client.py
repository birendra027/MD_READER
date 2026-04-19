"""
backend/s3_client.py

Thin wrapper around boto3 S3, pre-configured for LocalStack (or real AWS).

All configuration comes from environment variables:
    S3_ENDPOINT_URL       – LocalStack:  http://localstack:4566
                            Real AWS:    leave unset / empty
    S3_BUCKET             – bucket name (default: md-reader-sessions)
    AWS_ACCESS_KEY_ID     – test  (LocalStack)
    AWS_SECRET_ACCESS_KEY – test  (LocalStack)
    AWS_DEFAULT_REGION    – us-east-1

Key layout inside the bucket:
    sessions/<session_id>/memory.json      – serialised chat history
    sessions/<session_id>/output/<file>    – files produced by code execution

Public helpers
--------------
    ensure_bucket()                                → creates bucket if missing
    upload_bytes(key, data)                        → put raw bytes
    upload_file(key, local_path)                   → put a local file
    list_session_files(session_id)                 → [{key, filename, size, last_modified}]
    presigned_url(key, expires_in=3600)            → pre-signed GET URL
    delete_session(session_id)                     → remove all objects for a session
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────
_ENDPOINT = os.getenv("S3_ENDPOINT_URL", "").strip() or None
_BUCKET = os.getenv("S3_BUCKET", "md-reader-sessions")
_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

# For LocalStack we need path-style addressing
_config = Config(
    region_name=_REGION,
    signature_version="s3v4",
    s3={"addressing_style": "path"},
)


def _client() -> Any:
    """Return a boto3 S3 client (one per call is fine — boto3 reuses connections)."""
    kwargs: dict[str, Any] = {"config": _config}
    if _ENDPOINT:
        kwargs["endpoint_url"] = _ENDPOINT
    return boto3.client("s3", **kwargs)


# ── Bucket bootstrap ──────────────────────────────────────────────

def ensure_bucket() -> None:
    """Create the bucket if it does not already exist (idempotent)."""
    s3 = _client()
    try:
        s3.head_bucket(Bucket=_BUCKET)
        logger.debug("S3 bucket '%s' already exists", _BUCKET)
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code in ("404", "NoSuchBucket"):
            try:
                if _REGION == "us-east-1":
                    s3.create_bucket(Bucket=_BUCKET)
                else:
                    s3.create_bucket(
                        Bucket=_BUCKET,
                        CreateBucketConfiguration={"LocationConstraint": _REGION},
                    )
                logger.info("Created S3 bucket '%s'", _BUCKET)
            except ClientError:
                logger.exception("Failed to create bucket '%s'", _BUCKET)
        else:
            logger.exception("Unexpected error checking bucket '%s'", _BUCKET)


# ── Core operations ───────────────────────────────────────────────

def upload_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
    """Upload raw bytes to *key* in the session bucket."""
    try:
        _client().put_object(
            Bucket=_BUCKET,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        logger.debug("S3 upload_bytes → %s (%d bytes)", key, len(data))
    except Exception:
        logger.exception("S3 upload_bytes failed: key=%s", key)


def upload_file(key: str, local_path: Path) -> None:
    """Upload a local file to *key* in the session bucket."""
    try:
        _client().upload_file(str(local_path), _BUCKET, key)
        logger.debug("S3 upload_file → %s (%s)", key, local_path.name)
    except Exception:
        logger.exception("S3 upload_file failed: key=%s local=%s", key, local_path)


def list_session_files(session_id: str) -> list[dict]:
    """Return metadata for all output files belonging to *session_id*.

    Each entry:
        {"key": str, "filename": str, "size": int, "last_modified": str}
    """
    prefix = _output_prefix(session_id)
    try:
        resp = _client().list_objects_v2(Bucket=_BUCKET, Prefix=prefix)
        items = []
        for obj in resp.get("Contents", []):
            key: str = obj["Key"]
            items.append({
                "key": key,
                "filename": key.split("/")[-1],
                "size": obj["Size"],
                "last_modified": obj["LastModified"].isoformat(),
            })
        return items
    except Exception:
        logger.exception("S3 list_session_files failed: session_id=%s", session_id)
        return []


def presigned_url(key: str, expires_in: int = 3600) -> str:
    """Generate a pre-signed GET URL valid for *expires_in* seconds.

    For LocalStack in a Docker network the URL will be an internal hostname.
    We rewrite it to the host-facing ``localhost:4566`` so browsers can reach it.
    """
    try:
        url: str = _client().generate_presigned_url(
            "get_object",
            Params={"Bucket": _BUCKET, "Key": key},
            ExpiresIn=expires_in,
        )
        # Rewrite internal container hostname → localhost so the browser works
        if _ENDPOINT:
            from urllib.parse import urlparse, urlunparse
            parsed = urlparse(url)
            # _ENDPOINT is e.g. http://localstack:4566 — replace that host/port
            # with localhost so requests from the user's browser work.
            ep = urlparse(_ENDPOINT)
            rewritten = parsed._replace(netloc=f"localhost:{ep.port or 4566}")
            url = urlunparse(rewritten)
        return url
    except Exception:
        logger.exception("S3 presigned_url failed: key=%s", key)
        return ""


def delete_session(session_id: str) -> int:
    """Delete all S3 objects for *session_id* (both memory and output).
    Returns the number of objects deleted.
    """
    prefix = f"sessions/{_sanitise(session_id)}/"
    s3 = _client()
    deleted = 0
    try:
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=_BUCKET, Prefix=prefix):
            objects = [{"Key": o["Key"]} for o in page.get("Contents", [])]
            if objects:
                s3.delete_objects(Bucket=_BUCKET, Delete={"Objects": objects})
                deleted += len(objects)
        logger.info("S3 delete_session: removed %d object(s) for %s", deleted, session_id[:8])
    except Exception:
        logger.exception("S3 delete_session failed: session_id=%s", session_id)
    return deleted


# ── Internal helpers ──────────────────────────────────────────────

def _sanitise(session_id: str) -> str:
    """Prevent path traversal in S3 keys."""
    return session_id.replace("/", "_").replace("\\", "_").replace("..", "_")


def _memory_key(session_id: str) -> str:
    return f"sessions/{_sanitise(session_id)}/memory.json"


def _output_prefix(session_id: str) -> str:
    return f"sessions/{_sanitise(session_id)}/output/"


def _output_key(session_id: str, filename: str) -> str:
    safe_name = Path(filename).name  # strip any directory component
    return f"{_output_prefix(session_id)}{safe_name}"
