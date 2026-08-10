from dataclasses import dataclass

import httpx
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)


JOBICY_REMOTE_JOBS_URL = (
    "https://jobicy.com/api/v2/remote-jobs"
)

JOBICY_ENGINEERING_INDUSTRY = "engineering"
JOBICY_TARGET_GEO = "latam"


class JobicyJobPosting(BaseModel):
    model_config = ConfigDict(
        extra="allow"
    )

    id: int | str
    url: str
    job_title: str = Field(
        alias="jobTitle"
    )
    company_name: str = Field(
        alias="companyName"
    )

    job_industry: list[str] | str | None = Field(
        default=None,
        alias="jobIndustry",
    )
    job_type: list[str] | str | None = Field(
        default=None,
        alias="jobType",
    )
    job_geo: str | None = Field(
        default=None,
        alias="jobGeo",
    )
    job_level: str | None = Field(
        default=None,
        alias="jobLevel",
    )
    job_excerpt: str | None = Field(
        default=None,
        alias="jobExcerpt",
    )
    job_description: str | None = Field(
        default=None,
        alias="jobDescription",
    )
    pub_date: str | None = Field(
        default=None,
        alias="pubDate",
    )


class JobicyJobsResponse(BaseModel):
    model_config = ConfigDict(
        extra="allow"
    )

    jobs: list[
        JobicyJobPosting
    ] = Field(
        default_factory=list
    )


@dataclass(frozen=True, slots=True)
class JobicyJobsFetch:
    requests_made: int
    jobs: list[
        JobicyJobPosting
    ]


class JobicyJobsClient:
    def __init__(
        self,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.timeout_seconds = (
            timeout_seconds
        )

    def fetch_engineering_jobs(
        self,
        max_jobs: int,
    ) -> JobicyJobsFetch:
        if not 1 <= max_jobs <= 100:
            raise ValueError(
                "max_jobs must be "
                "between 1 and 100."
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
                JOBICY_REMOTE_JOBS_URL,
                params={
                    "count": max_jobs,
                    "industry": (
                        JOBICY_ENGINEERING_INDUSTRY
                    ),
                    "geo": (
                        JOBICY_TARGET_GEO
                    ),
                },
            )

            if response.status_code == 429:
                raise RuntimeError(
                    "Jobicy rate limit reached."
                )

            response.raise_for_status()

            payload = (
                JobicyJobsResponse
                .model_validate(
                    response.json()
                )
            )

        jobs: list[
            JobicyJobPosting
        ] = []
        seen_ids: set[str] = set()

        for job in payload.jobs:
            external_id = str(
                job.id
            ).strip()

            if not external_id:
                raise ValueError(
                    "Jobicy returned "
                    "an empty job id."
                )

            if external_id in seen_ids:
                continue

            seen_ids.add(
                external_id
            )
            jobs.append(job)

        return JobicyJobsFetch(
            requests_made=1,
            jobs=jobs,
        )
