import argparse
import sys

from chamba_hunter.db.connection import (
    Database,
)
from chamba_hunter.db.migrations import (
    migrate,
)
from chamba_hunter.repositories.job_lead_canonicalization_repository import (
    JobLeadCanonicalizationRepository,
)
from chamba_hunter.repositories.tracing_repository import (
    TracingRepository,
)
from chamba_hunter.services.job_lead_canonicalization_service import (
    JobLeadCanonicalizationService,
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
            "Conservatively canonicalize broad "
            "job leads against active ATS jobs."
        )
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Persist unambiguous canonical links. "
            "Without this flag the command is "
            "read-only."
        ),
    )

    args = parser.parse_args()

    database = Database()

    # Do not apply migrations in read-only mode.
    # The migration is required only when links
    # are actually persisted.
    if args.apply:
        applied_migrations = migrate(
            database
        )

        for migration in applied_migrations:
            print(
                "Applied migration:",
                migration,
            )

        if applied_migrations:
            print()

    repository = (
        JobLeadCanonicalizationRepository(
            database
        )
    )

    service = (
        JobLeadCanonicalizationService(
            repository=repository,
            tracing_repository=(
                TracingRepository(
                    database
                )
            ),
        )
    )

    summary = service.run(
        apply=args.apply
    )

    print(
        "Job lead canonicalization"
    )
    print(
        "-------------------------"
    )
    print(
        "Mode:       ",
        (
            "APPLY"
            if args.apply
            else "DRY RUN"
        ),
    )
    print(
        "Total:      ",
        summary.total,
    )
    print(
        "Resolved:   ",
        summary.resolved,
    )
    print(
        "Ambiguous:  ",
        summary.ambiguous,
    )
    print(
        "Unmatched:  ",
        summary.unmatched,
    )

    if args.apply:
        print(
            "Applied:    ",
            summary.applied,
        )
        print(
            "Run id:     ",
            summary.run_id,
        )

    print()
    print(
        (
            "APPLIED LINKS"
            if args.apply
            else "PROPOSED LINKS"
        )
    )
    print(
        "-------------"
    )

    if not summary.decisions:
        print("None.")
    else:
        for decision in (
            summary.decisions
        ):
            print()
            print(
                f"LEAD {decision.lead_id} "
                f"=> JOB {decision.job_id} "
                f"[{decision.method}]"
            )
            print(
                "  company:  ",
                decision.company_name,
            )
            print(
                "  title:    ",
                decision.title,
            )
            print(
                "  location: ",
                decision.lead_location,
                "=>",
                decision.job_location,
            )
            print(
                "  workplace:",
                decision.lead_workplace,
                "=>",
                decision.job_workplace,
            )
            print(
                "  provider: ",
                decision.provider,
            )

    print()
    print("AMBIGUOUS")
    print("---------")

    if not summary.ambiguities:
        print("None.")
    else:
        for ambiguity in (
            summary.ambiguities
        ):
            print()
            print(
                "LEAD",
                ambiguity.lead_id,
                "|",
                ambiguity.company_name,
                "|",
                ambiguity.title,
            )
            print(
                "  location:",
                ambiguity.location_text,
            )
            print(
                "  candidates:",
                len(
                    ambiguity
                    .candidate_job_ids
                ),
            )

            preview = list(
                zip(
                    ambiguity
                    .candidate_job_ids,
                    ambiguity
                    .candidate_locations,
                )
            )[:5]

            for (
                job_id,
                location,
            ) in preview:
                print(
                    "   ",
                    job_id,
                    "|",
                    location,
                )

            remaining = (
                len(
                    ambiguity
                    .candidate_job_ids
                )
                - len(preview)
            )

            if remaining > 0:
                print(
                    "   ... and",
                    remaining,
                    "more",
                )


if __name__ == "__main__":
    main()
