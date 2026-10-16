import argparse
from pathlib import Path
import sys

from chamba_hunter.db.connection import Database
from chamba_hunter.repositories.job_shortlist_report_repository import (
    JobShortlistReportRepository,
)
from chamba_hunter.services.job_shortlist_report_service import (
    DEFAULT_PROFILE_NAME,
    REPORT_VERSION,
    export_shortlist,
)
from chamba_hunter.services.openoffice_shortlist_actions import (
    OPENOFFICE_ACTIONS_VERSION,
    add_openoffice_application_actions,
)
from chamba_hunter.services.pipeline_snapshot_service import (
    inspect_pipeline_snapshots,
    require_complete,
)
from chamba_hunter.services.search_profile_registry import (
    ROLLOUT_PROFILE_NAMES,
)


DEFAULT_OUTPUT = Path(
    "output/chamba-shortlist.xlsx"
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
            "Export the persisted Chamba Hunter "
            "operational shortlist to XLSX."
        )
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=(
            "Output XLSX path. "
            "Default: output/chamba-shortlist.xlsx"
        ),
    )

    parser.add_argument(
        "--profile",
        choices=ROLLOUT_PROFILE_NAMES,
        default=DEFAULT_PROFILE_NAME,
        help=(
            "Search profile to export. "
            f"Default: {DEFAULT_PROFILE_NAME}"
        ),
    )

    parser.add_argument(
        "--database",
        type=Path,
        default=None,
        help=(
            "Optional SQLite database path. "
            "Default: project database."
        ),
    )

    args = parser.parse_args()

    database = (
        Database(
            args.database,
            read_only=True,
        )
        if args.database
        is not None
        else Database(read_only=True)
    )

    preflight = inspect_pipeline_snapshots(database, args.profile)
    for issue in preflight.issues:
        print(f"Preflight {issue.severity}: {issue.code}={issue.count} - {issue.detail}")
    if args.profile != DEFAULT_PROFILE_NAME:
        require_complete(preflight, "shortlist export")

    repository = (
        JobShortlistReportRepository(
            database
        )
    )

    summary = export_shortlist(
        repository=repository,
        output_path=args.output,
        profile_name=args.profile,
    )

    action_count = (
        add_openoffice_application_actions(
            args.output
        )
    )

    print("Chamba Hunter shortlist export")
    print("-----------------------------")
    print(
        "Report version: ",
        REPORT_VERSION,
    )
    print(
        "OpenOffice:     ",
        OPENOFFICE_ACTIONS_VERSION,
    )
    print(
        "APPLY links:    ",
        action_count,
    )
    print(
        "Profile:        ",
        summary.source.profile_name,
    )
    print(
        "Priority run:   ",
        summary.source.priority_run_id,
    )
    print(
        "Output:         ",
        args.output.resolve(),
    )
    print()
    print(
        "Focus:          ",
        len(
            summary.focus
        ),
    )
    print(
        "High Value:     ",
        len(
            summary.high_value
        ),
    )
    print(
        "All Current:    ",
        len(
            summary.all_current
        ),
    )
    print(
        "History:        ",
        len(
            summary.history
        ),
    )


if __name__ == "__main__":
    main()
