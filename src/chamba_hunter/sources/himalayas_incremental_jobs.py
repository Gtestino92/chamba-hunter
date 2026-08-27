from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from time import sleep

import httpx
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)


HIMALAYAS_SEARCH_URL = (
    "https://himalayas.app/jobs/api/search"
)

ARGENTINA_COUNTRY_CODE = "AR"

CONSECUTIVE_OLD_PAGES_TO_STOP = 2

DEFAULT_REQUEST_DELAY_SECONDS = 0.75
MAX_RATE_LIMIT_RETRIES = 5
DEFAULT_RATE_LIMIT_BACKOFF_SECONDS = 2.0


class HimalayasLocationRestriction(BaseModel):
    model_config = ConfigDict(
        extra="allow"
    )

    alpha2: str | None = None
    name: str | None = None
    slug: str | None = None


class HimalayasJobPosting(BaseModel):
    model_config = ConfigDict(
        extra="allow"
    )

    guid: str
    title: str

    excerpt: str | None = None
    description: str | None = None

    company_name: str = Field(
        alias="companyName"
    )
    company_slug: str = Field(
        alias="companySlug"
    )

    employment_type: str | None = Field(
        default=None,
        alias="employmentType",
    )

    location_restrictions: list[
        str | HimalayasLocationRestriction
    ] = Field(
        default_factory=list,
        alias="locationRestrictions",
    )

    timezone_restrictions: list[
        str | int | float
    ] = Field(
        default_factory=list,
        alias="timezoneRestrictions",
    )

    categories: list[str] = Field(
        default_factory=list
    )

    parent_categories: list[str] = Field(
        default_factory=list,
        alias="parentCategories",
    )

    seniority: list[str] = Field(
        default_factory=list
    )

    pub_date: int | float | str | None = Field(
        default=None,
        alias="pubDate",
    )

    expiry_date: int | float | str | None = Field(
        default=None,
        alias="expiryDate",
    )

    application_link: str | None = Field(
        default=None,
        alias="applicationLink",
    )


class HimalayasJobsResponse(BaseModel):
    model_config = ConfigDict(
        extra="allow"
    )

    total_count: int = Field(
        alias="totalCount"
    )

    jobs: list[
        HimalayasJobPosting
    ]


@dataclass(frozen=True, slots=True)
class HimalayasWindowFetch:
    cutoff: datetime

    total_available: int
    requests_made: int
    pages_fetched: int

    cutoff_reached: bool

    jobs: list[HimalayasJobPosting]

    old_jobs_skipped: int
    undated_jobs_kept: int


def publication_datetime(
    job: HimalayasJobPosting,
) -> datetime | None:
    return _source_datetime(
        job.pub_date,
        field_name="pubDate",
    )


def _source_datetime(
    value: int | float | str | None,
    *,
    field_name: str,
) -> datetime | None:
    if value is None:
        return None

    if isinstance(
        value,
        str,
    ):
        cleaned = value.strip()

        if not cleaned:
            return None

        try:
            numeric = float(
                cleaned
            )
        except ValueError:
            normalized = (
                cleaned[:-1] + "+00:00"
                if cleaned.endswith("Z")
                else cleaned
            )

            parsed = (
                datetime.fromisoformat(
                    normalized
                )
            )

            if parsed.tzinfo is None:
                raise ValueError(
                    "Himalayas "
                    f"{field_name} must include "
                    "timezone information: "
                    f"{value}"
                )

            return parsed.astimezone(
                UTC
            )
    else:
        numeric = float(
            value
        )

    seconds = (
        numeric / 1000
        if abs(numeric)
        >= 100_000_000_000
        else numeric
    )

    return datetime.fromtimestamp(
        seconds,
        tz=UTC,
    )


def expiry_datetime(
    job: HimalayasJobPosting,
) -> datetime | None:
    return _source_datetime(
        job.expiry_date,
        field_name="expiryDate",
    )


def _retry_after_seconds(
    response: httpx.Response,
) -> float | None:
    raw = response.headers.get(
        "Retry-After"
    )

    if raw is None:
        return None

    value = raw.strip()

    if not value:
        return None

    try:
        seconds = float(
            value
        )
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(
                value
            )
        except (
            TypeError,
            ValueError,
            OverflowError,
        ):
            return None

        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(
                tzinfo=UTC
            )

        seconds = (
            retry_at.astimezone(UTC)
            - datetime.now(UTC)
        ).total_seconds()

    return max(
        0.0,
        seconds,
    )


