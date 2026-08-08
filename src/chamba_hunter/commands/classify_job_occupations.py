import argparse
from collections import Counter
import sys

from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate
from chamba_hunter.repositories.job_occupation_repository import (
    JobOccupationRepository,
)
from chamba_hunter.repositories.tracing_repository import (
    TracingRepository,
)
from chamba_hunter.services.job_occupation_classification_service import (
    JobOccupationClassificationService,
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
            "Classify geographically viable job "
            "candidates by occupation and backend "
            "relevance."
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
        default=12,
        help=(
            "Maximum UNKNOWN occupation examples "
            "to print."
        ),
    )

    parser.add_argument(
        "--backend-unknown-samples",
        type=int,
        default=12,
        help=(
            "Maximum SOFTWARE_ENGINEERING examples "
            "with UNKNOWN backend relevance to print."
        ),
    )

    args = parser.parse_args()

    if args.unknown_samples < 0:
        parser.error(
            "--unknown-samples cannot be negative."
        )

    if args.backend_unknown_samples < 0:
        parser.error(
            "--backend-unknown-samples cannot "
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

    service = JobOccupationClassificationService(
        repository=JobOccupationRepository(
            database
        ),
        tracing_repository=TracingRepository(
            database
        ),
    )

    summary = service.run(
        apply=args.apply
    )

    print("Job occupation classification")
    print("-----------------------------")
    print(
        "Rule version:",
        RULE_VERSION,
    )
    print(
        "Scope:       ",
        "Argentina ELIGIBLE + UNKNOWN",
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
        "Software:    ",
        summary.software_engineering,
    )
    print(
        "IT technical:",
        summary.it_technical,
    )
    print(
        "Tech adjacent:",
        summary.tech_adjacent,
    )
    print(
        "Non technical:",
        summary.non_technical,
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

    backend_counts = Counter(
        decision.backend_relevance
        for decision in summary.decisions
        if (
            decision.occupation_class
            == "SOFTWARE_ENGINEERING"
        )
    )

    method_counts = Counter(
        decision.method
        for decision in summary.decisions
    )

    reason_counts = Counter(
        (
            decision.occupation_class,
            decision.reason,
        )
        for decision in summary.decisions
    )

    print()
    print("SOFTWARE BACKEND RELEVANCE")
    print("--------------------------")

    for backend, count in sorted(
        backend_counts.items()
    ):
        print(
            f"{backend:<16} {count}"
        )

    print()
    print("METHODS")
    print("-------")

    for method, count in sorted(
        method_counts.items()
    ):
        print(
            f"{method:<20} {count}"
        )

    print()
    print("REASONS")
    print("-------")

    for (
        occupation_class,
        reason,
    ), count in sorted(
        reason_counts.items()
    ):
        print(
            f"{occupation_class:<22} "
            f"{reason:<36} "
            f"{count}"
        )

    unknowns = [
        decision
        for decision in summary.decisions
        if decision.occupation_class == "UNKNOWN"
    ]

    print()
    print("UNKNOWN OCCUPATION SAMPLES")
    print("--------------------------")

    if not unknowns:
        print("None.")
    else:
        for decision in unknowns[
            :args.unknown_samples
        ]:
            print(
                decision.record_kind,
                decision.record_id,
                "|",
                decision.origin,
                "|",
                decision.company_name,
                "|",
                decision.eligibility_status,
                "|",
                decision.title,
            )

    backend_unknowns = [
        decision
        for decision in summary.decisions
        if (
            decision.occupation_class
            == "SOFTWARE_ENGINEERING"
            and decision.backend_relevance
            == "UNKNOWN"
        )
    ]

    print()
    print("SOFTWARE WITH UNKNOWN BACKEND")
    print("-----------------------------")

    if not backend_unknowns:
        print("None.")
    else:
        for decision in backend_unknowns[
            :args.backend_unknown_samples
        ]:
            print(
                decision.record_kind,
                decision.record_id,
                "|",
                decision.origin,
                "|",
                decision.company_name,
                "|",
                decision.title,
            )


if __name__ == "__main__":
    main()
