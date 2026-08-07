import argparse

from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate
from chamba_hunter.repositories.company_classification_repository import (
    CompanyClassificationRepository,
)
from chamba_hunter.repositories.company_repository import (
    CompanyRepository,
)
from chamba_hunter.repositories.company_source_repository import (
    CompanySourceRepository,
)
from chamba_hunter.services.company_enrichment_service import (
    CompanyEnrichmentService,
)
from chamba_hunter.sources.himalayas import HimalayasClient


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enrich Himalayas companies."
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum companies to enrich.",
    )

    args = parser.parse_args()

    if args.limit < 1:
        parser.error("--limit must be at least 1")

    database = Database()
    migrate(database)

    service = CompanyEnrichmentService(
        HimalayasClient(),
        CompanyRepository(database),
        CompanySourceRepository(database),
        CompanyClassificationRepository(database),
    )

    summary = service.enrich_himalayas(
        limit=args.limit,
    )

    print()
    print("Enrichment finished")
    print("-------------------")
    print(f"Processed:        {summary.processed}")
    print(f"Websites found:   {summary.websites_found}")
    print(f"Classified:       {summary.classified}")
    print(f"Unknown:          {summary.unknown}")
    print(f"Domain conflicts: {summary.domain_conflicts}")
    print(f"Failed:           {summary.failed}")

    if summary.errors:
        print()
        print("Errors:")

        for error in summary.errors:
            print(f"  {error}")


if __name__ == "__main__":
    main()