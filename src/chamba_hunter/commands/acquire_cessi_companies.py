import argparse
import sys

from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate
from chamba_hunter.repositories.company_repository import (
    CompanyRepository,
)
from chamba_hunter.repositories.company_source_repository import (
    CompanySourceRepository,
)
from chamba_hunter.repositories.public_contact_repository import (
    PublicContactRepository,
)
from chamba_hunter.services.cessi_company_acquisition_service import (
    CessiCompanyAcquisitionService,
)
from chamba_hunter.services.company_import_service import (
    CompanyImportService,
)
from chamba_hunter.sources.cessi_companies import (
    CessiDirectoryClient,
    DEFAULT_MAX_PAGES,
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
            "Import public CESSI directory "
            "companies and contact emails."
        )
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=DEFAULT_MAX_PAGES,
    )
    args = parser.parse_args()

    if args.max_pages < 1:
        parser.error(
            "--max-pages must be at least 1"
        )

    database = Database()
    applied = migrate(database)

    if applied:
        for migration in applied:
            print(
                "Applied migration:",
                migration,
            )
        print()

    service = (
        CessiCompanyAcquisitionService(
            client=CessiDirectoryClient(),
            company_import_service=(
                CompanyImportService(
                    CompanyRepository(
                        database
                    ),
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
    )

    summary = service.run(
        max_pages=args.max_pages
    )

    print("CESSI company acquisition")
    print("-------------------------")
    print(
        f"Pages fetched:       "
        f"{summary.pages_fetched}"
    )
    print(
        f"Directory contacts:  "
        f"{summary.received}"
    )
    print(
        f"Normalized:          "
        f"{summary.normalized}"
    )
    print(
        f"Skipped:             "
        f"{summary.skipped}"
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


if __name__ == "__main__":
    main()
