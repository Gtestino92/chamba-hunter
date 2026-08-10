from dataclasses import dataclass
import os

import httpx
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)


JOOBLE_API_KEY_ENV = "JOOBLE_API_KEY"
JOOBLE_ARGENTINA_API_BASE = (
    "https://ar.jooble.org/api"
)
JOOBLE_LOCATION = "Argentina"
JOOBLE_RESULTS_PER_PAGE = 50
JOOBLE_QUERIES = (
    "backend",
    "java developer",
    "spring boot",
)


class JoobleJobPosting(BaseModel):
    model_config = ConfigDict(
        extra="allow"
    )

    id: int | str
    title: str | None = None
    location: str | None = None
    snippet: str | None = None
    salary: str | None = None
    source: str | None = None
    job_type: str | None = Field(
        default=None,
        alias="type",
    )
    link: str | None = None
    company: str | None = None
    updated: str | None = None


class JoobleJobsResponse(BaseModel):
    model_config = ConfigDict(
        extra="allow"
    )

    total_count: int | None = Field(
        default=None,
        alias="totalCount",
    )
    jobs: list[JoobleJobPosting] = Field(
        default_factory=list
    )


@dataclass(frozen=True, slots=True)
class JoobleFetchedJob:
    posting: JoobleJobPosting
    matched_queries: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class JoobleJobsFetch:
    requests_made: int
    jobs: list[JoobleFetchedJob]


class JoobleJobsClient:
    def __init__(
        self,
        api_key: str,
        timeout_seconds: float = 30.0,
    ) -> None:
        cleaned_key = api_key.strip()

        if not cleaned_key:
            raise ValueError(
                "Jooble API key cannot be empty."
            )

        self.api_key = cleaned_key
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_environment(
        cls,
    ) -> "JoobleJobsClient":
        api_key = os.environ.get(
            JOOBLE_API_KEY_ENV
        )

        if api_key is None or not api_key.strip():
            raise RuntimeError(
                f"{JOOBLE_API_KEY_ENV} is not set."
            )

        return cls(
            api_key=api_key
        )

    def fetch_jobs(
        self,
        *,
        max_pages_per_query: int,
    ) -> JoobleJobsFetch:
        if max_pages_per_query <= 0:
            raise ValueError(
                "max_pages_per_query must be positive."
            )

        endpoint = (
            f"{JOOBLE_ARGENTINA_API_BASE}/"
            f"{self.api_key}"
        )

        requests_made = 0
        postings_by_id: dict[
            str,
            JoobleJobPosting,
        ] = {}
        query_matches_by_id: dict[
            str,
            list[str],
        ] = {}
        order: list[str] = []

        with httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "chamba-hunter/0.1",
            },
        ) as client:
            for query in JOOBLE_QUERIES:
                for page in range(
                    1,
                    max_pages_per_query + 1,
                ):
                    try:
                        response = client.post(
                            endpoint,
                            json={
                                "keywords": query,
                                "location": JOOBLE_LOCATION,
                                "page": str(page),
                                "ResultOnPage": str(
                                    JOOBLE_RESULTS_PER_PAGE
                                ),
                                "companysearch": "false",
                            },
                        )
                    except httpx.RequestError:
                        raise RuntimeError(
                            "Jooble request failed before "
                            "receiving an HTTP response."
                        ) from None

                    requests_made += 1

                    if response.status_code == 403:
                        raise RuntimeError(
                            "Jooble API key was rejected "
                            "by ar.jooble.org."
                        )

                    if response.status_code == 429:
                        raise RuntimeError(
                            "Jooble rate limit reached."
                        )

                    if response.status_code != 200:
                        raise RuntimeError(
                            "Jooble request failed with "
                            f"HTTP {response.status_code}."
                        )

                    payload = (
                        JoobleJobsResponse
                        .model_validate(
                            response.json()
                        )
                    )

                    for posting in payload.jobs:
                        external_id = str(
                            posting.id
                        ).strip()

                        if not external_id:
                            continue

                        if external_id not in postings_by_id:
                            postings_by_id[external_id] = posting
                            query_matches_by_id[external_id] = []
                            order.append(external_id)

                        matches = query_matches_by_id[
                            external_id
                        ]

                        if query not in matches:
                            matches.append(query)

                    if not payload.jobs:
                        break

                    if (
                        len(payload.jobs)
                        < JOOBLE_RESULTS_PER_PAGE
                    ):
                        break

                    if (
                        payload.total_count is not None
                        and page * JOOBLE_RESULTS_PER_PAGE
                        >= payload.total_count
                    ):
                        break

        jobs = [
            JoobleFetchedJob(
                posting=postings_by_id[external_id],
                matched_queries=tuple(
                    query_matches_by_id[external_id]
                ),
            )
            for external_id in order
        ]

        return JoobleJobsFetch(
            requests_made=requests_made,
            jobs=jobs,
        )
