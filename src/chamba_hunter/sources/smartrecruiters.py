from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
)
from dataclasses import dataclass

import httpx
from pydantic import BaseModel, ConfigDict, Field


SMARTRECRUITERS_COMPANIES_API_URL = (
    "https://api.smartrecruiters.com/"
    "v1/companies"
)

DEFAULT_PAGE_SIZE = 100


class SmartRecruitersLocation(BaseModel):
    model_config = ConfigDict(
        extra="allow"
    )

    city: str | None = None
    region: str | None = None
    country: str | None = None
    remote: bool | None = None
    hybrid: bool | None = None

    full_location: str | None = Field(
        default=None,
        alias="fullLocation",
    )


class SmartRecruitersLabel(BaseModel):
    model_config = ConfigDict(
        extra="allow"
    )

    id: str | None = None
    label: str | None = None


class SmartRecruitersSection(BaseModel):
    model_config = ConfigDict(
        extra="allow"
    )

    title: str | None = None
    text: str | None = None


class SmartRecruitersSections(BaseModel):
    model_config = ConfigDict(
        extra="allow"
    )

    company_description: (
        SmartRecruitersSection | None
    ) = Field(
        default=None,
        alias="companyDescription",
    )

    job_description: (
        SmartRecruitersSection | None
    ) = Field(
        default=None,
        alias="jobDescription",
    )

    qualifications: (
        SmartRecruitersSection | None
    ) = None

    additional_information: (
        SmartRecruitersSection | None
    ) = Field(
        default=None,
        alias="additionalInformation",
    )


class SmartRecruitersJobAd(BaseModel):
    model_config = ConfigDict(
        extra="allow"
    )

    sections: SmartRecruitersSections | None = (
        None
    )


class SmartRecruitersPostingSummary(BaseModel):
    model_config = ConfigDict(
        extra="allow"
    )

    id: str
    name: str

    released_date: str | None = Field(
        default=None,
        alias="releasedDate",
    )

    location: SmartRecruitersLocation | None = (
        None
    )

    type_of_employment: (
        SmartRecruitersLabel | None
    ) = Field(
        default=None,
        alias="typeOfEmployment",
    )

    visibility: str | None = None


class SmartRecruitersPostingsResponse(
    BaseModel
):
    model_config = ConfigDict(
        extra="allow"
    )

    offset: int
    limit: int

    total_found: int = Field(
        alias="totalFound"
    )

    content: list[
        SmartRecruitersPostingSummary
    ]


class SmartRecruitersPostingDetail(
    SmartRecruitersPostingSummary
):
    posting_url: str | None = Field(
        default=None,
        alias="postingUrl",
    )

    apply_url: str | None = Field(
        default=None,
        alias="applyUrl",
    )

    active: bool | None = None

    job_ad: SmartRecruitersJobAd | None = (
        Field(
            default=None,
            alias="jobAd",
        )
    )


@dataclass(frozen=True, slots=True)
class SmartRecruitersJobsFetch:
    http_status: int
    total: int
    jobs: list[
        SmartRecruitersPostingDetail
    ]


