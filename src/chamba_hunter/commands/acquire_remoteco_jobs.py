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
from chamba_hunter.services.remoteco_job_acquisition_service import (
    RemoteCoJobAcquisitionService,
)
from chamba_hunter.sources.remoteco import (
    DEFAULT_REMOTECO_DETAIL_WORKERS,
    DEFAULT_REMOTECO_MAX_JOBS,
    DEFAULT_REMOTECO_MAX_PAGES_PER_CATEGORY,
    MAX_REMOTECO_DETAIL_WORKERS,
    MAX_REMOTECO_MAX_JOBS,
    MAX_REMOTECO_MAX_PAGES_PER_CATEGORY,
    REMOTECO_CATEGORY_URLS,
    RemoteCoClient,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Preview or acquire Remote.co "
            "backend/java/software/full-stack "
            "job leads with source-side geo "
            "prefiltering."
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
        "--max-pages-per-category",
        type=int,
        default=(
            DEFAULT_REMOTECO_MAX_PAGES_PER_CATEGORY
        ),
        help=(
            "Maximum category pages to fetch per "
            "Remote.co category. Range 1-"
            f"{MAX_REMOTECO_MAX_PAGES_PER_CATEGORY}. "
            "Defaults to "
            f"{DEFAULT_REMOTECO_MAX_PAGES_PER_CATEGORY}."
        ),
    )
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=DEFAULT_REMOTECO_MAX_JOBS,
        help=(
            "Maximum unique Remote.co detail "
            "jobs to fetch. Range 1-"
            f"{MAX_REMOTECO_MAX_JOBS}. "
            f"Defaults to {DEFAULT_REMOTECO_MAX_JOBS}."
        ),
    )
    parser.add_argument(
        "--detail-workers",
        type=int,
        default=DEFAULT_REMOTECO_DETAIL_WORKERS,
        help=(
            "Bounded concurrent detail workers. "
            "Range 1-"
            f"{MAX_REMOTECO_DETAIL_WORKERS}. "
            "Defaults to "
            f"{DEFAULT_REMOTECO_DETAIL_WORKERS}."
        ),
    )

    args = parser.parse_args()

    if not (
        1
        <= args.max_pages_per_category
        <= MAX_REMOTECO_MAX_PAGES_PER_CATEGORY
    ):
        parser.error(
            "--max-pages-per-category must be "
            "between 1 and "
            f"{MAX_REMOTECO_MAX_PAGES_PER_CATEGORY}"
        )

    if not 1 <= args.max_jobs <= MAX_REMOTECO_MAX_JOBS:
        parser.error(
            "--max-jobs must be between 1 and "
            f"{MAX_REMOTECO_MAX_JOBS}"
        )

    if not (
        1
        <= args.detail_workers
        <= MAX_REMOTECO_DETAIL_WORKERS
    ):
        parser.error(
            "--detail-workers must be between 1 "
            "and "
            f"{MAX_REMOTECO_DETAIL_WORKERS}"
        )

    client = RemoteCoClient()

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
            RemoteCoJobAcquisitionService(
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

        print("Remote.co acquisition APPLY")
    else:
        service = (
            RemoteCoJobAcquisitionService(
                client=client
            )
        )

        print("Remote.co acquisition preview")
        print(
            "Preview is non-mutating: no "
            "database connection or migration "
            "is opened."
        )

    print("-----------------------------")
    print("Configured categories:")

    for url in REMOTECO_CATEGORY_URLS:
        print(f"  - {url}")

    print()
    print(
        "max pages/category: "
        f"{args.max_pages_per_category}"
    )
    print(f"max jobs:           {args.max_jobs}")
    print(
        f"detail workers:     {args.detail_workers}"
    )
    print()

    if args.apply:
        summary = service.run(
            max_pages_per_category=(
                args.max_pages_per_category
            ),
            max_jobs=args.max_jobs,
            detail_workers=args.detail_workers,
        )
    else:
        summary = service.preview(
            max_pages_per_category=(
                args.max_pages_per_category
            ),
            max_jobs=args.max_jobs,
            detail_workers=args.detail_workers,
        )

    print("Remote.co acquisition result")
    print("----------------------------")
    print(
        "mode:                 "
        + (
            "APPLY"
            if summary.applied
            else "PREVIEW"
        )
    )
    print(
        f"categories configured:{summary.categories_configured:5d}"
    )
    print(
        f"pages fetched:        {summary.pages_fetched:5d}"
    )
    print(
        f"listing rows:         {summary.listing_rows:5d}"
    )
    print(
        "listing locations:    "
        f"{summary.listing_locations_found:5d}"
    )
    print(
        "missing locations:    "
        f"{summary.listing_locations_missing:5d}"
    )
    print(
        f"unique jobs:          {summary.unique_jobs:5d}"
    )
    print(
        f"duplicates removed:   {summary.duplicates_removed:5d}"
    )
    print(
        f"explicit geo rejects: {summary.explicit_geo_rejects:5d}"
    )
    print(
        f"remote-level rejects: {summary.remote_level_rejects:5d}"
    )
    print(
        "international rejects:"
        f" {summary.international_non_tech_rejects:5d}"
    )
    print(
        f"unknown geography:    {summary.unknown_geography:5d}"
    )
    print(
        f"potentially eligible: {summary.potentially_eligible:5d}"
    )
    print(
        f"details attempted:    {summary.details_attempted:5d}"
    )
    print(
        f"details fetched:      {summary.details_succeeded:5d}"
    )
    print(
        f"details enriched:     {summary.details_enriched:5d}"
    )
    print(
        f"details partial/gated:{summary.details_partial_gated:5d}"
    )
    print(
        f"detail failures:      {summary.details_failed:5d}"
    )
    print(
        f"normalized jobs:      {summary.normalized_jobs:5d}"
    )
    print(
        f"unique companies:     {summary.unique_companies:5d}"
    )
    print(
        f"ATS hints detected:   {summary.ats_hints_detected:5d}"
    )
    print(
        f"coverage warnings:    {len(summary.coverage_warnings):5d}"
    )

    for warning in summary.coverage_warnings:
        print(f"  - {warning}")

    if summary.applied:
        print(
            f"run id:               {summary.run_id}"
        )
        print(
            f"companies created:    {summary.companies_created:5d}"
        )
        print(
            f"companies existing:   {summary.companies_existing:5d}"
        )
        print(
            f"jobs created:         {summary.jobs_created:5d}"
        )
        print(
            f"jobs updated:         {summary.jobs_updated:5d}"
        )
        print(
            f"ATS hints created:    {summary.ats_hints_created:5d}"
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
