import argparse

from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate
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
from chamba_hunter.repositories.tracing_repository import (
    TracingRepository,
)
from chamba_hunter.services.company_import_service import (
    CompanyImportService,
)
from chamba_hunter.services.remotive_job_acquisition_service import (
    RemotiveJobAcquisitionService,
)
from chamba_hunter.sources.remotive_jobs import (
    DEFAULT_REMOTIVE_MAX_JOBS,
    MAX_REMOTIVE_MAX_JOBS,
    REMOTIVE_REMOTE_JOBS_URL,
    REMOTIVE_TARGET_CATEGORIES,
    RemotiveJobsClient,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Preview or acquire Remotive software/"
            "DevOps remote job leads via the "
            "official public API."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Persist companies, job leads, "
            "tracing, and source state. Omit "
            "for a non-mutating preview."
        ),
    )
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=DEFAULT_REMOTIVE_MAX_JOBS,
        help=(
            "Maximum Remotive jobs to retain "
            "after local category, geography, "
            "and dedup filtering. Range 1-"
            f"{MAX_REMOTIVE_MAX_JOBS}. Defaults "
            f"to {DEFAULT_REMOTIVE_MAX_JOBS}."
        ),
    )

    args = parser.parse_args()

    if not 1 <= args.max_jobs <= MAX_REMOTIVE_MAX_JOBS:
        parser.error(
            "--max-jobs must be between 1 and "
            f"{MAX_REMOTIVE_MAX_JOBS}"
        )

    client = RemotiveJobsClient()

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
            RemotiveJobAcquisitionService(
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

        print("Remotive acquisition APPLY")
    else:
        service = (
            RemotiveJobAcquisitionService(
                client=client
            )
        )

        print("Remotive acquisition preview")
        print(
            "Preview is non-mutating: no "
            "database connection or migration "
            "is opened."
        )

    print("-----------------------------")
    print(
        f"endpoint: {REMOTIVE_REMOTE_JOBS_URL}"
    )
    print("target categories:")

    for category in REMOTIVE_TARGET_CATEGORIES:
        print(f"  - {category}")

    print()
    print(f"max jobs: {args.max_jobs}")
    print()

    if args.apply:
        summary = service.run(
            max_jobs=args.max_jobs
        )
    else:
        summary = service.preview(
            max_jobs=args.max_jobs
        )

    print("Remotive acquisition result")
    print("---------------------------")
    print(
        "mode:                         "
        + (
            "APPLY"
            if summary.applied
            else "PREVIEW"
        )
    )
    print(
        f"endpoint:                     {summary.endpoint}"
    )
    print(
        f"requests made:                {summary.requests_made:5d}"
    )
    print(
        "jobs reported by API:         "
        f"{summary.jobs_reported_by_api:5d}"
    )
    print(
        f"jobs parsed:                  {summary.jobs_parsed:5d}"
    )
    print(
        f"duplicates removed:           {summary.duplicates_removed:5d}"
    )
    print(
        f"category rejects:             {summary.category_rejects:5d}"
    )
    print(
        f"category candidates:          {summary.category_candidates:5d}"
    )
    print(
        f"explicit geo rejects:         {summary.explicit_geo_rejects:5d}"
    )
    print(
        f"unknown geography:            {summary.unknown_geography:5d}"
    )
    print(
        f"potentially eligible:         {summary.potentially_eligible:5d}"
    )
    print(
        "selected after max-jobs:      "
        f"{summary.selected_after_max_jobs:5d}"
    )
    print(
        f"normalized jobs:              {summary.normalized_jobs:5d}"
    )
    print(
        f"unique companies:             {summary.unique_companies:5d}"
    )
    print(
        "publication dates parsed:     "
        f"{summary.publication_dates_parsed:5d}"
    )
    print(
        "publication dates missing:    "
        f"{summary.publication_dates_missing:5d}"
    )
    print(
        f"ATS hints detected:           {summary.ats_hints_detected:5d}"
    )

    if summary.retained_categories:
        print()
        print("retained categories:")

        for category, count in sorted(
            summary.retained_categories.items()
        ):
            print(f"  - {category}: {count}")

    if summary.applied:
        print()
        print(f"run id:                       {summary.run_id}")
        print(
            f"companies created:            {summary.companies_created:5d}"
        )
        print(
            f"companies existing:           {summary.companies_existing:5d}"
        )
        print(
            f"jobs created:                 {summary.jobs_created:5d}"
        )
        print(
            f"jobs updated:                 {summary.jobs_updated:5d}"
        )
    else:
        print()
        print(
            "No companies, company_sources, "
            "job_leads, runs, run_steps, or "
            "source acquisition state were "
            "written."
        )


if __name__ == "__main__":
    main()
