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
            args.database
        )
        if args.database
        is not None
        else Database()
    )

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

    print("Chamba Hunter shortlist export")
    print("-----------------------------")
    print(
        "Report version: ",
        REPORT_VERSION,
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
