import argparse
import sys

from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate
from chamba_hunter.domain.enums import (
    ApplicationStatus,
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
            "Track a spontaneous/direct "
            "company outreach."
        )
    )
    parser.add_argument(
        "--company",
        required=True,
    )
    parser.add_argument(
        "--contact",
        help=(
            "Optional exact public email/URL. "
            "If omitted, use the highest-quality "
            "active contact."
        ),
    )
    parser.add_argument(
        "--status",
        choices=[
            status.value
            for status
            in ApplicationStatus
        ],
        default=(
            ApplicationStatus.SENT.value
        ),
    )
    parser.add_argument(
        "--notes",
    )
    args = parser.parse_args()

    database = Database()
    migrate(database)

    company_repository = (
        CompanyRepository(
            database
        )
    )

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

    if args.contact:
        contact = (
            outreach_repository
            .find_active_contact_value(
                company.id,
                args.contact,
            )
        )
    else:
        contact = (
            outreach_repository
            .best_active_contact(
                company.id
            )
        )

    if contact is None:
        raise SystemExit(
            "No matching active public "
            "contact was found."
        )

    result = (
        outreach_repository
        .track_outreach(
            company_id=company.id,
            contact=contact,
            status=ApplicationStatus(
                args.status
            ),
            notes=args.notes,
        )
    )

    print("Outreach tracked")
    print("----------------")
    print(
        f"Company:          "
        f"{company.name}"
    )
    print(
        f"Contact:          "
        f"{contact.value}"
    )
    print(
        f"Contact type:     "
        f"{contact.contact_type.value}"
    )
    print(
        f"Application id:   "
        f"{result.application_id}"
    )
    print(
        f"Created:          "
        f"{result.created}"
    )
    print(
        f"Previous status:  "
        f"{result.previous_status or '-'}"
    )
    print(
        f"Current status:   "
        f"{result.current_status}"
    )


if __name__ == "__main__":
    main()
