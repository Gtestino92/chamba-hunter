from dataclasses import dataclass

import httpx
from pydantic import BaseModel, ConfigDict


HIMALAYAS_SEARCH_URL = "https://himalayas.app/jobs/api/search"


class HimalayasJob(BaseModel):
    model_config = ConfigDict(extra="ignore")

    companyName: str
    companySlug: str


class HimalayasSearchResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    jobs: list[HimalayasJob]


@dataclass(frozen=True, slots=True)
class HimalayasCompany:
    name: str
    slug: str

    @property
    def source_url(self) -> str:
        return f"https://himalayas.app/companies/{self.slug}"


class HimalayasClient:
    def __init__(
        self,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.timeout_seconds = timeout_seconds

    def search_companies(
        self,
        query: str,
        country: str,
        max_pages: int,
    ) -> list[HimalayasCompany]:
        companies: dict[str, HimalayasCompany] = {}

        with httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": "chamba-hunter/0.1"
            },
        ) as client:
            for page in range(1, max_pages + 1):
                response = client.get(
                    HIMALAYAS_SEARCH_URL,
                    params={
                        "q": query,
                        "country": country,
                        "sort": "recent",
                        "page": page,
                    },
                )

                if response.status_code == 429:
                    raise RuntimeError(
                        "Himalayas rate limit reached. "
                        "Try again later with fewer pages."
                    )

                response.raise_for_status()

                payload = HimalayasSearchResponse.model_validate(
                    response.json()
                )

                if not payload.jobs:
                    break

                for job in payload.jobs:
                    companies[job.companySlug] = HimalayasCompany(
                        name=job.companyName,
                        slug=job.companySlug,
                    )

        return list(companies.values())