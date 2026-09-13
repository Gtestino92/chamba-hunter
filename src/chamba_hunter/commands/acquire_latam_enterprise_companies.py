import argparse
from pathlib import Path
import sys

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
from chamba_hunter.services.latam_enterprise_company_acquisition_service import (
    LatamEnterpriseAcquisitionSummary,
    LatamEnterpriseCompanyAcquisitionService,
)
from chamba_hunter.sources.latam_enterprise_companies import (
    DEFAULT_REGISTRY_PATH,
    load_latam_enterprise_registry,
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
            "Preview or import the curated "
            "Argentina/LATAM enterprise "
            "company universe."
        )
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Persist companies and source "
            "tracking. Without this flag, "
            "only preview matches/creates."
        ),
    )

    parser.add_argument(
        "--country",
        help=(
            "Only process registry entries "
            "for this country, for example "
            "Argentina."
        ),
    )

    parser.add_argument(
        "--limit",
        type=int,
        help=(
            "Process at most N selected "
            "registry entries."
        ),
    )

    parser.add_argument(
        "--registry",
        type=Path,
        default=DEFAULT_REGISTRY_PATH,
        help=(
            "Path to the curated registry "
            "JSON file."
        ),
    )

    args = parser.parse_args()

    if (
        args.limit is not None
        and args.limit < 1
    ):
        parser.error(
            "--limit must be at least 1"
        )

    registry = load_latam_enterprise_registry(
        args.registry
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
        LatamEnterpriseCompanyAcquisitionService(
            CompanyImportService(
                CompanyRepository(
                    database
                ),
                CompanySourceRepository(
                    database
                ),
            )
        )
    )

    summary = service.run(
        registry=registry,
        apply=args.apply,
        country=args.country,
        limit=args.limit,
    )

    _print_summary(
        summary
    )


def _print_summary(
    summary: LatamEnterpriseAcquisitionSummary,
) -> None:
    print(
        "LATAM enterprise company acquisition"
    )
    print(
        "===================================="
    )
    print(
        "Mode:                "
        + (
            "APPLY"
            if summary.apply
            else "DRY RUN"
        )
    )
    print(
        f"Registry entries:    "
        f"{summary.registry_entries}"
    )
    print(
        f"Selected entries:    "
        f"{summary.selected_entries}"
    )
    print(
        f"Created companies:   "
        f"{summary.companies_created}"
    )
    print(
        f"Existing companies:  "
        f"{summary.companies_existing}"
    )
    print(
        f"Skipped entries:     "
        f"{summary.skipped_entries}"
    )
    print(
        f"Failed entries:      "
        f"{summary.failed_entries}"
    )

    if summary.matched_by_counts:
        print()
        print("Existing match methods")
        print("----------------------")

        for matched_by, count in sorted(
            summary.matched_by_counts.items()
        ):
            print(
                f"{matched_by:<28} "
                f"{count}"
            )

    failures = [
        result
        for result in summary.results
        if result.error_type is not None
    ]

    if failures:
        print()
        print("Failures")
        print("--------")

        for result in failures:
            print(
                f"{result.name}: "
                f"{result.error_type}: "
                f"{result.error_message}"
            )

    if not summary.apply:
        print()
        print(
            "Dry run; no companies or "
            "company sources were written."
        )
        print(
            "Use --apply to persist this "
            "company universe."
        )


if __name__ == "__main__":
    main()
