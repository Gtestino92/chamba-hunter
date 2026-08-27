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
from chamba_hunter.services.company_import_service import (
    CompanyImportService,
)
from chamba_hunter.services.getonboard_job_acquisition_service import (
    GetOnBoardJobAcquisitionService,
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

    repository.record_success(
        source_type=source_type,
        scope_key=scope_key,
        started_at=started_at,
        finished_at=finished_at,
        is_backfill=False,
        metadata={
            "strategy": strategy,
            **metadata,
        },
    )


def _success(
    *,
    source_type: SourceType,
    received: int,
    normalized: int,
    jobs_created: int,
    jobs_updated: int,
) -> SourceOutcome:
    _, strategy = (
        _STATE_SCOPES[
            source_type
        ]
    )

    return SourceOutcome(
        source_type=source_type,
        status=RunStatus.SUCCESS,
        strategy=strategy,
        received=received,
        normalized=normalized,
        jobs_created=jobs_created,
        jobs_updated=jobs_updated,
    )


def _failure(
    *,
    source_type: SourceType,
    error: Exception,
    strategy: str | None = None,
) -> SourceOutcome:
    if strategy is None:
        _, strategy = (
            _STATE_SCOPES[
                source_type
            ]
        )

    return SourceOutcome(
        source_type=source_type,
        status=RunStatus.FAILED,
        strategy=strategy,
        error_type=(
            type(error).__name__
        ),
        error_message=str(
            error
        ),
    )


def _print_outcome(
    outcome: SourceOutcome,
) -> None:
    print(
        f"{outcome.source_type.value}: "
        f"{outcome.status.value}"
    )
    print(
        f"  strategy:     "
        f"{outcome.strategy}"
    )

    if (
        outcome.status
        == RunStatus.SUCCESS
    ):
        print(
            f"  received:     "
            f"{outcome.received}"
        )
        print(
            f"  normalized:   "
            f"{outcome.normalized}"
        )
        print(
            f"  jobs created: "
            f"{outcome.jobs_created}"
        )
        print(
            f"  jobs updated: "
            f"{outcome.jobs_updated}"
        )
    else:
        print(
            "  error:        "
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
    )

    parser.add_argument(
        "--himalayas-overlap-hours",
        type=int,
        default=DEFAULT_OVERLAP_HOURS,
    )

    parser.add_argument(
        "--getonboard-max-pages",
        type=int,
        default=(
            DEFAULT_GETONBOARD_MAX_PAGES
        ),
    )

    parser.add_argument(
        "--jobicy-max-jobs",
        type=int,
        default=(
            DEFAULT_JOBICY_MAX_JOBS
        ),
    )

    parser.add_argument(
        "--wwr-max-jobs",
        type=int,
        default=DEFAULT_WWR_MAX_JOBS,
    )

    parser.add_argument(
        "--jooble-max-pages-per-query",
        type=int,
        default=(
            DEFAULT_JOOBLE_MAX_PAGES_PER_QUERY
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

    company_import_service = (
        CompanyImportService(
            CompanyRepository(
                database
            ),
            CompanySourceRepository(
                database
            ),
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
            outcome = _failure(
                source_type=(
                    SourceType.HIMALAYAS
                ),
                error=error,
                strategy=(
                    "TEMPORAL_BACKFILL_"
                    "INCREMENTAL"
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
                GetOnBoardJobAcquisitionService(
                    client=(
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
                    max_pages=(
                        args
                        .getonboard_max_pages
                    )
                )
            )

            finished_at = utc_now()

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
                    "ats_hints_created": (
                        summary
                        .ats_hints_created
                    ),
                },
            )

            outcome = _success(
                source_type=(
                    SourceType.GETONBOARD
                ),
                received=(
                    summary.received
                ),
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
            outcome = _failure(
                source_type=(
                    SourceType.GETONBOARD
                ),
                error=error,
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
                result.source_type: result
                for result
                in summary.results
            }

            for source_type, enabled in (
                (
                    SourceType.JOBICY,
                    (
                        args.jobicy_max_jobs
                        > 0
                    ),
                ),
                (
                    SourceType.WEWORKREMOTELY,
                    (
                        args.wwr_max_jobs
                        > 0
                    ),
                ),
            ):
                if not enabled:
                    continue

                result = (
                    result_by_source.get(
                        source_type
                    )
                )

                if result is None:
                    outcome = _failure(
                        source_type=(
                            source_type
                        ),
                        error=RuntimeError(
                            "Public acquisition "
                            "returned no source "
                            "result."
                        ),
                    )
                elif (
                    result.status
                    == RunStatus.SUCCESS
                ):
                    max_jobs = (
                        args.jobicy_max_jobs
                        if (
                            source_type
                            == SourceType.JOBICY
                        )
                        else args.wwr_max_jobs
                    )

                    _record_source_success(
                        repository=(
                            state_repository
                        ),
                        source_type=(
                            source_type
                        ),
                        started_at=(
                            started_at
                        ),
                        finished_at=(
                            finished_at
                        ),
                        metadata={
                            "max_jobs": (
                                max_jobs
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

                    outcome = _success(
                        source_type=(
                            source_type
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
                            source_type
                        ),
                        status=(
                            RunStatus.FAILED
                        ),
                        strategy=(
                            _STATE_SCOPES[
                                source_type
                            ][1]
                        ),
                        error_type=(
                            result.error_type
                        ),
                        error_message=(
                            result.error_message
                        ),
                    )

                outcomes.append(
                    outcome
                )
                _print_outcome(
                    outcome
                )

        except Exception as error:
            for source_type, enabled in (
                (
                    SourceType.JOBICY,
                    (
                        args.jobicy_max_jobs
                        > 0
                    ),
                ),
                (
                    SourceType.WEWORKREMOTELY,
                    (
                        args.wwr_max_jobs
                        > 0
                    ),
                ),
            ):
                if not enabled:
                    continue

                outcome = _failure(
                    source_type=(
                        source_type
                    ),
                    error=error,
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

            outcome = _success(
                source_type=(
                    SourceType.JOOBLE
                ),
                received=(
                    summary.received
                ),
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
            outcome = _failure(
                source_type=(
                    SourceType.JOOBLE
                ),
                error=error,
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

    failed = (
        len(outcomes)
        - succeeded
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
