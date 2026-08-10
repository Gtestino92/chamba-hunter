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
from chamba_hunter.repositories.job_lead_repository import (
    JobLeadRepository,
)
from chamba_hunter.repositories.tracing_repository import (
    TracingRepository,
)
from chamba_hunter.services.company_import_service import (
    CompanyImportService,
)
from chamba_hunter.services.public_job_acquisition_service import (
    PublicJobAcquisitionService,
)
from chamba_hunter.sources.jobicy_jobs import (
    JobicyJobsClient,
)
from chamba_hunter.sources.weworkremotely_jobs import (
    WeWorkRemotelyJobsClient,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Acquire broad public job leads "
            "from Jobicy and We Work Remotely."
        )
    )

    parser.add_argument(
        "--jobicy-max-jobs",
        type=int,
        default=100,
        help=(
            "Maximum Jobicy Software Engineering "
            "jobs requested for LATAM. "
            "Range 1-100; use 0 to disable. "
            "Defaults to 100."
        ),
    )

    parser.add_argument(
        "--wwr-max-jobs",
        type=int,
        default=300,
        help=(
            "Maximum unique We Work Remotely jobs "
            "kept across Programming and DevOps "
            "RSS feeds. Use 0 to disable. "
            "Defaults to 300."
        ),
    )

    args = parser.parse_args()

    if (
        args.jobicy_max_jobs
        < 0
        or args.jobicy_max_jobs
        > 100
    ):
        parser.error(
            "--jobicy-max-jobs must "
            "be between 0 and 100"
        )

    if args.wwr_max_jobs < 0:
        parser.error(
            "--wwr-max-jobs cannot "
            "be negative"
        )

    if (
        args.jobicy_max_jobs
        == 0
        and args.wwr_max_jobs
        == 0
    ):
        parser.error(
            "At least one source must "
            "be enabled."
        )

    database = Database()
    applied = migrate(
        database
    )

    if applied:
        for migration in applied:
            print(
                f"Applied migration: "
                f"{migration}"
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

    job_lead_repository = (
        JobLeadRepository(
            database
        )
    )
    tracing_repository = (
        TracingRepository(
            database
        )
    )

    service = (
        PublicJobAcquisitionService(
            jobicy_client=(
                JobicyJobsClient()
            ),
            weworkremotely_client=(
                WeWorkRemotelyJobsClient()
            ),
            company_import_service=(
                company_import_service
            ),
            job_lead_repository=(
                job_lead_repository
            ),
            tracing_repository=(
                tracing_repository
            ),
        )
    )

    print(
        "Acquiring additional public "
        "job leads..."
    )
    print(
        "Jobicy max jobs:    "
        f"{args.jobicy_max_jobs}"
    )
    print(
        "WWR max jobs:        "
        f"{args.wwr_max_jobs}"
    )
    print()

    summary = service.run(
        jobicy_max_jobs=(
            args.jobicy_max_jobs
        ),
        wwr_max_jobs=(
            args.wwr_max_jobs
        ),
    )

    for result in summary.results:
        print(
            f"{result.source_type.value}: "
            f"{result.status.value}"
        )

        if (
            result.status
            == RunStatus.SUCCESS
        ):
            print(
                "  received:           "
                f"{result.received}"
            )
            print(
                "  normalized:         "
                f"{result.normalized}"
            )
            print(
                "  skipped:            "
                f"{result.skipped}"
            )
            print(
                "  companies created:  "
                f"{result.companies_created}"
            )
            print(
                "  companies existing: "
                f"{result.companies_existing}"
            )
            print(
                "  jobs created:       "
                f"{result.jobs_created}"
            )
            print(
                "  jobs updated:       "
                f"{result.jobs_updated}"
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

    print(
        "Additional public acquisition "
        "finished"
    )
    print(
        "--------------------------------"
    )
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
    print()
    print(
        "Active unresolved leads: "
        f"{active_leads}"
    )
    print(
        "Raw active candidates "
        "(ATS + unresolved leads): "
        f"{raw_candidates}"
    )
    print()
    print(
        "Note: raw candidates are "
        "before cross-source deduplication."
    )


if __name__ == "__main__":
    main()
