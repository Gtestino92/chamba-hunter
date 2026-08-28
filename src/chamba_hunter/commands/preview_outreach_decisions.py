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
from chamba_hunter.repositories.public_contact_repository import (
    PublicContactRepository,
)
from chamba_hunter.services.outreach_decision_service import (
    DECISION_VERSION,
    decide_outreach,
)
from chamba_hunter.services.outreach_eligibility_service import (
    ELIGIBILITY_VERSION,
    OutreachEligibilityService,
)


DEFAULT_PROFILE = "BACKEND_SOFTWARE_V1"
DEFAULT_MIN_SCORE = 35.0
DEFAULT_TOP = 20


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
            "Preview the next direct outreach "
            "decisions in operational order."
        )
    )

    parser.add_argument(
        "--profile",
        default=DEFAULT_PROFILE,
    )

    parser.add_argument(
        "--min-score",
        type=float,
        default=DEFAULT_MIN_SCORE,
    )

    parser.add_argument(
        "--top",
        type=int,
        default=DEFAULT_TOP,
    )

    parser.add_argument(
        "--include-forms",
        action="store_true",
        help=(
            "Include GENERAL_FORM decisions. "
            "By default only email candidates "
            "are printed."
        ),
    )

    parser.add_argument(
        "--include-unknown",
        action="store_true",
        help=(
            "Also include companies whose "
            "Argentina/LATAM eligibility is "
            "UNKNOWN. INELIGIBLE companies "
            "remain excluded."
        ),
    )

    args = parser.parse_args()

    if not 0 <= args.min_score <= 100:
        parser.error(
            "--min-score must be between 0 and 100"
        )

    if args.top < 1:
        parser.error(
            "--top must be at least 1"
        )

    database = Database()
    migrate(
        database
    )

    contacts = PublicContactRepository(
        database
    )

    repository = CompanyOutreachRepository(
        database,
        contacts,
    )

    eligibility_service = (
        OutreachEligibilityService(
            database
        )
    )

    rows = repository.list_report_rows(
        search_profile_name=args.profile,
        min_score=args.min_score,
    )

    selected = []
    skipped_unknown = 0
    skipped_ineligible = 0

    for row in rows:
        if row.contacted:
            continue

        eligibility = (
            eligibility_service.decide(
                row
            )
        )

        if eligibility.status == "INELIGIBLE":
            skipped_ineligible += 1
            continue

        if (
            eligibility.status == "UNKNOWN"
            and not args.include_unknown
        ):
            skipped_unknown += 1
            continue

        decision = decide_outreach(
            row
        )

        if (
            not args.include_forms
            and not decision.is_email
        ):
            continue

        selected.append(
            (
                row,
                decision,
                eligibility,
            )
        )

        if len(selected) >= args.top:
            break

    print("Outreach decisions")
    print("------------------")
    print(
        f"Decision version: {DECISION_VERSION}"
    )
    print(
        f"Eligibility:      {ELIGIBILITY_VERSION}"
    )
    print(
        f"Profile:          {args.profile}"
    )
    print(
        f"Minimum score:    {args.min_score:.0f}"
    )
    print(
        f"Candidates:       {len(selected)}"
    )
    print(
        f"Skipped unknown:  {skipped_unknown}"
    )
    print(
        f"Skipped inelig.:  {skipped_ineligible}"
    )
    print()

    for index, (
        row,
        decision,
        eligibility,
    ) in enumerate(
        selected,
        start=1,
    ):
        print(
            f"{index:>2}. {row.score:>6.2f} "
            f"{row.company_name}"
        )
        print(
            "    Contact:    "
            f"{row.contact_value}"
        )
        print(
            "    Strategy:   "
            f"{decision.strategy}"
        )
        print(
            "    Language:   "
            f"{decision.language}"
        )
        print(
            "    Confidence: "
            f"{decision.confidence}"
        )
        print(
            "    Eligibility:"
            f" {eligibility.status} / "
            f"{eligibility.reason}"
        )
        if eligibility.active_jobs:
            print(
                "    Job geo:    "
                f"{eligibility.eligible_jobs} eligible, "
                f"{eligibility.ineligible_jobs} ineligible, "
                f"{eligibility.unknown_jobs} unknown"
            )
        print(
            "    Direct:     "
            f"{decision.contact_score:.0f}"
            + (
                " / "
                + decision.role_hint
                if decision.role_hint
                else ""
            )
        )
        print(
            "    Source:     "
            f"{row.contact_source_url or '-'}"
        )
        print()


if __name__ == "__main__":
    main()
