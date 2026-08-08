from dataclasses import dataclass

import httpx
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
)


LEVER_POSTINGS_API_URL = (
    "https://api.lever.co/v0/postings"
)

DEFAULT_PAGE_SIZE = 100


class LeverCategories(BaseModel):
    model_config = ConfigDict(
        extra="allow"
    )

    location: str | None = None
    commitment: str | None = None
    team: str | None = None
    department: str | None = None
    all_locations: list[str] = Field(
        default_factory=list,
        alias="allLocations",
    )


class LeverJob(BaseModel):
    model_config = ConfigDict(
        extra="allow"
    )

    id: str
    text: str

    categories: LeverCategories | None = (
        None
    )

    country: str | None = None

    description_plain: str | None = Field(
        default=None,
        alias="descriptionPlain",
    )

    additional_plain: str | None = Field(
        default=None,
        alias="additionalPlain",
    )

    hosted_url: str | None = Field(
        default=None,
        alias="hostedUrl",
    )

    apply_url: str | None = Field(
        default=None,
        alias="applyUrl",
    )

    workplace_type: str | None = Field(
        default=None,
        alias="workplaceType",
    )


@dataclass(frozen=True, slots=True)
class LeverJobsFetch:
    http_status: int
    total: int
    jobs: list[LeverJob]


_LEVER_JOBS_ADAPTER = TypeAdapter(
    list[LeverJob]
)


class LeverClient:
    def __init__(
        self,
        timeout_seconds: float = 20.0,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> None:
        if not 1 <= page_size <= 100:
            raise ValueError(
                "Lever page_size must be "
                "between 1 and 100."
            )

        self.timeout_seconds = (
            timeout_seconds
        )
        self.page_size = page_size

    def fetch_jobs(
        self,
        site_name: str,
    ) -> LeverJobsFetch:
        cleaned_site_name = (
            site_name.strip()
        )

        if not cleaned_site_name:
            raise ValueError(
                "Lever site name cannot "
                "be empty."
            )

        url = (
            f"{LEVER_POSTINGS_API_URL}/"
            f"{cleaned_site_name}"
        )

        jobs: list[LeverJob] = []
        seen_ids: set[str] = set()
        skip = 0
        http_status = 200

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
            while True:
                response = client.get(
                    url,
                    params={
                        "mode": "json",
                        "skip": skip,
                        "limit": (
                            self.page_size
                        ),
                    },
                )

                response.raise_for_status()

                http_status = (
                    response.status_code
                )

                page_jobs = (
                    _LEVER_JOBS_ADAPTER
                    .validate_python(
                        response.json()
                    )
                )

                if not page_jobs:
                    break

                for job in page_jobs:
                    posting_id = job.id.strip()

                    if not posting_id:
                        raise ValueError(
                            "Lever returned a "
                            "posting with an "
                            "empty id."
                        )

                    if posting_id in seen_ids:
                        raise ValueError(
                            "Lever returned a "
                            "duplicate posting "
                            "id across paginated "
                            "results: "
                            f"{posting_id}"
                        )

                    seen_ids.add(
                        posting_id
                    )

                jobs.extend(page_jobs)

                if (
                    len(page_jobs)
                    < self.page_size
                ):
                    break

                skip += len(page_jobs)

        return LeverJobsFetch(
            http_status=http_status,
            total=len(jobs),
            jobs=jobs,
        )
