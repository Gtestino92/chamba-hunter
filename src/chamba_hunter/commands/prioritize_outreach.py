import argparse
import sys

from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate
from chamba_hunter.repositories.company_outreach_repository import (
    CompanyOutreachRepository,
)
from chamba_hunter.repositories.public_contact_repository import (
    PublicContactRepository,
)
from chamba_hunter.services.company_outreach_priority_service import (
    CompanyOutreachPriorityService,
    DEFAULT_MIN_ACTIONABLE_SCORE,
    RULE_VERSION,
)


DEFAULT_PROFILE = "BACKEND_SOFTWARE_V1"


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
            "Score direct company outreach "
            "opportunities."
        )
    )
    parser.add_argument(
        "--profile",
        default=DEFAULT_PROFILE,
    )
    parser.add_argument(
        "--apply",
        action="store_true",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=20,
    )
    args = parser.parse_args()

    if args.top < 0:
        parser.error(
            "--top cannot be negative"
        )

    database = Database()
    migrate(database)

    contact_repository = (
        PublicContactRepository(
            database
        )
    )

    contact_repository.import_company_general_application_urls()

    repository = (
        CompanyOutreachRepository(
            database,
            contact_repository,
        )
    )

    summary = (
        CompanyOutreachPriorityService(
            repository
        )
        .run(
            search_profile_name=(
                args.profile
            ),
            apply=args.apply,
        )
    )

    print("Company outreach priority")
    print("-------------------------")
    print(
        f"Rule version:       "
        f"{RULE_VERSION}"
    )
    print(
        f"Profile:            "
        f"{summary.search_profile_name}"
    )
    print(
        f"Mode:               "
        f"{'APPLY' if args.apply else 'DRY RUN'}"
    )
    print(
        f"Evaluated:          "
        f"{summary.evaluated}"
    )
    print(
        f"Actionable >= "
        f"{DEFAULT_MIN_ACTIONABLE_SCORE:.0f}: "
        f"{summary.actionable}"
    )
    print(
        f"Already contacted:  "
        f"{summary.already_contacted}"
    )
    print(
        f"VERY_HIGH:          "
        f"{summary.very_high}"
    )
    print(
        f"HIGH:               "
        f"{summary.high}"
    )
    print(
        f"MEDIUM:             "
        f"{summary.medium}"
    )
    print(
        f"LOW:                "
        f"{summary.low}"
    )

    if args.top:
        print()
        print("Top direct outreach")
        print("-------------------")
        shown = 0

        for item in summary.evaluations:
            if item.contacted:
                continue
            if (
                item.best_contact
                is None
                or item.score
                < DEFAULT_MIN_ACTIONABLE_SCORE
            ):
                continue

            print(
                f"{item.score:>6.2f} "
                f"{item.level:<9} "
                f"{item.company_name}"
            )
            print(
                "         "
                f"{item.best_contact.value} "
                f"[{item.best_contact.contact_type.value}]"
            )
            shown += 1

            if shown >= args.top:
                break


if __name__ == "__main__":
    main()
