from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from html import unescape
from html.parser import HTMLParser
import re
from typing import Any

import httpx
from pydantic import (
    BaseModel,
    ConfigDict,
    ValidationError,
)


REMOTEOK_API_URL = "https://remoteok.com/api"
DEFAULT_REMOTEOK_MAX_JOBS = 100
MAX_REMOTEOK_MAX_JOBS = 500


class RemoteOkApiError(RuntimeError):
    pass


class RemoteOkGeoClassification(StrEnum):
    POTENTIALLY_ELIGIBLE = "POTENTIALLY_ELIGIBLE"
    EXPLICITLY_INELIGIBLE = "EXPLICITLY_INELIGIBLE"
    UNKNOWN = "UNKNOWN"


class RemoteOkJobPosting(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int | str
    company: str
    position: str
    url: str

    slug: str | None = None
    epoch: int | float | str | None = None
    date: str | None = None
    company_logo: str | None = None
    tags: list[str] | None = None
    description: str | None = None
    location: str | None = None
    salary_min: int | float | str | None = None
    salary_max: int | float | str | None = None
    apply_url: str | None = None
    original: bool | None = None
    logo: str | None = None


@dataclass(frozen=True, slots=True)
class RemoteOkNormalizedJob:
    external_id: str
    title: str
    company_name: str
    tags: tuple[str, ...]
    location_text: str | None
    job_url: str
    apply_url: str | None
    published_at: datetime | None
    description: str | None
    raw_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RemoteOkJobsFetch:
    endpoint: str
    requests_made: int
    array_elements_received: int
    metadata_elements_skipped: int
    job_objects_parsed: int
    invalid_job_objects_skipped: int
    duplicates_removed: int
    technical_candidates: int
    technical_rejects: int
    explicit_geo_rejects: int
    unknown_geography: int
    potentially_eligible: int
    selected_after_max_jobs: int
    normalized_jobs: int
    unique_companies: int
    publication_dates_parsed: int
    publication_dates_from_date: int
    publication_dates_from_epoch_fallback: int
    publication_dates_missing: int
    top_retained_tags: dict[str, int]
    top_retained_locations: dict[str, int]
    jobs: list[RemoteOkNormalizedJob]


class RemoteOkJobsClient:
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
        max_jobs: int = DEFAULT_REMOTEOK_MAX_JOBS,
    ) -> RemoteOkJobsFetch:
        if not 1 <= max_jobs <= MAX_REMOTEOK_MAX_JOBS:
            raise ValueError(
                "max_jobs must be between 1 and "
                f"{MAX_REMOTEOK_MAX_JOBS}."
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
                response = client.get(REMOTEOK_API_URL)

            if response.status_code == 429:
                raise RemoteOkApiError(
                    "Remote OK rate limit reached "
                    "(HTTP 429). Try again later."
                )

            if response.status_code == 403:
                raise RemoteOkApiError(
                    "Remote OK rejected the request "
                    "(HTTP 403)."
                )

            if 500 <= response.status_code <= 599:
                raise RemoteOkApiError(
                    "Remote OK server error: "
                    f"HTTP {response.status_code}."
                )

            response.raise_for_status()

            try:
                data = response.json()
            except ValueError as error:
                raise RemoteOkApiError(
                    "Remote OK returned invalid JSON."
                ) from error

            if not isinstance(data, list):
                raise RemoteOkApiError(
                    "Remote OK response shape is "
                    "missing or invalid; expected "
                    "a top-level array."
                )

        except httpx.TimeoutException as error:
            raise RemoteOkApiError(
                "Remote OK request timed out."
            ) from error
        except httpx.NetworkError as error:
            raise RemoteOkApiError(
                "Remote OK network request failed."
            ) from error

        return _normalize_response(
            data,
            max_jobs=max_jobs,
        )


def _normalize_response(
    payload: list[Any],
    *,
    max_jobs: int,
) -> RemoteOkJobsFetch:
    parsed_jobs: list[
        tuple[RemoteOkJobPosting, dict[str, Any]]
    ] = []
    metadata_elements_skipped = 0
    invalid_job_objects_skipped = 0

    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            invalid_job_objects_skipped += 1
            continue

        if index == 0 and _is_metadata_element(item):
            metadata_elements_skipped += 1
            continue

        try:
            job = RemoteOkJobPosting.model_validate(item)
        except ValidationError:
            invalid_job_objects_skipped += 1
            continue

        if _clean_text(str(job.id)) is None:
            invalid_job_objects_skipped += 1
            continue

        parsed_jobs.append((job, item))

    if metadata_elements_skipped > 0 and not parsed_jobs:
        raise RemoteOkApiError(
            "Remote OK response contained metadata "
            "but no valid job objects; expected at "
            "least one job object after metadata."
        )

    seen_ids: set[str] = set()
    unique_jobs: list[
        tuple[RemoteOkJobPosting, dict[str, Any]]
    ] = []
    duplicates_removed = 0

    for job, raw_payload in parsed_jobs:
        external_id = _clean_text(str(job.id))

        if external_id is None:
            invalid_job_objects_skipped += 1
            continue

        if external_id in seen_ids:
            duplicates_removed += 1
            continue

        seen_ids.add(external_id)
        unique_jobs.append((job, raw_payload))

    technical_jobs: list[
        tuple[RemoteOkJobPosting, dict[str, Any]]
    ] = []
    technical_rejects = 0

    for job, raw_payload in unique_jobs:
        if _is_technical_candidate(
            title=job.position,
            tags=job.tags,
        ):
            technical_jobs.append((job, raw_payload))
        else:
            technical_rejects += 1

    retained: list[
        tuple[RemoteOkJobPosting, dict[str, Any]]
    ] = []
    explicit_geo_rejects = 0
    unknown_geography = 0
    potentially_eligible = 0

    for job, raw_payload in technical_jobs:
        geo = classify_remoteok_geography(
            location=job.location,
            description=job.description,
        )

        if (
            geo
            == RemoteOkGeoClassification.EXPLICITLY_INELIGIBLE
        ):
            explicit_geo_rejects += 1
            continue

        if geo == RemoteOkGeoClassification.UNKNOWN:
            unknown_geography += 1
        else:
            potentially_eligible += 1

        retained.append((job, raw_payload))

    retained.sort(
        key=lambda pair: (
            _published_at(pair[0])
            or datetime.min.replace(tzinfo=UTC)
        ),
        reverse=True,
    )

    selected = retained[:max_jobs]
    normalized_jobs: list[RemoteOkNormalizedJob] = []
    publication_dates_from_date = 0
    publication_dates_from_epoch_fallback = 0
    publication_dates_missing = 0
    tag_counts: Counter[str] = Counter()
    location_counts: Counter[str] = Counter()

    for job, raw_payload in selected:
        published_at, publication_source = (
            _published_at_with_source(job)
        )

        if publication_source == "date":
            publication_dates_from_date += 1
        elif publication_source == "epoch_fallback":
            publication_dates_from_epoch_fallback += 1
        else:
            publication_dates_missing += 1

        tags = tuple(
            tag
            for tag in (
                _clean_text(value)
                for value in (job.tags or [])
            )
            if tag is not None
        )
        tag_counts.update(tags)

        location = _clean_text(job.location)
        if location is not None:
            location_counts.update([location])

        normalized_jobs.append(
            RemoteOkNormalizedJob(
                external_id=_required_text(
                    str(job.id),
                    "id",
                ),
                title=_required_text(
                    job.position,
                    "position",
                ),
                company_name=_required_text(
                    job.company,
                    "company",
                ),
                tags=tags,
                location_text=location,
                job_url=_required_text(
                    job.url,
                    "url",
                ),
                apply_url=_clean_text(
                    job.apply_url
                ),
                published_at=published_at,
                description=_html_to_text(
                    job.description
                ),
                raw_payload={
                    **raw_payload,
                    "tags": job.tags or [],
                },
            )
        )

    return RemoteOkJobsFetch(
        endpoint=REMOTEOK_API_URL,
        requests_made=1,
        array_elements_received=len(payload),
        metadata_elements_skipped=(
            metadata_elements_skipped
        ),
        job_objects_parsed=len(parsed_jobs),
        invalid_job_objects_skipped=(
            invalid_job_objects_skipped
        ),
        duplicates_removed=duplicates_removed,
        technical_candidates=len(technical_jobs),
        technical_rejects=technical_rejects,
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
            publication_dates_from_date
            + publication_dates_from_epoch_fallback
        ),
        publication_dates_from_date=(
            publication_dates_from_date
        ),
        publication_dates_from_epoch_fallback=(
            publication_dates_from_epoch_fallback
        ),
        publication_dates_missing=(
            publication_dates_missing
        ),
        top_retained_tags=dict(
            tag_counts.most_common(10)
        ),
        top_retained_locations=dict(
            location_counts.most_common(10)
        ),
        jobs=normalized_jobs,
    )


