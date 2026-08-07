import argparse

from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate
from chamba_hunter.repositories.company_repository import (
    CompanyRepository,
)
from chamba_hunter.repositories.company_source_repository import (
    CompanySourceRepository,
)
from chamba_hunter.services.company_import_service import (
    CompanyImportService,
)
from chamba_hunter.services.getonboard_discovery_service import (
    GetOnBoardDiscoveryService,
)
from chamba_hunter.sources.getonboard import (
    GetOnBoardClient,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Discover software companies from "
            "Get on Board's Programming feed."
        )
    )

    parser.add_argument(
        "--max-pages",
        type=int,
        default=2,
        help=(
            "Maximum pages to fetch. "
            "Each page contains up to 100 jobs. "
            "Defaults to 2."
        ),
    )

    args = parser.parse_args()

    if args.max_pages < 1:
        parser.error(
            "--max-pages must be at least 1"
        )

    database = Database()
    migrate(database)

    company_repository = CompanyRepository(
        database
    )

    company_source_repository = (
        CompanySourceRepository(database)
    )

    import_service = CompanyImportService(
        company_repository,
        company_source_repository,
    )

    discovery_service = (
        GetOnBoardDiscoveryService(
            GetOnBoardClient(),
            import_service,
        )
    )

    print(
        "Discovering companies from "
        "Get on Board..."
    )
    print(
        f"Max pages: {args.max_pages}"
    )
    print()

    summary = discovery_service.discover(
        max_pages=args.max_pages,
    )

    print("Discovery finished")
    print("------------------")
    print(
        f"Jobs seen:                  "
        f"{summary.jobs_seen}"
    )
    print(
        f"Companies discovered:       "
        f"{summary.discovered}"
    )
    print(
        f"Created:                    "
        f"{summary.created}"
    )
    print(
        f"Existing:                   "
        f"{summary.existing}"
    )

    print()
    print(
        f"Matched by source:          "
        f"{summary.matched_by_source}"
    )
    print(
        f"Matched by domain:          "
        f"{summary.matched_by_domain}"
    )
    print(
        f"Matched by name:            "
        f"{summary.matched_by_name}"
    )

    print()
    print("Geographic signals")
    print("------------------")
    print(
        f"Company based Argentina:    "
        f"{summary.company_argentina_signal}"
    )
    print(
        f"Buenos Aires:               "
        f"{summary.buenos_aires_signal}"
    )
    print(
        f"Remote global:              "
        f"{summary.remote_global_signal}"
    )
    print(
        f"Remote LATAM/South America: "
        f"{summary.remote_latam_signal}"
    )
    print(
        f"Remote compatible Argentina:"
        f" {summary.remote_argentina_signal}"
    )
    print(
        f"Remote + Buenos Aires:      "
        f"{summary.remote_buenos_aires_signal}"
    )

    print()
    print(
        f"Failed:                     "
        f"{summary.failed}"
    )

    if summary.errors:
        print()
        print("Errors:")

        for error in summary.errors:
            print(
                f"  {error}"
            )


if __name__ == "__main__":
    main()