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
