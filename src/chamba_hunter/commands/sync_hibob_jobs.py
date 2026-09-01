import argparse

from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate
from chamba_hunter.domain.enums import AtsProvider, RunStatus
from chamba_hunter.repositories.company_ats_repository import CompanyAtsRepository
from chamba_hunter.repositories.company_repository import CompanyRepository
from chamba_hunter.repositories.job_repository import JobRepository
from chamba_hunter.repositories.tracing_repository import TracingRepository
from chamba_hunter.services.hibob_job_ingestion_service import HiBobJobIngestionService
from chamba_hunter.sources.hibob import HiBobClient


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync jobs from active HiBob public careers boards."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of HiBob tenants to sync.",
    )
    parser.add_argument(
        "--tenant",
        default=None,
        help="Sync only one known HiBob tenant identifier.",
    )
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")

    database = Database()
    migrate(database)
    company_repository = CompanyRepository(database)
    company_ats_repository = CompanyAtsRepository(database)
    job_repository = JobRepository(database)
    tracing_repository = TracingRepository(database)

    records = company_ats_repository.list_active_primary_by_provider(
        AtsProvider.HIBOB
    )
    if args.tenant is not None:
        requested = args.tenant.strip().casefold()
        records = [
            item
            for item in records
            if (item.external_identifier or "").casefold() == requested
        ]
        if not records:
            parser.error(
                "No active primary HiBob ATS found "
                f"for tenant '{args.tenant}'."
            )
    if args.limit is not None:
        records = records[: args.limit]

    company_names = {
        company.id: company.name
        for company in company_repository.list_all()
        if company.id is not None
    }
    print("Syncing HiBob jobs...")
    print(f"Tenants: {len(records)}")
    print()

    summary = HiBobJobIngestionService(
        hibob_client=HiBobClient(),
        company_ats_repository=company_ats_repository,
        job_repository=job_repository,
        tracing_repository=tracing_repository,
    ).run(records)

    for result in summary.results:
        company_name = company_names.get(
            result.company_id,
            f"company {result.company_id}",
        )
        print(
            f"{company_name}: {result.status.value} "
            f"[{result.tenant_identifier}]"
        )
        print(f"  board:        {result.board_url}")
        print(f"  received:     {result.jobs_received}")
        if result.status == RunStatus.SUCCESS:
            print(f"  created:      {result.jobs_created}")
            print(f"  updated:      {result.jobs_updated}")
            print(f"  deactivated:  {result.jobs_deactivated}")
        else:
            if result.http_status is not None:
                print(f"  http status:  {result.http_status}")
            print(
                f"  error:        {result.error_type}: "
                f"{result.error_message}"
            )
        print()

    print("HiBob sync finished")
    print("--------------------")
    print(f"Run id:        {summary.run_id}")
    print(f"Processed:     {summary.processed}")
    print(f"Succeeded:     {summary.succeeded}")
    print(f"Failed:        {summary.failed}")
    print(f"Skipped:       {summary.skipped}")
    print(f"Jobs received: {summary.jobs_received}")
    print(f"Jobs created:  {summary.jobs_created}")
    print(f"Jobs updated:  {summary.jobs_updated}")
    print(f"Deactivated:   {summary.jobs_deactivated}")


if __name__ == "__main__":
    main()
