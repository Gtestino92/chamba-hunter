import argparse
from dataclasses import replace

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
from chamba_hunter.services.hibob_ats_detection_service import (
    HiBobAtsDetectionService,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Rediscover a company's careers "
            "page and revalidate its ATS."
        )
    )

    parser.add_argument(
        "--company-name",
        required=True,
        help=(
            "Exact company name to refresh "
            "(case-insensitive)."
        ),
    )

    args = parser.parse_args()

    database = Database()
    migrate(database)

    company_repository = (
        CompanyRepository(database)
    )
    company_ats_repository = (
        CompanyAtsRepository(database)
    )
    tracing_repository = (
        TracingRepository(database)
    )

    requested_name = (
        args.company_name.strip().casefold()
    )

    matches = [
        company
        for company
        in company_repository.list_all()
        if (
            company.status
            == CompanyStatus.ACTIVE
            and company.name.casefold()
            == requested_name
        )
    ]

    if not matches:
        parser.error(
            "No active company found with "
            f"name '{args.company_name}'."
        )

    if len(matches) > 1:
        parser.error(
            "More than one active company "
            "matches that name."
        )

    company = matches[0]

    if company.id is None:
        raise RuntimeError(
            "Company must have an id."
        )

    if company.website_url is None:
        parser.error(
            f"{company.name} does not have "
            "a website URL, so careers "
            "rediscovery cannot run."
        )

    old_careers_url = (
        company.careers_url
    )

    print(
        f"Refreshing careers ATS for "
        f"{company.name}..."
    )
    print(
        "Website:     "
        f"{company.website_url}"
    )
    print(
        "Old careers: "
        f"{old_careers_url}"
    )
    print()

    refresh_company = replace(
        company,
        careers_url=None,
    )

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
        [refresh_company]
    )

    if len(summary.results) != 1:
        raise RuntimeError(
            "Expected exactly one refresh "
            "result."
        )

    result = summary.results[0]

    if (
        result.ats_status
        == AtsScanStatus.DETECTED
    ):
        if result.careers_url is not None:
            (
                company_repository
                .update_careers_url(
                    company_id=company.id,
                    careers_url=(
                        result.careers_url
                    ),
                )
            )

        print("Result: DETECTED")
        print(
            "Careers: "
            f"{result.careers_url}"
        )
        print(
            "ATS:     "
            f"{result.provider.value}"
        )
        print(
            "ID:      "
            f"{result.external_identifier}"
        )
        print()
        print(
            "The detected ATS is now the "
            "active primary ATS."
        )

        return

    if (
        result.ats_status
        == AtsScanStatus.NOT_DETECTED
    ):
        if result.careers_url is None:
            print(
                "Result: NOT_DETECTED"
            )
            print(
                "No current careers URL "
                "was discovered."
            )
            print()
            print(
                "No company or ATS state "
                "was changed."
            )

            return

        hibob_summary = (
            HiBobAtsDetectionService(
                company_ats_repository=(
                    company_ats_repository
                ),
                tracing_repository=(
                    tracing_repository
                ),
            )
            .run(
                [
                    replace(
                        company,
                        careers_url=(
                            result.careers_url
                        ),
                    )
                ]
            )
        )

        if len(hibob_summary.results) != 1:
            raise RuntimeError(
                "Expected exactly one HiBob "
                "fallback result."
            )

        hibob_result = (
            hibob_summary.results[0]
        )

        if hibob_result.detected:
            (
                company_repository
                .update_careers_url(
                    company_id=company.id,
                    careers_url=(
                        result.careers_url
                    ),
                )
            )

            print("Result: DETECTED")
            print(
                "Careers: "
                f"{result.careers_url}"
            )
            print("ATS:     HIBOB")
            print(
                "ID:      "
                f"{hibob_result.tenant}"
            )
            print()
            print(
                "The detected ATS is now the "
                "active primary ATS."
            )

            return

        if hibob_result.error is not None:
            print("Result: ERROR")
            print(
                "HiBob fallback could not "
                "revalidate the careers page."
            )
            print(
                f"Error: {hibob_result.error}"
            )
            print()
            print(
                "No company or ATS state "
                "was changed."
            )

            return

        (
            company_repository
            .update_careers_url(
                company_id=company.id,
                careers_url=(
                    result.careers_url
                ),
            )
        )

        deactivated = (
            company_ats_repository
            .deactivate_all_for_company(
                company.id
            )
        )

        print("Result: NOT_DETECTED")
        print(
            "New careers: "
            f"{result.careers_url}"
        )
        print(
            "ATS rows deactivated: "
            f"{deactivated}"
        )
        print()
        print(
            "The careers page was refreshed "
            "successfully, but no supported "
            "ATS was detected."
        )

        return

    if (
        result.ats_status
        == AtsScanStatus.BLOCKED
    ):
        print("Result: BLOCKED")
        print(
            "Careers: "
            f"{result.careers_url}"
        )

        if result.warning:
            print(
                "Warning: "
                f"{result.warning}"
            )

        print()
        print(
            "No company or ATS state "
            "was changed."
        )

        return

    print("Result: ERROR")
    print(
        f"Error: {result.error}"
    )
    print()
    print(
        "No company or ATS state "
        "was changed."
    )


if __name__ == "__main__":
    main()
