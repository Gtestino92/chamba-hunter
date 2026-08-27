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
from chamba_hunter.services.company_import_service import (
    CompanyImportService,
)
from chamba_hunter.services.yc_company_acquisition_service import (
    YcCompanyAcquisitionService,
)
from chamba_hunter.sources.yc_companies import (
    DEFAULT_CATEGORIES,
    DEFAULT_MAX_COMPANIES,
    YcDirectoryClient,
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
            "Import relevant public YC "
            "technology companies for "
            "direct outreach."
        )
    )

    parser.add_argument(
        "--max-companies",
        type=int,
        default=(
            DEFAULT_MAX_COMPANIES
        ),
        help=(
            "Maximum active/public YC "
            "companies to import after "
            "cross-category deduplication."
        ),
    )

    parser.add_argument(
        "--category",
        action="append",
        dest="categories",
        help=(
            "YC technical category. Repeat "
            "to override the default set."
        ),
    )

    args = parser.parse_args()

    if args.max_companies < 1:
        parser.error(
            "--max-companies must be "
            "at least 1"
        )

    categories = tuple(
        args.categories
        or DEFAULT_CATEGORIES
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

    company_import_service = (
        CompanyImportService(
            company_repository,
            CompanySourceRepository(
                database
            ),
        )
    )

    summary = (
        YcCompanyAcquisitionService(
            client=(
                YcDirectoryClient()
            ),
            company_import_service=(
                company_import_service
            ),
            company_repository=(
                company_repository
            ),
        )
        .run(
            categories=categories,
            max_companies=(
                args.max_companies
            ),
        )
    )

    print(
        "YC company acquisition"
    )
    print(
        "----------------------"
    )
    print(
        "Categories:           "
        + ", ".join(
            categories
        )
    )
    print(
        f"Feeds requested:      "
        f"{summary.feeds_requested}"
    )
    print(
        f"Feeds fetched:        "
        f"{summary.feeds_fetched}"
    )
    print(
        f"Feed failures:        "
        f"{summary.feeds_failed}"
    )
    print(
        f"Raw records:          "
        f"{summary.raw_records}"
    )
    print(
        f"Unique candidates:    "
        f"{summary.unique_candidates}"
    )
    print(
        f"Status skipped:       "
        f"{summary.skipped_status}"
    )
    print(
        f"No website skipped:   "
        f"{summary.skipped_missing_website}"
    )
    print(
        f"Invalid skipped:      "
        f"{summary.skipped_invalid}"
    )
    print(
        f"Import skipped:       "
        f"{summary.skipped_import}"
    )
    print(
        f"Companies selected:   "
        f"{summary.received}"
    )
    print(
        f"Companies created:    "
        f"{summary.companies_created}"
    )
    print(
        f"Companies existing:   "
        f"{summary.companies_existing}"
    )
    print(
        f"Currently hiring:     "
        f"{summary.currently_hiring}"
    )
    print(
        f"Classified PRODUCT:   "
        f"{summary.product_classified}"
    )


if __name__ == "__main__":
    main()
