import argparse

from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate
from chamba_hunter.domain.enums import (
    CompanyType,
    SourceType,
)
from chamba_hunter.domain.models import (
    CompanyClassification,
)
from chamba_hunter.repositories.company_classification_repository import (
    CompanyClassificationRepository,
)
from chamba_hunter.repositories.company_repository import (
    CompanyRepository,
)
from chamba_hunter.repositories.company_source_repository import (
    CompanySourceRepository,
)
from chamba_hunter.services.company_classifier import (
    classify_company,
)


METHOD = "GETONBOARD_METADATA_RULES_V3"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Classify Get on Board companies "
            "using their public company metadata."
        )
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help=(
            "Maximum new classifications to create. "
            "Defaults to 20."
        ),
    )

    args = parser.parse_args()

    if args.limit < 1:
        parser.error(
            "--limit must be at least 1"
        )

    database = Database()
    migrate(database)

    company_repository = CompanyRepository(
        database
    )

    source_repository = CompanySourceRepository(
        database
    )

    classification_repository = (
        CompanyClassificationRepository(
            database
        )
    )

    sources = source_repository.list_by_source_type(
        SourceType.GETONBOARD
    )

    processed = 0
    skipped = 0

    product = 0
    consultancy = 0
    recruiter = 0
    unknown = 0

    failed = 0

    print(
        "Classifying Get on Board companies..."
    )
    print(
        f"Method: {METHOD}"
    )
    print(
        f"Limit: {args.limit}"
    )
    print()

    for source in sources:
        if processed >= args.limit:
            break

        company = company_repository.get_by_id(
            source.company_id
        )

        if company is None:
            failed += 1
            continue

        if company.id is None:
            failed += 1
            continue

        if (
            classification_repository
            .exists_for_company_and_method(
                company_id=company.id,
                method=METHOD,
            )
        ):
            skipped += 1
            continue

        metadata = source.metadata or {}

        description = _optional_string(
            metadata.get(
                "company_description"
            )
        )

        long_description = _optional_string(
            metadata.get(
                "company_long_description"
            )
        )

        decision = classify_company(
            name=company.name,
            description=description,
            long_description=long_description,
        )

        classification_repository.add(
            CompanyClassification(
                company_id=company.id,
                company_type=decision.company_type,
                confidence=decision.confidence,
                method=METHOD,
                evidence=decision.evidence,
            )
        )

        if (
            company.company_type
            == CompanyType.UNKNOWN
            and decision.company_type
            != CompanyType.UNKNOWN
        ):
            company_repository.update_enrichment(
                company_id=company.id,
                company_type=(
                    decision.company_type
                ),
            )

        processed += 1

        if (
            decision.company_type
            == CompanyType.PRODUCT
        ):
            product += 1

        elif (
            decision.company_type
            == CompanyType.CONSULTANCY
        ):
            consultancy += 1

        elif (
            decision.company_type
            == CompanyType.RECRUITER
        ):
            recruiter += 1

        else:
            unknown += 1

        matches = decision.evidence.get(
            "matches",
            {},
        )

        print(
            f"{company.name}: "
            f"{decision.company_type.value} "
            f"({decision.confidence:.2f})"
        )

        relevant_matches = [
            phrase
            for values in matches.values()
            for phrase in values
        ]

        if relevant_matches:
            print(
                "  evidence: "
                + ", ".join(
                    relevant_matches
                )
            )

    print()
    print("Classification finished")
    print("-----------------------")
    print(
        f"Processed:   {processed}"
    )
    print(
        f"Skipped:     {skipped}"
    )
    print(
        f"Product:     {product}"
    )
    print(
        f"Consultancy: {consultancy}"
    )
    print(
        f"Recruiter:   {recruiter}"
    )
    print(
        f"Unknown:     {unknown}"
    )
    print(
        f"Failed:      {failed}"
    )


def _optional_string(
    value: object,
) -> str | None:
    if not isinstance(value, str):
        return None

    cleaned = value.strip()

    return cleaned if cleaned else None


if __name__ == "__main__":
    main()