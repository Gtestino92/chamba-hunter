from dataclasses import dataclass

from pydantic import ValidationError

from chamba_hunter.domain.enums import (
    ContactType,
    SourceType,
)
from chamba_hunter.domain.models import (
    PublicContact,
)
from chamba_hunter.repositories.public_contact_repository import (
    PublicContactRepository,
)
from chamba_hunter.schemas.inputs import (
    CompanySeedInput,
)
from chamba_hunter.services.company_import_service import (
    CompanyImportService,
)
from chamba_hunter.sources.cessi_companies import (
    CessiDirectoryClient,
)


@dataclass(frozen=True, slots=True)
class CessiAcquisitionSummary:
    pages_fetched: int
    received: int
    normalized: int
    skipped: int
    companies_created: int
    companies_existing: int
    contacts_created: int
    contacts_existing: int


class CessiCompanyAcquisitionService:
    def __init__(
        self,
        *,
        client: CessiDirectoryClient,
        company_import_service: (
            CompanyImportService
        ),
        public_contact_repository: (
            PublicContactRepository
        ),
    ) -> None:
        self.client = client
        self.company_import_service = (
            company_import_service
        )
        self.public_contact_repository = (
            public_contact_repository
        )

    def run(
        self,
        *,
        max_pages: int,
    ) -> CessiAcquisitionSummary:
        fetch = self.client.fetch(
            max_pages=max_pages
        )

        normalized = 0
        skipped = 0
        contacts_created = 0
        contacts_existing = 0

        seen_company_ids: set[
            int
        ] = set()
        created_company_ids: set[
            int
        ] = set()

        for source_company in (
            fetch.companies
        ):
            try:
                import_result = (
                    self.company_import_service
                    .import_seed(
                        CompanySeedInput(
                            name=source_company.name,
                            country="Argentina",
                            source_type=(
                                SourceType.CESSI
                            ),
                            external_id=(
                                source_company
                                .external_id
                            ),
                            source_url=(
                                source_company
                                .page_url
                            ),
                        ),
                        source_metadata={
                            "activity": (
                                source_company
                                .activity
                            ),
                            "address": (
                                source_company
                                .address
                            ),
                            "city": (
                                source_company
                                .city
                            ),
                            "province": (
                                source_company
                                .province
                            ),
                            "public_contact_email": (
                                source_company
                                .email
                            ),
                        },
                    )
                )

                company = (
                    import_result.company
                )

                if company.id is None:
                    raise RuntimeError(
                        "Imported company must "
                        "have an id."
                    )

                seen_company_ids.add(
                    company.id
                )

                if import_result.created:
                    created_company_ids.add(
                        company.id
                    )

                _, created = (
                    self.public_contact_repository
                    .add_or_touch(
                        PublicContact(
                            company_id=company.id,
                            contact_type=(
                                ContactType
                                .GENERAL_EMAIL
                            ),
                            value=(
                                source_company
                                .email
                            ),
                            source_url=(
                                source_company
                                .page_url
                            ),
                            notes=(
                                "Public contact "
                                "published in the "
                                "CESSI company "
                                "directory."
                            ),
                        )
                    )
                )

                if created:
                    contacts_created += 1
                else:
                    contacts_existing += 1

                normalized += 1

            except (
                ValidationError,
                ValueError,
                RuntimeError,
            ):
                skipped += 1

        return CessiAcquisitionSummary(
            pages_fetched=(
                fetch.pages_fetched
            ),
            received=len(
                fetch.companies
            ),
            normalized=normalized,
            skipped=skipped,
            companies_created=len(
                created_company_ids
            ),
            companies_existing=len(
                seen_company_ids
                - created_company_ids
            ),
            contacts_created=(
                contacts_created
            ),
            contacts_existing=(
                contacts_existing
            ),
        )
