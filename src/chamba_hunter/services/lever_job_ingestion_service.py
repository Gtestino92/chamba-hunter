from dataclasses import dataclass, field
from datetime import datetime

import httpx

from chamba_hunter.domain.common import (
    utc_now,
)
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
from chamba_hunter.sources.lever import (
    LeverClient,
    LeverJob,
)


@dataclass(frozen=True, slots=True)
class LeverJobSyncResult:
    company_id: int
    company_ats_id: int
    site_name: str

    status: RunStatus
    http_status: int | None

    jobs_received: int = 0
    jobs_created: int = 0
    jobs_updated: int = 0
    jobs_deactivated: int = 0

    error_type: str | None = None
    error_message: str | None = None


@dataclass(slots=True)
class LeverJobIngestionSummary:
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
        LeverJobSyncResult
    ] = field(
        default_factory=list
    )


class LeverJobIngestionService:
    def __init__(
        self,
        lever_client: LeverClient,
        company_ats_repository: (
            CompanyAtsRepository
        ),
        job_repository: JobRepository,
        tracing_repository: (
            TracingRepository
        ),
    ) -> None:
        self.lever_client = lever_client
        self.company_ats_repository = (
            company_ats_repository
        )
        self.job_repository = (
            job_repository
        )
        self.tracing_repository = (
            tracing_repository
        )

    def run(
        self,
        company_ats_records: list[
            CompanyAts
        ],
    ) -> LeverJobIngestionSummary:
        run = (
            self.tracing_repository
            .add_run(
                Run(
                    command=(
                        "sync_lever_jobs"
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
                        "lever_job_ingestion"
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
            LeverJobIngestionSummary(
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
                items_failed=(
                    summary.failed
                ),
                items_skipped=(
                    summary.skipped
                ),
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
        summary: (
            LeverJobIngestionSummary
        ),
    ) -> None:
        if company_ats.id is None:
            summary.skipped += 1
            return

        site_name = (
            company_ats
            .external_identifier
        )

        if site_name is None:
            summary.skipped += 1
            return

        ats_sync = (
            self.tracing_repository
            .add_ats_sync(
                AtsSync(
                    run_step_id=(
                        run_step_id
                    ),
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
            fetch = (
                self.lever_client
                .fetch_jobs(
                    site_name
                )
            )

            http_status = fetch.http_status
            jobs_received = fetch.total

            seen_at = utc_now()

            jobs = [
                _to_job(
                    company_ats=(
                        company_ats
                    ),
                    source_job=(
                        source_job
                    ),
                    seen_at=seen_at,
                )
                for source_job
                in fetch.jobs
            ]

            counts = (
                self.job_repository
                .sync_board_jobs(
                    company_ats=(
                        company_ats
                    ),
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
                    ats_sync_id=(
                        ats_sync.id
                    ),
                    status=(
                        RunStatus.SUCCESS
                    ),
                    http_status=(
                        fetch.http_status
                    ),
                    jobs_received=(
                        fetch.total
                    ),
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
                site_name=site_name,
                fetch_total=fetch.total,
                counts=counts,
                http_status=(
                    fetch.http_status
                ),
                summary=summary,
            )

        except (
            httpx.HTTPStatusError
        ) as error:
            self._record_failure(
                ats_sync_id=ats_sync.id,
                company_ats=company_ats,
                site_name=site_name,
                http_status=(
                    error.response
                    .status_code
                ),
                jobs_received=0,
                error_type="HTTP_ERROR",
                error_message=str(error),
                summary=summary,
            )

        except (
            httpx.RequestError
        ) as error:
            self._record_failure(
                ats_sync_id=ats_sync.id,
                company_ats=company_ats,
                site_name=site_name,
                http_status=None,
                jobs_received=0,
                error_type=(
                    "REQUEST_ERROR"
                ),
                error_message=str(error),
                summary=summary,
            )

        except Exception as error:
            self._record_failure(
                ats_sync_id=ats_sync.id,
                company_ats=company_ats,
                site_name=site_name,
                http_status=http_status,
                jobs_received=(
                    jobs_received
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
        site_name: str,
        fetch_total: int,
        counts: JobSyncCounts,
        http_status: int,
        summary: (
            LeverJobIngestionSummary
        ),
    ) -> None:
        if company_ats.id is None:
            raise ValueError(
                "Company ATS must have "
                "an id."
            )

        summary.succeeded += 1
        summary.jobs_received += (
            fetch_total
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
            LeverJobSyncResult(
                company_id=(
                    company_ats.company_id
                ),
                company_ats_id=(
                    company_ats.id
                ),
                site_name=site_name,
                status=RunStatus.SUCCESS,
                http_status=http_status,
                jobs_received=(
                    fetch_total
                ),
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

    def _record_failure(
        self,
        ats_sync_id: int,
        company_ats: CompanyAts,
        site_name: str,
        http_status: int | None,
        jobs_received: int,
        error_type: str,
        error_message: str,
        summary: (
            LeverJobIngestionSummary
        ),
    ) -> None:
        if company_ats.id is None:
            raise ValueError(
                "Company ATS must have "
                "an id."
            )

        (
            self.tracing_repository
            .finish_ats_sync(
                ats_sync_id=(
                    ats_sync_id
                ),
                status=(
                    RunStatus.FAILED
                ),
                http_status=(
                    http_status
                ),
                jobs_received=(
                    jobs_received
                ),
                jobs_created=0,
                jobs_updated=0,
                jobs_deactivated=0,
                error_type=error_type,
                error_message=(
                    error_message
                ),
            )
        )

        summary.failed += 1
        summary.jobs_received += (
            jobs_received
        )

        summary.results.append(
            LeverJobSyncResult(
                company_id=(
                    company_ats.company_id
                ),
                company_ats_id=(
                    company_ats.id
                ),
                site_name=site_name,
                status=RunStatus.FAILED,
                http_status=http_status,
                jobs_received=(
                    jobs_received
                ),
                error_type=error_type,
                error_message=(
                    error_message
                ),
            )
        )


def _to_job(
    company_ats: CompanyAts,
    source_job: LeverJob,
    seen_at: datetime,
) -> Job:
    if company_ats.id is None:
        raise ValueError(
            "Company ATS must have "
            "an id."
        )

    external_id = _required_text(
        source_job.id,
        field_name="id",
    )

    title = _required_text(
        source_job.text,
        field_name="text",
    )

    categories = (
        source_job.categories
    )

    employment_type = None

    if categories is not None:
        employment_type = (
            _clean_text(
                categories.commitment
            )
        )

    return Job(
        company_id=(
            company_ats.company_id
        ),
        company_ats_id=(
            company_ats.id
        ),
        external_id=external_id,
        title=title,
        description=_description_text(
            source_job
        ),
        location_text=(
            _location_text(
                source_job
            )
        ),
        workplace_type=(
            _workplace_type(
                source_job
            )
        ),
        employment_type=(
            employment_type
        ),
        job_url=_clean_text(
            source_job.hosted_url
        ),
        apply_url=_clean_text(
            source_job.apply_url
        ),
        published_at=None,
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


def _description_text(
    source_job: LeverJob,
) -> str | None:
    parts: list[str] = []

    for value in (
        source_job.description_plain,
        source_job.additional_plain,
    ):
        cleaned = _clean_text(value)

        if (
            cleaned is not None
            and cleaned not in parts
        ):
            parts.append(cleaned)

    if not parts:
        return None

    return "\n\n".join(parts)


def _location_text(
    source_job: LeverJob,
) -> str | None:
    categories = (
        source_job.categories
    )

    if categories is None:
        return None

    candidates = [
        *categories.all_locations,
        categories.location,
    ]

    locations: list[str] = []

    for value in candidates:
        cleaned = _clean_text(value)

        if (
            cleaned is not None
            and cleaned not in locations
        ):
            locations.append(
                cleaned
            )

    if not locations:
        return None

    return "; ".join(locations)


def _workplace_type(
    source_job: LeverJob,
) -> WorkplaceType:
    value = _clean_text(
        source_job.workplace_type
    )

    if value is None:
        return WorkplaceType.UNKNOWN

    mapping = {
        "remote": (
            WorkplaceType.REMOTE
        ),
        "hybrid": (
            WorkplaceType.HYBRID
        ),
        "on-site": (
            WorkplaceType.ONSITE
        ),
        "unspecified": (
            WorkplaceType.UNKNOWN
        ),
    }

    return mapping.get(
        value.casefold(),
        WorkplaceType.UNKNOWN,
    )


def _required_text(
    value: str,
    field_name: str,
) -> str:
    cleaned = _clean_text(value)

    if cleaned is None:
        raise ValueError(
            "Lever returned an empty "
            f"{field_name}."
        )

    return cleaned


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
