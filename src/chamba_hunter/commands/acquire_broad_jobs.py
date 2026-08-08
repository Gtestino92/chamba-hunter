import argparse

from chamba_hunter.db.connection import (
    Database,
)
from chamba_hunter.db.migrations import (
    migrate,
)
from chamba_hunter.domain.enums import (
    RunStatus,
)
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
from chamba_hunter.repositories.tracing_repository import (
    TracingRepository,
)
from chamba_hunter.services.broad_job_acquisition_service import (
    BroadJobAcquisitionService,
)
from chamba_hunter.services.company_import_service import (
    CompanyImportService,
)
from chamba_hunter.sources.getonboard_jobs import (
    GetOnBoardJobsClient,
)
from chamba_hunter.sources.himalayas_jobs import (
    HimalayasJobsClient,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Acquire broad public job leads "
            "from Himalayas and Get on Board."
        )
    )

    parser.add_argument(
        "--himalayas-max-jobs",
        type=int,
        default=500,
        help=(
            "Maximum Himalayas jobs to fetch "
            "from the full remote jobs feed. "
            "Use 0 to disable. Defaults to 500."
        ),
    )

    parser.add_argument(
        "--getonboard-max-pages",
        type=int,
        default=5,
        help=(
            "Maximum Get on Board Programming "
            "pages to fetch (up to 100 jobs per "
            "page). Use 0 to disable. "
            "Defaults to 5."
        ),
    )

    args = parser.parse_args()

    if args.himalayas_max_jobs < 0:
        parser.error(
            "--himalayas-max-jobs cannot "
            "be negative"
        )

    if args.getonboard_max_pages < 0:
        parser.error(
            "--getonboard-max-pages cannot "
            "be negative"
        )

    if (
        args.himalayas_max_jobs == 0
        and args.getonboard_max_pages == 0
    ):
        parser.error(
            "At least one source must be "
            "enabled."
        )

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

    company_import_service = (
        CompanyImportService(
            company_repository,
            company_source_repository,
        )
    )

    job_lead_repository = (
        JobLeadRepository(database)
    )

    ats_hint_repository = (
        JobAtsHintRepository(database)
    )

    tracing_repository = (
        TracingRepository(database)
    )

    service = BroadJobAcquisitionService(
        himalayas_client=(
            HimalayasJobsClient()
        ),
        getonboard_client=(
            GetOnBoardJobsClient()
        ),
        company_import_service=(
            company_import_service
        ),
        job_lead_repository=(
            job_lead_repository
        ),
        ats_hint_repository=(
            ats_hint_repository
        ),
        tracing_repository=(
            tracing_repository
        ),
    )

    print("Acquiring broad job leads...")
    print(
        "Himalayas max jobs:  "
        f"{args.himalayas_max_jobs}"
    )
    print(
        "Get on Board pages:  "
        f"{args.getonboard_max_pages}"
    )
    print()

    summary = service.run(
        himalayas_max_jobs=(
            args.himalayas_max_jobs
        ),
        getonboard_max_pages=(
            args.getonboard_max_pages
        ),
    )

    for result in summary.results:
        print(
            f"{result.source_type.value}: "
            f"{result.status.value}"
        )

        if result.status == RunStatus.SUCCESS:
            print(
                "  received:            "
                f"{result.received}"
            )
            print(
                "  normalized:          "
                f"{result.normalized}"
            )
            print(
                "  skipped:             "
                f"{result.skipped}"
            )
            print(
                "  companies created:   "
                f"{result.companies_created}"
            )
            print(
                "  companies existing:  "
                f"{result.companies_existing}"
            )
            print(
                "  jobs created:        "
                f"{result.jobs_created}"
            )
            print(
                "  jobs updated:        "
                f"{result.jobs_updated}"
            )
            print(
                "  ATS hints created:   "
                f"{result.ats_hints_created}"
            )

        else:
            print(
                "  error: "
                f"{result.error_type}: "
                f"{result.error_message}"
            )

        print()

    active_leads = (
        job_lead_repository
        .count_active_unresolved()
    )

    raw_candidates = (
        job_lead_repository
        .count_active_candidates()
    )

    all_hints = (
        ats_hint_repository.count_all()
    )

    print("Broad acquisition finished")
    print("--------------------------")
    print(
        f"Run id:             "
        f"{summary.run_id}"
    )
    print(
        f"Sources succeeded:  "
        f"{summary.succeeded}"
    )
    print(
        f"Sources failed:     "
        f"{summary.failed}"
    )
    print(
        f"Received:           "
        f"{summary.received}"
    )
    print(
        f"Normalized:         "
        f"{summary.normalized}"
    )
    print(
        f"Skipped:            "
        f"{summary.skipped}"
    )
    print(
        f"Companies created:  "
        f"{summary.companies_created}"
    )
    print(
        f"Companies existing: "
        f"{summary.companies_existing}"
    )
    print(
        f"Jobs created:       "
        f"{summary.jobs_created}"
    )
    print(
        f"Jobs updated:       "
        f"{summary.jobs_updated}"
    )
    print(
        f"ATS hints created:  "
        f"{summary.ats_hints_created}"
    )
    print()
    print(
        f"Active unresolved leads: "
        f"{active_leads}"
    )
    print(
        "Raw active candidates "
        "(ATS + unresolved leads): "
        f"{raw_candidates}"
    )
    print(
        f"Stored ATS hints:    "
        f"{all_hints}"
    )
    print()
    print(
        "Note: raw candidates are "
        "before cross-source deduplication."
    )


if __name__ == "__main__":
    main()
