from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import json
import re
import unicodedata


RECENCY_RANK = {
    "VERY_RECENT": 4,
    "RECENT": 3,
    "AGING": 2,
    "UNKNOWN": 1,
    "OLD": 0,
}


@dataclass(frozen=True, slots=True)
class SourceRecency:
    bucket: str
    min_age_days: int | None
    max_age_days: int | None
    evidence_type: str | None
    evidence_value: str | None

    def as_json(self) -> dict[str, str | int | None]:
        return {
            "bucket": self.bucket,
            "min_age_days": self.min_age_days,
            "max_age_days": self.max_age_days,
            "evidence_type": self.evidence_type,
            "evidence_value": self.evidence_value,
        }


def evaluate_source_recency(
    *,
    now: datetime,
    published_at: datetime | None,
    raw_payload_json: str | None,
) -> SourceRecency:
    if published_at is not None:
        age_days = max(
            0,
            (
                now.date()
                - published_at.date()
            ).days,
        )

        return _exact_age(
            age_days=age_days,
            evidence_type="PUBLISHED_AT",
            evidence_value=published_at.isoformat(),
        )

    payload = _json_object(
        raw_payload_json
    )

    getonboard = payload.get(
        "_chamba_source_enrichment",
        {},
    )

    if isinstance(
        getonboard,
        dict,
    ):
        published_date = (
            getonboard.get(
                "published_date"
            )
        )

        if isinstance(
            published_date,
            str,
        ):
            try:
                parsed_date = date.fromisoformat(
                    published_date
                )
            except ValueError:
                parsed_date = None

            if parsed_date is not None:
                age_days = max(
                    0,
                    (
                        now.date()
                        - parsed_date
                    ).days,
                )

                return _exact_age(
                    age_days=age_days,
                    evidence_type=(
                        "GETONBOARD_PUBLISHED_DATE"
                    ),
                    evidence_value=published_date,
                )

    board = payload.get(
        "board",
        {},
    )

    if isinstance(
        board,
        dict,
    ):
        published_relative = (
            board.get(
                "published_relative"
            )
        )

        if isinstance(
            published_relative,
            str,
        ):
            relative = (
                _relative_age_range(
                    published_relative
                )
            )

            if relative is not None:
                (
                    min_age_days,
                    max_age_days,
                ) = relative

                return SourceRecency(
                    bucket=(
                        _range_bucket(
                            min_age_days,
                            max_age_days,
                        )
                    ),
                    min_age_days=(
                        min_age_days
                    ),
                    max_age_days=(
                        max_age_days
                    ),
                    evidence_type=(
                        "HIRINGROOM_RELATIVE"
                    ),
                    evidence_value=(
                        published_relative
                    ),
                )

    return SourceRecency(
        bucket="UNKNOWN",
        min_age_days=None,
        max_age_days=None,
        evidence_type=None,
        evidence_value=None,
    )


def _exact_age(
    *,
    age_days: int,
    evidence_type: str,
    evidence_value: str,
) -> SourceRecency:
    return SourceRecency(
        bucket=_exact_bucket(
            age_days
        ),
        min_age_days=age_days,
        max_age_days=age_days,
        evidence_type=evidence_type,
        evidence_value=evidence_value,
    )


def _exact_bucket(
    age_days: int,
) -> str:
    if age_days <= 7:
        return "VERY_RECENT"

    if age_days <= 30:
        return "RECENT"

    if age_days <= 60:
        return "AGING"

    return "OLD"


def _range_bucket(
    min_age_days: int,
    max_age_days: int,
) -> str:
    if min_age_days > 60:
        return "OLD"

    if max_age_days > 30:
        return "AGING"

    if max_age_days > 7:
        return "RECENT"

    return "VERY_RECENT"


def _relative_age_range(
    value: str,
) -> tuple[int, int] | None:
    normalized = _normalize_text(
        value
    )

    if re.search(
        r"\b(hoy|today|just posted)\b",
        normalized,
    ):
        return (0, 0)

    if re.search(
        r"\b(ayer|yesterday)\b",
        normalized,
    ):
        return (1, 1)

    match = re.search(
        r"\b(\d+|un|una|one|a)\s+"
        r"(dia|dias|day|days|"
        r"semana|semanas|week|weeks|"
        r"mes|meses|month|months)\b",
        normalized,
    )

    if match is None:
        return None

    raw_amount = match.group(1)

    amount = (
        1
        if raw_amount
        in {
            "un",
            "una",
            "one",
            "a",
        }
        else int(
            raw_amount
        )
    )

    unit = match.group(2)

    if unit in {
        "dia",
        "dias",
        "day",
        "days",
    }:
        return (
            amount,
            amount,
        )

    if unit in {
        "semana",
        "semanas",
        "week",
        "weeks",
    }:
        return (
            amount * 7,
            amount * 7 + 6,
        )

    return (
        amount * 28,
        amount * 31,
    )


def _json_object(
    raw: str | None,
) -> dict:
    if not raw:
        return {}

    try:
        parsed = json.loads(
            raw
        )
    except (
        TypeError,
        json.JSONDecodeError,
    ):
        return {}

    return (
        parsed
        if isinstance(
            parsed,
            dict,
        )
        else {}
    )


def _normalize_text(
    value: str,
) -> str:
    decomposed = unicodedata.normalize(
        "NFKD",
        value,
    )

    without_accents = "".join(
        character
        for character
        in decomposed
        if not unicodedata.combining(
            character
        )
    )

    return " ".join(
        without_accents
        .casefold()
        .split()
    )
