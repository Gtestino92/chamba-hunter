from dataclasses import dataclass

from pydantic import (
    ValidationError,
)

from chamba_hunter.domain.enums import (
    CompanyType,
    SourceType,
)
from chamba_hunter.repositories.company_repository import (
    CompanyRepository,
)
from chamba_hunter.schemas.inputs import (
    CompanySeedInput,
)
from chamba_hunter.services.company_import_service import (
    CompanyImportService,
)
from chamba_hunter.sources.yc_companies import (
    YcDirectoryClient,
)


@dataclass(frozen=True, slots=True)
class YcAcquisitionSummary:
    feeds_requested: int
    feeds_fetched: int
    feeds_failed: int

    raw_records: int
    unique_candidates: int

    skipped_status: int
    skipped_missing_website: int
    skipped_invalid: int
    skipped_import: int

    received: int

    companies_created: int
    companies_existing: int

    product_classified: int
    currently_hiring: int


class YcCompanyAcquisitionService:
    def __init__(
        self,
        *,
        client: YcDirectoryClient,
        company_import_service: (
            CompanyImportService
        ),
        company_repository: (
            CompanyRepository
        ),
    ) -> None:
        self.client = client
        self.company_import_service = (
            company_import_service
        )
        self.company_repository = (
            company_repository
        )

    def run(
        self,
        *,
        categories: tuple[str, ...],
        max_companies: int,
    ) -> YcAcquisitionSummary:
        fetch = self.client.fetch(
            categories=categories,
            max_companies=(
                max_companies
            ),
        )

        seen_company_ids: set[
            int
        ] = set()

        created_company_ids: set[
            int
        ] = set()

        skipped_import = 0
        product_classified = 0
        currently_hiring = 0

        for source_company in (
            fetch.companies
        ):
            try:
                import_result = (
                    self.company_import_service
                    .import_seed(
                        CompanySeedInput(
                            name=(
                                source_company
                                .name
                            ),
                            website_url=(
                                source_company
                                .website_url
                            ),
                            source_type=(
                                SourceType.YC
                            ),
                            external_id=(
                                source_company
                                .external_id
                            ),
                            source_url=(
                                source_company
                                .profile_url
                            ),
                        ),
                        source_metadata={
                            "snapshot_provider": (
                                "yc-oss"
                            ),
                            "yc_id": (
                                source_company
                                .yc_id
                            ),
                            "yc_status": (
                                source_company
                                .status
                            ),
                            "batch": (
                                source_company
                                .batch
                            ),
                            "team_size": (
                                source_company
                                .team_size
                            ),
                            "location": (
                                source_company
                                .location
                            ),
                            "industry": (
                                source_company
                                .industry
                            ),
                            "subindustry": (
                                source_company
                                .subindustry
                            ),
                            "industries": list(
                                source_company
                                .industries
                            ),
                            "tags": list(
                                source_company
                                .tags
                            ),
                            "regions": list(
                                source_company
                                .regions
                            ),
                            "stage": (
                                source_company
                                .stage
                            ),
                            "is_hiring": (
                                source_company
                                .is_hiring
                            ),
                            "top_company": (
                                source_company
                                .top_company
                            ),
                            "matched_categories": list(
                                source_company
                                .matched_categories
                            ),
                            "directory_rank": (
                                source_company
                                .directory_rank
                            ),
                            "outreach_relevance_score": (
                                source_company
                                .outreach_relevance_score
                            ),
                        },
                    )
                )

                company = (
                    import_result.company
                )

                if company.id is None:
                    raise RuntimeError(
                        "Imported YC company "
                        "must have an id."
                    )

                seen_company_ids.add(
                    company.id
                )

                if import_result.created:
                    created_company_ids.add(
                        company.id
                    )

                if source_company.is_hiring:
                    currently_hiring += 1

                if (
                    company.company_type
                    == CompanyType.UNKNOWN
                ):
                    self.company_repository.update_enrichment(
                        company_id=(
                            company.id
                        ),
                        company_type=(
                            CompanyType.PRODUCT
                        ),
                    )

                    product_classified += 1

            except (
                ValidationError,
                ValueError,
                RuntimeError,
            ):
                skipped_import += 1

        return YcAcquisitionSummary(
            feeds_requested=(
                fetch.feeds_requested
            ),
            feeds_fetched=(
                fetch.feeds_fetched
            ),
            feeds_failed=(
                fetch.feeds_failed
            ),
            raw_records=(
                fetch.raw_records
            ),
            unique_candidates=(
                fetch.unique_candidates
            ),
            skipped_status=(
                fetch.skipped_status
            ),
            skipped_missing_website=(
                fetch
                .skipped_missing_website
            ),
            skipped_invalid=(
                fetch.skipped_invalid
            ),
            skipped_import=(
                skipped_import
            ),
            received=len(
                fetch.companies
            ),
            companies_created=len(
                created_company_ids
            ),
            companies_existing=len(
                seen_company_ids
                - created_company_ids
            ),
            product_classified=(
                product_classified
            ),
            currently_hiring=(
                currently_hiring
            ),
        )
