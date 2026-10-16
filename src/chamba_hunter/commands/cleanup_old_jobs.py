import argparse
from pathlib import Path

from chamba_hunter.db.connection import DEFAULT_DB_PATH, Database
from chamba_hunter.repositories.job_retention_repository import JobRetentionRepository
from chamba_hunter.services.job_retention_service import (
    JobRetentionService,
    PHYSICAL_RETENTION_DAYS,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Safely preview or delete inactive, unreferenced job records "
            f"older than {PHYSICAL_RETENTION_DAYS} days."
        )
    )
    parser.add_argument("--database", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete eligible records. Default is a read-only dry-run.",
    )
    args = parser.parse_args()

    if not args.database.exists():
        parser.error(f"Database does not exist: {args.database}")

    database = Database(args.database, read_only=not args.apply)
    summary = JobRetentionService(
        JobRetentionRepository(database)
    ).run(apply=args.apply)

    print("Job retention cleanup")
    print("---------------------")
    print(f"Mode:       {'APPLY' if args.apply else 'DRY RUN'}")
    print(f"Database:   {args.database.resolve()}")
    print(f"Age policy: published_at, else first_seen_at, > {PHYSICAL_RETENTION_DAYS} days")
    print(f"Candidates: {len(summary.candidates)}")
    print(f"Deletable:  {len(summary.deletable)}")
    print(f"Protected:  {len(summary.protected)}")

    if summary.protection_counts:
        print("Protection reasons:")
        for reason, count in summary.protection_counts.items():
            print(f"  {reason:<32} {count}")

    print("Deleted ATS jobs:             ", summary.deleted.ats_jobs)
    print("Deleted broad job leads:      ", summary.deleted.job_leads)
    print("Deleted classification rows:  ", summary.deleted.classification_rows)

    if not args.apply:
        print("DRY RUN: no records were deleted. Use --apply only after review.")


if __name__ == "__main__":
    main()
