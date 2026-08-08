from dataclasses import dataclass

import httpx

from chamba_hunter.sources.getonboard import (
    GETONBOARD_PROGRAMMING_URL,
    PER_PAGE,
    GetOnBoardJobResource,
    GetOnBoardJobsResponse,
)


@dataclass(frozen=True, slots=True)
class GetOnBoardJobsFetch:
    pages_fetched: int
    jobs: list[GetOnBoardJobResource]


class GetOnBoardJobsClient:
    def __init__(
        self,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.timeout_seconds = (
            timeout_seconds
        )

    def fetch_programming_jobs(
        self,
        max_pages: int,
    ) -> GetOnBoardJobsFetch:
        if max_pages < 1:
            raise ValueError(
                "max_pages must be at least 1."
            )

        jobs: list[
            GetOnBoardJobResource
        ] = []
        seen_ids: set[str] = set()
        pages_fetched = 0

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
            for page in range(
                1,
                max_pages + 1,
            ):
                response = client.get(
                    GETONBOARD_PROGRAMMING_URL,
                    params={
                        "per_page": PER_PAGE,
                        "expand[]": "company",
                        "page": page,
                    },
                )

                if response.status_code == 429:
                    raise RuntimeError(
                        "Get on Board rate "
                        "limit reached."
                    )

                response.raise_for_status()

                pages_fetched += 1

                payload = (
                    GetOnBoardJobsResponse
                    .model_validate(
                        response.json()
                    )
                )

                if not payload.data:
                    break

                for job in payload.data:
                    external_id = (
                        job.id.strip()
                    )

                    if not external_id:
                        raise ValueError(
                            "Get on Board "
                            "returned an empty "
                            "job id."
                        )

                    if external_id in seen_ids:
                        raise ValueError(
                            "Get on Board "
                            "returned a duplicate "
                            "job id while "
                            "paginating: "
                            f"{external_id}"
                        )

                    seen_ids.add(
                        external_id
                    )

                jobs.extend(payload.data)

                if len(payload.data) < PER_PAGE:
                    break

        return GetOnBoardJobsFetch(
            pages_fetched=pages_fetched,
            jobs=jobs,
        )