def classify_remoteok_geography(
    *,
    location: str | None,
    description: str | None = None,
) -> RemoteOkGeoClassification:
    location_text = _normalize_text(location)
    description_text = _normalize_text(
        _html_to_text(description)
    )

    location_restrictive = (
        _has_restrictive_location_signal(
            location_text
        )
    )

    if _has_compatible_location_signal(location_text):
        return (
            RemoteOkGeoClassification.POTENTIALLY_ELIGIBLE
        )

    if (
        _has_explicit_positive_description_signal(
            description_text
        )
        and not location_restrictive
    ):
        return (
            RemoteOkGeoClassification.POTENTIALLY_ELIGIBLE
        )

    if (
        _has_explicit_restrictive_description_signal(
            description_text
        )
        or location_restrictive
    ):
        return (
            RemoteOkGeoClassification.EXPLICITLY_INELIGIBLE
        )

    return RemoteOkGeoClassification.UNKNOWN


def _is_metadata_element(
    value: dict[str, Any],
) -> bool:
    return (
        "last_updated" in value
        or "legal" in value
    ) and "id" not in value


def _is_technical_candidate(
    *,
    title: str | None,
    tags: list[str] | None,
) -> bool:
    normalized_title = _normalize_text(title)
    normalized_tags = {
        _normalize_text(tag)
        for tag in (tags or [])
        if _normalize_text(tag)
    }

    if _has_non_target_title(normalized_title):
        return False

    if _has_positive_title_signal(normalized_title):
        return True

    return any(
        _has_positive_tag_signal(tag)
        for tag in normalized_tags
    )


