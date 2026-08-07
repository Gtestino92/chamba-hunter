from dataclasses import dataclass, field
from datetime import datetime
from html import unescape

import httpx

from chamba_hunter.domain.common import utc_now
from chamba_hunter.domain.enums import (
    RunStatus,
    WorkplaceType,
)
from chamba_hunter.domain.models import (
    CompanyAts,
    Job,
)
from chamba_hunter.domain.tracing import (
    AtsSync,
    Run,
    RunStep,
)
from chamba_hunter.repositories.company_ats_repository import (
    CompanyAtsRepository,
)
from chamba_hunter.repositories.job_repository import (
    JobRepository,
    JobSyncCounts,
)
from chamba_hunter.repositories.tracing_repository import (
    TracingRepository,
)
from chamba_hunter.sources.greenhouse import (
    GreenhouseClient,
    GreenhouseJob,
)


@dataclass(frozen=True, slots=True)
class GreenhouseJobSyncResult:
    company_id: int
    company_ats_id: int
    board_token: str

    status: RunStatus
    http_status: int | None

    jobs_received: int = 0
    prospect_posts_skipped: int = 0
    jobs_created: int = 0
    jobs_updated: int = 0
    jobs_deactivated: int = 0

    error_type: str | None = None
    error_message: str | None = None


@dataclass(slots=True)
class GreenhouseJobIngestionSummary:
    run_id: int

    processed: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0

    jobs_received: int = 0
    prospect_posts_skipped: int = 0
    jobs_created: int = 0
    jobs_updated: int = 0
    jobs_deactivated: int = 0

    results: list[
        GreenhouseJobSyncResult
    ] = field(
        default_factory=list
    )


