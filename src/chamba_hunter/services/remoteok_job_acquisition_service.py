from dataclasses import dataclass
from datetime import datetime

from pydantic import ValidationError

from chamba_hunter.domain.common import utc_now
from chamba_hunter.domain.enums import (
    RunStatus,
    SourceType,
    WorkplaceType,
)
from chamba_hunter.domain.job_leads import JobLead
from chamba_hunter.domain.tracing import (
    Run,
    RunStep,
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
from chamba_hunter.schemas.inputs import CompanySeedInput
from chamba_hunter.services.company_import_service import (
    CompanyImportService,
)
from chamba_hunter.sources.remoteok_jobs import (
    REMOTEOK_API_URL,
    RemoteOkJobsClient,
    RemoteOkJobsFetch,
    RemoteOkNormalizedJob,
)


SOURCE_TYPE = SourceType.REMOTEOK
REMOTEOK_SCOPE_KEY = (
    "REMOTEOK_SOFTWARE_ARGENTINA_COMPATIBLE_V1"
)
REMOTEOK_STRATEGY = (
    "PUBLIC_API_SINGLE_FETCH_LOCAL_FILTER_V1"
)
REMOTEOK_SNAPSHOT_SEMANTICS = (
    "PARTIAL_FILTERED_SOURCE_RESPONSE"
)


@dataclass(frozen=True, slots=True)
class RemoteOkAcquisitionSummary:
    applied: bool
    run_id: int | None

    endpoint: str
    requests_made: int
    array_elements_received: int
    metadata_elements_skipped: int
    job_objects_parsed: int
    invalid_job_objects_skipped: int
    duplicates_removed: int
    technical_candidates: int
    technical_rejects: int
    explicit_geo_rejects: int
    unknown_geography: int
    potentially_eligible: int
    selected_after_max_jobs: int
    normalized_jobs: int
    unique_companies: int
    publication_dates_parsed: int
    publication_dates_from_date: int
    publication_dates_from_epoch_fallback: int
    publication_dates_missing: int
    top_retained_tags: dict[str, int]
    top_retained_locations: dict[str, int]
    ats_hints_detected: int
    max_jobs: int

    companies_created: int = 0
    companies_existing: int = 0
    jobs_created: int = 0
    jobs_updated: int = 0
    jobs_skipped_during_persistence: int = 0


class RemoteOkJobAcquisitionService:
    def __init__(
        self,
        *,
        client: RemoteOkJobsClient,
        company_import_service: (
            CompanyImportService | None
        ) = None,
        job_lead_repository: (
            JobLeadRepository | None
        ) = None,
        tracing_repository: (
            TracingRepository | None
        ) = None,
        state_repository: (
            SourceAcquisitionStateRepository
            | None
        ) = None,
    ) -> None:
        self.client = client
        self.company_import_service = (
            company_import_service
        )
        self.job_lead_repository = (
            job_lead_repository
        )
        self.tracing_repository = (
            tracing_repository
        )
        self.state_repository = state_repository

    def preview(
        self,
        *,
        max_jobs: int,
    ) -> RemoteOkAcquisitionSummary:
        fetch = self.client.fetch_jobs(
            max_jobs=max_jobs
        )

        return _summary_from_fetch(
            fetch=fetch,
            applied=False,
            run_id=None,
            max_jobs=max_jobs,
        )

    def run(
        self,
        *,
        max_jobs: int,
    ) -> RemoteOkAcquisitionSummary:
        self._require_apply_dependencies()

        assert self.tracing_repository is not None

        run = self.tracing_repository.add_run(
            Run(command="acquire_remoteok_jobs")
        )

        if run.id is None:
            raise RuntimeError("Run must have an id.")

        step = (
            self.tracing_repository
            .add_run_step(
                RunStep(
                    run_id=run.id,
                    step_name=(
                        "remoteok_job_acquisition"
                    ),
                    items_total=1,
                )
            )
        )

        if step.id is None:
            raise RuntimeError(
                "Run step must have an id."
            )

        started_at = utc_now()

        try:
            summary = self._acquire(
                run_id=run.id,
                max_jobs=max_jobs,
                started_at=started_at,
            )

            self.tracing_repository.finish_run_step(
                run_step_id=step.id,
                status=RunStatus.SUCCESS,
                items_success=1,
                items_failed=0,
                items_skipped=(
                    summary.invalid_job_objects_skipped
                    + summary.duplicates_removed
                    + summary.technical_rejects
                    + summary.explicit_geo_rejects
                    + summary.jobs_skipped_during_persistence
                ),
                metadata=_metadata(summary),
            )
            self.tracing_repository.finish_run(
                run_id=run.id,
                status=RunStatus.SUCCESS,
            )

            return summary

        except Exception as error:
            self.tracing_repository.finish_run_step(
                run_step_id=step.id,
                status=RunStatus.FAILED,
                items_success=0,
                items_failed=1,
                items_skipped=0,
                metadata={
                    "error_type": (
                        type(error).__name__
                    ),
                    "error_message": str(error),
                    "scope": REMOTEOK_SCOPE_KEY,
                    "strategy": REMOTEOK_STRATEGY,
                },
            )
            self.tracing_repository.finish_run(
                run_id=run.id,
                status=RunStatus.FAILED,
            )
            raise

    def _acquire(
        self,
        *,
        run_id: int,
        max_jobs: int,
        started_at: datetime,
    ) -> RemoteOkAcquisitionSummary:
        assert self.company_import_service is not None
        assert self.job_lead_repository is not None
        assert self.state_repository is not None

        fetch = self.client.fetch_jobs(
            max_jobs=max_jobs
        )
        seen_at = utc_now()

        leads: list[JobLead] = []
        seen_company_ids: set[int] = set()
        created_company_ids: set[int] = set()
        jobs_skipped_during_persistence = 0

        for source_job in fetch.jobs:
            try:
                import_result = (
                    self.company_import_service
                    .import_seed(
                        CompanySeedInput(
                            name=(
                                source_job
                                .company_name
                            ),
                            source_type=(
                                SOURCE_TYPE
                            ),
                            external_id=None,
                            source_url=(
                                source_job.job_url
                            ),
                        ),
                        source_metadata={
                            (
                                "broad_job_"
                                "acquisition"
                            ): True,
                            "scope": (
                                REMOTEOK_SCOPE_KEY
                            ),
                            "strategy": (
                                REMOTEOK_STRATEGY
                            ),
                            "snapshot_semantics": (
                                REMOTEOK_SNAPSHOT_SEMANTICS
                            ),
                        },
                    )
                )

                company = import_result.company

                if company.id is None:
                    raise RuntimeError(
                        "Imported company must "
                        "have an id."
                    )

                seen_company_ids.add(company.id)

                if import_result.created:
                    created_company_ids.add(
                        company.id
                    )

                leads.append(
                    _to_lead(
                        company_id=company.id,
                        source_job=source_job,
                        seen_at=seen_at,
                    )
                )

            except (
                ValidationError,
                ValueError,
                RuntimeError,
            ):
                jobs_skipped_during_persistence += 1

        counts = (
            self.job_lead_repository
            .upsert_source_jobs(
                source_type=SOURCE_TYPE,
                jobs=leads,
                seen_at=seen_at,
            )
        )
        finished_at = utc_now()

        summary = _summary_from_fetch(
            fetch=fetch,
            applied=True,
            run_id=run_id,
            max_jobs=max_jobs,
            companies_created=len(
                created_company_ids
            ),
            companies_existing=len(
                seen_company_ids
                - created_company_ids
            ),
            jobs_created=counts.created,
            jobs_updated=counts.updated,
            jobs_skipped_during_persistence=(
                jobs_skipped_during_persistence
            ),
        )

        self.state_repository.record_success(
            source_type=SOURCE_TYPE,
            scope_key=REMOTEOK_SCOPE_KEY,
            started_at=started_at,
            finished_at=finished_at,
            is_backfill=False,
            metadata=_metadata(summary),
        )

        return summary

    def _require_apply_dependencies(
        self,
    ) -> None:
        missing = [
            name
            for name, value in (
                (
                    "company_import_service",
                    self.company_import_service,
                ),
                (
                    "job_lead_repository",
                    self.job_lead_repository,
                ),
                (
                    "tracing_repository",
                    self.tracing_repository,
                ),
                (
                    "state_repository",
                    self.state_repository,
                ),
            )
            if value is None
        ]

        if missing:
            raise RuntimeError(
                "Apply mode requires: "
                + ", ".join(missing)
            )


def _to_lead(
    *,
    company_id: int,
    source_job: RemoteOkNormalizedJob,
    seen_at: datetime,
) -> JobLead:
    return JobLead(
        company_id=company_id,
        source_type=SOURCE_TYPE,
        external_id=source_job.external_id,
        title=source_job.title,
        description=source_job.description,
        location_text=source_job.location_text,
        workplace_type=WorkplaceType.REMOTE,
        employment_type=None,
        job_url=source_job.job_url,
        apply_url=source_job.apply_url,
        published_at=source_job.published_at,
        expires_at=None,
        first_seen_at=seen_at,
        last_seen_at=seen_at,
        is_active=True,
        raw_payload={
            **source_job.raw_payload,
            "_chamba_source_metadata": {
                "source": SOURCE_TYPE.value,
                "scope": REMOTEOK_SCOPE_KEY,
                "strategy": REMOTEOK_STRATEGY,
                "snapshot_semantics": (
                    REMOTEOK_SNAPSHOT_SEMANTICS
                ),
                "source_url": (
                    source_job.job_url
                ),
            },
        },
    )


def _summary_from_fetch(
    *,
    fetch: RemoteOkJobsFetch,
    applied: bool,
    run_id: int | None,
    max_jobs: int,
    companies_created: int = 0,
    companies_existing: int = 0,
    jobs_created: int = 0,
    jobs_updated: int = 0,
    jobs_skipped_during_persistence: int = 0,
) -> RemoteOkAcquisitionSummary:
    return RemoteOkAcquisitionSummary(
        applied=applied,
        run_id=run_id,
        endpoint=fetch.endpoint,
        requests_made=fetch.requests_made,
        array_elements_received=(
            fetch.array_elements_received
        ),
        metadata_elements_skipped=(
            fetch.metadata_elements_skipped
        ),
        job_objects_parsed=fetch.job_objects_parsed,
        invalid_job_objects_skipped=(
            fetch.invalid_job_objects_skipped
        ),
        duplicates_removed=fetch.duplicates_removed,
        technical_candidates=(
            fetch.technical_candidates
        ),
        technical_rejects=fetch.technical_rejects,
        explicit_geo_rejects=(
            fetch.explicit_geo_rejects
        ),
        unknown_geography=fetch.unknown_geography,
        potentially_eligible=(
            fetch.potentially_eligible
        ),
        selected_after_max_jobs=(
            fetch.selected_after_max_jobs
        ),
        normalized_jobs=fetch.normalized_jobs,
        unique_companies=fetch.unique_companies,
        publication_dates_parsed=(
            fetch.publication_dates_parsed
        ),
        publication_dates_from_date=(
            fetch.publication_dates_from_date
        ),
        publication_dates_from_epoch_fallback=(
            fetch.publication_dates_from_epoch_fallback
        ),
        publication_dates_missing=(
            fetch.publication_dates_missing
        ),
        top_retained_tags=dict(
            fetch.top_retained_tags
        ),
        top_retained_locations=dict(
            fetch.top_retained_locations
        ),
        ats_hints_detected=0,
        max_jobs=max_jobs,
        companies_created=companies_created,
        companies_existing=companies_existing,
        jobs_created=jobs_created,
        jobs_updated=jobs_updated,
        jobs_skipped_during_persistence=(
            jobs_skipped_during_persistence
        ),
    )


def _metadata(
    summary: RemoteOkAcquisitionSummary,
) -> dict:
    return {
        "scope": REMOTEOK_SCOPE_KEY,
        "strategy": REMOTEOK_STRATEGY,
        "snapshot_semantics": (
            REMOTEOK_SNAPSHOT_SEMANTICS
        ),
        "endpoint": REMOTEOK_API_URL,
        "requests_made": summary.requests_made,
        "max_jobs": summary.max_jobs,
        "array_elements_received": (
            summary.array_elements_received
        ),
        "metadata_elements_skipped": (
            summary.metadata_elements_skipped
        ),
        "job_objects_parsed": (
            summary.job_objects_parsed
        ),
        "invalid_job_objects_skipped": (
            summary.invalid_job_objects_skipped
        ),
        "duplicates_removed": (
            summary.duplicates_removed
        ),
        "technical_candidates": (
            summary.technical_candidates
        ),
        "technical_rejects": (
            summary.technical_rejects
        ),
        "explicit_geo_rejects": (
            summary.explicit_geo_rejects
        ),
        "unknown_geography": (
            summary.unknown_geography
        ),
        "potentially_eligible": (
            summary.potentially_eligible
        ),
        "selected_after_max_jobs": (
            summary.selected_after_max_jobs
        ),
        "normalized_jobs": (
            summary.normalized_jobs
        ),
        "unique_companies": (
            summary.unique_companies
        ),
        "publication_dates_parsed": (
            summary.publication_dates_parsed
        ),
        "publication_dates_from_date": (
            summary.publication_dates_from_date
        ),
        "publication_dates_from_epoch_fallback": (
            summary
            .publication_dates_from_epoch_fallback
        ),
        "publication_dates_missing": (
            summary.publication_dates_missing
        ),
        "top_retained_tags": (
            summary.top_retained_tags
        ),
        "top_retained_locations": (
            summary.top_retained_locations
        ),
        "ats_hints_detected": (
            summary.ats_hints_detected
        ),
        "jobs_created": summary.jobs_created,
        "jobs_updated": summary.jobs_updated,
        "jobs_skipped_during_persistence": (
            summary.jobs_skipped_during_persistence
        ),
        "companies_created": (
            summary.companies_created
        ),
        "companies_existing": (
            summary.companies_existing
        ),
    }