def _has_positive_title_signal(
    normalized_title: str,
) -> bool:
    return re.search(
        r"\b("
        r"software engineer|software developer|"
        r"backend|back end|developer|engineer|java|"
        r"kotlin|node|node js|full stack|fullstack|"
        r"platform engineer|devops|site reliability|"
        r"sre|cloud engineer|infrastructure engineer|"
        r"api engineer|systems engineer|"
        r"distributed systems|tech lead|technical lead|"
        r"software architect|solutions architect"
        r")\b",
        normalized_title,
    ) is not None


def _has_positive_tag_signal(
    normalized_tag: str,
) -> bool:
    if normalized_tag in {
        "technical",
        "remote",
        "digital nomad",
        "exec",
    }:
        return False

    return normalized_tag in {
        "dev",
        "developer",
        "engineer",
        "backend",
        "java",
        "kotlin",
        "spring",
        "spring boot",
        "node",
        "node js",
        "typescript",
        "javascript",
        "python",
        "golang",
        "go",
        "api",
        "microservices",
        "distributed systems",
        "devops",
        "sys admin",
        "kubernetes",
        "docker",
        "aws",
        "cloud",
        "postgres",
        "postgresql",
        "sql",
    }


def _has_non_target_title(
    normalized_title: str,
) -> bool:
    return re.search(
        r"\b("
        r"recruiter|sales|customer support|"
        r"customer success|marketing|writer|"
        r"translator|data annotator|mechanic|"
        r"accountant|designer|product manager|"
        r"project manager|medical|teacher"
        r")\b",
        normalized_title,
    ) is not None


