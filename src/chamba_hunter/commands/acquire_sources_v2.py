import argparse
from dataclasses import dataclass
from datetime import datetime
import sys

from chamba_hunter.db.connection import (
    Database,
)
from chamba_hunter.db.migrations import (
    migrate,
)
from chamba_hunter.domain.common import (
    JsonObject,
    utc_now,
)
from chamba_hunter.domain.enums import (
    RunStatus,
    SourceType,
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
from chamba_hunter.repositories.source_acquisition_state_repository import (
    SourceAcquisitionStateRepository,
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
from chamba_hunter.services.himalayas_incremental_acquisition_service import (
    DEFAULT_BACKFILL_DAYS,
    DEFAULT_OVERLAP_HOURS,
    HimalayasIncrementalAcquisitionService,
)
from chamba_hunter.services.jooble_job_acquisition_service import (
    JoobleJobAcquisitionService,
)
from chamba_hunter.services.public_job_acquisition_service import (
    PublicJobAcquisitionService,
)
from chamba_hunter.sources.getonboard_jobs import (
    GetOnBoardJobsClient,
)
from chamba_hunter.sources.himalayas_incremental_jobs import (
    HimalayasIncrementalJobsClient,
)
from chamba_hunter.sources.himalayas_jobs import (
    HimalayasJobsClient,
)
from chamba_hunter.sources.jobicy_jobs import (
    JobicyJobsClient,
)
from chamba_hunter.sources.jooble_jobs import (
    JoobleJobsClient,
)
from chamba_hunter.sources.weworkremotely_jobs import (
    WeWorkRemotelyJobsClient,
)


DEFAULT_GETONBOARD_MAX_PAGES = 5
DEFAULT_JOBICY_MAX_JOBS = 100
DEFAULT_WWR_MAX_JOBS = 300
DEFAULT_JOOBLE_MAX_PAGES_PER_QUERY = 2


@dataclass(frozen=True, slots=True)
class SourceOutcome:
    source_type: SourceType
    status: RunStatus
    strategy: str

    received: int = 0
    normalized: int = 0
    jobs_created: int = 0
    jobs_updated: int = 0

    error_type: str | None = None
    error_message: str | None = None


_STATE_SCOPES = {
    SourceType.GETONBOARD: (
        "PROGRAMMING_CURRENT",
        "FULL_CURRENT_SNAPSHOT",
    ),
    SourceType.JOBICY: (
        "ENGINEERING_LATAM",
        "LATEST_100_FEED",
    ),
    SourceType.WEWORKREMOTELY: (
        "PROGRAMMING_DEVOPS",
        "FULL_RSS_SNAPSHOT",
    ),
    SourceType.JOOBLE: (
        "ARGENTINA_BACKEND_QUERIES",
        "BOUNDED_QUERY_SNAPSHOT",
    ),
}


def _record_source_success(
    *,
    repository: SourceAcquisitionStateRepository,
    source_type: SourceType,
    started_at: datetime,
    finished_at: datetime,
    metadata: JsonObject,
) -> None:
    scope_key, strategy = (
        _STATE_SCOPES[
            source_type
        ]
    )

    final_metadata = {
        "strategy": strategy,
        **metadata,
    }

    repository.record_success(
        source_type=source_type,
        scope_key=scope_key,
        started_at=started_at,
        finished_at=finished_at,
        is_backfill=False,
        metadata=final_metadata,
    )


def _print_outcome(
    outcome: SourceOutcome,
) -> None:
    print(
        f"{outcome.source_type.value}: "
        f"{outcome.status.value}"
    )
    print(
        f"  strategy:    "
        f"{outcome.strategy}"
    )

    if (
        outcome.status
        == RunStatus.SUCCESS
    ):
        print(
            f"  received:    "
            f"{outcome.received}"
        )
        print(
            f"  normalized:  "
            f"{outcome.normalized}"
        )
        print(
            f"  jobs created:"
            f" {outcome.jobs_created}"
        )
        print(
            f"  jobs updated:"
            f" {outcome.jobs_updated}"
        )
    else:
        print(
            "  error:       "
            f"{outcome.error_type}: "
            f"{outcome.error_message}"
        )

    print()


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
            "Acquire all configured broad "
            "sources using provider-aware "
            "refresh strategies."
        )
    )

    parser.add_argument(
        "--skip-himalayas",
        action="store_true",
        help=(
            "Skip Himalayas temporal "
            "backfill/incremental acquisition."
        ),
    )

    parser.add_argument(
        "--himalayas-backfill-days",
        type=int,
        default=DEFAULT_BACKFILL_DAYS,
        help=(
            "Maximum Himalayas historical "
            "window. Defaults to 30 days."
        ),
    )

    parser.add_argument(
        "--himalayas-overlap-hours",
        type=int,
        default=DEFAULT_OVERLAP_HOURS,
        help=(
            "Himalayas overlap before the "
            "previous successful start. "
            "Defaults to 48 hours."
        ),
    )

    parser.add_argument(
        "--getonboard-max-pages",
        type=int,
        default=(
            DEFAULT_GETONBOARD_MAX_PAGES
        ),
        help=(
            "Get on Board Programming pages. "
            "Use 0 to disable. Defaults to 5."
        ),
    )

    parser.add_argument(
        "--jobicy-max-jobs",
        type=int,
        default=(
            DEFAULT_JOBICY_MAX_JOBS
        ),
        help=(
            "Jobicy Engineering LATAM jobs. "
            "Range 1-100; use 0 to disable. "
            "Defaults to 100."
        ),
    )

    parser.add_argument(
        "--wwr-max-jobs",
        type=int,
        default=DEFAULT_WWR_MAX_JOBS,
        help=(
            "Maximum unique We Work Remotely "
            "Programming + DevOps jobs. "
            "Use 0 to disable. Defaults to 300."
        ),
    )

    parser.add_argument(
        "--jooble-max-pages-per-query",
        type=int,
        default=(
            DEFAULT_JOOBLE_MAX_PAGES_PER_QUERY
        ),
        help=(
            "Jooble Argentina pages for each "
            "configured backend query. "
            "Use 0 to disable. Defaults to 2."
        ),
    )

    args = parser.parse_args()

    if args.himalayas_backfill_days < 1:
        parser.error(
            "--himalayas-backfill-days "
            "must be at least 1"
        )

    if args.himalayas_overlap_hours < 0:
        parser.error(
            "--himalayas-overlap-hours "
            "cannot be negative"
        )

    if args.getonboard_max_pages < 0:
        parser.error(
            "--getonboard-max-pages "
            "cannot be negative"
        )

    if (
        args.jobicy_max_jobs < 0
        or args.jobicy_max_jobs > 100
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
        args.jooble_max_pages_per_query
        < 0
    ):
        parser.error(
            "--jooble-max-pages-per-query "
            "cannot be negative"
        )

    if (
        args.skip_himalayas
        and args.getonboard_max_pages == 0
        and args.jobicy_max_jobs == 0
        and args.wwr_max_jobs == 0
        and (
            args.jooble_max_pages_per_query
            == 0
        )
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
                "Applied migration:",
                migration,
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

    ats_hint_repository = (
        JobAtsHintRepository(
            database
        )
    )

    tracing_repository = (
        TracingRepository(
            database
        )
    )

    state_repository = (
        SourceAcquisitionStateRepository(
            database
        )
    )

    outcomes: list[
        SourceOutcome
    ] = []

    print(
        "Broad acquisition V2"
    )
    print(
        "===================="
    )
    print()

    if not args.skip_himalayas:
        try:
            summary = (
                HimalayasIncrementalAcquisitionService(
                    client=(
                        HimalayasIncrementalJobsClient()
                    ),
                    company_import_service=(
                        company_import_service
                    ),
                    job_lead_repository=(
                        job_lead_repository
                    ),
                    state_repository=(
                        state_repository
                    ),
                )
                .run(
                    backfill_days=(
                        args
                        .himalayas_backfill_days
                    ),
                    overlap_hours=(
                        args
                        .himalayas_overlap_hours
                    ),
                )
            )

            outcome = SourceOutcome(
                source_type=(
                    SourceType.HIMALAYAS
                ),
                status=RunStatus.SUCCESS,
                strategy=(
                    "TEMPORAL_BACKFILL_"
                    "INCREMENTAL"
                ),
                received=summary.received,
                normalized=(
                    summary.normalized
                ),
                jobs_created=(
                    summary.jobs_created
                ),
                jobs_updated=(
                    summary.jobs_updated
                ),
            )

        except Exception as error:
            outcome = SourceOutcome(
                source_type=(
                    SourceType.HIMALAYAS
                ),
                status=RunStatus.FAILED,
                strategy=(
                    "TEMPORAL_BACKFILL_"
                    "INCREMENTAL"
                ),
                error_type=(
                    type(error).__name__
                ),
                error_message=str(
                    error
                ),
            )

        outcomes.append(
            outcome
        )
        _print_outcome(
            outcome
        )

    if args.getonboard_max_pages > 0:
        started_at = utc_now()

        try:
            summary = (
                BroadJobAcquisitionService(
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
                .run(
                    himalayas_max_jobs=0,
                    getonboard_max_pages=(
                        args
                        .getonboard_max_pages
                    ),
                )
            )

            finished_at = utc_now()

            result = next(
                (
                    item
                    for item in summary.results
                    if (
                        item.source_type
                        == SourceType.GETONBOARD
                    )
                ),
                None,
            )

            if result is None:
                raise RuntimeError(
                    "Get on Board acquisition "
                    "did not return a source "
                    "result."
                )

            if (
                result.status
                == RunStatus.SUCCESS
            ):
                _record_source_success(
                    repository=(
                        state_repository
                    ),
                    source_type=(
                        SourceType.GETONBOARD
                    ),
                    started_at=started_at,
                    finished_at=finished_at,
                    metadata={
                        "max_pages": (
                            args
                            .getonboard_max_pages
                        ),
                        "received": (
                            result.received
                        ),
                        "normalized": (
                            result.normalized
                        ),
                        "skipped": (
                            result.skipped
                        ),
                        "jobs_created": (
                            result.jobs_created
                        ),
                        "jobs_updated": (
                            result.jobs_updated
                        ),
                    },
                )

                outcome = SourceOutcome(
                    source_type=(
                        SourceType.GETONBOARD
                    ),
                    status=RunStatus.SUCCESS,
                    strategy=(
                        "FULL_CURRENT_SNAPSHOT"
                    ),
                    received=(
                        result.received
                    ),
                    normalized=(
                        result.normalized
                    ),
                    jobs_created=(
                        result.jobs_created
                    ),
                    jobs_updated=(
                        result.jobs_updated
                    ),
                )
            else:
                outcome = SourceOutcome(
                    source_type=(
                        SourceType.GETONBOARD
                    ),
                    status=RunStatus.FAILED,
                    strategy=(
                        "FULL_CURRENT_SNAPSHOT"
                    ),
                    error_type=(
                        result.error_type
                    ),
                    error_message=(
                        result.error_message
                    ),
                )

        except Exception as error:
            outcome = SourceOutcome(
                source_type=(
                    SourceType.GETONBOARD
                ),
                status=RunStatus.FAILED,
                strategy=(
                    "FULL_CURRENT_SNAPSHOT"
                ),
                error_type=(
                    type(error).__name__
                ),
                error_message=str(
                    error
                ),
            )

        outcomes.append(
            outcome
        )
        _print_outcome(
            outcome
        )

    if (
        args.jobicy_max_jobs > 0
        or args.wwr_max_jobs > 0
    ):
        started_at = utc_now()

        try:
            summary = (
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
                .run(
                    jobicy_max_jobs=(
                        args.jobicy_max_jobs
                    ),
                    wwr_max_jobs=(
                        args.wwr_max_jobs
                    ),
                )
            )

            finished_at = utc_now()

            result_by_source = {
                item.source_type: item
                for item in summary.results
            }

            for (
                source_type,
                enabled,
            ) in (
                (
                    SourceType.JOBICY,
                    (
                        args.jobicy_max_jobs
                        > 0
                    ),
                ),
                (
                    SourceType
                    .WEWORKREMOTELY,
                    args.wwr_max_jobs > 0,
                ),
            ):
                if not enabled:
                    continue

                result = (
                    result_by_source.get(
                        source_type
                    )
                )

                scope_key, strategy = (
                    _STATE_SCOPES[
                        source_type
                    ]
                )
                del scope_key

                if result is None:
                    outcome = (
                        SourceOutcome(
                            source_type=(
                                source_type
                            ),
                            status=(
                                RunStatus.FAILED
                            ),
                            strategy=strategy,
                            error_type=(
                                "RuntimeError"
                            ),
                            error_message=(
                                "Public acquisition "
                                "did not return a "
                                "source result."
                            ),
                        )
                    )
                elif (
                    result.status
                    == RunStatus.SUCCESS
                ):
                    metadata: JsonObject = {
                        "received": (
                            result.received
                        ),
                        "normalized": (
                            result.normalized
                        ),
                        "skipped": (
                            result.skipped
                        ),
                        "jobs_created": (
                            result.jobs_created
                        ),
                        "jobs_updated": (
                            result.jobs_updated
                        ),
                    }

                    if (
                        source_type
                        == SourceType.JOBICY
                    ):
                        metadata[
                            "max_jobs"
                        ] = (
                            args
                            .jobicy_max_jobs
                        )
                    else:
                        metadata[
                            "max_jobs"
                        ] = (
                            args.wwr_max_jobs
                        )

                    _record_source_success(
                        repository=(
                            state_repository
                        ),
                        source_type=(
                            source_type
                        ),
                        started_at=started_at,
                        finished_at=(
                            finished_at
                        ),
                        metadata=metadata,
                    )

                    outcome = (
                        SourceOutcome(
                            source_type=(
                                source_type
                            ),
                            status=(
                                RunStatus.SUCCESS
                            ),
                            strategy=strategy,
                            received=(
                                result.received
                            ),
                            normalized=(
                                result.normalized
                            ),
                            jobs_created=(
                                result.jobs_created
                            ),
                            jobs_updated=(
                                result.jobs_updated
                            ),
                        )
                    )
                else:
                    outcome = (
                        SourceOutcome(
                            source_type=(
                                source_type
                            ),
                            status=(
                                RunStatus.FAILED
                            ),
                            strategy=strategy,
                            error_type=(
                                result.error_type
                            ),
                            error_message=(
                                result
                                .error_message
                            ),
                        )
                    )

                outcomes.append(
                    outcome
                )
                _print_outcome(
                    outcome
                )

        except Exception as error:
            for (
                source_type,
                enabled,
            ) in (
                (
                    SourceType.JOBICY,
                    (
                        args.jobicy_max_jobs
                        > 0
                    ),
                ),
                (
                    SourceType
                    .WEWORKREMOTELY,
                    args.wwr_max_jobs > 0,
                ),
            ):
                if not enabled:
                    continue

                _, strategy = (
                    _STATE_SCOPES[
                        source_type
                    ]
                )

                outcome = (
                    SourceOutcome(
                        source_type=(
                            source_type
                        ),
                        status=(
                            RunStatus.FAILED
                        ),
                        strategy=strategy,
                        error_type=(
                            type(error).__name__
                        ),
                        error_message=str(
                            error
                        ),
                    )
                )

                outcomes.append(
                    outcome
                )
                _print_outcome(
                    outcome
                )

    if (
        args.jooble_max_pages_per_query
        > 0
    ):
        started_at = utc_now()

        try:
            summary = (
                JoobleJobAcquisitionService(
                    jooble_client=(
                        JoobleJobsClient
                        .from_environment()
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
                .run(
                    max_pages_per_query=(
                        args
                        .jooble_max_pages_per_query
                    )
                )
            )

            finished_at = utc_now()

            _record_source_success(
                repository=(
                    state_repository
                ),
                source_type=(
                    SourceType.JOOBLE
                ),
                started_at=started_at,
                finished_at=finished_at,
                metadata={
                    "max_pages_per_query": (
                        args
                        .jooble_max_pages_per_query
                    ),
                    "requests_made": (
                        summary.requests_made
                    ),
                    "received": (
                        summary.received
                    ),
                    "normalized": (
                        summary.normalized
                    ),
                    "skipped": (
                        summary.skipped
                    ),
                    "jobs_created": (
                        summary.jobs_created
                    ),
                    "jobs_updated": (
                        summary.jobs_updated
                    ),
                },
            )

            _, strategy = (
                _STATE_SCOPES[
                    SourceType.JOOBLE
                ]
            )

            outcome = SourceOutcome(
                source_type=(
                    SourceType.JOOBLE
                ),
                status=RunStatus.SUCCESS,
                strategy=strategy,
                received=summary.received,
                normalized=(
                    summary.normalized
                ),
                jobs_created=(
                    summary.jobs_created
                ),
                jobs_updated=(
                    summary.jobs_updated
                ),
            )

        except Exception as error:
            _, strategy = (
                _STATE_SCOPES[
                    SourceType.JOOBLE
                ]
            )

            outcome = SourceOutcome(
                source_type=(
                    SourceType.JOOBLE
                ),
                status=RunStatus.FAILED,
                strategy=strategy,
                error_type=(
                    type(error).__name__
                ),
                error_message=str(
                    error
                ),
            )

        outcomes.append(
            outcome
        )
        _print_outcome(
            outcome
        )

    succeeded = sum(
        1
        for outcome in outcomes
        if (
            outcome.status
            == RunStatus.SUCCESS
        )
    )

    failed = sum(
        1
        for outcome in outcomes
        if (
            outcome.status
            != RunStatus.SUCCESS
        )
    )

    print(
        "Acquisition V2 finished"
    )
    print(
        "-----------------------"
    )
    print(
        f"Sources succeeded: {succeeded}"
    )
    print(
        f"Sources failed:    {failed}"
    )

    if failed:
        raise SystemExit(
            1
        )


if __name__ == "__main__":
    main()
