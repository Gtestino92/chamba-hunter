import argparse
from collections import Counter
import sys

from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate
from chamba_hunter.repositories.job_eligibility_repository import (
    JobEligibilityRepository,
)
from chamba_hunter.repositories.tracing_repository import (
    TracingRepository,
)
from chamba_hunter.services.argentina_eligibility_service import (
    ArgentinaEligibilityService,
    RULE_VERSION,
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
            "Classify active job candidates "
            "for Argentina geographic "
            "eligibility."
        )
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Persist current classifications. "
            "Without this flag the command "
            "is read-only."
        ),
    )

    parser.add_argument(
        "--unknown-samples",
        type=int,
        default=8,
        help=(
            "Maximum examples to print for "
            "each UNKNOWN reason."
        ),
    )

    args = parser.parse_args()

    if args.unknown_samples < 0:
        parser.error(
            "--unknown-samples cannot "
            "be negative."
        )

    database = Database()

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

    service = ArgentinaEligibilityService(
        repository=JobEligibilityRepository(
            database
        ),
        tracing_repository=TracingRepository(
            database
        ),
    )

    summary = service.run(
        apply=args.apply
    )

    print("Argentina eligibility")
    print("---------------------")
    print(
        "Rule version:",
        RULE_VERSION,
    )
    print(
        "Mode:        ",
        (
            "APPLY"
            if args.apply
            else "DRY RUN"
        ),
    )
    print(
        "Total:       ",
        summary.total,
    )
    print(
        "Eligible:    ",
        summary.eligible,
    )
    print(
        "Ineligible:  ",
        summary.ineligible,
    )
    print(
        "Unknown:     ",
        summary.unknown,
    )

    if args.apply:
        print(
            "Created:     ",
            summary.created,
        )
        print(
            "Updated:     ",
            summary.updated,
        )
        print(
            "Deleted:     ",
            summary.deleted,
        )
        print(
            "Run id:      ",
            summary.run_id,
        )

    status_reason_counts = Counter(
        (
            decision.status,
            decision.reason,
        )
        for decision in summary.decisions
    )

    print()
    print("REASONS")
    print("-------")

    for (
        status,
        reason,
    ), count in sorted(
        status_reason_counts.items()
    ):
        print(
            f"{status:<12} "
            f"{reason:<30} "
            f"{count}"
        )

    print()
    print("UNKNOWN SAMPLES")
    print("---------------")

    unknown_by_reason = {}

    for decision in summary.decisions:
        if decision.status != "UNKNOWN":
            continue

        unknown_by_reason.setdefault(
            decision.reason,
            [],
        ).append(decision)

    if not unknown_by_reason:
        print("None.")
        return

    for reason in sorted(
        unknown_by_reason
    ):
        decisions = unknown_by_reason[
            reason
        ]

        print()
        print(
            reason,
            f"({len(decisions)})",
        )

        for decision in decisions[
            :args.unknown_samples
        ]:
            print(
                " ",
                decision.record_kind,
                decision.record_id,
                "|",
                decision.workplace_type,
                "|",
                repr(
                    decision.location_text
                ),
                "|",
                decision.title,
            )


if __name__ == "__main__":
    main()
