from hashlib import sha256
import json


JOB_CONTENT_HASH_VERSION = "JOB_CONTENT_V1"


def _normalize_text(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    normalized = " ".join(
        value
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .split()
    )

    return normalized or None


def _normalize_scalar(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    normalized = value.strip()

    return normalized or None


def build_job_content_hash(
    *,
    title: str,
    description: str | None,
    location_text: str | None,
    workplace_type: str | None,
    employment_type: str | None,
    job_url: str | None,
    apply_url: str | None,
    published_at: str | None,
    expires_at: str | None = None,
) -> str:
    payload = {
        "title": _normalize_text(title),
        "description": _normalize_text(description),
        "location_text": _normalize_text(location_text),
        "workplace_type": _normalize_scalar(workplace_type),
        "employment_type": _normalize_text(employment_type),
        "job_url": _normalize_scalar(job_url),
        "apply_url": _normalize_scalar(apply_url),
        "published_at": _normalize_scalar(published_at),
        "expires_at": _normalize_scalar(expires_at),
    }

    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    return sha256(
        serialized.encode("utf-8")
    ).hexdigest()
