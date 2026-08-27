import argparse
import sys

from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate
from chamba_hunter.domain.enums import ContactType
from chamba_hunter.domain.models import PublicContact
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
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(
            encoding="utf-8",
            errors="replace",
        )

    parser = argparse.ArgumentParser(
        description=(
            "Add a known public contact to an "
            "existing company."
        )
    )

    parser.add_argument(
        "--company",
        required=True,
    )

    parser.add_argument(
        "--type",
        required=True,
        choices=[
            item.value
            for item in ContactType
        ],
    )

    parser.add_argument(
        "--value",
        required=True,
    )

    parser.add_argument(
        "--source-url",
    )

    parser.add_argument(
        "--notes",
    )

    args = parser.parse_args()

    database = Database()
    migrate(database)

    company = (
        CompanyRepository(database)
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

    contact, created = (
        PublicContactRepository(database)
        .add_or_touch(
            PublicContact(
                company_id=company.id,
                contact_type=ContactType(
                    args.type
                ),
                value=args.value,
                source_url=args.source_url,
                notes=args.notes,
            )
        )
    )

    print("Public contact")
    print("--------------")
    print(f"Company:      {company.name}")
    print(f"Contact id:   {contact.id}")
    print(f"Type:         {contact.contact_type.value}")
    print(f"Value:        {contact.value}")
    print(f"Created:      {created}")


if __name__ == "__main__":
    main()
