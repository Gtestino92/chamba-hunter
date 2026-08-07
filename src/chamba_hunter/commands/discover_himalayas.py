import argparse

from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate
from chamba_hunter.repositories.company_repository import (
    CompanyRepository,
)
from chamba_hunter.repositories.company_source_repository import (
    CompanySourceRepository,
)
from chamba_hunter.services.company_discovery_service import (
    CompanyDiscoveryService,
)
from chamba_hunter.services.company_import_service import (
    CompanyImportService,
)
from chamba_hunter.sources.himalayas import HimalayasClient


DEFAULT_QUERIES = [
    # General backend/software roles
    "software engineer",
    "software developer",
    "backend engineer",
    "backend developer",

    # Primary stack
    "java",
    "kotlin",
    "spring boot",
    "jvm",

    # Architecture / backend systems
    "distributed systems",
    "microservices",
    "platform engineer",
    "integration engineer",
    "api engineer",

    # Broader compatible roles
    "full stack engineer",

    # Secondary stack from actual experience
    "node.js backend",
    "typescript backend",

    # Domain experience
    "payments engineer",
]

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Discover companies from Himalayas job listings."
        )
    )

    parser.add_argument(
        "--query",
        action="append",
        dest="queries",
        help=(
            "Search query. Can be specified multiple times. "
            "Uses backend/Java/Kotlin defaults if omitted."
        ),
    )

    parser.add_argument(
        "--country",
        default="AR",
        help="Country filter. Defaults to AR.",
    )

    parser.add_argument(
        "--max-pages",
        type=int,
        default=2,
        help="Maximum pages fetched per query. Defaults to 2.",
    )

    args = parser.parse_args()

    queries = args.queries or DEFAULT_QUERIES

    if args.max_pages < 1:
        parser.error("--max-pages must be at least 1")

    database = Database()
    migrate(database)

    company_repository = CompanyRepository(database)
    company_source_repository = CompanySourceRepository(database)

    import_service = CompanyImportService(
        company_repository,
        company_source_repository,
    )

    discovery_service = CompanyDiscoveryService(
        HimalayasClient(),
        import_service,
    )

    print("Discovering companies from Himalayas...")
    print(f"Country: {args.country}")
    print(f"Queries: {', '.join(queries)}")
    print(f"Max pages/query: {args.max_pages}")
    print()

    summary = discovery_service.discover_himalayas(
        queries=queries,
        country=args.country,
        max_pages=args.max_pages,
    )

    print("Discovery finished")
    print("------------------")
    print(f"Queries:    {summary.queries}")
    print(f"Raw hits:   {summary.query_company_hits}")
    print(f"Discovered: {summary.discovered}")
    print(f"Created:    {summary.created}")
    print(f"Existing:   {summary.existing}")


if __name__ == "__main__":
    main()