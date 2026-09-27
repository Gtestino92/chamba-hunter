import argparse
from pathlib import Path

from chamba_hunter.db.connection import DEFAULT_DB_PATH
from chamba_hunter.services.retired_source_cleanup_service import (
    LEAD_DERIVED_TABLES,
    RETIRED_SOURCE_TYPES,
    RetiredSourceCleanupPlan,
    RetiredSourceCleanupService,
    open_cleanup_connection,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Preview or apply safe persisted-data cleanup for "
            "retired broad sources REMOTECO, REMOTIVE, and "
            "REMOTEOK. Dynamite Jobs is intentionally preserved."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Delete retired-source persisted data. Omit for "
            "read-only preview."
        ),
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=(
            "SQLite database path. Defaults to data/chamba-hunter.db."
        ),
    )

    args = parser.parse_args()

    connection = open_cleanup_connection(
        args.database,
        read_only=not args.apply,
    )
    try:
        service = RetiredSourceCleanupService(connection)
        if args.apply:
            plan = service.apply()
            print("Retired source cleanup APPLY")
            print("----------------------------")
            print_cleanup_plan(plan)
            print()
            print("Cleanup committed.")
        else:
            plan = service.build_plan()
            print("Retired source cleanup preview")
            print("------------------------------")
            print_cleanup_plan(plan)
            print()
            print("No data was modified.")
    finally:
        connection.close()


def print_cleanup_plan(
    plan: RetiredSourceCleanupPlan,
) -> None:
    print()
    for source_count in plan.source_counts:
        print(source_count.source_type)
        print(f"  job leads: {source_count.job_leads}")
        print(
            "  canonicalized leads: "
            f"{source_count.canonicalized_leads}"
        )
        print(
            "  current/unmatched leads: "
            f"{source_count.current_unmatched_leads}"
        )
        print()

    print("Derived records that would be removed:")
    for table in LEAD_DERIVED_TABLES:
        print(f"  {table}: {plan.lead_derived_counts[table]}")
    print(f"  job_ats_hints (FK cascade): {plan.job_ats_hints}")
    print()

    print(
        "Source acquisition state rows: "
        f"{plan.source_acquisition_states}"
    )
    print(
        "Tracked applications referencing target leads: "
        f"{plan.applications}"
    )
    print(
        "Company source evidence rows: "
        f"{plan.company_sources}"
    )
    print()

    print(f"Companies touched: {plan.companies.touched}")
    print(
        "Companies that would become safely orphaned: "
        f"{plan.companies.safe_orphans}"
    )
    print(
        "Companies preserved because referenced elsewhere: "
        f"{plan.companies.preserved}"
    )
    print()

    print(
        "Tracing runs/run_steps attributable exclusively to "
        "retired acquisition commands:"
    )
    print(f"  runs: {plan.source_specific_runs}")
    print(f"  run_steps (FK cascade): {plan.source_specific_run_steps}")
    print()

    print("Target source types:")
    for source_type in RETIRED_SOURCE_TYPES:
        print(f"  - {source_type}")
    print("Preserved source type:")
    print("  - DYNAMITEJOBS")


if __name__ == "__main__":
    main()
