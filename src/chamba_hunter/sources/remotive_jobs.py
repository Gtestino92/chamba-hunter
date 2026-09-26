from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from html.parser import HTMLParser
import re
from typing import Any

import httpx
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
)


REMOTIVE_REMOTE_JOBS_URL = (
    "https://remotive.com/api/remote-jobs"
)
DEFAULT_REMOTIVE_MAX_JOBS = 100
MAX_REMOTIVE_MAX_JOBS = 500
REMOTIVE_TARGET_CATEGORIES = (
    "Software Development",
    "DevOps / Sysadmin",
)


class RemotiveApiError(RuntimeError):
    pass


class RemotiveGeoClassification(StrEnum):
    POTENTIALLY_ELIGIBLE = "POTENTIALLY_ELIGIBLE"
    EXPLICITLY_INELIGIBLE = "EXPLICITLY_INELIGIBLE"
    UNKNOWN = "UNKNOWN"


class RemotiveJobPosting(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int | str
    url: str
    title: str
    company_name: str

    company_logo: str | None = None
    category: str | None = None
    job_type: str | None = None
    publication_date: str | None = None
    candidate_required_location: str | None = None
    salary: str | None = None
    description: str | None = None
    tags: list[str] | None = None


class RemotiveJobsResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    job_count: int | None = Field(
        default=None,
        alias="job-count",
    )
    jobs: list[RemotiveJobPosting]


@dataclass(frozen=True, slots=True)
class RemotiveNormalizedJob:
    external_id: str
    title: str
    company_name: str
    category: str | None
    job_type: str | None
    location_text: str | None
    job_url: str
    published_at: datetime | None
    description: str | None
    raw_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RemotiveJobsFetch:
    endpoint: str
    requests_made: int
    jobs_reported_by_api: int
    jobs_parsed: int
    duplicates_removed: int
    category_rejects: int
    category_candidates: int
    explicit_geo_rejects: int
    unknown_geography: int
    potentially_eligible: int
    selected_after_max_jobs: int
    normalized_jobs: int
    unique_companies: int
    publication_dates_parsed: int
    publication_dates_missing: int
    retained_categories: dict[str, int]
    jobs: list[RemotiveNormalizedJob]


class RemotiveJobsClient:
    def __init__(
        self,
        timeout_seconds: float = 20.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def fetch_jobs(
        self,
        *,
        max_jobs: int = DEFAULT_REMOTIVE_MAX_JOBS,
    ) -> RemotiveJobsFetch:
        if not 1 <= max_jobs <= MAX_REMOTIVE_MAX_JOBS:
            raise ValueError(
                "max_jobs must be between 1 and "
                f"{MAX_REMOTIVE_MAX_JOBS}."
            )

        try:
            with httpx.Client(
                timeout=self.timeout_seconds,
                follow_redirects=True,
                transport=self.transport,
                headers={
                    "User-Agent": "chamba-hunter/0.1",
                    "Accept": "application/json",
                },
            ) as client:
                response = client.get(
                    REMOTIVE_REMOTE_JOBS_URL
                )

            if response.status_code == 429:
                raise RemotiveApiError(
                    "Remotive rate limit reached "
                    "(HTTP 429). Try again later; "
                    "Remotive recommends infrequent "
                    "polling."
                )

            if response.status_code == 403:
                raise RemotiveApiError(
                    "Remotive rejected the request "
                    "(HTTP 403)."
                )

            if 500 <= response.status_code <= 599:
                raise RemotiveApiError(
                    "Remotive server error: "
                    f"HTTP {response.status_code}."
                )

            response.raise_for_status()

            try:
                data = response.json()
            except ValueError as error:
                raise RemotiveApiError(
                    "Remotive returned invalid JSON."
                ) from error

            try:
                payload = (
                    RemotiveJobsResponse
                    .model_validate(data)
                )
            except ValidationError as error:
                raise RemotiveApiError(
                    "Remotive response shape is "
                    "missing or invalid; expected "
                    "a top-level jobs array."
                ) from error

        except httpx.TimeoutException as error:
            raise RemotiveApiError(
                "Remotive request timed out."
            ) from error
        except httpx.NetworkError as error:
            raise RemotiveApiError(
                "Remotive network request failed."
            ) from error

        return _normalize_response(
            payload,
            max_jobs=max_jobs,
        )


def _normalize_response(
    payload: RemotiveJobsResponse,
    *,
    max_jobs: int,
) -> RemotiveJobsFetch:
    jobs_reported = (
        payload.job_count
        if payload.job_count is not None
        else len(payload.jobs)
    )
    jobs_parsed = len(payload.jobs)

    seen_ids: set[str] = set()
    unique_jobs: list[RemotiveJobPosting] = []
    duplicates_removed = 0

    for job in payload.jobs:
        external_id = _clean_text(str(job.id))

        if external_id is None:
            continue

        if external_id in seen_ids:
            duplicates_removed += 1
            continue

        seen_ids.add(external_id)
        unique_jobs.append(job)

    category_candidates: list[RemotiveJobPosting] = []
    category_rejects = 0

    for job in unique_jobs:
        if _is_target_category(job.category):
            category_candidates.append(job)
        else:
            category_rejects += 1

    retained: list[RemotiveJobPosting] = []
    explicit_geo_rejects = 0
    unknown_geography = 0
    potentially_eligible = 0

    for job in category_candidates:
        geo = classify_remotive_geography(
            job.candidate_required_location
        )

        if (
            geo
            == RemotiveGeoClassification
            .EXPLICITLY_INELIGIBLE
        ):
            explicit_geo_rejects += 1
            continue

        if geo == RemotiveGeoClassification.UNKNOWN:
            unknown_geography += 1
        else:
            potentially_eligible += 1

        retained.append(job)

    retained.sort(
        key=lambda job: (
            _clean_text(str(job.id)) or ""
        )
    )
    retained.sort(
        key=lambda job: (
            _parse_publication_date(
                job.publication_date
            )
            or datetime.min.replace(
                tzinfo=UTC
            )
        ),
        reverse=True,
    )

    selected = retained[:max_jobs]
    normalized_jobs: list[RemotiveNormalizedJob] = []
    publication_dates_parsed = 0
    publication_dates_missing = 0
    retained_categories: dict[str, int] = {}

    for job in selected:
        parsed_date = _parse_publication_date(
            job.publication_date
        )

        if parsed_date is None:
            publication_dates_missing += 1
        else:
            publication_dates_parsed += 1

        category = _clean_text(job.category)
        if category is not None:
            retained_categories[category] = (
                retained_categories.get(category, 0)
                + 1
            )

        normalized_jobs.append(
            RemotiveNormalizedJob(
                external_id=_required_text(
                    str(job.id),
                    "id",
                ),
                title=_required_text(
                    job.title,
                    "title",
                ),
                company_name=_required_text(
                    job.company_name,
                    "company_name",
                ),
                category=category,
                job_type=_clean_text(job.job_type),
                location_text=_clean_text(
                    job.candidate_required_location
                ),
                job_url=_required_text(
                    job.url,
                    "url",
                ),
                published_at=parsed_date,
                description=_html_to_text(
                    job.description
                ),
                raw_payload=job.model_dump(
                    mode="json",
                    by_alias=True,
                ),
            )
        )

    return RemotiveJobsFetch(
        endpoint=REMOTIVE_REMOTE_JOBS_URL,
        requests_made=1,
        jobs_reported_by_api=jobs_reported,
        jobs_parsed=jobs_parsed,
        duplicates_removed=duplicates_removed,
        category_rejects=category_rejects,
        category_candidates=len(category_candidates),
        explicit_geo_rejects=explicit_geo_rejects,
        unknown_geography=unknown_geography,
        potentially_eligible=potentially_eligible,
        selected_after_max_jobs=len(selected),
        normalized_jobs=len(normalized_jobs),
        unique_companies=len(
            {
                job.company_name.casefold()
                for job in normalized_jobs
            }
        ),
        publication_dates_parsed=(
            publication_dates_parsed
        ),
        publication_dates_missing=(
            publication_dates_missing
        ),
        retained_categories=retained_categories,
        jobs=normalized_jobs,
    )


def classify_remotive_geography(
    value: str | None,
) -> RemotiveGeoClassification:
    cleaned = _clean_text(value)

    if cleaned is None:
        return RemotiveGeoClassification.UNKNOWN

    text = cleaned.casefold()

    if re.search(
        r"\b(argentina|buenos aires|latam|latin "
        r"america|south america|worldwide|anywhere|"
        r"global|americas)\b",
        text,
    ):
        return (
            RemotiveGeoClassification
            .POTENTIALLY_ELIGIBLE
        )

    if re.search(
        r"\b(gmt|utc)\s*[-+−]\s*(2|3|4)\b|"
        r"\b(art|america/argentina|"
        r"america/buenos_aires)\b",
        text,
    ):
        return (
            RemotiveGeoClassification
            .POTENTIALLY_ELIGIBLE
        )

    if re.search(
        r"\b(us|usa|u\.s\.|united states|"
        r"us only|us-only|us national|canada|"
        r"united kingdom|uk|europe|europe only|"
        r"eu only|india|australia|new zealand|"
        r"germany only|france only|spain only|"
        r"brazil only|mexico only|colombia only)\b",
        text,
    ):
        return (
            RemotiveGeoClassification
            .EXPLICITLY_INELIGIBLE
        )

    if re.search(
        r"\b(alabama|alaska|arizona|arkansas|"
        r"california|colorado|connecticut|delaware|"
        r"florida|georgia|hawaii|idaho|illinois|"
        r"indiana|iowa|kansas|kentucky|louisiana|"
        r"maine|maryland|massachusetts|michigan|"
        r"minnesota|mississippi|missouri|montana|"
        r"nebraska|nevada|ohio|oregon|texas|"
        r"washington|austin|new york|san francisco|"
        r"los angeles|chicago|boston|seattle)\b",
        text,
    ):
        return (
            RemotiveGeoClassification
            .EXPLICITLY_INELIGIBLE
        )

    return RemotiveGeoClassification.UNKNOWN


def _is_target_category(
    value: str | None,
) -> bool:
    cleaned = _clean_text(value)

    if cleaned is None:
        return False

    normalized = re.sub(
        r"[^a-z0-9]+",
        " ",
        cleaned.casefold(),
    ).strip()

    return normalized in {
        "software development",
        "devops sysadmin",
        "devops",
    }


def _parse_publication_date(
    value: str | None,
) -> datetime | None:
    cleaned = _clean_text(value)

    if cleaned is None:
        return None

    try:
        normalized = (
            cleaned[:-1] + "+00:00"
            if cleaned.endswith("Z")
            else cleaned
        )
        parsed = datetime.fromisoformat(
            normalized
        )
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=UTC
        )

    return parsed.astimezone(UTC)


def _required_text(
    value: str | None,
    field: str,
) -> str:
    cleaned = _clean_text(value)

    if cleaned is None:
        raise ValueError(f"{field} cannot be empty.")

    return cleaned


def _clean_text(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    cleaned = " ".join(str(value).split())

    return cleaned if cleaned else None


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(
        self,
        data: str,
    ) -> None:
        cleaned = " ".join(data.split())

        if cleaned:
            self.parts.append(cleaned)


def _html_to_text(
    value: str | None,
) -> str | None:
    cleaned = _clean_text(value)

    if cleaned is None:
        return None

    parser = _TextExtractor()
    parser.feed(value)
    text = re.sub(
        r"\s+([,.;:!?])",
        r"\1",
        " ".join(parser.parts),
    )

    return text if text else cleaned
