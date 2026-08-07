import argparse
from pathlib import Path

from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate
from chamba_hunter.importers.company_csv_importer import (
    import_companies_csv,
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import companies from a CSV file."
    )

    parser.add_argument(
        "csv_path",
        type=Path,
        help="Path to the CSV file to import.",
    )

    args = parser.parse_args()

    database = Database()

    migrate(database)

    company_repository = CompanyRepository(database)
    company_source_repository = CompanySourceRepository(database)

    service = CompanyImportService(
        company_repository,
        company_source_repository,
    )

    summary = import_companies_csv(
        args.csv_path,
        service,
    )

    print()
    print("Company import finished")
    print("-----------------------")
    print(f"Processed: {summary.total}")
    print(f"Created:   {summary.created}")
    print(f"Existing:  {summary.existing}")
    print(f"Invalid:   {summary.invalid}")

    if summary.errors:
        print()
        print("Errors:")

        for error in summary.errors:
            print(
                f"  row {error.row_number}: "
                f"{error.message}"
            )


if __name__ == "__main__":
    main()