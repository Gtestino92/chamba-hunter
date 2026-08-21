import argparse

from chamba_hunter.db.connection import (
    Database,
)
from chamba_hunter.db.migrations import (
    migrate,
)
from chamba_hunter.repositories.company_repository import (
    CompanyRepository,
)
from chamba_hunter.repositories.company_source_repository import (
    CompanySourceRepository,
)
from chamba_hunter.repositories.job_lead_repository import (
    JobLeadRepository,
)
from chamba_hunter.repositories.source_acquisition_state_repository import (
    SourceAcquisitionStateRepository,
)
from chamba_hunter.services.company_import_service import (
    CompanyImportService,
)
from chamba_hunter.services.himalayas_incremental_acquisition_service import (
    DEFAULT_BACKFILL_DAYS,
    DEFAULT_OVERLAP_HOURS,
    HimalayasIncrementalAcquisitionService,
)
from chamba_hunter.sources.himalayas_incremental_jobs import (
    HimalayasIncrementalJobsClient,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Acquire Argentina-compatible "
            "Himalayas jobs using a temporal "
            "backfill/incremental window."
        )
    )

    parser.add_argument(
        "--backfill-days",
        type=int,
        default=DEFAULT_BACKFILL_DAYS,
        help=(
            "Maximum historical window. "
            "Defaults to 30 days."
        ),
    )

    parser.add_argument(
        "--overlap-hours",
        type=int,
        default=DEFAULT_OVERLAP_HOURS,
        help=(
            "Overlap before the previous "
            "successful source run. "
            "Defaults to 48 hours."
        ),
    )

    args = parser.parse_args()

    if args.backfill_days < 1:
        parser.error(
            "--backfill-days must be "
            "at least 1."
        )

    if args.overlap_hours < 0:
        parser.error(
            "--overlap-hours cannot "
            "be negative."
        )

    database = Database()

    applied = migrate(
        database
    )

    if applied:
        for migration in applied:
            print(
                "Applied migration:",
                migration,
            )

        print()

    company_repository = (
        CompanyRepository(
            database
        )
    )

    company_source_repository = (
        CompanySourceRepository(
            database
        )
    )

    company_import_service = (
        CompanyImportService(
            company_repository,
            company_source_repository,
        )
    )

    service = (
        HimalayasIncrementalAcquisitionService(
            client=(
                HimalayasIncrementalJobsClient()
            ),
            company_import_service=(
                company_import_service
            ),
            job_lead_repository=(
                JobLeadRepository(
                    database
                )
            ),
            state_repository=(
                SourceAcquisitionStateRepository(
                    database
                )
            ),
        )
    )

    summary = service.run(
        backfill_days=(
            args.backfill_days
        ),
        overlap_hours=(
            args.overlap_hours
        ),
    )

    print(
        "Himalayas incremental acquisition"
    )
    print(
        "---------------------------------"
    )
    print(
        "Mode:              ",
        summary.mode,
    )
    print(
        "Started:           ",
        summary.started_at.isoformat(),
    )
    print(
        "Finished:          ",
        summary.finished_at.isoformat(),
    )
    print(
        "Cutoff:            ",
        summary.cutoff.isoformat(),
    )
    print(
        "Total available:   ",
        summary.total_available,
    )
    print(
        "Requests:          ",
        summary.requests_made,
    )
    print(
        "Pages:             ",
        summary.pages_fetched,
    )
    print(
        "Cutoff reached:    ",
        summary.cutoff_reached,
    )
    print(
        "Received in window:",
        summary.received,
    )
    print(
        "Old skipped:       ",
        summary.old_jobs_skipped,
    )
    print(
        "Undated kept:      ",
        summary.undated_jobs_kept,
    )
    print(
        "Normalized:        ",
        summary.normalized,
    )
    print(
        "Skipped malformed: ",
        summary.skipped,
    )
    print(
        "Companies created: ",
        summary.companies_created,
    )
    print(
        "Companies existing:",
        summary.companies_existing,
    )
    print(
        "Jobs created:      ",
        summary.jobs_created,
    )
    print(
        "Jobs updated:      ",
        summary.jobs_updated,
    )


if __name__ == "__main__":
    main()
