from dataclasses import dataclass

from pydantic import (
    ValidationError,
)

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
from chamba_hunter.services.public_contact_quality import (
    classify_email,
)
from chamba_hunter.sources.argentina_company_directories import (
    ArgentinaSoftwareDirectoryClient,
    DirectoryFetch,
)


@dataclass(frozen=True, slots=True)
class ArgentinaCompanyDiscoverySummary:
    osm: DirectoryFetch

    companies_created: int
    companies_existing: int

    contacts_created: int
    contacts_existing: int

    import_skipped: int


class ArgentinaCompanyDiscoveryService:
    def __init__(
        self,
        *,
        client: (
            ArgentinaSoftwareDirectoryClient
        ),
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
        max_companies: int,
    ) -> ArgentinaCompanyDiscoverySummary:
        fetch = self.client.fetch(
            max_companies=(
                max_companies
            )
        )

        created_ids: set[
            int
        ] = set()

        seen_ids: set[
            int
        ] = set()

        contacts_created = 0
        contacts_existing = 0
        import_skipped = 0

        for source_company in (
            fetch.companies
        ):
            try:
                result = (
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
                            country="Argentina",
                            source_type=(
                                SourceType
                                .OPENSTREETMAP
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
                            "discovery_scope": (
                                "ARGENTINA_SOFTWARE"
                            ),
                            "machine_source": (
                                "OPENSTREETMAP_OVERPASS"
                            ),
                            "argentina_presence": True,
                            "signal_tags": list(
                                source_company
                                .signal_tags
                            ),
                            "latitude": (
                                source_company
                                .latitude
                            ),
                            "longitude": (
                                source_company
                                .longitude
                            ),
                            "outreach_relevance_score": (
                                source_company
                                .discovery_score
                            ),
                        },
                    )
                )

                company = result.company

                if company.id is None:
                    raise RuntimeError(
                        "Imported Argentina "
                        "discovery company has "
                        "no id."
                    )

                seen_ids.add(
                    company.id
                )

                if result.created:
                    created_ids.add(
                        company.id
                    )

                email = (
                    source_company.email
                )

                if email is None:
                    continue

                contact_type = (
                    classify_email(
                        email
                    )
                )

                if contact_type is None:
                    continue

                _, created = (
                    self.public_contact_repository
                    .add_or_touch(
                        PublicContact(
                            company_id=(
                                company.id
                            ),
                            contact_type=(
                                contact_type
                            ),
                            value=email,
                            source_url=(
                                source_company
                                .profile_url
                            ),
                            notes=(
                                "Public email "
                                "published in "
                                "OpenStreetMap tags "
                                "for this Argentina "
                                "IT/software company."
                            ),
                        )
                    )
                )

                if created:
                    contacts_created += 1
                else:
                    contacts_existing += 1

            except (
                ValidationError,
                ValueError,
                RuntimeError,
            ):
                import_skipped += 1

        return (
            ArgentinaCompanyDiscoverySummary(
                osm=fetch,
                companies_created=len(
                    created_ids
                ),
                companies_existing=len(
                    seen_ids
                    - created_ids
                ),
                contacts_created=(
                    contacts_created
                ),
                contacts_existing=(
                    contacts_existing
                ),
                import_skipped=(
                    import_skipped
                ),
            )
        )
