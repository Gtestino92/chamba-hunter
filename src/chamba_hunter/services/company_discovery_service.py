from dataclasses import dataclass, field

from chamba_hunter.domain.enums import SourceType
from chamba_hunter.schemas.inputs import CompanySeedInput
from chamba_hunter.services.company_import_service import (
    CompanyImportService,
)
from chamba_hunter.sources.himalayas import (
    HimalayasClient,
    HimalayasCompany,
)


@dataclass(slots=True)
class DiscoverySummary:
    queries: int = 0
    discovered: int = 0
    created: int = 0
    existing: int = 0
    query_company_hits: int = 0


@dataclass(slots=True)
class DiscoveredHimalayasCompany:
    company: HimalayasCompany
    matched_queries: set[str] = field(default_factory=set)


class CompanyDiscoveryService:
    def __init__(
        self,
        himalayas_client: HimalayasClient,
        import_service: CompanyImportService,
    ) -> None:
        self.himalayas_client = himalayas_client
        self.import_service = import_service

    def discover_himalayas(
        self,
        queries: list[str],
        country: str,
        max_pages: int,
    ) -> DiscoverySummary:
        summary = DiscoverySummary()

        discovered: dict[str, DiscoveredHimalayasCompany] = {}

        for query in queries:
            summary.queries += 1

            companies = self.himalayas_client.search_companies(
                query=query,
                country=country,
                max_pages=max_pages,
            )

            summary.query_company_hits += len(companies)

            for company in companies:
                item = discovered.get(company.slug)

                if item is None:
                    item = DiscoveredHimalayasCompany(
                        company=company,
                    )
                    discovered[company.slug] = item

                item.matched_queries.add(query)

        summary.discovered = len(discovered)

        for item in discovered.values():
            company = item.company

            result = self.import_service.import_seed(
                CompanySeedInput(
                    name=company.name,
                    source_type=SourceType.HIMALAYAS,
                    external_id=company.slug,
                    source_url=company.source_url,
                ),
                source_metadata={
                    "country_filter": country,
                    "matched_queries": sorted(
                        item.matched_queries
                    ),
                },
            )

            if result.created:
                summary.created += 1
            else:
                summary.existing += 1

        return summary