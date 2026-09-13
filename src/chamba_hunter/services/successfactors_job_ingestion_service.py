from dataclasses import dataclass, field
from datetime import datetime
import unicodedata

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
from chamba_hunter.sources.successfactors import (
    SuccessFactorsClient,
    SuccessFactorsJobDetail,
)


@dataclass(frozen=True, slots=True)
class SuccessFactorsJobSyncResult:
    company_id: int
    company_ats_id: int
    external_identifier: str
    board_url: str
    status: RunStatus
    snapshot_complete: bool
    variant: str | None
    http_status: int | None
    jobs_received: int = 0
    jobs_created: int = 0
    jobs_updated: int = 0
    jobs_deactivated: int = 0
    error_type: str | None = None
    error_message: str | None = None


@dataclass(slots=True)
class SuccessFactorsJobIngestionSummary:
    run_id: int
    processed: int = 0
    succeeded: int = 0
    partial: int = 0
    failed: int = 0
    skipped: int = 0
    jobs_received: int = 0
    jobs_created: int = 0
    jobs_updated: int = 0
    jobs_deactivated: int = 0
    results: list[
        SuccessFactorsJobSyncResult
    ] = field(default_factory=list)


class SuccessFactorsJobIngestionService:
    def __init__(
        self,
        *,
        successfactors_client: SuccessFactorsClient,
        company_ats_repository: CompanyAtsRepository,
        job_repository: JobRepository,
        tracing_repository: TracingRepository,
    ) -> None:
        self.successfactors_client = (
            successfactors_client
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
        company_ats_records: list[CompanyAts],
    ) -> SuccessFactorsJobIngestionSummary:
        run = self.tracing_repository.add_run(
            Run(
                command="sync_successfactors_jobs"
            )
        )
        if run.id is None:
            raise RuntimeError(
                "Run must have an id."
            )
        step = self.tracing_repository.add_run_step(
            RunStep(
                run_id=run.id,
                step_name=(
                    "successfactors_job_ingestion"
                ),
                items_total=len(
                    company_ats_records
                ),
            )
        )
        if step.id is None:
            raise RuntimeError(
                "Run step must have an id."
            )

        summary = (
            SuccessFactorsJobIngestionSummary(
                run_id=run.id
            )
        )
        for company_ats in company_ats_records:
            if (
                company_ats.id is None
                or company_ats.external_identifier
                is None
                or company_ats.board_url is None
            ):
                summary.skipped += 1
                continue
            self._sync_one(
                run_step_id=step.id,
                company_ats=company_ats,
                summary=summary,
            )

        status = _run_status(
            summary.succeeded,
            summary.partial,
            summary.failed,
        )
        self.tracing_repository.finish_run_step(
            run_step_id=step.id,
            status=status,
            items_success=(
                summary.succeeded
                + summary.partial
            ),
            items_failed=summary.failed,
            items_skipped=summary.skipped,
            metadata={
                "partial": summary.partial,
                "jobs_received": (
                    summary.jobs_received
                ),
                "jobs_created": (
                    summary.jobs_created
                ),
                "jobs_updated": (
                    summary.jobs_updated
                ),
                "jobs_deactivated": (
                    summary.jobs_deactivated
                ),
            },
        )
        self.tracing_repository.finish_run(
            run_id=run.id,
            status=status,
        )
        return summary

    def _sync_one(
        self,
        *,
        run_step_id: int,
        company_ats: CompanyAts,
        summary: SuccessFactorsJobIngestionSummary,
    ) -> None:
        if company_ats.id is None:
            summary.skipped += 1
            return

        ats_sync = (
            self.tracing_repository
            .add_ats_sync(
                AtsSync(
                    run_step_id=run_step_id,
                    company_ats_id=company_ats.id,
                )
            )
        )
        if ats_sync.id is None:
            raise RuntimeError(
                "ATS sync must have an id."
            )

        summary.processed += 1
        board_url = company_ats.board_url or ""
        external_identifier = (
            company_ats.external_identifier or ""
        )
        http_status: int | None = None
        jobs_received = 0

        try:
            fetch = (
                self.successfactors_client
                .fetch_jobs(board_url)
            )
            http_status = fetch.http_status
            jobs_received = fetch.total
            seen_at = utc_now()
            jobs = [
                _to_job(
                    company_ats=company_ats,
                    source_job=source_job,
                    seen_at=seen_at,
                )
                for source_job in fetch.jobs
            ]
            counts = (
                self.job_repository
                .sync_board_jobs(
                    company_ats=company_ats,
                    jobs=jobs,
                    seen_at=seen_at,
                    deactivate_missing=(
                        fetch
                        .snapshot_complete
                    ),
                )
            )
            status = (
                RunStatus.SUCCESS
                if fetch.snapshot_complete
                else RunStatus.PARTIAL
            )
            if fetch.snapshot_complete:
                (
                    self.company_ats_repository
                    .mark_successful_sync(
                        company_ats.id
                    )
                )

            self.tracing_repository.finish_ats_sync(
                ats_sync_id=ats_sync.id,
                status=status,
                http_status=http_status,
                jobs_received=jobs_received,
                jobs_created=counts.created,
                jobs_updated=counts.updated,
                jobs_deactivated=counts.deactivated,
                error_type=fetch.error_type,
                error_message=(
                    fetch.error_message
                ),
            )
            _record_result(
                summary=summary,
                company_ats=company_ats,
                external_identifier=(
                    external_identifier
                ),
                board_url=board_url,
                status=status,
                snapshot_complete=(
                    fetch.snapshot_complete
                ),
                variant=fetch.variant,
                http_status=http_status,
                jobs_received=jobs_received,
                counts=counts,
                error_type=fetch.error_type,
                error_message=(
                    fetch.error_message
                ),
            )

        except httpx.HTTPStatusError as error:
            self._record_failure(
                ats_sync_id=ats_sync.id,
                company_ats=company_ats,
                external_identifier=(
                    external_identifier
                ),
                board_url=board_url,
                http_status=(
                    error.response.status_code
                ),
                jobs_received=jobs_received,
                error=error,
                summary=summary,
            )
        except (
            httpx.RequestError,
            ValueError,
            RuntimeError,
        ) as error:
            self._record_failure(
                ats_sync_id=ats_sync.id,
                company_ats=company_ats,
                external_identifier=(
                    external_identifier
                ),
                board_url=board_url,
                http_status=http_status,
                jobs_received=jobs_received,
                error=error,
                summary=summary,
            )

    def _record_failure(
        self,
        *,
        ats_sync_id: int,
        company_ats: CompanyAts,
        external_identifier: str,
        board_url: str,
        http_status: int | None,
        jobs_received: int,
        error: Exception,
        summary: SuccessFactorsJobIngestionSummary,
    ) -> None:
        if company_ats.id is None:
            raise ValueError(
                "Company ATS must have an id."
            )

        self.tracing_repository.finish_ats_sync(
            ats_sync_id=ats_sync_id,
            status=RunStatus.FAILED,
            http_status=http_status,
            jobs_received=jobs_received,
            jobs_created=0,
            jobs_updated=0,
            jobs_deactivated=0,
            error_type=type(error).__name__,
            error_message=str(error),
        )
        summary.failed += 1
        summary.jobs_received += jobs_received
        summary.results.append(
            SuccessFactorsJobSyncResult(
                company_id=(
                    company_ats.company_id
                ),
                company_ats_id=company_ats.id,
                external_identifier=(
                    external_identifier
                ),
                board_url=board_url,
                status=RunStatus.FAILED,
                snapshot_complete=False,
                variant=None,
                http_status=http_status,
                jobs_received=jobs_received,
                error_type=type(error).__name__,
                error_message=str(error),
            )
        )


