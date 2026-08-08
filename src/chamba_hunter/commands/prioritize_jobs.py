import argparse
from collections import Counter, defaultdict
from pathlib import Path
import sys

from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate
from chamba_hunter.repositories.job_freshness_repository import (
    JobFreshnessRepository,
)
from chamba_hunter.repositories.job_operational_priority_repository import (
    JobOperationalPriorityRepository,
)
from chamba_hunter.repositories.tracing_repository import (
    TracingRepository,
)
from chamba_hunter.services.job_operational_priority_service import (
    JobOperationalPriorityService,
    PROFILE_NAME,
    RULE_VERSION,
    operational_sort_key,
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
            "Evaluate operational/application "
            "priority for the current backend "
            "software search profile."
        )
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Apply migrations, initialize missing "
            "content-hash baselines, and persist "
            "current operational priority state. "
            "Without this flag the command is read-only."
        ),
    )

    parser.add_argument(
        "--top",
        type=int,
        default=100,
        help=(
            "Maximum operationally ranked candidates "
            "to print."
        ),
    )

    parser.add_argument(
        "--database",
        type=Path,
        default=None,
        help=(
            "Optional SQLite database path. "
            "Primarily useful for isolated validation."
        ),
    )

    args = parser.parse_args()

    if args.top < 0:
        parser.error(
            "--top cannot be negative."
        )

    database = (
        Database(args.database)
        if args.database
        is not None
        else Database()
    )

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

    priority_repository = (
        JobOperationalPriorityRepository(
            database
        )
    )

    freshness_repository = (
        JobFreshnessRepository(
            database
        )
    )

    service = JobOperationalPriorityService(
        repository=priority_repository,
        freshness_repository=(
            freshness_repository
        ),
        tracing_repository=(
            TracingRepository(
                database
            )
        ),
    )

    summary = service.run(
        apply=args.apply
    )

    state_counts = Counter(
        decision.operational_state
        for decision in summary.decisions
    )

    channel_counts = Counter(
        decision.application_channel
        for decision in summary.decisions
    )

    state_by_level = defaultdict(
        Counter
    )

    for decision in summary.decisions:
        state_by_level[
            decision.professional_match_level
        ][
            decision.operational_state
        ] += 1

    ranked = sorted(
        summary.decisions,
        key=operational_sort_key,
    )

    print(
        "Operational / application priority"
    )
    print(
        "----------------------------------"
    )
    print(
        "Rule version:  ",
        RULE_VERSION,
    )
    print(
        "Search profile:",
        PROFILE_NAME,
    )
    print(
        "Mode:          ",
        (
            "APPLY"
            if args.apply
            else "DRY RUN"
        ),
    )
    print(
        "Database:      ",
        database.path,
    )
    print(
        "Candidates:    ",
        summary.total,
    )
    print(
        "Watermark:     ",
        (
            summary.previous_watermark
            .isoformat()
            if summary.previous_watermark
            is not None
            else "<INITIAL BASELINE>"
        ),
    )

    if args.apply:
        baseline = (
            summary.freshness_baseline
        )

        print(
            "Created:       ",
            summary.created,
        )
        print(
            "Updated:       ",
            summary.updated,
        )
        print(
            "Run id:        ",
            summary.run_id,
        )
        print(
            "Profile id:    ",
            summary.search_profile_id,
        )
        print(
            "Hash baseline jobs:",
            (
                baseline.jobs_initialized
                if baseline is not None
                else 0
            ),
        )
        print(
            "Hash baseline leads:",
            (
                baseline.leads_initialized
                if baseline is not None
                else 0
            ),
        )
    else:
        print(
            "Freshness schema:",
            (
                "AVAILABLE"
                if freshness_repository
                .schema_available()
                else "NOT YET APPLIED"
            ),
        )
        print(
            "Priority schema: ",
            (
                "AVAILABLE"
                if priority_repository
                .priority_schema_available()
                else "NOT YET APPLIED"
            ),
        )

    print()
    print("OPERATIONAL STATES")
    print("------------------")

    for state in [
        "NEW",
        "UPDATED",
        "KNOWN",
        "INACTIVE",
        "SUPERSEDED",
        "OUT_OF_SCOPE",
    ]:
        print(
            f"{state:<14} "
            f"{state_counts[state]:>4}"
        )

    print()
    print("STATES BY MATCH LEVEL")
    print("---------------------")

    for level in [
        "VERY_HIGH",
        "HIGH",
        "MEDIUM",
        "LOW",
    ]:
        counts = state_by_level[
            level
        ]

        rendered = ", ".join(
            f"{state}={counts[state]}"
            for state in [
                "NEW",
                "UPDATED",
                "KNOWN",
                "INACTIVE",
                "SUPERSEDED",
                "OUT_OF_SCOPE",
            ]
            if counts[state]
        )

        print(
            f"{level:<12} "
            f"{rendered or '<none>'}"
        )

    print()
    print("APPLICATION CHANNELS")
    print("--------------------")

    for channel in [
        "DIRECT_APPLY_URL",
        "JOB_URL",
        "GENERAL_APPLICATION_URL",
        "PUBLIC_CONTACT",
        "NONE",
    ]:
        print(
            f"{channel:<26} "
            f"{channel_counts[channel]}"
        )

    print()
    print("NEW / UPDATED")
    print("-------------")

    changed = [
        decision
        for decision in ranked
        if decision.operational_state
        in {
            "NEW",
            "UPDATED",
        }
    ]

    if not changed:
        print("None.")
    else:
        for decision in changed[:100]:
            print(
                f"{decision.professional_score:>5.1f} "
                f"{decision.professional_match_level:<9} | "
                f"{decision.operational_state:<7} | "
                f"{decision.record_kind} "
                f"{decision.record_id} | "
                f"{decision.company_name} | "
                f"{decision.title}"
            )
            print(
                "      channel=",
                decision.application_channel,
                "| first_seen=",
                decision
                .first_seen_at
                .isoformat(),
                "| changed=",
                (
                    decision
                    .last_changed_at
                    .isoformat()
                    if decision
                    .last_changed_at
                    is not None
                    else "<none>"
                ),
            )

    print()
    print("NON-ACTIONABLE RETAINED STATE")
    print("-----------------------------")

    non_actionable = [
        decision
        for decision in ranked
        if not decision.actionable
    ]

    if not non_actionable:
        print("None.")
    else:
        for decision in (
            non_actionable[:100]
        ):
            print(
                f"{decision.professional_score:>5.1f} "
                f"{decision.professional_match_level:<9} | "
                f"{decision.operational_state:<12} | "
                f"{decision.record_kind} "
                f"{decision.record_id} | "
                f"{decision.company_name} | "
                f"{decision.title}"
            )

    print()
    print("TOP OPERATIONAL PRIORITY")
    print("------------------------")

    for index, decision in enumerate(
        ranked[:args.top],
        start=1,
    ):
        print(
            f"{index:>3}. "
            f"{decision.professional_score:>5.1f} "
            f"{decision.professional_match_level:<9} | "
            f"{decision.operational_state:<12} | "
            f"{decision.application_channel:<22} | "
            f"{decision.record_kind} "
            f"{decision.record_id} | "
            f"{decision.company_name} | "
            f"{decision.title}"
        )

        print(
            "     first_seen=",
            decision
            .first_seen_at
            .isoformat(),
            "| last_changed=",
            (
                decision
                .last_changed_at
                .isoformat()
                if decision
                .last_changed_at
                is not None
                else "<none>"
            ),
        )

        print(
            "     target=",
            (
                decision.application_target
                or "<none>"
            ),
        )


if __name__ == "__main__":
    main()
