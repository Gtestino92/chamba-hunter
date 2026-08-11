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
from chamba_hunter.sources.teamtailor import (
    TeamtailorClient,
    TeamtailorJobDetail,
)


@dataclass(frozen=True, slots=True)
class TeamtailorJobSyncResult:
    company_id: int
    company_ats_id: int
    tenant_identifier: str
    board_url: str

    status: RunStatus
    http_status: int | None

    jobs_received: int = 0
    jobs_created: int = 0
    jobs_updated: int = 0
    jobs_deactivated: int = 0

    error_type: str | None = None
    error_message: str | None = None


@dataclass(slots=True)
class TeamtailorJobIngestionSummary:
    run_id: int

    processed: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0

    jobs_received: int = 0
    jobs_created: int = 0
    jobs_updated: int = 0
    jobs_deactivated: int = 0

    results: list[
        TeamtailorJobSyncResult
    ] = field(default_factory=list)


class TeamtailorJobIngestionService:
    def __init__(
        self,
        teamtailor_client: TeamtailorClient,
        company_ats_repository: CompanyAtsRepository,
        job_repository: JobRepository,
        tracing_repository: TracingRepository,
    ) -> None:
        self.teamtailor_client = teamtailor_client
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
    ) -> TeamtailorJobIngestionSummary:
        run = self.tracing_repository.add_run(
            Run(
                command=(
                    "sync_teamtailor_jobs"
                )
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
                    "teamtailor_job_ingestion"
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

        summary = TeamtailorJobIngestionSummary(
            run_id=run.id
        )

        for company_ats in company_ats_records:
            if (
                company_ats.id is None
                or company_ats.external_identifier
                is None
                or company_ats.board_url
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

        self.tracing_repository.finish_run_step(
            run_step_id=step.id,
            status=status,
            items_success=summary.succeeded,
            items_failed=summary.failed,
            items_skipped=summary.skipped,
            metadata={
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
        run_step_id: int,
        company_ats: CompanyAts,
        summary: TeamtailorJobIngestionSummary,
    ) -> None:
        if company_ats.id is None:
            summary.skipped += 1
            return

        tenant_identifier = (
            company_ats.external_identifier
        )
        board_url = company_ats.board_url

        if (
            tenant_identifier is None
            or board_url is None
        ):
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

        http_status: int | None = None
        jobs_received = 0

        try:
            fetch = self.teamtailor_client.fetch_jobs(
                board_url
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
                self.job_repository.sync_board_jobs(
                    company_ats=company_ats,
                    jobs=jobs,
                    seen_at=seen_at,
                )
            )

            self.company_ats_repository.mark_successful_sync(
                company_ats.id
            )

            self.tracing_repository.finish_ats_sync(
                ats_sync_id=ats_sync.id,
                status=RunStatus.SUCCESS,
                http_status=fetch.http_status,
                jobs_received=fetch.total,
                jobs_created=counts.created,
                jobs_updated=counts.updated,
                jobs_deactivated=(
                    counts.deactivated
                ),
            )

            self._record_success(
                company_ats=company_ats,
                tenant_identifier=(
                    tenant_identifier
                ),
                board_url=board_url,
                fetch_total=fetch.total,
                counts=counts,
                http_status=fetch.http_status,
                summary=summary,
            )

        except httpx.HTTPStatusError as error:
            self._record_failure(
                ats_sync_id=ats_sync.id,
                company_ats=company_ats,
                tenant_identifier=(
                    tenant_identifier
                ),
                board_url=board_url,
                http_status=(
                    error.response.status_code
                ),
                jobs_received=jobs_received,
                error_type="HTTP_ERROR",
                error_message=str(error),
                summary=summary,
            )

        except httpx.RequestError as error:
            self._record_failure(
                ats_sync_id=ats_sync.id,
                company_ats=company_ats,
                tenant_identifier=(
                    tenant_identifier
                ),
                board_url=board_url,
                http_status=http_status,
                jobs_received=jobs_received,
                error_type="REQUEST_ERROR",
                error_message=str(error),
                summary=summary,
            )

        except Exception as error:
            self._record_failure(
                ats_sync_id=ats_sync.id,
                company_ats=company_ats,
                tenant_identifier=(
                    tenant_identifier
                ),
                board_url=board_url,
                http_status=http_status,
                jobs_received=jobs_received,
                error_type=(
                    type(error).__name__
                ),
                error_message=str(error),
                summary=summary,
            )

    def _record_success(
        self,
        company_ats: CompanyAts,
        tenant_identifier: str,
        board_url: str,
        fetch_total: int,
        counts: JobSyncCounts,
        http_status: int,
        summary: TeamtailorJobIngestionSummary,
    ) -> None:
        if company_ats.id is None:
            raise ValueError(
                "Company ATS must have an id."
            )

        summary.succeeded += 1
        summary.jobs_received += fetch_total
        summary.jobs_created += counts.created
        summary.jobs_updated += counts.updated
        summary.jobs_deactivated += (
            counts.deactivated
        )

        summary.results.append(
            TeamtailorJobSyncResult(
                company_id=company_ats.company_id,
                company_ats_id=company_ats.id,
                tenant_identifier=(
                    tenant_identifier
                ),
                board_url=board_url,
                status=RunStatus.SUCCESS,
                http_status=http_status,
                jobs_received=fetch_total,
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
        tenant_identifier: str,
        board_url: str,
        http_status: int | None,
        jobs_received: int,
        error_type: str,
        error_message: str,
        summary: TeamtailorJobIngestionSummary,
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
            error_type=error_type,
            error_message=error_message,
        )

        summary.failed += 1
        summary.jobs_received += jobs_received

        summary.results.append(
            TeamtailorJobSyncResult(
                company_id=company_ats.company_id,
                company_ats_id=company_ats.id,
                tenant_identifier=(
                    tenant_identifier
                ),
                board_url=board_url,
                status=RunStatus.FAILED,
                http_status=http_status,
                jobs_received=jobs_received,
                error_type=error_type,
                error_message=error_message,
            )
        )


def _to_job(
    company_ats: CompanyAts,
    source_job: TeamtailorJobDetail,
    seen_at: datetime,
) -> Job:
    if company_ats.id is None:
        raise ValueError(
            "Company ATS must have an id."
        )

    external_id = source_job.external_id.strip()
    title = source_job.title.strip()

    if not external_id:
        raise ValueError(
            "Teamtailor job id is empty."
        )

    if not title:
        raise ValueError(
            "Teamtailor job title is empty."
        )

    return Job(
        company_id=company_ats.company_id,
        company_ats_id=company_ats.id,
        external_id=external_id,
        title=title,
        description=source_job.description,
        location_text=source_job.location_text,
        workplace_type=(
            _workplace_type(source_job)
        ),
        employment_type=(
            source_job.employment_type
        ),
        job_url=source_job.job_url,
        apply_url=source_job.apply_url,
        published_at=source_job.published_at,
        first_seen_at=seen_at,
        last_seen_at=seen_at,
        is_active=True,
        raw_payload=source_job.raw_payload,
    )


def _workplace_type(
    source_job: TeamtailorJobDetail,
) -> WorkplaceType:
    structured = _normalize_label(
        source_job.job_location_type
        or ""
    )

    if "telecommute" in structured:
        return WorkplaceType.REMOTE

    remote_status = _normalize_label(
        source_job.remote_status
        or ""
    )

    if any(
        marker in remote_status
        for marker in (
            "remote",
            "remoto",
        )
    ):
        return WorkplaceType.REMOTE

    if any(
        marker in remote_status
        for marker in (
            "hybrid",
            "hibrido",
        )
    ):
        return WorkplaceType.HYBRID

    if any(
        marker in remote_status
        for marker in (
            "onsite",
            "on site",
            "presencial",
        )
    ):
        return WorkplaceType.ONSITE

    return WorkplaceType.UNKNOWN


def _normalize_label(
    value: str,
) -> str:
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
    failed: int,
) -> RunStatus:
    if failed == 0:
        return RunStatus.SUCCESS

    if succeeded == 0:
        return RunStatus.FAILED

    return RunStatus.PARTIAL