def _record_result(
    *,
    summary: SuccessFactorsJobIngestionSummary,
    company_ats: CompanyAts,
    external_identifier: str,
    board_url: str,
    status: RunStatus,
    snapshot_complete: bool,
    variant: str,
    http_status: int | None,
    jobs_received: int,
    counts: JobSyncCounts,
    error_type: str | None,
    error_message: str | None,
) -> None:
    if company_ats.id is None:
        raise ValueError(
            "Company ATS must have an id."
        )
    if status == RunStatus.SUCCESS:
        summary.succeeded += 1
    elif status == RunStatus.PARTIAL:
        summary.partial += 1
    else:
        summary.failed += 1

    summary.jobs_received += jobs_received
    summary.jobs_created += counts.created
    summary.jobs_updated += counts.updated
    summary.jobs_deactivated += counts.deactivated
    summary.results.append(
        SuccessFactorsJobSyncResult(
            company_id=company_ats.company_id,
            company_ats_id=company_ats.id,
            external_identifier=(
                external_identifier
            ),
            board_url=board_url,
            status=status,
            snapshot_complete=(
                snapshot_complete
            ),
            variant=variant,
            http_status=http_status,
            jobs_received=jobs_received,
            jobs_created=counts.created,
            jobs_updated=counts.updated,
            jobs_deactivated=(
                counts.deactivated
            ),
            error_type=error_type,
            error_message=error_message,
        )
    )


