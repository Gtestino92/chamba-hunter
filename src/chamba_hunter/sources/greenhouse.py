from dataclasses import dataclass

import httpx
from pydantic import BaseModel, ConfigDict


GREENHOUSE_BOARDS_API_URL = (
    "https://boards-api.greenhouse.io/"
    "v1/boards"
)


class GreenhouseLocation(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str | None = None


class GreenhouseJob(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    internal_job_id: int | None = None
    title: str

    location: GreenhouseLocation | None = None
    absolute_url: str | None = None
    content: str | None = None


class GreenhouseJobsMeta(BaseModel):
    model_config = ConfigDict(extra="allow")

    total: int


class GreenhouseJobsResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    jobs: list[GreenhouseJob]
    meta: GreenhouseJobsMeta


@dataclass(frozen=True, slots=True)
class GreenhouseJobsFetch:
    http_status: int
    total: int
    jobs: list[GreenhouseJob]


class GreenhouseClient:
    def __init__(
        self,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.timeout_seconds = timeout_seconds

    def fetch_jobs(
        self,
        board_token: str,
    ) -> GreenhouseJobsFetch:
        url = (
            f"{GREENHOUSE_BOARDS_API_URL}/"
            f"{board_token}/jobs"
        )

        with httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": "chamba-hunter/0.1"
            },
        ) as client:
            response = client.get(
                url,
                params={
                    "content": "true",
                },
            )

        response.raise_for_status()

        payload = (
            GreenhouseJobsResponse
            .model_validate(
                response.json()
            )
        )

        if payload.meta.total != len(
            payload.jobs
        ):
            raise ValueError(
                "Greenhouse returned an "
                "incomplete jobs response: "
                f"meta.total={payload.meta.total}, "
                f"jobs={len(payload.jobs)}."
            )

        return GreenhouseJobsFetch(
            http_status=response.status_code,
            total=payload.meta.total,
            jobs=payload.jobs,
        )