import argparse
import sys

from chamba_hunter.db.connection import (
    Database,
)
from chamba_hunter.db.migrations import (
    migrate,
)
from chamba_hunter.repositories.company_repository import (
    CompanyRepository,
)
from chamba_hunter.repositories.company_source_repository import (
    CompanySourceRepository,
)
from chamba_hunter.repositories.public_contact_repository import (
    PublicContactRepository,
)
from chamba_hunter.services.argentina_company_discovery_service import (
    ArgentinaCompanyDiscoveryService,
)
from chamba_hunter.services.company_import_service import (
    CompanyImportService,
)
from chamba_hunter.sources.argentina_company_directories import (
    ArgentinaSoftwareDirectoryClient,
    DEFAULT_MAX_COMPANIES,
)


def main() -> None:
    if hasattr(
        sys.stdout,
        "reconfigure",
    ):
        sys.stdout.reconfigure(
            encoding="utf-8",
            errors="replace",
        )

    parser = argparse.ArgumentParser(
        description=(
            "Discover public IT/software "
            "companies with Argentina "
            "presence via OpenStreetMap/"
            "Overpass."
        )
    )

    parser.add_argument(
        "--max-companies",
        type=int,
        default=(
            DEFAULT_MAX_COMPANIES
        ),
    )

    args = parser.parse_args()

    if args.max_companies < 1:
        parser.error(
            "--max-companies must "
            "be at least 1"
        )

    database = Database()
    applied = migrate(
        database
    )

    if applied:
        for migration in applied:
            print(
                "Applied migration:",
                migration,
            )
        print()

    company_repository = (
        CompanyRepository(
            database
        )
    )

    summary = (
        ArgentinaCompanyDiscoveryService(
            client=(
                ArgentinaSoftwareDirectoryClient()
            ),
            company_import_service=(
                CompanyImportService(
                    company_repository,
                    CompanySourceRepository(
                        database
                    ),
                )
            ),
            public_contact_repository=(
                PublicContactRepository(
                    database
                )
            ),
        )
        .run(
            max_companies=(
                args.max_companies
            )
        )
    )

    result = summary.osm

    print(
        "Argentina company discovery"
    )
    print(
        "---------------------------"
    )
    print(
        f"Source:              "
        f"OPENSTREETMAP"
    )
    print(
        f"Overpass endpoint:   "
        f"{result.endpoint}"
    )
    print(
        f"Elements received:   "
        f"{result.elements_received}"
    )
    print(
        f"With name:           "
        f"{result.candidates_with_name}"
    )
    print(
        f"With website:        "
        f"{result.candidates_with_website}"
    )
    print(
        f"With public email:   "
        f"{result.candidates_with_email}"
    )
    print(
        f"Selected/importable: "
        f"{len(result.companies)}"
    )
    print(
        f"Skipped no name:     "
        f"{result.skipped_no_name}"
    )
    print(
        f"Skipped no website:  "
        f"{result.skipped_no_website}"
    )

    print()
    print(
        "Discovery summary"
    )
    print(
        "-----------------"
    )
    print(
        f"Companies created:   "
        f"{summary.companies_created}"
    )
    print(
        f"Companies existing:  "
        f"{summary.companies_existing}"
    )
    print(
        f"Contacts created:    "
        f"{summary.contacts_created}"
    )
    print(
        f"Contacts existing:   "
        f"{summary.contacts_existing}"
    )
    print(
        f"Import skipped:      "
        f"{summary.import_skipped}"
    )


if __name__ == "__main__":
    main()
