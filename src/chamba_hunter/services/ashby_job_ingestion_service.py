from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import unquote, urlparse
from uuid import UUID

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
from chamba_hunter.sources.ashby import (
    AshbyClient,
    AshbyJob,
)


@dataclass(frozen=True, slots=True)
class AshbyJobSyncResult:
    company_id: int
    company_ats_id: int
    board_name: str

    status: RunStatus
    http_status: int | None

    jobs_received: int = 0
    unlisted_posts_skipped: int = 0
    jobs_created: int = 0
    jobs_updated: int = 0
    jobs_deactivated: int = 0

    error_type: str | None = None
    error_message: str | None = None


@dataclass(slots=True)
class AshbyJobIngestionSummary:
    run_id: int

    processed: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0

    jobs_received: int = 0
    unlisted_posts_skipped: int = 0
    jobs_created: int = 0
    jobs_updated: int = 0
    jobs_deactivated: int = 0

    results: list[
        AshbyJobSyncResult
    ] = field(
        default_factory=list
    )


class AshbyJobIngestionService:
    def __init__(
        self,
        ashby_client: AshbyClient,
        company_ats_repository: CompanyAtsRepository,
        job_repository: JobRepository,
        tracing_repository: TracingRepository,
    ) -> None:
        self.ashby_client = ashby_client
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
    ) -> AshbyJobIngestionSummary:
        run = (
            self.tracing_repository
            .add_run(
                Run(
                    command="sync_ashby_jobs"
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
                        "ashby_job_ingestion"
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

        summary = AshbyJobIngestionSummary(
            run_id=run.id
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
                    "unlisted_posts_skipped": (
                        summary
                        .unlisted_posts_skipped
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
        summary: AshbyJobIngestionSummary,
    ) -> None:
        if company_ats.id is None:
            summary.skipped += 1
            return

        board_name = (
            company_ats.external_identifier
        )

        if board_name is None:
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
        unlisted_skipped = 0

        try:
            fetch = (
                self.ashby_client
                .fetch_jobs(
                    board_name
                )
            )

            http_status = fetch.http_status
            jobs_received = fetch.total

            source_jobs = [
                job
                for job in fetch.jobs
                if job.is_listed
            ]

            unlisted_skipped = (
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
                board_name=board_name,
                fetch_total=fetch.total,
                unlisted_skipped=(
                    unlisted_skipped
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
                board_name=board_name,
                http_status=(
                    error.response.status_code
                ),
                jobs_received=0,
                unlisted_skipped=0,
                error_type="HTTP_ERROR",
                error_message=str(error),
                summary=summary,
            )

        except httpx.RequestError as error:
            self._record_failure(
                ats_sync_id=ats_sync.id,
                company_ats=company_ats,
                board_name=board_name,
                http_status=None,
                jobs_received=0,
                unlisted_skipped=0,
                error_type="REQUEST_ERROR",
                error_message=str(error),
                summary=summary,
            )

        except Exception as error:
            self._record_failure(
                ats_sync_id=ats_sync.id,
                company_ats=company_ats,
                board_name=board_name,
                http_status=http_status,
                jobs_received=jobs_received,
                unlisted_skipped=(
                    unlisted_skipped
                ),
                error_type=(
                    type(error).__name__
                ),
                error_message=str(error),
                summary=summary,
            )

    def _record_success(
        self,
        company_ats: CompanyAts,
        board_name: str,
        fetch_total: int,
        unlisted_skipped: int,
        counts: JobSyncCounts,
        http_status: int,
        summary: AshbyJobIngestionSummary,
    ) -> None:
        if company_ats.id is None:
            raise ValueError(
                "Company ATS must have an id."
            )

        summary.succeeded += 1
        summary.jobs_received += fetch_total
        summary.unlisted_posts_skipped += (
            unlisted_skipped
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
            AshbyJobSyncResult(
                company_id=(
                    company_ats.company_id
                ),
                company_ats_id=(
                    company_ats.id
                ),
                board_name=board_name,
                status=RunStatus.SUCCESS,
                http_status=http_status,
                jobs_received=fetch_total,
                unlisted_posts_skipped=(
                    unlisted_skipped
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
        board_name: str,
        http_status: int | None,
        jobs_received: int,
        unlisted_skipped: int,
        error_type: str,
        error_message: str,
        summary: AshbyJobIngestionSummary,
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
                jobs_received=jobs_received,
                jobs_created=0,
                jobs_updated=0,
                jobs_deactivated=0,
                error_type=error_type,
                error_message=error_message,
            )
        )

        summary.failed += 1
        summary.jobs_received += (
            jobs_received
        )
        summary.unlisted_posts_skipped += (
            unlisted_skipped
        )

        summary.results.append(
            AshbyJobSyncResult(
                company_id=(
                    company_ats.company_id
                ),
                company_ats_id=(
                    company_ats.id
                ),
                board_name=board_name,
                status=RunStatus.FAILED,
                http_status=http_status,
                jobs_received=jobs_received,
                unlisted_posts_skipped=(
                    unlisted_skipped
                ),
                error_type=error_type,
                error_message=error_message,
            )
        )


def _to_job(
    company_ats: CompanyAts,
    source_job: AshbyJob,
    seen_at: datetime,
) -> Job:
    if company_ats.id is None:
        raise ValueError(
            "Company ATS must have an id."
        )

    published_at = source_job.published_at

    if (
        published_at is not None
        and published_at.tzinfo is None
    ):
        raise ValueError(
            "Ashby publishedAt must include "
            "timezone information."
        )

    external_id = _external_id_from_job_url(
        source_job.job_url
    )

    return Job(
        company_id=company_ats.company_id,
        company_ats_id=company_ats.id,
        external_id=external_id,
        title=source_job.title.strip(),
        description=_clean_text(
            source_job.description_plain
        ),
        location_text=_location_text(
            source_job
        ),
        workplace_type=_workplace_type(
            source_job
        ),
        employment_type=_clean_text(
            source_job.employment_type
        ),
        job_url=_clean_text(
            source_job.job_url
        ),
        apply_url=_clean_text(
            source_job.apply_url
        ),
        published_at=published_at,
        first_seen_at=seen_at,
        last_seen_at=seen_at,
        is_active=True,
        raw_payload=(
            source_job.model_dump(
                mode="json",
                by_alias=True,
            )
        ),
    )


def _external_id_from_job_url(
    job_url: str,
) -> str:
    cleaned = _clean_text(job_url)

    if cleaned is None:
        raise ValueError(
            "Ashby jobUrl is empty."
        )

    parsed = urlparse(cleaned)

    if (
        not parsed.scheme
        or not parsed.netloc
    ):
        raise ValueError(
            "Ashby jobUrl is not an "
            f"absolute URL: {cleaned}"
        )

    path_segments = [
        unquote(segment)
        for segment in parsed.path.split("/")
        if segment
    ]

    if not path_segments:
        raise ValueError(
            "Ashby jobUrl does not contain "
            f"a posting id: {cleaned}"
        )

    candidate = path_segments[-1]

    try:
        posting_id = UUID(candidate)
    except ValueError as error:
        raise ValueError(
            "Ashby jobUrl does not end in "
            "a valid posting UUID: "
            f"{cleaned}"
        ) from error

    return str(posting_id)


def _location_text(
    source_job: AshbyJob,
) -> str | None:
    values = [
        source_job.location,
        *[
            secondary.location
            for secondary
            in source_job.secondary_locations
        ],
    ]

    unique_locations: list[str] = []

    for value in values:
        cleaned = _clean_text(value)

        if (
            cleaned is not None
            and cleaned not in unique_locations
        ):
            unique_locations.append(
                cleaned
            )

    if not unique_locations:
        return None

    return "; ".join(unique_locations)


def _workplace_type(
    source_job: AshbyJob,
) -> WorkplaceType:
    value = _clean_text(
        source_job.workplace_type
    )

    mapping = {
        "Remote": WorkplaceType.REMOTE,
        "Hybrid": WorkplaceType.HYBRID,
        "OnSite": WorkplaceType.ONSITE,
    }

    if value in mapping:
        return mapping[value]

    if source_job.is_remote is True:
        return WorkplaceType.REMOTE

    return WorkplaceType.UNKNOWN


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