from dataclasses import dataclass
import re
from typing import Any
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field


TENANT_PATTERN = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?$"
)


class BambooHRLocation(BaseModel):
    model_config = ConfigDict(
        extra="allow"
    )

    city: str | None = None
    state: str | None = None

    postal_code: str | None = Field(
        default=None,
        alias="postalCode",
    )

    address_country: str | None = Field(
        default=None,
        alias="addressCountry",
    )


class BambooHRAtsLocation(BaseModel):
    model_config = ConfigDict(
        extra="allow"
    )

    country: str | None = None

    country_id: str | int | None = Field(
        default=None,
        alias="countryId",
    )

    state: str | None = None
    province: str | None = None
    city: str | None = None


class BambooHRJobSummary(BaseModel):
    model_config = ConfigDict(
        extra="allow"
    )

    id: str

    job_opening_name: str = Field(
        alias="jobOpeningName"
    )

    department_id: str | int | None = Field(
        default=None,
        alias="departmentId",
    )

    department_label: str | None = Field(
        default=None,
        alias="departmentLabel",
    )

    employment_status_label: str | None = Field(
        default=None,
        alias="employmentStatusLabel",
    )

    employment_type: str | None = Field(
        default=None,
        alias="employmentType",
    )

    location: BambooHRLocation | None = None

    ats_location: BambooHRAtsLocation | None = Field(
        default=None,
        alias="atsLocation",
    )

    is_remote: bool | None = Field(
        default=None,
        alias="isRemote",
    )

    location_type: str | int | None = Field(
        default=None,
        alias="locationType",
    )


class BambooHRMeta(BaseModel):
    model_config = ConfigDict(
        extra="allow"
    )

    total_count: int = Field(
        alias="totalCount"
    )


class BambooHRJobsListResponse(BaseModel):
    model_config = ConfigDict(
        extra="allow"
    )

    meta: BambooHRMeta
    result: list[BambooHRJobSummary]


class BambooHRJobOpening(BaseModel):
    model_config = ConfigDict(
        extra="allow"
    )

    job_opening_share_url: str = Field(
        alias="jobOpeningShareUrl"
    )

    job_opening_name: str = Field(
        alias="jobOpeningName"
    )

    job_opening_status: str | None = Field(
        default=None,
        alias="jobOpeningStatus",
    )

    job_category_id: str | int | None = Field(
        default=None,
        alias="jobCategoryId",
    )

    department_id: str | int | None = Field(
        default=None,
        alias="departmentId",
    )

    department_label: str | None = Field(
        default=None,
        alias="departmentLabel",
    )

    employment_status_label: str | None = Field(
        default=None,
        alias="employmentStatusLabel",
    )

    employment_type: str | None = Field(
        default=None,
        alias="employmentType",
    )

    location: BambooHRLocation | None = None

    ats_location: BambooHRAtsLocation | None = Field(
        default=None,
        alias="atsLocation",
    )

    description: str | None = None
    compensation: str | None = None

    date_posted: str | None = Field(
        default=None,
        alias="datePosted",
    )

    minimum_experience: str | None = Field(
        default=None,
        alias="minimumExperience",
    )

    location_type: str | int | None = Field(
        default=None,
        alias="locationType",
    )

    seek_promoted: bool | None = Field(
        default=None,
        alias="seekPromoted",
    )


class BambooHRJobDetailResult(BaseModel):
    model_config = ConfigDict(
        extra="allow"
    )

    job_opening: BambooHRJobOpening = Field(
        alias="jobOpening"
    )

    form_fields: Any = Field(
        default=None,
        alias="formFields",
    )


class BambooHRJobDetailResponse(BaseModel):
    model_config = ConfigDict(
        extra="allow"
    )

    meta: dict[str, Any] = Field(
        default_factory=dict
    )

    result: BambooHRJobDetailResult


@dataclass(frozen=True, slots=True)
class BambooHRJobDetail:
    summary: BambooHRJobSummary
    job_opening: BambooHRJobOpening
    raw_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class BambooHRJobsFetch:
    http_status: int
    total: int
    jobs: list[BambooHRJobDetail]


class BambooHRClient:
    def __init__(
        self,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.timeout_seconds = (
            timeout_seconds
        )

    def fetch_jobs(
        self,
        tenant_subdomain: str,
    ) -> BambooHRJobsFetch:
        tenant = _clean_tenant(
            tenant_subdomain
        )

        careers_url = (
            f"https://{tenant}.bamboohr.com/"
            "careers"
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
                f"{careers_url}/list"
            )

            response.raise_for_status()

            payload = (
                BambooHRJobsListResponse
                .model_validate(
                    response.json()
                )
            )

            total = payload.meta.total_count

            if total < 0:
                raise ValueError(
                    "BambooHR returned a "
                    "negative totalCount."
                )

            if len(payload.result) != total:
                raise ValueError(
                    "BambooHR returned an "
                    "incomplete careers list: "
                    f"totalCount={total}, "
                    "postings="
                    f"{len(payload.result)}."
                )

            seen_ids: set[str] = set()
            summaries: list[
                BambooHRJobSummary
            ] = []

            for summary in payload.result:
                job_id = summary.id.strip()

                if not job_id:
                    raise ValueError(
                        "BambooHR returned a job "
                        "with an empty id."
                    )

                if job_id in seen_ids:
                    raise ValueError(
                        "BambooHR returned a "
                        "duplicate job id: "
                        f"{job_id}"
                    )

                seen_ids.add(job_id)

                summaries.append(
                    summary.model_copy(
                        update={"id": job_id}
                    )
                )

            jobs = [
                self._fetch_detail(
                    client=client,
                    careers_url=careers_url,
                    summary=summary,
                )
                for summary in summaries
            ]

        return BambooHRJobsFetch(
            http_status=response.status_code,
            total=total,
            jobs=jobs,
        )

    @staticmethod
    def _fetch_detail(
        client: httpx.Client,
        careers_url: str,
        summary: BambooHRJobSummary,
    ) -> BambooHRJobDetail:
        job_id = summary.id

        response = client.get(
            f"{careers_url}/{job_id}/detail"
        )

        response.raise_for_status()

        raw_payload = response.json()

        detail = (
            BambooHRJobDetailResponse
            .model_validate(
                raw_payload
            )
        )

        opening = detail.result.job_opening

        share_url = (
            opening.job_opening_share_url
            .strip()
        )

        if not share_url:
            raise ValueError(
                "BambooHR detail returned an "
                "empty jobOpeningShareUrl for "
                f"job {job_id}."
            )

        try:
            share_path = (
                urlsplit(share_url)
                .path
                .rstrip("/")
            )
        except ValueError as error:
            raise ValueError(
                "BambooHR detail returned an "
                "invalid jobOpeningShareUrl "
                f"for job {job_id}: "
                f"{share_url}"
            ) from error

        if (
            not share_path
            or share_path.split("/")[-1]
            != job_id
        ):
            raise ValueError(
                "BambooHR detail URL does not "
                "match requested job id: "
                f"requested={job_id}, "
                f"url={share_url}"
            )

        return BambooHRJobDetail(
            summary=summary,
            job_opening=opening,
            raw_payload=raw_payload,
        )


def _clean_tenant(
    value: str,
) -> str:
    cleaned = value.strip()

    if not cleaned:
        raise ValueError(
            "BambooHR tenant subdomain "
            "cannot be empty."
        )

    if TENANT_PATTERN.fullmatch(
        cleaned
    ) is None:
        raise ValueError(
            "Invalid BambooHR tenant "
            "subdomain: "
            f"{value}"
        )

    return cleaned
