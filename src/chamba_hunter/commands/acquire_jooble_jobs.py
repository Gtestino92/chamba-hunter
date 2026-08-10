import argparse
import sys

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
from chamba_hunter.repositories.tracing_repository import (
    TracingRepository,
)
from chamba_hunter.services.company_import_service import (
    CompanyImportService,
)
from chamba_hunter.services.jooble_job_acquisition_service import (
    JoobleJobAcquisitionService,
)
from chamba_hunter.sources.jooble_jobs import (
    JOOBLE_LOCATION,
    JOOBLE_QUERIES,
    JOOBLE_RESULTS_PER_PAGE,
    JoobleJobsClient,
)


DEFAULT_MAX_PAGES_PER_QUERY = 2


def main() -> None:
    if hasattr(
        sys.stdout,
        "reconfigure",
    ):
        sys.stdout.reconfigure(
            encoding="utf-8",
            errors="replace",
        )

    parser = argparse.ArgumentParser(
        description=(
            "Acquire Jooble Argentina broad job "
            "leads for the configured backend "
            "search queries."
        )
    )

    parser.add_argument(
        "--max-pages-per-query",
        type=int,
        default=DEFAULT_MAX_PAGES_PER_QUERY,
        help=(
            "Maximum Jooble result pages fetched "
            "for each configured query. "
            "Defaults to 2."
        ),
    )

    args = parser.parse_args()

    if args.max_pages_per_query <= 0:
        parser.error(
            "--max-pages-per-query must be positive"
        )

    database = Database()
    applied = migrate(database)

    if applied:
        for migration in applied:
            print(
                f"Applied migration: {migration}"
            )
        print()

    company_import_service = CompanyImportService(
        CompanyRepository(database),
        CompanySourceRepository(database),
    )

    service = JoobleJobAcquisitionService(
        jooble_client=(
            JoobleJobsClient.from_environment()
        ),
        company_import_service=(
            company_import_service
        ),
        job_lead_repository=(
            JobLeadRepository(database)
        ),
        tracing_repository=(
            TracingRepository(database)
        ),
    )

    print("Acquiring Jooble Argentina job leads...")
    print(f"Location:          {JOOBLE_LOCATION}")
    print(
        "Queries:           "
        + ", ".join(JOOBLE_QUERIES)
    )
    print(
        "Results per page:  "
        f"{JOOBLE_RESULTS_PER_PAGE}"
    )
    print(
        "Max pages/query:   "
        f"{args.max_pages_per_query}"
    )
    print()

    summary = service.run(
        max_pages_per_query=(
            args.max_pages_per_query
        )
    )

    print("Jooble acquisition finished")
    print("---------------------------")
    print(f"Run id:             {summary.run_id}")
    print(
        f"Requests made:      "
        f"{summary.requests_made}"
    )
    print(f"Received unique:    {summary.received}")
    print(f"Normalized:         {summary.normalized}")
    print(f"Skipped:            {summary.skipped}")
    print(
        f"Companies created:  "
        f"{summary.companies_created}"
    )
    print(
        f"Companies existing: "
        f"{summary.companies_existing}"
    )
    print(f"Jobs created:       {summary.jobs_created}")
    print(f"Jobs updated:       {summary.jobs_updated}")


if __name__ == "__main__":
    main()
