import argparse
from pathlib import Path

from chamba_hunter.db.connection import DEFAULT_DB_PATH, Database
from chamba_hunter.services.pipeline_snapshot_service import inspect_pipeline_snapshots
from chamba_hunter.services.search_profile_registry import (
    DEFAULT_PROFILE_NAME,
    ROLLOUT_PROFILE_NAMES,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Strictly read-only classification/matching/priority preflight."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument(
        "--profile",
        choices=ROLLOUT_PROFILE_NAMES,
        default=DEFAULT_PROFILE_NAME,
    )
    args = parser.parse_args()
    if not args.db.exists():
        parser.error(f"Database does not exist: {args.db}")

    report = inspect_pipeline_snapshots(
        Database(args.db, read_only=True),
        args.profile,
    )
    print("Pipeline snapshot audit (strictly read-only)")
    print("--------------------------------------------")
    print(f"Profile:           {report.profile_name}")
    print(f"Scoped candidates: {report.scoped_candidates}")
    if not report.issues:
        print("Status:            COMPLETE")
        return
    print("Status:            INCOMPLETE/WARNINGS")
    for issue in report.issues:
        print(
            f"{issue.severity:<7} {issue.code:<38} "
            f"count={issue.count} | {issue.detail}"
        )


if __name__ == "__main__":
    main()
