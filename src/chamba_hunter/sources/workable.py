from dataclasses import dataclass

import httpx
from pydantic import BaseModel, ConfigDict, Field


WORKABLE_ACCOUNTS_API_URL = (
    "https://www.workable.com/api/accounts"
)


class WorkableLocation(BaseModel):
    model_config = ConfigDict(
        extra="allow"
    )

    country: str | None = None
    country_code: str | None = Field(
        default=None,
        alias="countryCode",
    )
    city: str | None = None
    region: str | None = None
    hidden: bool | None = None


class WorkableJob(BaseModel):
    model_config = ConfigDict(
        extra="allow"
    )

    title: str
    shortcode: str

    code: str | None = None
    employment_type: str | None = None
    telecommuting: bool | None = None
    department: str | None = None

    url: str | None = None
    shortlink: str | None = None
    application_url: str | None = None

    published_on: str | None = None
    created_at: str | None = None

    country: str | None = None
    city: str | None = None
    state: str | None = None

    education: str | None = None
    experience: str | None = None
    function: str | None = None
    industry: str | None = None

    locations: list[WorkableLocation] = Field(
        default_factory=list
    )

    description: str | None = None


class WorkableJobsResponse(BaseModel):
    model_config = ConfigDict(
        extra="allow"
    )

    name: str
    description: str | None = None
    jobs: list[WorkableJob]


@dataclass(frozen=True, slots=True)
class WorkableJobsFetch:
    http_status: int
    total: int
    jobs: list[WorkableJob]


class WorkableClient:
    def __init__(
        self,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.timeout_seconds = (
            timeout_seconds
        )

    def fetch_jobs(
        self,
        account_subdomain: str,
    ) -> WorkableJobsFetch:
        cleaned_account = (
            account_subdomain.strip()
        )

        if not cleaned_account:
            raise ValueError(
                "Workable account subdomain "
                "cannot be empty."
            )

        url = (
            f"{WORKABLE_ACCOUNTS_API_URL}/"
            f"{cleaned_account}"
        )

        with httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "chamba-hunter/0.1"
                ),
                "Accept": "application/json",
            },
        ) as client:
            response = client.get(
                url,
                params={
                    "details": "true",
                },
            )

        response.raise_for_status()

        payload = (
            WorkableJobsResponse
            .model_validate(
                response.json()
            )
        )

        jobs = _collapse_location_variants(
            payload.jobs
        )

        return WorkableJobsFetch(
            http_status=response.status_code,
            total=len(jobs),
            jobs=jobs,
        )


def _collapse_location_variants(
    jobs: list[WorkableJob],
) -> list[WorkableJob]:
    by_shortcode: dict[
        str,
        WorkableJob,
    ] = {}

    order: list[str] = []

    for job in jobs:
        shortcode = job.shortcode.strip()

        if not shortcode:
            raise ValueError(
                "Workable returned a job "
                "with an empty shortcode."
            )

        normalized_job = (
            job.model_copy(
                update={
                    "shortcode": shortcode,
                    "locations": (
                        _job_locations(job)
                    ),
                }
            )
        )

        existing = by_shortcode.get(
            shortcode
        )

        if existing is None:
            by_shortcode[shortcode] = (
                normalized_job
            )
            order.append(shortcode)
            continue

        if (
            _posting_signature(existing)
            != _posting_signature(
                normalized_job
            )
        ):
            raise ValueError(
                "Workable returned multiple "
                "different postings with the "
                "same shortcode: "
                f"{shortcode}"
            )

        merged_locations = (
            _merge_locations(
                existing.locations,
                normalized_job.locations,
            )
        )

        by_shortcode[shortcode] = (
            existing.model_copy(
                update={
                    "locations": (
                        merged_locations
                    ),
                    "country": None,
                    "city": None,
                    "state": None,
                }
            )
        )

    return [
        by_shortcode[shortcode]
        for shortcode in order
    ]


def _posting_signature(
    job: WorkableJob,
) -> tuple:
    return (
        job.title,
        job.code,
        job.employment_type,
        job.telecommuting,
        job.department,
        job.url,
        job.shortlink,
        job.application_url,
        job.published_on,
        job.created_at,
        job.education,
        job.experience,
        job.function,
        job.industry,
        job.description,
    )


def _job_locations(
    job: WorkableJob,
) -> list[WorkableLocation]:
    if job.locations:
        return list(job.locations)

    if not any(
        (
            job.country,
            job.city,
            job.state,
        )
    ):
        return []

    return [
        WorkableLocation(
            country=job.country,
            city=job.city,
            region=job.state,
        )
    ]


def _merge_locations(
    first: list[WorkableLocation],
    second: list[WorkableLocation],
) -> list[WorkableLocation]:
    merged: list[WorkableLocation] = []
    seen: set[tuple] = set()

    for location in [
        *first,
        *second,
    ]:
        key = (
            _normalized_location_part(
                location.country_code
            ),
            _normalized_location_part(
                location.country
            ),
            _normalized_location_part(
                location.city
            ),
            _normalized_location_part(
                location.region
            ),
            location.hidden,
        )

        if key in seen:
            continue

        seen.add(key)
        merged.append(location)

    return merged


def _normalized_location_part(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    cleaned = value.strip()

    if not cleaned:
        return None

    return cleaned.casefold()
