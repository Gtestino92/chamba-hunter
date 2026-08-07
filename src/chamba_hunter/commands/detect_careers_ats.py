import argparse

from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate
from chamba_hunter.domain.enums import (
    AtsScanStatus,
    CompanyStatus,
)
from chamba_hunter.repositories.company_ats_repository import (
    CompanyAtsRepository,
)
from chamba_hunter.repositories.company_repository import (
    CompanyRepository,
)
from chamba_hunter.repositories.tracing_repository import (
    TracingRepository,
)
from chamba_hunter.services.careers_ats_detection_service import (
    CareersAtsDetectionService,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Detect ATS providers from "
            "known careers pages."
        )
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Maximum number of companies "
            "to scan."
        ),
    )

    parser.add_argument(
        "--include-missing-careers",
        action="store_true",
        help=(
            "Also scan companies without "
            "a known careers URL by first "
            "looking for one on the homepage."
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

    company_repository = (
        CompanyRepository(database)
    )

    tracing_repository = (
        TracingRepository(database)
    )

    company_ats_repository = (
        CompanyAtsRepository(database)
    )

    companies = [
        company
        for company
        in company_repository.list_all()
        if (
            company.status
            == CompanyStatus.ACTIVE
            and (
                company.careers_url
                is not None
                or (
                    args.include_missing_careers
                    and company.website_url
                    is not None
                )
            )
        )
    ]

    if args.limit is not None:
        companies = companies[
            :args.limit
        ]

    print(
        "Detecting careers ATS..."
    )
    print(
        f"Companies: {len(companies)}"
    )
    print()

    service = CareersAtsDetectionService(
        company_repository=(
            company_repository
        ),
        tracing_repository=(
            tracing_repository
        ),
        company_ats_repository=(
            company_ats_repository
        ),
    )

    summary = service.run(
        companies
    )

    for result in summary.results:
        if (
            result.ats_status
            == AtsScanStatus.DETECTED
        ):
            identifier = (
                result.external_identifier
                or "identifier unknown"
            )

            print(
                f"{result.company_name}: "
                f"{result.provider.value} "
                f"[{identifier}]"
            )

            print(
                "  method: "
                f"{result.method.value}"
            )

            print(
                "  confidence: "
                f"{result.confidence:.2f}"
            )

            print(
                "  careers: "
                f"{result.careers_url}"
            )

            if result.warning:
                print(
                    "  warning: "
                    f"{result.warning}"
                )

        elif (
            result.ats_status
            == AtsScanStatus.BLOCKED
        ):
            print(
                f"{result.company_name}: "
                "BLOCKED"
            )

            print(
                "  careers: "
                f"{result.careers_url}"
            )

            if result.warning:
                print(
                    "  warning: "
                    f"{result.warning}"
                )

        elif (
            result.ats_status
            == AtsScanStatus.NOT_DETECTED
        ):
            print(
                f"{result.company_name}: "
                "NOT_DETECTED"
            )

            print(
                "  careers: "
                f"{result.careers_url}"
            )

        else:
            print(
                f"{result.company_name}: "
                "ERROR"
            )

            print(
                f"  {result.error}"
            )

        print()

    print("Detection finished")
    print("------------------")
    print(
        f"Run id:        "
        f"{summary.run_id}"
    )
    print(
        f"Processed:     "
        f"{summary.processed}"
    )
    print(
        f"Detected:      "
        f"{summary.detected}"
    )
    print(
        f"Not detected:  "
        f"{summary.not_detected}"
    )
    print(
        f"Blocked:       "
        f"{summary.blocked}"
    )
    print(
        f"Failed:        "
        f"{summary.failed}"
    )
    print(
        f"Skipped:       "
        f"{summary.skipped}"
    )


if __name__ == "__main__":
    main()