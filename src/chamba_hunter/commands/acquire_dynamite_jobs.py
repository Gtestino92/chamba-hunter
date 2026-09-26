import argparse

from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate
from chamba_hunter.repositories.company_repository import (
    CompanyRepository,
)
from chamba_hunter.repositories.company_source_repository import (
    CompanySourceRepository,
)
from chamba_hunter.repositories.job_ats_hint_repository import (
    JobAtsHintRepository,
)
from chamba_hunter.repositories.job_lead_repository import (
    JobLeadRepository,
)
from chamba_hunter.repositories.source_acquisition_state_repository import (
    SourceAcquisitionStateRepository,
)
from chamba_hunter.repositories.tracing_repository import (
    TracingRepository,
)
from chamba_hunter.services.company_import_service import (
    CompanyImportService,
)
from chamba_hunter.services.dynamitejobs_job_acquisition_service import (
    DynamiteJobsJobAcquisitionService,
)
from chamba_hunter.sources.dynamitejobs import (
    DEFAULT_DYNAMITE_DETAIL_WORKERS,
    DEFAULT_DYNAMITE_MAX_JOBS,
    DYNAMITEJOBS_INDEX_URLS,
    DynamiteJobsClient,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Preview or acquire Dynamite Jobs "
            "remote backend/full-stack job leads."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Persist companies, job leads, ATS "
            "hints, tracing, and source state. "
            "Omit for a non-mutating preview."
        ),
    )
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=DEFAULT_DYNAMITE_MAX_JOBS,
        help=(
            "Maximum unique Dynamite detail "
            "jobs to fetch. Range 1-"
            f"{DEFAULT_DYNAMITE_MAX_JOBS}. "
            f"Defaults to {DEFAULT_DYNAMITE_MAX_JOBS}."
        ),
    )
    parser.add_argument(
        "--detail-workers",
        type=int,
        default=DEFAULT_DYNAMITE_DETAIL_WORKERS,
        help=(
            "Bounded concurrent detail workers. "
            "Range 1-"
            f"{DEFAULT_DYNAMITE_DETAIL_WORKERS}. "
            "Defaults to "
            f"{DEFAULT_DYNAMITE_DETAIL_WORKERS}."
        ),
    )

    args = parser.parse_args()

    if not 1 <= args.max_jobs <= DEFAULT_DYNAMITE_MAX_JOBS:
        parser.error(
            "--max-jobs must be between 1 and "
            f"{DEFAULT_DYNAMITE_MAX_JOBS}"
        )

    if (
        not 1
        <= args.detail_workers
        <= DEFAULT_DYNAMITE_DETAIL_WORKERS
    ):
        parser.error(
            "--detail-workers must be between "
            "1 and "
            f"{DEFAULT_DYNAMITE_DETAIL_WORKERS}"
        )

    client = DynamiteJobsClient()

    if args.apply:
        database = Database()
        applied = migrate(database)

        if applied:
            for migration in applied:
                print(
                    f"Applied migration: "
                    f"{migration}"
                )

            print()

        company_repository = (
            CompanyRepository(database)
        )
        company_source_repository = (
            CompanySourceRepository(database)
        )
        service = (
            DynamiteJobsJobAcquisitionService(
                client=client,
                company_import_service=(
                    CompanyImportService(
                        company_repository,
                        company_source_repository,
                    )
                ),
                job_lead_repository=(
                    JobLeadRepository(database)
                ),
                ats_hint_repository=(
                    JobAtsHintRepository(database)
                ),
                tracing_repository=(
                    TracingRepository(database)
                ),
                state_repository=(
                    SourceAcquisitionStateRepository(
                        database
                    )
                ),
            )
        )

        print(
            "Dynamite Jobs acquisition APPLY"
        )
    else:
        service = (
            DynamiteJobsJobAcquisitionService(
                client=client
            )
        )

        print(
            "Dynamite Jobs acquisition preview"
        )
        print(
            "Preview is non-mutating: no "
            "database connection or migration "
            "is opened."
        )

    print("-------------------------------")
    print("Configured index pages:")

    for url in DYNAMITEJOBS_INDEX_URLS:
        print(f"  - {url}")

    print()
    print(f"max jobs:       {args.max_jobs}")
    print(
        f"detail workers: {args.detail_workers}"
    )
    print()

    if args.apply:
        summary = service.run(
            max_jobs=args.max_jobs,
            detail_workers=(
                args.detail_workers
            ),
        )
    else:
        summary = service.preview(
            max_jobs=args.max_jobs,
            detail_workers=(
                args.detail_workers
            ),
        )

    print("Dynamite Jobs acquisition result")
    print("--------------------------------")
    print(
        "mode:                 "
        + (
            "APPLY"
            if summary.applied
            else "PREVIEW"
        )
    )
    print(
        f"index pages fetched:  "
        f"{summary.index_pages_fetched}"
    )
    print(
        f"links discovered:     "
        f"{summary.links_discovered}"
    )
    print(
        f"unique jobs:          "
        f"{summary.unique_jobs}"
    )
    print(
        f"duplicates removed:   "
        f"{summary.duplicates_removed}"
    )
    print(
        f"details attempted:    "
        f"{summary.details_attempted}"
    )
    print(
        f"details fetched:      "
        f"{summary.details_succeeded}"
    )
    print(
        f"detail failures:      "
        f"{summary.details_failed}"
    )
    print(
        f"closed skipped:       "
        f"{summary.closed_skipped}"
    )
    print(
        f"parse failures:       "
        f"{summary.parse_failures}"
    )
    print(
        f"normalized jobs:      "
        f"{summary.normalized}"
    )
    print(
        f"unique companies:     "
        f"{summary.unique_companies}"
    )
    print(
        f"ATS hints detected:   "
        f"{summary.ats_hints_detected}"
    )

    if summary.applied:
        print(
            f"run id:               "
            f"{summary.run_id}"
        )
        print(
            f"companies created:    "
            f"{summary.companies_created}"
        )
        print(
            f"companies existing:   "
            f"{summary.companies_existing}"
        )
        print(
            f"jobs created:         "
            f"{summary.jobs_created}"
        )
        print(
            f"jobs updated:         "
            f"{summary.jobs_updated}"
        )
        print(
            f"ATS hints created:    "
            f"{summary.ats_hints_created}"
        )
    else:
        print()
        print(
            "No companies, company_sources, "
            "job_leads, job_ats_hints, runs, "
            "run_steps, or source acquisition "
            "state were written."
        )


if __name__ == "__main__":
    main()
