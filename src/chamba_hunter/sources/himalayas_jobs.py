from dataclasses import dataclass
from time import sleep

import httpx
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)


HIMALAYAS_JOBS_URL = (
    "https://himalayas.app/jobs/api"
)

PAGE_SIZE = 20


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

    # The live API currently returns country names as strings,
    # while Himalayas documentation has also shown object-shaped
    # restrictions. Accept both so acquisition is resilient.
    location_restrictions: list[
        str | HimalayasLocationRestriction
    ] = Field(
        default_factory=list,
        alias="locationRestrictions",
    )

    # The live API currently returns numeric UTC offsets, while
    # documentation has also described them as strings.
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

    jobs: list[HimalayasJobPosting]


@dataclass(frozen=True, slots=True)
class HimalayasJobsFetch:
    total_available: int
    requests_made: int
    jobs: list[HimalayasJobPosting]


class HimalayasJobsClient:
    def __init__(
        self,
        timeout_seconds: float = 20.0,
        request_delay_seconds: float = 0.05,
    ) -> None:
        self.timeout_seconds = (
            timeout_seconds
        )
        self.request_delay_seconds = (
            request_delay_seconds
        )

    def browse_jobs(
        self,
        max_jobs: int,
    ) -> HimalayasJobsFetch:
        if max_jobs < 1:
            raise ValueError(
                "max_jobs must be at least 1."
            )

        jobs: list[HimalayasJobPosting] = []
        seen_guids: set[str] = set()

        offset = 0
        total_available = 0
        requests_made = 0

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
            while len(jobs) < max_jobs:
                limit = min(
                    PAGE_SIZE,
                    max_jobs - len(jobs),
                )

                response = client.get(
                    HIMALAYAS_JOBS_URL,
                    params={
                        "offset": offset,
                        "limit": limit,
                    },
                )

                requests_made += 1

                if response.status_code == 429:
                    raise RuntimeError(
                        "Himalayas rate limit "
                        "reached. Re-run later "
                        "with a smaller --"
                        "himalayas-max-jobs."
                    )

                response.raise_for_status()

                payload = (
                    HimalayasJobsResponse
                    .model_validate(
                        response.json()
                    )
                )

                total_available = (
                    payload.total_count
                )

                if not payload.jobs:
                    break

                unique_page_jobs: list[
                    HimalayasJobPosting
                ] = []

                for job in payload.jobs:
                    guid = job.guid.strip()

                    if not guid:
                        raise ValueError(
                            "Himalayas returned "
                            "an empty job guid."
                        )

                    # The public feed can overlap across adjacent
                    # offset pages. Treat guid as the stable identity
                    # and ignore repeated postings instead of failing
                    # the entire acquisition run.
                    if guid in seen_guids:
                        continue

                    seen_guids.add(guid)
                    unique_page_jobs.append(job)

                jobs.extend(unique_page_jobs)

                # Advance by the number of records returned by the
                # provider, not by the number of unique records kept.
                # This guarantees progress even when pages overlap.
                offset += len(payload.jobs)

                if (
                    offset >= total_available
                    or len(payload.jobs) < limit
                ):
                    break

                if self.request_delay_seconds > 0:
                    sleep(
                        self.request_delay_seconds
                    )

        return HimalayasJobsFetch(
            total_available=total_available,
            requests_made=requests_made,
            jobs=jobs[:max_jobs],
        )
