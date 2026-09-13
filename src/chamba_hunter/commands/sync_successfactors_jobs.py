import argparse

from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate
from chamba_hunter.domain.enums import (
    AtsProvider,
    RunStatus,
)
from chamba_hunter.repositories.company_ats_repository import (
    CompanyAtsRepository,
)
from chamba_hunter.repositories.company_repository import (
    CompanyRepository,
)
from chamba_hunter.repositories.job_repository import (
    JobRepository,
)
from chamba_hunter.repositories.tracing_repository import (
    TracingRepository,
)
from chamba_hunter.services.successfactors_job_ingestion_service import (
    SuccessFactorsJobIngestionService,
)
from chamba_hunter.sources.successfactors import (
    SuccessFactorsClient,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Sync jobs from active SAP "
            "SuccessFactors public boards."
        )
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Maximum number of "
            "SuccessFactors boards to sync."
        ),
    )
    parser.add_argument(
        "--company-id",
        type=int,
        default=None,
        help=(
            "Sync only one company id with "
            "an active SuccessFactors ATS."
        ),
    )
    parser.add_argument(
        "--external-identifier",
        default=None,
        help=(
            "Sync only one known "
            "SuccessFactors board identity."
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

    if (
        args.company_id is not None
        and args.company_id < 1
    ):
        parser.error(
            "--company-id must be at least 1"
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

    records = (
        company_ats_repository
        .list_active_primary_by_provider(
            AtsProvider.SUCCESSFACTORS
        )
    )

    if args.company_id is not None:
        records = [
            record
            for record in records
            if record.company_id
            == args.company_id
        ]
        if not records:
            parser.error(
                "No active primary "
                "SuccessFactors ATS found "
                f"for company id "
                f"{args.company_id}."
            )

    if (
        args.external_identifier
        is not None
    ):
        requested = (
            args.external_identifier
            .strip()
            .casefold()
        )
        records = [
            record
            for record in records
            if (
                record.external_identifier
                or ""
            ).casefold()
            == requested
        ]
        if not records:
            parser.error(
                "No active primary "
                "SuccessFactors ATS found "
                "for external identifier "
                f"'{args.external_identifier}'."
            )

    if args.limit is not None:
        records = records[: args.limit]

    company_names = {
        company.id: company.name
        for company in (
            company_repository.list_all()
        )
        if company.id is not None
    }

    print(
        "Syncing SuccessFactors jobs..."
    )
    print(f"Boards: {len(records)}")
    print()

    summary = (
        SuccessFactorsJobIngestionService(
            successfactors_client=(
                SuccessFactorsClient()
            ),
            company_ats_repository=(
                company_ats_repository
            ),
            job_repository=job_repository,
            tracing_repository=(
                tracing_repository
            ),
        )
        .run(records)
    )

    for result in summary.results:
        company_name = company_names.get(
            result.company_id,
            f"company {result.company_id}",
        )
        print(
            f"{company_name}: "
            f"{result.status.value} "
            f"[{result.external_identifier}]"
        )
        print(f"  board:        {result.board_url}")
        print(
            "  variant:      "
            f"{result.variant or '-'}"
        )
        print(
            "  complete:     "
            f"{result.snapshot_complete}"
        )
        print(
            "  received:     "
            f"{result.jobs_received}"
        )
        if result.status in {
            RunStatus.SUCCESS,
            RunStatus.PARTIAL,
        }:
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
        if result.error_message:
            print(
                "  error:        "
                f"{result.error_type}: "
                f"{result.error_message}"
            )
        print()

    print(
        "SuccessFactors sync finished"
    )
    print(
        "----------------------------"
    )
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
        f"Partial:       {summary.partial}"
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