class SmartRecruitersClient:
    def __init__(
        self,
        timeout_seconds: float = 20.0,
        page_size: int = DEFAULT_PAGE_SIZE,
        max_detail_workers: int = 6,
    ) -> None:
        if not 1 <= page_size <= 100:
            raise ValueError(
                "SmartRecruiters page_size must "
                "be between 1 and 100."
            )

        if max_detail_workers < 1:
            raise ValueError(
                "max_detail_workers must "
                "be at least 1."
            )

        self.timeout_seconds = (
            timeout_seconds
        )
        self.page_size = page_size
        self.max_detail_workers = (
            max_detail_workers
        )

    def fetch_jobs(
        self,
        company_identifier: str,
    ) -> SmartRecruitersJobsFetch:
        cleaned_identifier = (
            company_identifier.strip()
        )

        if not cleaned_identifier:
            raise ValueError(
                "SmartRecruiters company "
                "identifier cannot be empty."
            )

        postings_url = (
            f"{SMARTRECRUITERS_COMPANIES_API_URL}/"
            f"{cleaned_identifier}/postings"
        )

        summaries: list[
            SmartRecruitersPostingSummary
        ] = []

        seen_ids: set[str] = set()
        offset = 0
        expected_total: int | None = None
        http_status = 200

        with httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            limits=httpx.Limits(
                max_connections=(
                    self.max_detail_workers
                ),
                max_keepalive_connections=(
                    self.max_detail_workers
                ),
            ),
            headers={
                "User-Agent": (
                    "chamba-hunter/0.1"
                ),
                "Accept": "application/json",
            },
        ) as client:
            while True:
                response = client.get(
                    postings_url,
                    params={
                        "limit": self.page_size,
                        "offset": offset,
                    },
                )

                response.raise_for_status()

                http_status = (
                    response.status_code
                )

                page = (
                    SmartRecruitersPostingsResponse
                    .model_validate(
                        response.json()
                    )
                )

                if expected_total is None:
                    expected_total = (
                        page.total_found
                    )
                elif (
                    page.total_found
                    != expected_total
                ):
                    raise ValueError(
                        "SmartRecruiters changed "
                        "totalFound during "
                        "pagination: "
                        f"{expected_total} -> "
                        f"{page.total_found}."
                    )

                if page.offset != offset:
                    raise ValueError(
                        "SmartRecruiters returned "
                        "an unexpected offset: "
                        f"requested={offset}, "
                        f"returned={page.offset}."
                    )

                if not page.content:
                    break

                for posting in page.content:
                    posting_id = (
                        posting.id.strip()
                    )

                    if not posting_id:
                        raise ValueError(
                            "SmartRecruiters "
                            "returned a posting "
                            "with an empty id."
                        )

                    if posting_id in seen_ids:
                        raise ValueError(
                            "SmartRecruiters "
                            "returned a duplicate "
                            "posting id across "
                            "paginated results: "
                            f"{posting_id}"
                        )

                    seen_ids.add(posting_id)
                    summaries.append(posting)

                offset += len(page.content)

                if (
                    expected_total is not None
                    and offset >= expected_total
                ):
                    break

                if (
                    len(page.content)
                    < self.page_size
                ):
                    break

            total = expected_total or 0

            if len(summaries) != total:
                raise ValueError(
                    "SmartRecruiters returned an "
                    "incomplete postings list: "
                    f"totalFound={total}, "
                    f"postings={len(summaries)}."
                )

            jobs = self._fetch_details(
                client=client,
                postings_url=postings_url,
                summaries=summaries,
            )

        return SmartRecruitersJobsFetch(
            http_status=http_status,
            total=total,
            jobs=jobs,
        )

    def _fetch_details(
        self,
        client: httpx.Client,
        postings_url: str,
        summaries: list[
            SmartRecruitersPostingSummary
        ],
    ) -> list[
        SmartRecruitersPostingDetail
    ]:
        if not summaries:
            return []

        worker_count = min(
            self.max_detail_workers,
            len(summaries),
        )

        details: list[
            SmartRecruitersPostingDetail
            | None
        ] = [
            None
            for _ in summaries
        ]

        with ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix=(
                "smartrecruiters-detail"
            ),
        ) as executor:
            future_indexes = {
                executor.submit(
                    self._fetch_detail,
                    client=client,
                    postings_url=postings_url,
                    posting_id=posting.id,
                ): index
                for index, posting
                in enumerate(summaries)
            }

            try:
                for future in as_completed(
                    future_indexes
                ):
                    index = (
                        future_indexes[
                            future
                        ]
                    )

                    details[index] = (
                        future.result()
                    )

            except Exception:
                for pending in (
                    future_indexes
                ):
                    pending.cancel()

                raise

        if any(
            detail is None
            for detail in details
        ):
            raise RuntimeError(
                "SmartRecruiters detail fetch "
                "completed without a full "
                "snapshot."
            )

        return [
            detail
            for detail in details
            if detail is not None
        ]

    @staticmethod
    def _fetch_detail(
        client: httpx.Client,
        postings_url: str,
        posting_id: str,
    ) -> SmartRecruitersPostingDetail:
        response = client.get(
            f"{postings_url}/{posting_id}"
        )

        response.raise_for_status()

        detail = (
            SmartRecruitersPostingDetail
            .model_validate(
                response.json()
            )
        )

        if detail.id.strip() != posting_id:
            raise ValueError(
                "SmartRecruiters detail id "
                "does not match requested "
                "posting id: "
                f"requested={posting_id}, "
                f"returned={detail.id}."
            )

        return detail
