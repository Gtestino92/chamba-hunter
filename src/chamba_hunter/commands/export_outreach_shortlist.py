import argparse
from pathlib import Path
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
)
from chamba_hunter.services.outreach_eligibility_service import (
    ELIGIBILITY_VERSION,
)
from chamba_hunter.services.outreach_shortlist_report_service import (
    DEFAULT_MIN_EXPLORE_SCORE,
    DEFAULT_MIN_SCORE,
    REPORT_VERSION,
    OutreachShortlistReportService,
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
            "Export direct company outreach "
            "shortlist."
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
        help=(
            "Priority Outreach minimum "
            "score. Kept for backwards "
            "compatibility."
        ),
    )

    parser.add_argument(
        "--min-explore-score",
        type=float,
        default=(
            DEFAULT_MIN_EXPLORE_SCORE
        ),
    )

    parser.add_argument(
        "--include-unknown",
        action="store_true",
        help=(
            "Include companies with UNKNOWN "
            "Argentina/LATAM eligibility. "
            "INELIGIBLE companies remain excluded."
        ),
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "output/"
            "chamba-outreach.xlsx"
        ),
    )

    args = parser.parse_args()

    for (
        argument_name,
        value,
    ) in (
        (
            "--min-score",
            args.min_score,
        ),
        (
            "--min-explore-score",
            args.min_explore_score,
        ),
    ):
        if (
            value < 0
            or value > 100
        ):
            parser.error(
                f"{argument_name} must "
                "be between 0 and 100"
            )

    if (
        args.min_explore_score
        > args.min_score
    ):
        parser.error(
            "--min-explore-score cannot "
            "be greater than --min-score"
        )

    database = Database()
    migrate(
        database
    )

    contact_repository = (
        PublicContactRepository(
            database
        )
    )

    repository = (
        CompanyOutreachRepository(
            database,
            contact_repository,
        )
    )

    summary = (
        OutreachShortlistReportService(
            repository
        )
        .export(
            search_profile_name=(
                args.profile
            ),
            output=args.output,
            min_score=args.min_score,
            min_explore_score=(
                args.min_explore_score
            ),
            include_unknown=(
                args.include_unknown
            ),
        )
    )

    print(
        "Chamba Hunter outreach export"
    )
    print(
        "-----------------------------"
    )
    print(
        f"Report version: "
        f"{REPORT_VERSION}"
    )
    print(
        f"Decision:       "
        f"{DECISION_VERSION}"
    )
    print(
        f"Eligibility:    "
        f"{ELIGIBILITY_VERSION}"
    )
    print(
        f"Profile:        "
        f"{args.profile}"
    )
    print(
        f"Priority min:   "
        f"{args.min_score:.0f}"
    )
    print(
        f"Explore min:    "
        f"{args.min_explore_score:.0f}"
    )
    print(
        f"Priority:       "
        f"{summary.priority}"
    )
    print(
        f"Explore:        "
        f"{summary.explore}"
    )
    print(
        f"History:        "
        f"{summary.history}"
    )
    print(
        f"Unknown skipped:"
        f" {summary.skipped_unknown}"
    )
    print(
        f"Inelig. skipped:"
        f" {summary.skipped_ineligible}"
    )
    print(
        f"Output:         "
        f"{args.output.resolve()}"
    )


if __name__ == "__main__":
    main()