class HimalayasIncrementalJobsClient:
    def __init__(
        self,
        timeout_seconds: float = 20.0,
        request_delay_seconds: float = (
            DEFAULT_REQUEST_DELAY_SECONDS
        ),
        max_rate_limit_retries: int = (
            MAX_RATE_LIMIT_RETRIES
        ),
    ) -> None:
        if request_delay_seconds < 0:
            raise ValueError(
                "request_delay_seconds cannot "
                "be negative."
            )

        if max_rate_limit_retries < 0:
            raise ValueError(
                "max_rate_limit_retries cannot "
                "be negative."
            )

        self.timeout_seconds = (
            timeout_seconds
        )
        self.request_delay_seconds = (
            request_delay_seconds
        )
        self.max_rate_limit_retries = (
            max_rate_limit_retries
        )

    def fetch_since(
        self,
        *,
        cutoff: datetime,
    ) -> HimalayasWindowFetch:
        if cutoff.tzinfo is None:
            raise ValueError(
                "cutoff must be timezone-aware."
            )

        cutoff = cutoff.astimezone(
            UTC
        )

        jobs: list[
            HimalayasJobPosting
        ] = []

        seen_guids: set[str] = set()

        page_number = 1

        total_available = 0
        requests_made = 0
        pages_fetched = 0

        cutoff_reached = False

        old_jobs_skipped = 0
        undated_jobs_kept = 0

        consecutive_old_pages = 0

        with httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "chamba-hunter/0.1"
                ),
                "Accept": (
                    "application/json"
                ),
            },
        ) as client:
            while True:
                response: (
                    httpx.Response
                    | None
                ) = None

                for retry_index in range(
                    self.max_rate_limit_retries
                    + 1
                ):
                    response = client.get(
                        HIMALAYAS_SEARCH_URL,
                        params={
                            "country": (
                                ARGENTINA_COUNTRY_CODE
                            ),
                            "sort": "recent",
                            "page": page_number,
                        },
                    )

                    requests_made += 1

                    if (
                        response.status_code
                        != 429
                    ):
                        break

                    if (
                        retry_index
                        >= self.max_rate_limit_retries
                    ):
                        raise RuntimeError(
                            "Himalayas rate limit "
                            "reached after retries."
                        )

                    retry_after = (
                        _retry_after_seconds(
                            response
                        )
                    )

                    delay = (
                        retry_after
                        if retry_after is not None
                        else (
                            DEFAULT_RATE_LIMIT_BACKOFF_SECONDS
                            * (
                                2
                                ** retry_index
                            )
                        )
                    )

                    sleep(
                        delay
                    )

                if response is None:
                    raise RuntimeError(
                        "Himalayas request did "
                        "not produce a response."
                    )

                response.raise_for_status()

                payload = (
                    HimalayasJobsResponse
                    .model_validate(
                        response.json()
                    )
                )

                pages_fetched += 1
                total_available = (
                    payload.total_count
                )

                page = payload.jobs

                if not page:
                    cutoff_reached = True
                    break

                page_dates: list[
                    datetime
                ] = []

                for job in page:
                    guid = (
                        job.guid.strip()
                    )

                    if not guid:
                        raise ValueError(
                            "Himalayas returned "
                            "an empty job guid."
                        )

                    published_at = (
                        publication_datetime(
                            job
                        )
                    )

                    if published_at is not None:
                        page_dates.append(
                            published_at
                        )

                    if guid in seen_guids:
                        continue

                    seen_guids.add(
                        guid
                    )

                    if published_at is None:
                        jobs.append(
                            job
                        )
                        undated_jobs_kept += 1
                        continue

                    if published_at >= cutoff:
                        jobs.append(
                            job
                        )
                    else:
                        old_jobs_skipped += 1

                page_is_fully_old = (
                    bool(page_dates)
                    and max(page_dates)
                    < cutoff
                )

                if page_is_fully_old:
                    consecutive_old_pages += 1
                else:
                    consecutive_old_pages = 0

                if (
                    consecutive_old_pages
                    >= CONSECUTIVE_OLD_PAGES_TO_STOP
                ):
                    cutoff_reached = True
                    break

                page_number += 1

                if self.request_delay_seconds > 0:
                    sleep(
                        self.request_delay_seconds
                    )

        return HimalayasWindowFetch(
            cutoff=cutoff,
            total_available=total_available,
            requests_made=requests_made,
            pages_fetched=pages_fetched,
            cutoff_reached=cutoff_reached,
            jobs=jobs,
            old_jobs_skipped=(
                old_jobs_skipped
            ),
            undated_jobs_kept=(
                undated_jobs_kept
            ),
        )
