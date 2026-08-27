import argparse
import sys

from chamba_hunter.db.connection import (
    Database,
)
from chamba_hunter.db.migrations import (
    migrate,
)
from chamba_hunter.repositories.company_outreach_repository import (
    CompanyOutreachRepository,
)
from chamba_hunter.repositories.company_repository import (
    CompanyRepository,
)
from chamba_hunter.repositories.public_contact_repository import (
    PublicContactRepository,
)
from chamba_hunter.services.company_import_service import (
    normalize_company_name,
)
from chamba_hunter.services.public_contact_discovery_service import (
    DEFAULT_MAX_PAGES_PER_COMPANY,
    PublicContactDiscoveryService,
)


DEFAULT_PROFILE = (
    "BACKEND_SOFTWARE_V1"
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
            "Scan selected official company "
            "websites for public recruiting, "
            "careers and general contacts."
        )
    )

    parser.add_argument(
        "--profile",
        default=DEFAULT_PROFILE,
    )

    parser.add_argument(
        "--company",
        help=(
            "Scan exactly one known company "
            "by normalized name. This bypasses "
            "batch selection and recent-scan "
            "suppression."
        ),
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=75,
    )

    parser.add_argument(
        "--max-pages-per-company",
        type=int,
        default=(
            DEFAULT_MAX_PAGES_PER_COMPANY
        ),
    )

    parser.add_argument(
        "--rescan-after-days",
        type=int,
        default=30,
    )

    parser.add_argument(
        "--force",
        action="store_true",
    )

    args = parser.parse_args()

    if args.limit < 1:
        parser.error(
            "--limit must be at least 1"
        )

    if (
        args.max_pages_per_company
        < 1
    ):
        parser.error(
            "--max-pages-per-company "
            "must be at least 1"
        )

    if args.rescan_after_days < 1:
        parser.error(
            "--rescan-after-days must "
            "be at least 1"
        )

    database = Database()
    migrate(
        database
    )

    company_repository = (
        CompanyRepository(
            database
        )
    )

    contact_repository = (
        PublicContactRepository(
            database
        )
    )

    outreach_repository = (
        CompanyOutreachRepository(
            database,
            contact_repository,
        )
    )

    if args.company:
        company = (
            company_repository
            .get_unique_by_normalized_name(
                normalize_company_name(
                    args.company
                )
            )
        )

        if company is None:
            raise SystemExit(
                "Could not resolve a unique "
                f"company: {args.company!r}"
            )

        if company.id is None:
            raise RuntimeError(
                "Resolved company has no id."
            )

        if not company.website_url:
            raise SystemExit(
                "Company has no website_url: "
                f"{company.name}"
            )

        target_ids = [
            company.id
        ]

    else:
        target_ids = (
            outreach_repository
            .list_contact_scan_target_ids(
                search_profile_name=(
                    args.profile
                ),
                limit=args.limit,
                rescan_after_days=(
                    args.rescan_after_days
                ),
                force=args.force,
            )
        )

    print(
        "Public contact discovery"
    )
    print(
        "------------------------"
    )
    print(
        f"Selected: "
        f"{len(target_ids)}"
    )
    print()

    if not target_ids:
        print(
            "No companies require a "
            "contact scan."
        )
        return

    summary = (
        PublicContactDiscoveryService(
            company_repository=(
                company_repository
            ),
            public_contact_repository=(
                contact_repository
            ),
            outreach_repository=(
                outreach_repository
            ),
        )
        .run(
            company_ids=target_ids,
            max_pages_per_company=(
                args
                .max_pages_per_company
            ),
        )
    )

    for result in (
        summary.results
    ):
        print(
            f"{result.company_name}: "
            f"{result.status.value}"
        )
        print(
            "  pages: "
            f"{result.pages_fetched}"
        )
        print(
            "  new:   "
            f"{result.contacts_created}"
        )
        print(
            "  seen:  "
            f"{result.contacts_existing}"
        )

        if result.error_message:
            print(
                "  error: "
                f"{result.error_type}: "
                f"{result.error_message}"
            )

    print()
    print(
        "Contact discovery finished"
    )
    print(
        "--------------------------"
    )
    print(
        f"Processed:          "
        f"{summary.processed}"
    )
    print(
        f"Succeeded:          "
        f"{summary.succeeded}"
    )
    print(
        f"Failed:             "
        f"{summary.failed}"
    )
    print(
        f"Pages fetched:      "
        f"{summary.pages_fetched}"
    )
    print(
        f"Contacts created:   "
        f"{summary.contacts_created}"
    )
    print(
        f"Contacts existing:  "
        f"{summary.contacts_existing}"
    )


if __name__ == "__main__":
    main()
