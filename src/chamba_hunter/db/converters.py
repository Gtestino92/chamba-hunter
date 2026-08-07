import json
from datetime import datetime, timezone
from typing import Any


def datetime_to_db(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("Database datetimes must be timezone-aware.")

    return (
        value
        .astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def datetime_from_db(value: str) -> datetime:
    return datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )


def bool_to_db(value: bool | None) -> int | None:
    if value is None:
        return None

    return int(value)


def bool_from_db(value: int | None) -> bool | None:
    if value is None:
        return None

    return bool(value)


def json_to_db(value: Any | None) -> str | None:
    if value is None:
        return None

    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def json_from_db(value: str | None) -> Any | None:
    if value is None:
        return None

    return json.loads(value)