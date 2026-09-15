import argparse
import sys

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
from chamba_hunter.services.hn_job_acquisition_service import (
    HnJobAcquisitionService,
)
from chamba_hunter.sources.hn_who_is_hiring import (
    DEFAULT_TIMEOUT_SECONDS,
    HnWhoIsHiringClient,
)


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
            "Acquire Hacker News 'Ask HN: "
            "Who is hiring?' job leads."
        )
    )
    parser.add_argument(
        "--thread-id",
        type=int,
        default=None,
        help=(
            "Explicit HN thread id to acquire. "
            "Defaults to discovering the newest "
            "valid monthly thread from the "
            "whoishiring user."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Maximum direct/top-level comments "
            "to fetch from the selected thread. "
            "Defaults to all direct comments."
        ),
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=(
            "HTTP timeout per HN API request. "
            f"Defaults to {DEFAULT_TIMEOUT_SECONDS}."
        ),
    )

    args = parser.parse_args()

    if (
        args.thread_id is not None
        and args.thread_id < 1
    ):
        parser.error(
            "--thread-id must be positive"
        )

    if (
        args.limit is not None
        and args.limit < 1
    ):
        parser.error(
            "--limit must be at least 1"
        )

    if args.timeout_seconds <= 0:
        parser.error(
            "--timeout-seconds must be positive"
        )

    database = Database()
    applied = migrate(database)

    if applied:
        for migration in applied:
            print(
                "Applied migration:",
                migration,
            )

        print()

    company_repository = CompanyRepository(
        database
    )
    company_source_repository = (
        CompanySourceRepository(
            database
        )
    )
    service = HnJobAcquisitionService(
        client=HnWhoIsHiringClient(
            timeout_seconds=(
                args.timeout_seconds
            ),
        ),
        company_import_service=(
            CompanyImportService(
                company_repository,
                company_source_repository,
            )
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
        tracing_repository=(
            TracingRepository(
                database
            )
        ),
    )

    print(
        "Acquiring Hacker News jobs..."
    )
    print(
        "Thread id:       "
        + (
            str(args.thread_id)
            if args.thread_id is not None
            else "latest"
        )
    )
    print(
        "Comment limit:   "
        + (
            str(args.limit)
            if args.limit is not None
            else "all"
        )
    )
    print(
        "Timeout seconds: "
        f"{args.timeout_seconds}"
    )
    print()

    summary = service.run(
        thread_id=args.thread_id,
        limit=args.limit,
    )

    print(
        "HN Who is Hiring acquisition"
    )
    print(
        "----------------------------"
    )
    print(
        f"Run id:                       "
        f"{summary.run_id}"
    )
    print(
        f"Thread id:                    "
        f"{summary.thread_id}"
    )
    print(
        f"Thread title:                 "
        f"{summary.thread_title}"
    )
    print(
        f"Direct comments discovered:   "
        f"{summary.direct_comments_discovered}"
    )
    print(
        f"Comments fetched:             "
        f"{summary.comments_fetched}"
    )
    print(
        f"Deleted/dead skipped:         "
        f"{summary.deleted_dead_skipped}"
    )
    print(
        f"Invalid skipped:              "
        f"{summary.invalid_skipped}"
    )
    print(
        f"Fetch failures:               "
        f"{summary.fetch_failures}"
    )
    print(
        f"Companies resolved:           "
        f"{summary.companies_resolved}"
    )
    print(
        f"Company resolution failures:  "
        f"{summary.company_resolution_failures}"
    )
    print(
        f"Companies created:            "
        f"{summary.companies_created}"
    )
    print(
        f"Leads normalized:             "
        f"{summary.leads_normalized}"
    )
    print(
        f"Jobs created:                 "
        f"{summary.jobs_created}"
    )
    print(
        f"Jobs updated:                 "
        f"{summary.jobs_updated}"
    )


if __name__ == "__main__":
    main()
