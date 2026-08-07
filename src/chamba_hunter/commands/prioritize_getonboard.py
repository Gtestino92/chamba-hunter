import argparse

from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate
from chamba_hunter.domain.enums import (
    SourceType,
    TargetPriority,
)
from chamba_hunter.repositories.company_repository import (
    CompanyRepository,
)
from chamba_hunter.repositories.company_source_repository import (
    CompanySourceRepository,
)
from chamba_hunter.services.company_priority_service import (
    prioritize_company,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Prioritize Get on Board companies "
            "using company type and geographic signals."
        )
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Maximum companies to process. "
            "Defaults to all Get on Board companies."
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

    database = Database()
    migrate(database)

    company_repository = CompanyRepository(
        database
    )

    source_repository = CompanySourceRepository(
        database
    )

    sources = source_repository.list_by_source_type(
        SourceType.GETONBOARD
    )

    if args.limit is not None:
        sources = sources[:args.limit]

    counts = {
        TargetPriority.VERY_HIGH: 0,
        TargetPriority.HIGH: 0,
        TargetPriority.MEDIUM: 0,
        TargetPriority.LOW: 0,
        TargetPriority.UNKNOWN: 0,
    }

    processed = 0
    failed = 0

    remote_argentina_count = 0
    remote_latam_count = 0

    top_companies: list[
        tuple[
            TargetPriority,
            str,
            list[str],
        ]
    ] = []

    for source in sources:
        company = company_repository.get_by_id(
            source.company_id
        )

        if (
            company is None
            or company.id is None
        ):
            failed += 1
            continue

        metadata = source.metadata or {}

        decision = prioritize_company(
            company_type=company.company_type,
            metadata=metadata,
        )

        company_repository.update_targeting(
            company_id=company.id,
            target_priority=decision.priority,
            remote_argentina=(
                True
                if decision.remote_argentina
                else None
            ),
            remote_latam=(
                True
                if decision.remote_latam
                else None
            ),
        )

        counts[decision.priority] += 1

        if decision.remote_argentina:
            remote_argentina_count += 1

        if decision.remote_latam:
            remote_latam_count += 1

        if decision.priority in {
            TargetPriority.VERY_HIGH,
            TargetPriority.HIGH,
        }:
            top_companies.append(
                (
                    decision.priority,
                    company.name,
                    decision.reasons,
                )
            )

        processed += 1

    print("Prioritization finished")
    print("-----------------------")
    print(
        f"Processed:        {processed}"
    )
    print(
        f"Failed:           {failed}"
    )

    print()
    print("Priorities")
    print("----------")
    print(
        f"VERY_HIGH:        "
        f"{counts[TargetPriority.VERY_HIGH]}"
    )
    print(
        f"HIGH:             "
        f"{counts[TargetPriority.HIGH]}"
    )
    print(
        f"MEDIUM:           "
        f"{counts[TargetPriority.MEDIUM]}"
    )
    print(
        f"LOW:              "
        f"{counts[TargetPriority.LOW]}"
    )
    print(
        f"UNKNOWN:          "
        f"{counts[TargetPriority.UNKNOWN]}"
    )

    print()
    print("Remote compatibility")
    print("--------------------")
    print(
        f"Argentina:        "
        f"{remote_argentina_count}"
    )
    print(
        f"LATAM:            "
        f"{remote_latam_count}"
    )

    if top_companies:
        order = {
            TargetPriority.VERY_HIGH: 0,
            TargetPriority.HIGH: 1,
        }

        top_companies.sort(
            key=lambda item: (
                order[item[0]],
                item[1].casefold(),
            )
        )

        print()
        print("Top priority companies")
        print("----------------------")

        for (
            priority,
            name,
            reasons,
        ) in top_companies:
            print(
                f"{priority.value:<10} {name}"
            )

            if reasons:
                print(
                    "           "
                    + "; ".join(reasons)
                )


if __name__ == "__main__":
    main()