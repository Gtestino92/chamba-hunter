from dataclasses import dataclass
from datetime import datetime

import httpx
from pydantic import BaseModel, ConfigDict, Field


ASHBY_POSTING_API_URL = (
    "https://api.ashbyhq.com/"
    "posting-api/job-board"
)


class AshbySecondaryLocation(BaseModel):
    model_config = ConfigDict(extra="allow")

    location: str | None = None


class AshbyJob(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str
    location: str | None = None
    secondary_locations: list[
        AshbySecondaryLocation
    ] = Field(
        default_factory=list,
        alias="secondaryLocations",
    )
    department: str | None = None
    team: str | None = None
    is_listed: bool = Field(
        alias="isListed"
    )
    is_remote: bool | None = Field(
        default=None,
        alias="isRemote",
    )
    workplace_type: str | None = Field(
        default=None,
        alias="workplaceType",
    )
    description_html: str | None = Field(
        default=None,
        alias="descriptionHtml",
    )
    description_plain: str | None = Field(
        default=None,
        alias="descriptionPlain",
    )
    published_at: datetime | None = Field(
        default=None,
        alias="publishedAt",
    )
    employment_type: str | None = Field(
        default=None,
        alias="employmentType",
    )
    job_url: str = Field(
        alias="jobUrl"
    )
    apply_url: str | None = Field(
        default=None,
        alias="applyUrl",
    )


class AshbyJobsResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    api_version: str = Field(
        alias="apiVersion"
    )
    jobs: list[AshbyJob]


@dataclass(frozen=True, slots=True)
class AshbyJobsFetch:
    http_status: int
    total: int
    jobs: list[AshbyJob]


class AshbyClient:
    def __init__(
        self,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.timeout_seconds = timeout_seconds

    def fetch_jobs(
        self,
        board_name: str,
    ) -> AshbyJobsFetch:
        url = (
            f"{ASHBY_POSTING_API_URL}/"
            f"{board_name}"
        )

        with httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": "chamba-hunter/0.1"
            },
        ) as client:
            response = client.get(url)

        response.raise_for_status()

        payload = (
            AshbyJobsResponse
            .model_validate(
                response.json()
            )
        )

        if payload.api_version != "1":
            raise ValueError(
                "Unsupported Ashby public jobs "
                "API version: "
                f"{payload.api_version}."
            )

        return AshbyJobsFetch(
            http_status=response.status_code,
            total=len(payload.jobs),
            jobs=payload.jobs,
        )