def _to_job(
    *,
    company_ats: CompanyAts,
    source_job: SuccessFactorsJobDetail,
    seen_at: datetime,
) -> Job:
    if company_ats.id is None:
        raise ValueError(
            "Company ATS must have an id."
        )
    external_id = (
        source_job.external_id.strip()
    )
    title = source_job.title.strip()
    if not external_id:
        raise ValueError(
            "SuccessFactors job id is empty."
        )
    if not title:
        raise ValueError(
            "SuccessFactors job title is empty."
        )

    return Job(
        company_id=company_ats.company_id,
        company_ats_id=company_ats.id,
        external_id=external_id,
        title=title,
        description=source_job.description,
        location_text=(
            source_job.location_text
        ),
        workplace_type=_workplace_type(
            source_job
        ),
        employment_type=(
            source_job.employment_type
        ),
        job_url=source_job.job_url,
        apply_url=source_job.apply_url,
        published_at=(
            source_job.published_at
        ),
        first_seen_at=seen_at,
        last_seen_at=seen_at,
        is_active=True,
        raw_payload=source_job.raw_payload,
    )


def _workplace_type(
    source_job: SuccessFactorsJobDetail,
) -> WorkplaceType:
    text = _normalize(
        " ".join(
            value
            for value in (
                source_job.title,
                source_job.description or "",
                source_job.location_text or "",
                source_job.employment_type or "",
            )
            if value
        )
    )

    if any(
        marker in text
        for marker in (
            "remote",
            "remoto",
            "teletrabajo",
        )
    ):
        return WorkplaceType.REMOTE

    if any(
        marker in text
        for marker in (
            "hybrid",
            "hibrido",
            "hibrida",
        )
    ):
        return WorkplaceType.HYBRID

    if any(
        marker in text
        for marker in (
            "onsite",
            "on site",
            "presencial",
        )
    ):
        return WorkplaceType.ONSITE

    return WorkplaceType.UNKNOWN


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize(
        "NFKD",
        value,
    )
    without_accents = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(
            character
        )
    )
    return " ".join(
        without_accents
        .casefold()
        .replace("-", " ")
        .split()
    )


def _run_status(
    succeeded: int,
    partial: int,
    failed: int,
) -> RunStatus:
    if failed == 0 and partial == 0:
        return RunStatus.SUCCESS
    if succeeded == 0 and partial == 0:
        return RunStatus.FAILED
    return RunStatus.PARTIAL
