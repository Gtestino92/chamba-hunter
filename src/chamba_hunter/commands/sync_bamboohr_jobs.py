import argparse

from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate
from chamba_hunter.domain.enums import (
    AtsProvider,
    RunStatus,
)
from chamba_hunter.repositories.company_repository import (
    CompanyRepository,
)
from chamba_hunter.repositories.company_ats_repository import (
    CompanyAtsRepository,
)
from chamba_hunter.repositories.job_repository import (
    JobRepository,
)
from chamba_hunter.repositories.tracing_repository import (
    TracingRepository,
)
from chamba_hunter.services.bamboohr_job_ingestion_service import (
    BambooHRJobIngestionService,
)
from chamba_hunter.sources.bamboohr import (
    BambooHRClient,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Sync jobs from active "
            "BambooHR tenants."
        )
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Maximum number of BambooHR "
            "tenants to sync."
        ),
    )

    parser.add_argument(
        "--tenant-subdomain",
        default=None,
        help=(
            "Sync only one known BambooHR "
            "tenant subdomain."
        ),
    )

    args = parser.parse_args()

    if (
        args.limit is not None
        and args.limit < 1
    ):
        parser.error(
            "--limit must be at least 1"
        )

    database = Database()
    migrate(database)

    company_repository = (
        CompanyRepository(database)
    )
    company_ats_repository = (
        CompanyAtsRepository(database)
    )
    job_repository = JobRepository(
        database
    )
    tracing_repository = (
        TracingRepository(database)
    )

    company_ats_records = (
        company_ats_repository
        .list_active_primary_by_provider(
            AtsProvider.BAMBOOHR
        )
    )

    if args.tenant_subdomain is not None:
        requested_tenant = (
            args.tenant_subdomain.strip()
        )

        company_ats_records = [
            company_ats
            for company_ats
            in company_ats_records
            if (
                company_ats
                .external_identifier
                == requested_tenant
            )
        ]

        if not company_ats_records:
            parser.error(
                "No active primary BambooHR "
                "ATS found for tenant "
                "subdomain "
                f"'{args.tenant_subdomain}'."
            )

    if args.limit is not None:
        company_ats_records = (
            company_ats_records[
                :args.limit
            ]
        )

    company_names = {
        company.id: company.name
        for company in (
            company_repository.list_all()
        )
        if company.id is not None
    }

    print("Syncing BambooHR jobs...")
    print(
        "Tenants: "
        f"{len(company_ats_records)}"
    )
    print()

    service = BambooHRJobIngestionService(
        bamboohr_client=BambooHRClient(),
        company_ats_repository=(
            company_ats_repository
        ),
        job_repository=job_repository,
        tracing_repository=(
            tracing_repository
        ),
    )

    summary = service.run(
        company_ats_records
    )

    for result in summary.results:
        company_name = company_names.get(
            result.company_id,
            f"company {result.company_id}",
        )

        if result.status == RunStatus.SUCCESS:
            print(
                f"{company_name}: SUCCESS "
                f"[{result.tenant_subdomain}]"
            )
            print(
                "  received:     "
                f"{result.jobs_received}"
            )
            print(
                "  created:      "
                f"{result.jobs_created}"
            )
            print(
                "  updated:      "
                f"{result.jobs_updated}"
            )
            print(
                "  deactivated:  "
                f"{result.jobs_deactivated}"
            )

        else:
            print(
                f"{company_name}: FAILED "
                f"[{result.tenant_subdomain}]"
            )

            if result.http_status is not None:
                print(
                    "  http status:  "
                    f"{result.http_status}"
                )

            print(
                "  received:     "
                f"{result.jobs_received}"
            )
            print(
                "  error:        "
                f"{result.error_type}: "
                f"{result.error_message}"
            )

        print()

    print("BambooHR sync finished")
    print("----------------------")
    print(
        f"Run id:        {summary.run_id}"
    )
    print(
        f"Processed:     {summary.processed}"
    )
    print(
        f"Succeeded:     {summary.succeeded}"
    )
    print(
        f"Failed:        {summary.failed}"
    )
    print(
        f"Skipped:       {summary.skipped}"
    )
    print(
        f"Jobs received: {summary.jobs_received}"
    )
    print(
        f"Jobs created:  {summary.jobs_created}"
    )
    print(
        f"Jobs updated:  {summary.jobs_updated}"
    )
    print(
        "Deactivated:   "
        f"{summary.jobs_deactivated}"
    )


if __name__ == "__main__":
    main()