class GreenhouseJobIngestionService:
    def __init__(
        self,
        greenhouse_client: GreenhouseClient,
        company_ats_repository: CompanyAtsRepository,
        job_repository: JobRepository,
        tracing_repository: TracingRepository,
    ) -> None:
        self.greenhouse_client = (
            greenhouse_client
        )
        self.company_ats_repository = (
            company_ats_repository
        )
        self.job_repository = job_repository
        self.tracing_repository = (
            tracing_repository
        )

    def run(
        self,
        company_ats_records: list[
            CompanyAts
        ],
    ) -> GreenhouseJobIngestionSummary:
        run = (
            self.tracing_repository
            .add_run(
                Run(
                    command=(
                        "sync_greenhouse_jobs"
                    )
                )
            )
        )

        if run.id is None:
            raise RuntimeError(
                "Run must have an id."
            )

        step = (
            self.tracing_repository
            .add_run_step(
                RunStep(
                    run_id=run.id,
                    step_name=(
                        "greenhouse_job_ingestion"
                    ),
                    items_total=len(
                        company_ats_records
                    ),
                )
            )
        )

        if step.id is None:
            raise RuntimeError(
                "Run step must have an id."
            )

        summary = (
            GreenhouseJobIngestionSummary(
                run_id=run.id
            )
        )

        for company_ats in (
            company_ats_records
        ):
            if (
                company_ats.id is None
                or company_ats
                .external_identifier
                is None
            ):
                summary.skipped += 1
                continue

            self._sync_one(
                run_step_id=step.id,
                company_ats=company_ats,
                summary=summary,
            )

        status = _run_status(
            succeeded=summary.succeeded,
            failed=summary.failed,
        )

        (
            self.tracing_repository
            .finish_run_step(
                run_step_id=step.id,
                status=status,
                items_success=(
                    summary.succeeded
                ),
                items_failed=summary.failed,
                items_skipped=summary.skipped,
                metadata={
                    "jobs_received": (
                        summary.jobs_received
                    ),
                    "prospect_posts_skipped": (
                        summary
                        .prospect_posts_skipped
                    ),
                    "jobs_created": (
                        summary.jobs_created
                    ),
                    "jobs_updated": (
                        summary.jobs_updated
                    ),
                    "jobs_deactivated": (
                        summary
                        .jobs_deactivated
                    ),
                },
            )
        )

        self.tracing_repository.finish_run(
            run_id=run.id,
            status=status,
        )

        return summary

    def _sync_one(
        self,
        run_step_id: int,
        company_ats: CompanyAts,
        summary: GreenhouseJobIngestionSummary,
    ) -> None:
        if company_ats.id is None:
            summary.skipped += 1
            return

        board_token = (
            company_ats.external_identifier
        )

        if board_token is None:
            summary.skipped += 1
            return

        ats_sync = (
            self.tracing_repository
            .add_ats_sync(
                AtsSync(
                    run_step_id=run_step_id,
                    company_ats_id=(
                        company_ats.id
                    ),
                )
            )
        )

        if ats_sync.id is None:
            raise RuntimeError(
                "ATS sync must have an id."
            )

        summary.processed += 1

        try:
            fetch = (
                self.greenhouse_client
                .fetch_jobs(
                    board_token
                )
            )

            source_jobs = [
                job
                for job in fetch.jobs
                if (
                    job.internal_job_id
                    is not None
                )
            ]

            prospects_skipped = (
                fetch.total
                - len(source_jobs)
            )

            seen_at = utc_now()

            jobs = [
                _to_job(
                    company_ats=company_ats,
                    source_job=source_job,
                    seen_at=seen_at,
                )
                for source_job in source_jobs
            ]

            counts = (
                self.job_repository
                .sync_board_jobs(
                    company_ats=company_ats,
                    jobs=jobs,
                    seen_at=seen_at,
                )
            )

            (
                self.company_ats_repository
                .mark_successful_sync(
                    company_ats.id
                )
            )

            (
                self.tracing_repository
                .finish_ats_sync(
                    ats_sync_id=ats_sync.id,
                    status=RunStatus.SUCCESS,
                    http_status=(
                        fetch.http_status
                    ),
                    jobs_received=fetch.total,
                    jobs_created=(
                        counts.created
                    ),
                    jobs_updated=(
                        counts.updated
                    ),
                    jobs_deactivated=(
                        counts.deactivated
                    ),
                )
            )

            self._record_success(
                company_ats=company_ats,
                board_token=board_token,
                fetch_total=fetch.total,
                prospects_skipped=(
                    prospects_skipped
                ),
                counts=counts,
                http_status=(
                    fetch.http_status
                ),
                summary=summary,
            )

        except httpx.HTTPStatusError as error:
            self._record_failure(
                ats_sync_id=ats_sync.id,
                company_ats=company_ats,
                board_token=board_token,
                http_status=(
                    error.response.status_code
                ),
                error_type="HTTP_ERROR",
                error_message=str(error),
                summary=summary,
            )

        except httpx.RequestError as error:
            self._record_failure(
                ats_sync_id=ats_sync.id,
                company_ats=company_ats,
                board_token=board_token,
                http_status=None,
                error_type="REQUEST_ERROR",
                error_message=str(error),
                summary=summary,
            )

        except Exception as error:
            self._record_failure(
                ats_sync_id=ats_sync.id,
                company_ats=company_ats,
                board_token=board_token,
                http_status=None,
                error_type=(
                    type(error).__name__
                ),
                error_message=str(error),
                summary=summary,
            )

    def _record_success(
        self,
        company_ats: CompanyAts,
        board_token: str,
        fetch_total: int,
        prospects_skipped: int,
        counts: JobSyncCounts,
        http_status: int,
        summary: GreenhouseJobIngestionSummary,
    ) -> None:
        if company_ats.id is None:
            raise ValueError(
                "Company ATS must have an id."
            )

        summary.succeeded += 1
        summary.jobs_received += fetch_total
        summary.prospect_posts_skipped += (
            prospects_skipped
        )
        summary.jobs_created += (
            counts.created
        )
        summary.jobs_updated += (
            counts.updated
        )
        summary.jobs_deactivated += (
            counts.deactivated
        )

        summary.results.append(
            GreenhouseJobSyncResult(
                company_id=(
                    company_ats.company_id
                ),
                company_ats_id=(
                    company_ats.id
                ),
                board_token=board_token,
                status=RunStatus.SUCCESS,
                http_status=http_status,
                jobs_received=fetch_total,
                prospect_posts_skipped=(
                    prospects_skipped
                ),
                jobs_created=counts.created,
                jobs_updated=counts.updated,
                jobs_deactivated=(
                    counts.deactivated
                ),
            )
        )

    def _record_failure(
        self,
        ats_sync_id: int,
        company_ats: CompanyAts,
        board_token: str,
        http_status: int | None,
        error_type: str,
        error_message: str,
        summary: GreenhouseJobIngestionSummary,
    ) -> None:
        if company_ats.id is None:
            raise ValueError(
                "Company ATS must have an id."
            )

        (
            self.tracing_repository
            .finish_ats_sync(
                ats_sync_id=ats_sync_id,
                status=RunStatus.FAILED,
                http_status=http_status,
                jobs_received=0,
                jobs_created=0,
                jobs_updated=0,
                jobs_deactivated=0,
                error_type=error_type,
                error_message=error_message,
            )
        )

        summary.failed += 1

        summary.results.append(
            GreenhouseJobSyncResult(
                company_id=(
                    company_ats.company_id
                ),
                company_ats_id=(
                    company_ats.id
                ),
                board_token=board_token,
                status=RunStatus.FAILED,
                http_status=http_status,
                error_type=error_type,
                error_message=error_message,
            )
        )


def _to_job(
    company_ats: CompanyAts,
    source_job: GreenhouseJob,
    seen_at: datetime,
) -> Job:
    if company_ats.id is None:
        raise ValueError(
            "Company ATS must have an id."
        )

    location_text = None

    if source_job.location is not None:
        location_text = _clean_text(
            source_job.location.name
        )

    return Job(
        company_id=company_ats.company_id,
        company_ats_id=company_ats.id,
        external_id=str(source_job.id),
        title=source_job.title.strip(),
        description=(
            _decode_description(
                source_job.content
            )
        ),
        location_text=location_text,
        workplace_type=(
            WorkplaceType.UNKNOWN
        ),
        employment_type=None,
        job_url=_clean_text(
            source_job.absolute_url
        ),
        apply_url=None,
        published_at=None,
        first_seen_at=seen_at,
        last_seen_at=seen_at,
        is_active=True,
        raw_payload=(
            source_job.model_dump(
                mode="json"
            )
        ),
    )


def _decode_description(
    value: str | None,
) -> str | None:
    cleaned = _clean_text(value)

    if cleaned is None:
        return None

    return unescape(cleaned)


def _clean_text(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    cleaned = value.strip()

    return cleaned or None


def _run_status(
    succeeded: int,
    failed: int,
) -> RunStatus:
    if failed == 0:
        return RunStatus.SUCCESS

    if succeeded == 0:
        return RunStatus.FAILED

    return RunStatus.PARTIAL