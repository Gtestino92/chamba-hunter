import argparse
from collections import Counter
import sys

from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate
from chamba_hunter.repositories.job_seniority_repository import (
    JobSeniorityRepository,
)
from chamba_hunter.repositories.tracing_repository import (
    TracingRepository,
)
from chamba_hunter.services.job_seniority_classification_service import (
    JobSeniorityClassificationService,
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
            "Classify job seniority and explicit "
            "leadership-title signals for geographically "
            "viable job candidates."
        )
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Persist current seniority classifications. "
            "Without this flag the command is read-only."
        ),
    )

    parser.add_argument(
        "--samples-per-class",
        type=int,
        default=8,
        help=(
            "Maximum title samples to print for each "
            "seniority class."
        ),
    )

    parser.add_argument(
        "--unknown-samples",
        type=int,
        default=40,
        help=(
            "Maximum UNKNOWN seniority samples to print."
        ),
    )

    parser.add_argument(
        "--conflict-samples",
        type=int,
        default=40,
        help=(
            "Maximum conflicting title samples to print."
        ),
    )

    args = parser.parse_args()

    for name, value in (
        (
            "--samples-per-class",
            args.samples_per_class,
        ),
        (
            "--unknown-samples",
            args.unknown_samples,
        ),
        (
            "--conflict-samples",
            args.conflict_samples,
        ),
    ):
        if value < 0:
            parser.error(
                f"{name} cannot be negative."
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

    service = JobSeniorityClassificationService(
        repository=JobSeniorityRepository(
            database
        ),
        tracing_repository=TracingRepository(
            database
        ),
    )

    summary = service.run(
        apply=args.apply
    )

    seniority_counts = Counter(
        decision.seniority_class
        for decision in summary.decisions
    )

    leadership_counts = Counter(
        decision.leadership_class
        for decision in summary.decisions
    )

    method_counts = Counter(
        decision.method
        for decision in summary.decisions
    )

    seniority_reason_counts = Counter(
        decision.seniority_reason
        for decision in summary.decisions
    )

    occupation_counts: dict[
        str,
        Counter[str],
    ] = {}

    experience_candidate_count = 0
    experience_signal_count = 0
    experience_min_year_counts: Counter[int] = (
        Counter()
    )

    for decision in summary.decisions:
        occupation = (
            decision.occupation_class
            or "UNCLASSIFIED"
        )

        occupation_counts.setdefault(
            occupation,
            Counter(),
        )[
            decision.seniority_class
        ] += 1

        experience_matches = (
            decision.evidence.get(
                "experience_years_matches",
                [],
            )
        )

        if isinstance(
            experience_matches,
            list,
        ) and experience_matches:
            experience_candidate_count += 1
            experience_signal_count += len(
                experience_matches
            )

            for match in experience_matches:
                if not isinstance(
                    match,
                    dict,
                ):
                    continue

                value = match.get(
                    "min_years"
                )

                if isinstance(value, int):
                    experience_min_year_counts[
                        value
                    ] += 1

    print("Job seniority classification")
    print("----------------------------")
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
        "Candidates:  ",
        summary.total,
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

    print()
    print("SENIORITY CLASSES")
    print("-----------------")

    for seniority_class, count in sorted(
        seniority_counts.items(),
        key=lambda item: (
            -item[1],
            item[0],
        ),
    ):
        percentage = (
            count
            / summary.total
            * 100
            if summary.total
            else 0
        )

        print(
            f"{seniority_class:<12} "
            f"{count:>4} "
            f"{percentage:>6.1f}%"
        )

    print()
    print("LEADERSHIP TITLE CLASSES")
    print("------------------------")

    for leadership_class, count in sorted(
        leadership_counts.items(),
        key=lambda item: (
            -item[1],
            item[0],
        ),
    ):
        print(
            f"{leadership_class:<12} {count}"
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
    print("SENIORITY REASONS")
    print("-----------------")

    for reason, count in sorted(
        seniority_reason_counts.items(),
        key=lambda item: (
            -item[1],
            item[0],
        ),
    ):
        print(
            f"{reason:<32} {count}"
        )

    print()
    print("SENIORITY BY OCCUPATION")
    print("-----------------------")

    seniority_order = (
        "INTERN",
        "ENTRY",
        "JUNIOR",
        "MID",
        "SENIOR",
        "STAFF",
        "PRINCIPAL",
        "LEAD",
        "UNKNOWN",
    )

    for occupation in sorted(
        occupation_counts
    ):
        counts = occupation_counts[
            occupation
        ]
        total = sum(counts.values())

        print(
            f"{occupation} | total={total}"
        )

        parts = [
            f"{seniority}={counts[seniority]}"
            for seniority in seniority_order
            if counts[seniority]
        ]

        print(
            "  "
            + ", ".join(parts)
        )

    print()
    print("EXPLICIT EXPERIENCE-YEAR EVIDENCE")
    print("---------------------------------")
    print(
        "Candidates with evidence:",
        experience_candidate_count,
    )
    print(
        "Evidence snippets:        ",
        experience_signal_count,
    )

    if experience_min_year_counts:
        print(
            "Lower-bound mentions:"
        )

        for years, count in sorted(
            experience_min_year_counts.items()
        ):
            print(
                f"  {years:>2} years | {count}"
            )

    print()
    print("CLASS SAMPLES")
    print("-------------")

    for seniority_class in seniority_order:
        if seniority_class == "UNKNOWN":
            continue

        matching = [
            decision
            for decision in summary.decisions
            if decision.seniority_class
            == seniority_class
        ]

        if not matching:
            continue

        print()
        print(
            seniority_class
        )

        for decision in matching[
            :args.samples_per_class
        ]:
            print(
                _format_decision(
                    decision
                )
            )

    conflicts = [
        decision
        for decision in summary.decisions
        if decision.seniority_reason
        in {
            "TITLE_CONFLICT",
            "DESCRIPTION_CONFLICT",
        }
    ]

    print()
    print("CONFLICT SAMPLES")
    print("----------------")

    if not conflicts:
        print("None.")
    else:
        for decision in conflicts[
            :args.conflict_samples
        ]:
            print(
                _format_decision(
                    decision
                )
            )
            print(
                "  title classes:",
                decision.evidence.get(
                    "title_seniority_classes",
                    [],
                ),
            )

    unknowns = [
        decision
        for decision in summary.decisions
        if decision.seniority_class
        == "UNKNOWN"
    ]

    unknowns.sort(
        key=lambda decision: (
            0
            if decision.occupation_class
            == "SOFTWARE_ENGINEERING"
            else 1,
            0
            if decision.occupation_class
            == "IT_TECHNICAL"
            else 1,
            decision.record_kind,
            decision.record_id,
        )
    )

    print()
    print("UNKNOWN SAMPLES")
    print("---------------")

    if not unknowns:
        print("None.")
    else:
        for decision in unknowns[
            :args.unknown_samples
        ]:
            print(
                _format_decision(
                    decision
                )
            )


def _format_decision(
    decision,
) -> str:
    return (
        f"{decision.record_kind} "
        f"{decision.record_id} | "
        f"{decision.origin} | "
        f"{decision.company_name} | "
        f"{decision.occupation_class or 'UNCLASSIFIED'} | "
        f"{decision.leadership_class} | "
        f"{decision.title}"
    )


if __name__ == "__main__":
    main()