def _has_compatible_location_signal(
    normalized_text: str,
) -> bool:
    return re.search(
        r"\b("
        r"argentina|buenos aires|latam|"
        r"latin america|south america|worldwide|"
        r"anywhere|global|globally|americas"
        r")\b|"
        r"\b(gmt|utc)\s*(minus\s*)?[-+−]?\s*(2|3|4)\b|"
        r"\b(art|america argentina|"
        r"america buenos aires)\b",
        normalized_text,
    ) is not None


def _has_restrictive_location_signal(
    normalized_text: str,
) -> bool:
    if not normalized_text:
        return False

    if re.search(
        r"\b("
        r"us only|usa only|united states only|"
        r"u s only|canada only|europe only|"
        r"eu only|uk only|united kingdom only|"
        r"germany only|france only|spain only|"
        r"india only|australia only|"
        r"new zealand only|brazil only|"
        r"mexico only|colombia only"
        r")\b",
        normalized_text,
    ):
        return True

    return re.search(
        r"\b("
        r"alabama|alaska|arizona|arkansas|"
        r"california|colorado|connecticut|"
        r"delaware|florida|georgia|hawaii|"
        r"idaho|illinois|indiana|iowa|kansas|"
        r"kentucky|louisiana|maine|maryland|"
        r"massachusetts|michigan|minnesota|"
        r"mississippi|missouri|montana|nebraska|"
        r"nevada|ohio|oregon|texas|washington|"
        r"austin|new york|san francisco|"
        r"los angeles|chicago|boston|seattle"
        r")\b",
        normalized_text,
    ) is not None


def _has_explicit_positive_description_signal(
    normalized_text: str,
) -> bool:
    if not normalized_text:
        return False

    return re.search(
        r"\b("
        r"we hire globally|we hire worldwide|"
        r"open to candidates worldwide|"
        r"candidates worldwide|remote worldwide|"
        r"open worldwide|work from anywhere|"
        r"location worldwide|"
        r"open to candidates in latin america|"
        r"open to latam candidates|"
        r"latam candidates accepted|"
        r"candidates in the americas"
        r")\b",
        normalized_text,
    ) is not None


def _has_explicit_restrictive_description_signal(
    normalized_text: str,
) -> bool:
    if not normalized_text:
        return False

    return re.search(
        r"\b("
        r"must be located in (the )?"
        r"(us|u s|usa|united states|germany|"
        r"canada|europe|uk|united kingdom)|"
        r"(us|u s|usa|united states) residents only|"
        r"candidates must reside in "
        r"(germany|canada|europe|uk|"
        r"united kingdom|us|u s|usa|united states)|"
        r"only candidates based in "
        r"(europe|germany|canada|uk|"
        r"united kingdom|us|u s|usa|united states)|"
        r"only open to applicants in "
        r"(the )?(uk|united kingdom|germany|"
        r"canada|europe|us|u s|usa|united states)"
        r")\b",
        normalized_text,
    ) is not None


def _published_at(
    job: RemoteOkJobPosting,
) -> datetime | None:
    published_at, _source = _published_at_with_source(
        job
    )
    return published_at


def _published_at_with_source(
    job: RemoteOkJobPosting,
) -> tuple[datetime | None, str | None]:
    date = _parse_iso_datetime(job.date)

    if date is not None:
        return (date, "date")

    epoch = _clean_text(
        str(job.epoch)
        if job.epoch is not None
        else None
    )

    if epoch is not None:
        try:
            return (
                datetime.fromtimestamp(
                    float(epoch),
                    tz=UTC,
                ),
                "epoch_fallback",
            )
        except (ValueError, OverflowError):
            pass

    return (None, None)


def _parse_iso_datetime(
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
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)

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

    cleaned = " ".join(unescape(str(value)).split())

    return cleaned if cleaned else None


def _normalize_text(
    value: str | None,
) -> str:
    if value is None:
        return ""

    cleaned = _clean_text(value)

    if cleaned is None:
        return ""

    return " ".join(
        re.findall(
            r"[a-z0-9]+",
            cleaned.casefold()
            .replace(".js", " js")
            .replace("-", " "),
        )
    )


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
