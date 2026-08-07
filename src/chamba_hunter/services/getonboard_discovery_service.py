from dataclasses import dataclass, field

from pydantic import ValidationError

from chamba_hunter.domain.enums import SourceType
from chamba_hunter.schemas.inputs import CompanySeedInput
from chamba_hunter.services.company_import_service import (
    CompanyImportService,
)
from chamba_hunter.sources.getonboard import (
    GetOnBoardClient,
    GetOnBoardCompany,
)


@dataclass(slots=True)
class GetOnBoardDiscoverySummary:
    jobs_seen: int = 0
    discovered: int = 0

    created: int = 0
    existing: int = 0

    matched_by_source: int = 0
    matched_by_domain: int = 0
    matched_by_name: int = 0

    company_argentina_signal: int = 0
    buenos_aires_signal: int = 0

    remote_global_signal: int = 0
    remote_latam_signal: int = 0
    remote_argentina_signal: int = 0
    remote_buenos_aires_signal: int = 0

    failed: int = 0

    errors: list[str] = field(
        default_factory=list
    )


class GetOnBoardDiscoveryService:
    def __init__(
        self,
        client: GetOnBoardClient,
        import_service: CompanyImportService,
    ) -> None:
        self.client = client
        self.import_service = import_service

    def discover(
        self,
        max_pages: int,
    ) -> GetOnBoardDiscoverySummary:
        summary = GetOnBoardDiscoverySummary()

        batch = (
            self.client
            .discover_programming_companies(
                max_pages=max_pages
            )
        )

        summary.jobs_seen = batch.jobs_seen
        summary.discovered = len(
            batch.companies
        )

        for company in batch.companies:
            self._count_location_signals(
                company,
                summary,
            )

            try:
                seed = CompanySeedInput(
                    name=company.name,
                    website_url=(
                        company.website_url
                        if _is_http_url(
                            company.website_url
                        )
                        else None
                    ),
                    country=company.country,
                    source_type=(
                        SourceType.GETONBOARD
                    ),
                    external_id=company.external_id,
                )

                result = (
                    self.import_service.import_seed(
                        seed,
                        source_metadata=(
                            _source_metadata(
                                company
                            )
                        ),
                    )
                )

            except (
                ValidationError,
                ValueError,
                RuntimeError,
            ) as exc:
                summary.failed += 1
                summary.errors.append(
                    f"{company.external_id}: "
                    f"{exc}"
                )
                continue

            if result.created:
                summary.created += 1
            else:
                summary.existing += 1

            if result.matched_by == "SOURCE":
                summary.matched_by_source += 1

            elif result.matched_by == "DOMAIN":
                summary.matched_by_domain += 1

            elif result.matched_by in {
                "NORMALIZED_NAME",
                "NORMALIZED_NAME_DOMAINLESS",
            }:
                summary.matched_by_name += 1

        return summary

    @staticmethod
    def _count_location_signals(
        company: GetOnBoardCompany,
        summary: GetOnBoardDiscoverySummary,
    ) -> None:
        if company.company_argentina_signal:
            summary.company_argentina_signal += 1

        if (
            company.company_buenos_aires_signal
            or company.job_buenos_aires_signal
        ):
            summary.buenos_aires_signal += 1

        if company.remote_global_signal:
            summary.remote_global_signal += 1

        if company.remote_latam_signal:
            summary.remote_latam_signal += 1

        if company.remote_argentina_signal:
            summary.remote_argentina_signal += 1

        if company.remote_buenos_aires_signal:
            summary.remote_buenos_aires_signal += 1


def _source_metadata(
    company: GetOnBoardCompany,
) -> dict:
    return {
        "company_country": company.country,
        "company_website": (
            company.website_url
        ),
        "company_description": (
            company.description
        ),
        "company_long_description": (
            company.long_description
        ),

        "job_count": company.job_count,
        "remote_job_count": (
            company.remote_job_count
        ),

        "remote_modalities": (
            company.remote_modalities
        ),
        "remote_zones": company.remote_zones,

        "job_countries": (
            company.job_countries
        ),
        "location_region_ids": (
            company.location_region_ids
        ),
        "location_city_ids": (
            company.location_city_ids
        ),

        "company_argentina_signal": (
            company.company_argentina_signal
        ),
        "company_buenos_aires_signal": (
            company.company_buenos_aires_signal
        ),

        "job_argentina_signal": (
            company.job_argentina_signal
        ),
        "job_buenos_aires_signal": (
            company.job_buenos_aires_signal
        ),

        "remote_global_signal": (
            company.remote_global_signal
        ),
        "remote_latam_signal": (
            company.remote_latam_signal
        ),
        "remote_argentina_signal": (
            company.remote_argentina_signal
        ),
        "remote_buenos_aires_signal": (
            company.remote_buenos_aires_signal
        ),

        "sample_job_urls": (
            company.sample_job_urls
        ),
    }


def _is_http_url(
    value: str | None,
) -> bool:
    if value is None:
        return False

    return value.startswith(
        (
            "http://",
            "https://",
        )
    )