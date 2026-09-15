import argparse
import sys

from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate
from chamba_hunter.domain.enums import RunStatus
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
from chamba_hunter.services.yc_job_acquisition_service import (
    YcJobAcquisitionService,
)
from chamba_hunter.sources.yc_jobs import (
    DEFAULT_REQUEST_DELAY_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
    YcJobsClient,
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
            "Acquire public YC job leads for "
            "already-imported YC companies."
        )
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Maximum existing YC company sources "
            "to consider. Defaults to all."
        ),
    )
    parser.add_argument(
        "--include-not-hiring",
        action="store_true",
        help=(
            "Fetch companies whose stored YC "
            "metadata explicitly says is_hiring=false."
        ),
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=(
            "HTTP timeout per request. "
            f"Defaults to {DEFAULT_TIMEOUT_SECONDS}."
        ),
    )
    parser.add_argument(
        "--request-delay-seconds",
        type=float,
        default=DEFAULT_REQUEST_DELAY_SECONDS,
        help=(
            "Delay between YC detail requests. "
            "Defaults to "
            f"{DEFAULT_REQUEST_DELAY_SECONDS}."
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

    if args.timeout_seconds <= 0:
        parser.error(
            "--timeout-seconds must be positive"
        )

    if args.request_delay_seconds < 0:
        parser.error(
            "--request-delay-seconds cannot be negative"
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

    service = YcJobAcquisitionService(
        client=YcJobsClient(
            timeout_seconds=(
                args.timeout_seconds
            ),
            request_delay_seconds=(
                args.request_delay_seconds
            ),
        ),
        company_source_repository=(
            CompanySourceRepository(
                database
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
        "Acquiring YC public jobs..."
    )
    print(
        "Company limit:       "
        + (
            str(args.limit)
            if args.limit is not None
            else "all"
        )
    )
    print(
        "Include not hiring:  "
        f"{args.include_not_hiring}"
    )
    print(
        "Timeout seconds:     "
        f"{args.timeout_seconds}"
    )
    print(
        "Delay seconds:       "
        f"{args.request_delay_seconds}"
    )
    print()

    summary = service.run(
        limit=args.limit,
        include_not_hiring=(
            args.include_not_hiring
        ),
    )

    for result in summary.results:
        print(
            f"{result.company_slug}: "
            f"{result.status.value}"
        )

        if (
            result.status
            in {
                RunStatus.SUCCESS,
                RunStatus.PARTIAL,
            }
        ):
            print(
                "  company id:       "
                f"{result.company_id}"
            )
            print(
                "  job links:        "
                f"{result.job_links_discovered}"
            )
            print(
                "  details fetched:  "
                f"{result.details_fetched}"
            )
            print(
                "  normalized:       "
                f"{result.normalized}"
            )
            print(
                "  skipped:          "
                f"{result.skipped}"
            )
            print(
                "  jobs created:     "
                f"{result.jobs_created}"
            )
            print(
                "  jobs updated:     "
                f"{result.jobs_updated}"
            )
        else:
            print(
                "  error: "
                f"{result.error_type}: "
                f"{result.error_message}"
            )

        print()

    print(
        "YC public jobs acquisition"
    )
    print(
        "--------------------------"
    )
    print(
        f"Run id:                  "
        f"{summary.run_id}"
    )
    print(
        f"Companies considered:    "
        f"{summary.companies_considered}"
    )
    print(
        f"Skipped not hiring:      "
        f"{summary.companies_skipped_not_hiring}"
    )
    print(
        f"Companies fetched:       "
        f"{summary.companies_fetched}"
    )
    print(
        f"Companies failed:        "
        f"{summary.companies_failed}"
    )
    print(
        f"Job links discovered:    "
        f"{summary.job_links_discovered}"
    )
    print(
        f"Details fetched:         "
        f"{summary.details_fetched}"
    )
    print(
        f"Detail failures:         "
        f"{summary.detail_failures}"
    )
    print(
        f"Normalized:              "
        f"{summary.normalized}"
    )
    print(
        f"Skipped:                 "
        f"{summary.skipped}"
    )
    print(
        f"Jobs created:            "
        f"{summary.jobs_created}"
    )
    print(
        f"Jobs updated:            "
        f"{summary.jobs_updated}"
    )


if __name__ == "__main__":
    main()
