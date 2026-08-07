from dataclasses import dataclass, field
import re
import unicodedata

import httpx
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)


GETONBOARD_PROGRAMMING_URL = (
    "https://www.getonbrd.com/"
    "api/v0/categories/programming/jobs"
)

PER_PAGE = 100


class GetOnBoardResourceRef(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str | int
    type: str


class GetOnBoardResourceCollection(BaseModel):
    model_config = ConfigDict(extra="ignore")

    data: list[GetOnBoardResourceRef] = Field(
        default_factory=list
    )


class GetOnBoardCompanyAttributes(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    description: str | None = None
    long_description: str | None = None
    web: str | None = None
    country: str | None = None


class GetOnBoardCompanyResource(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    type: str
    attributes: GetOnBoardCompanyAttributes


class GetOnBoardCompanyRelationship(BaseModel):
    model_config = ConfigDict(extra="ignore")

    data: GetOnBoardCompanyResource | None = None


class GetOnBoardJobAttributes(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str

    description: str | None = None
    projects: str | None = None
    functions: str | None = None

    remote: bool = False
    remote_modality: str | None = None
    remote_zone: str | None = None

    countries: list[str] | str | None = None

    company: GetOnBoardCompanyRelationship | None = None

    location_regions: GetOnBoardResourceCollection = Field(
        default_factory=GetOnBoardResourceCollection
    )
    location_tenants: GetOnBoardResourceCollection = Field(
        default_factory=GetOnBoardResourceCollection
    )
    location_cities: GetOnBoardResourceCollection = Field(
        default_factory=GetOnBoardResourceCollection
    )


class GetOnBoardJobLinks(BaseModel):
    model_config = ConfigDict(extra="ignore")

    public_url: str | None = None


class GetOnBoardJobResource(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    type: str
    attributes: GetOnBoardJobAttributes
    links: GetOnBoardJobLinks


class GetOnBoardJobsResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    data: list[GetOnBoardJobResource]


@dataclass(frozen=True, slots=True)
class GetOnBoardCompany:
    external_id: str
    name: str

    website_url: str | None
    country: str | None

    description: str | None
    long_description: str | None

    job_count: int
    remote_job_count: int

    remote_modalities: list[str]
    remote_zones: list[str]

    job_countries: list[str]
    location_region_ids: list[str]
    location_city_ids: list[str]

    company_argentina_signal: bool
    company_buenos_aires_signal: bool

    job_argentina_signal: bool
    job_buenos_aires_signal: bool

    remote_global_signal: bool
    remote_latam_signal: bool
    remote_argentina_signal: bool
    remote_buenos_aires_signal: bool

    sample_job_urls: list[str]


@dataclass(frozen=True, slots=True)
class GetOnBoardDiscoveryBatch:
    jobs_seen: int
    companies: list[GetOnBoardCompany]


@dataclass(slots=True)
class _CompanyAccumulator:
    external_id: str
    name: str

    website_url: str | None
    country: str | None

    description: str | None
    long_description: str | None

    job_count: int = 0
    remote_job_count: int = 0

    remote_modalities: set[str] = field(
        default_factory=set
    )
    remote_zones: set[str] = field(
        default_factory=set
    )

    job_countries: set[str] = field(
        default_factory=set
    )
    location_region_ids: set[str] = field(
        default_factory=set
    )
    location_city_ids: set[str] = field(
        default_factory=set
    )

    company_argentina_signal: bool = False
    company_buenos_aires_signal: bool = False

    job_argentina_signal: bool = False
    job_buenos_aires_signal: bool = False

    remote_global_signal: bool = False
    remote_latam_signal: bool = False
    remote_argentina_signal: bool = False
    remote_buenos_aires_signal: bool = False

    sample_job_urls: list[str] = field(
        default_factory=list
    )


class GetOnBoardClient:
    def __init__(
        self,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.timeout_seconds = timeout_seconds

    def discover_programming_companies(
        self,
        max_pages: int,
    ) -> GetOnBoardDiscoveryBatch:
        if max_pages < 1:
            raise ValueError(
                "max_pages must be at least 1."
            )

        accumulators: dict[
            str,
            _CompanyAccumulator,
        ] = {}

        jobs_seen = 0

        with httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": "chamba-hunter/0.1"
            },
        ) as client:
            for page in range(1, max_pages + 1):
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
                        "Get on Board rate limit reached."
                    )

                response.raise_for_status()

                payload = (
                    GetOnBoardJobsResponse.model_validate(
                        response.json()
                    )
                )

                if not payload.data:
                    break

                jobs_seen += len(payload.data)

                for job in payload.data:
                    self._accumulate_job(
                        accumulators,
                        job,
                    )

                if len(payload.data) < PER_PAGE:
                    break

        companies = [
            self._finish_company(accumulator)
            for accumulator in accumulators.values()
        ]

        return GetOnBoardDiscoveryBatch(
            jobs_seen=jobs_seen,
            companies=companies,
        )

    @staticmethod
    def _accumulate_job(
        accumulators: dict[
            str,
            _CompanyAccumulator,
        ],
        job: GetOnBoardJobResource,
    ) -> None:
        attributes = job.attributes
        relationship = attributes.company

        if (
            relationship is None
            or relationship.data is None
        ):
            return

        company_resource = relationship.data
        company_attributes = company_resource.attributes

        name = company_attributes.name.strip()

        if not name:
            return

        external_id = company_resource.id.strip()

        if not external_id:
            return

        website_url = _clean_optional(
            company_attributes.web
        )

        country = _clean_optional(
            company_attributes.country
        )

        if country is not None:
            country = country.upper()

        accumulator = accumulators.get(
            external_id
        )

        if accumulator is None:
            accumulator = _CompanyAccumulator(
                external_id=external_id,
                name=name,
                website_url=website_url,
                country=country,
                description=_clean_optional(
                    company_attributes.description
                ),
                long_description=_clean_optional(
                    company_attributes.long_description
                ),
            )

            company_text = _joined_text(
                accumulator.name,
                accumulator.description,
                accumulator.long_description,
            )

            accumulator.company_argentina_signal = (
                accumulator.country == "AR"
            )

            accumulator.company_buenos_aires_signal = (
                _contains_buenos_aires(
                    company_text
                )
            )

            accumulators[external_id] = (
                accumulator
            )

        accumulator.job_count += 1

        if attributes.remote:
            accumulator.remote_job_count += 1

        if attributes.remote_modality:
            accumulator.remote_modalities.add(
                attributes.remote_modality
            )

        if attributes.remote_zone:
            accumulator.remote_zones.add(
                attributes.remote_zone
            )

        countries = _normalize_countries(
            attributes.countries
        )

        accumulator.job_countries.update(
            countries
        )

        accumulator.location_region_ids.update(
            str(reference.id)
            for reference
            in attributes.location_regions.data
        )

        accumulator.location_city_ids.update(
            str(reference.id)
            for reference
            in attributes.location_cities.data
        )

        job_text = _joined_text(
            attributes.title,
            attributes.description,
            attributes.projects,
            attributes.functions,
        )

        restriction_text = _joined_text(
            job_text,
            attributes.remote_zone,
            " ".join(countries),
        )

        job_has_argentina = _contains_argentina(
            restriction_text
        )

        job_has_buenos_aires = (
            _contains_buenos_aires(
                restriction_text
            )
        )

        remote_is_global = (
            attributes.remote
            and attributes.remote_modality
            == "fully_remote"
        )

        remote_is_latam = (
            attributes.remote
            and attributes.remote_modality
            == "remote_local"
            and _contains_latam_region(
                restriction_text
            )
        )

        remote_is_argentina_explicit = (
            attributes.remote
            and job_has_argentina
        )

        remote_is_argentina_compatible = (
            remote_is_global
            or remote_is_latam
            or remote_is_argentina_explicit
        )

        if job_has_argentina:
            accumulator.job_argentina_signal = (
                True
            )

        if job_has_buenos_aires:
            accumulator.job_buenos_aires_signal = (
                True
            )

        if remote_is_global:
            accumulator.remote_global_signal = (
                True
            )

        if remote_is_latam:
            accumulator.remote_latam_signal = True

        if remote_is_argentina_compatible:
            accumulator.remote_argentina_signal = (
                True
            )

        if (
            attributes.remote
            and (
                job_has_buenos_aires
                or accumulator
                .company_buenos_aires_signal
            )
        ):
            accumulator.remote_buenos_aires_signal = (
                True
            )

        job_url = _clean_optional(
            job.links.public_url
        )

        if (
            job_url is not None
            and job_url
            not in accumulator.sample_job_urls
            and len(accumulator.sample_job_urls) < 5
        ):
            accumulator.sample_job_urls.append(
                job_url
            )

    @staticmethod
    def _finish_company(
        accumulator: _CompanyAccumulator,
    ) -> GetOnBoardCompany:
        return GetOnBoardCompany(
            external_id=accumulator.external_id,
            name=accumulator.name,
            website_url=accumulator.website_url,
            country=accumulator.country,
            description=accumulator.description,
            long_description=(
                accumulator.long_description
            ),
            job_count=accumulator.job_count,
            remote_job_count=(
                accumulator.remote_job_count
            ),
            remote_modalities=sorted(
                accumulator.remote_modalities
            ),
            remote_zones=sorted(
                accumulator.remote_zones
            ),
            job_countries=sorted(
                accumulator.job_countries
            ),
            location_region_ids=sorted(
                accumulator.location_region_ids
            ),
            location_city_ids=sorted(
                accumulator.location_city_ids
            ),
            company_argentina_signal=(
                accumulator
                .company_argentina_signal
            ),
            company_buenos_aires_signal=(
                accumulator
                .company_buenos_aires_signal
            ),
            job_argentina_signal=(
                accumulator.job_argentina_signal
            ),
            job_buenos_aires_signal=(
                accumulator
                .job_buenos_aires_signal
            ),
            remote_global_signal=(
                accumulator.remote_global_signal
            ),
            remote_latam_signal=(
                accumulator.remote_latam_signal
            ),
            remote_argentina_signal=(
                accumulator.remote_argentina_signal
            ),
            remote_buenos_aires_signal=(
                accumulator
                .remote_buenos_aires_signal
            ),
            sample_job_urls=list(
                accumulator.sample_job_urls
            ),
        )


def _clean_optional(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    cleaned = value.strip()

    if not cleaned:
        return None

    return cleaned


def _normalize_countries(
    value: list[str] | str | None,
) -> list[str]:
    if value is None:
        return []

    if isinstance(value, str):
        cleaned = value.strip()

        return [cleaned] if cleaned else []

    return [
        country.strip()
        for country in value
        if country.strip()
    ]


def _joined_text(
    *values: str | None,
) -> str:
    return " ".join(
        value
        for value in values
        if value
    )


def _normalize_text(
    value: str,
) -> str:
    decomposed = unicodedata.normalize(
        "NFKD",
        value,
    )

    without_accents = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(
            character
        )
    )

    return " ".join(
        without_accents.casefold().split()
    )


def _contains_buenos_aires(
    value: str,
) -> bool:
    normalized = _normalize_text(value)

    patterns = (
        r"\bbuenos aires\b",
        r"\bcaba\b",
        r"\bcapital federal\b",
        (
            r"\bciudad autonoma "
            r"de buenos aires\b"
        ),
    )

    return any(
        re.search(pattern, normalized)
        is not None
        for pattern in patterns
    )


def _contains_argentina(
    value: str,
) -> bool:
    normalized = _normalize_text(value)

    return (
        re.search(
            r"\bargentina\b",
            normalized,
        )
        is not None
    )


def _contains_latam_region(
    value: str,
) -> bool:
    normalized = _normalize_text(value)

    patterns = (
        r"\blatam\b",
        r"\blatin america\b",
        r"\blatinoamerica\b",
        r"\bamerica latina\b",
        r"\bsouth america\b",
        r"\bamerica del sur\b",
        r"\bsudamerica\b",
    )

    return any(
        re.search(pattern, normalized)
        is not None
        for pattern in patterns
    )