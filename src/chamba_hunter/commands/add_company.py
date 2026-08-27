import argparse
import sys

from pydantic import AnyHttpUrl, TypeAdapter

from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate
from chamba_hunter.domain.enums import (
    ContactType,
    SourceType,
)
from chamba_hunter.domain.models import PublicContact
from chamba_hunter.repositories.company_repository import (
    CompanyRepository,
)
from chamba_hunter.repositories.company_source_repository import (
    CompanySourceRepository,
)
from chamba_hunter.repositories.public_contact_repository import (
    PublicContactRepository,
)
from chamba_hunter.schemas.inputs import CompanySeedInput
from chamba_hunter.services.company_import_service import (
    CompanyImportService,
)


HTTP_URL_ADAPTER = TypeAdapter(AnyHttpUrl)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(
            encoding="utf-8",
            errors="replace",
        )

    parser = argparse.ArgumentParser(
        description=(
            "Add or enrich a manually known company "
            "for direct outreach."
        )
    )

    parser.add_argument(
        "--company",
        required=True,
        help="Company name.",
    )

    parser.add_argument(
        "--website",
        help="Official company website.",
    )

    parser.add_argument(
        "--country",
        help="Optional company country.",
    )

    parser.add_argument(
        "--contact",
        help=(
            "Optional public email or general "
            "application URL."
        ),
    )

    parser.add_argument(
        "--contact-type",
        choices=[
            item.value
            for item in ContactType
        ],
        default=ContactType.GENERAL_EMAIL.value,
    )

    parser.add_argument(
        "--source-url",
        help=(
            "Public page where the company/contact "
            "information was found."
        ),
    )

    parser.add_argument(
        "--notes",
    )

    args = parser.parse_args()

    website = (
        HTTP_URL_ADAPTER.validate_python(
            args.website
        )
        if args.website
        else None
    )

    source_url = (
        HTTP_URL_ADAPTER.validate_python(
            args.source_url
        )
        if args.source_url
        else website
    )

    database = Database()
    migrate(database)

    result = CompanyImportService(
        CompanyRepository(database),
        CompanySourceRepository(database),
    ).import_seed(
        CompanySeedInput(
            name=args.company,
            website_url=website,
            country=args.country,
            source_type=SourceType.MANUAL,
            source_url=source_url,
            notes=args.notes,
        ),
        source_metadata={
            "manual_reference": True,
        },
    )

    company = result.company

    if company.id is None:
        raise RuntimeError(
            "Imported company must have an id."
        )

    contact = None

    if args.contact:
        contact, _ = (
            PublicContactRepository(database)
            .add_or_touch(
                PublicContact(
                    company_id=company.id,
                    contact_type=ContactType(
                        args.contact_type
                    ),
                    value=args.contact,
                    source_url=(
                        str(source_url)
                        if source_url is not None
                        else None
                    ),
                    notes=(
                        "Manually supplied public "
                        "company contact."
                    ),
                )
            )
        )

    print("Manual company")
    print("--------------")
    print(f"Company id:   {company.id}")
    print(f"Name:         {company.name}")
    print(f"Created:      {result.created}")
    print(
        f"Matched by:   "
        f"{result.matched_by or '-'}"
    )
    print(
        f"Website:      "
        f"{company.website_url or '-'}"
    )
    print(
        f"Contact:      "
        f"{contact.value if contact else '-'}"
    )


if __name__ == "__main__":
    main()
