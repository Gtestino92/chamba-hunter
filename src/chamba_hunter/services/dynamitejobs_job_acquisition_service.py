from dataclasses import dataclass
from datetime import datetime

from pydantic import ValidationError

from chamba_hunter.domain.common import utc_now
from chamba_hunter.domain.enums import (
    RunStatus,
    SourceType,
    WorkplaceType,
)
from chamba_hunter.domain.job_leads import (
    JobAtsHint,
    JobLead,
)
from chamba_hunter.domain.tracing import (
    Run,
    RunStep,
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
from chamba_hunter.schemas.inputs import CompanySeedInput
from chamba_hunter.services.company_import_service import (
    CompanyImportService,
)
from chamba_hunter.services.job_ats_hint_service import (
    ats_hint_from_url,
)
from chamba_hunter.sources.dynamitejobs import (
    DYNAMITEJOBS_INDEX_URLS,
    DynamiteJobsClient,
    DynamiteJobsFetch,
    DynamiteJobsPosting,
)


SOURCE_TYPE = SourceType.DYNAMITEJOBS
DYNAMITEJOBS_SCOPE_KEY = (
    "DYNAMITE_BACKEND_JAVA_FULLSTACK_V1"
)
DYNAMITEJOBS_STRATEGY = (
    "CURATED_REMOTE_HTML_PAGES"
)


@dataclass(frozen=True, slots=True)
class DynamiteJobsAcquisitionSummary:
    applied: bool
    run_id: int | None

    index_pages_fetched: int
    links_discovered: int
    unique_jobs: int
    duplicates_removed: int
    details_attempted: int
    details_succeeded: int
    details_failed: int
    closed_skipped: int
    parse_failures: int
    normalized: int
    skipped: int
    unique_companies: int
    ats_hints_detected: int
    max_jobs: int
    detail_workers: int

    companies_created: int = 0
    companies_existing: int = 0
    jobs_created: int = 0
    jobs_updated: int = 0
    ats_hints_created: int = 0


class DynamiteJobsJobAcquisitionService:
    def __init__(
        self,
        *,
        client: DynamiteJobsClient,
        company_import_service: (
            CompanyImportService | None
        ) = None,
        job_lead_repository: (
            JobLeadRepository | None
        ) = None,
        ats_hint_repository: (
            JobAtsHintRepository | None
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
        self.ats_hint_repository = (
            ats_hint_repository
        )
        self.tracing_repository = (
            tracing_repository
        )
        self.state_repository = (
            state_repository
        )

    def preview(
        self,
        *,
        max_jobs: int,
        detail_workers: int,
    ) -> DynamiteJobsAcquisitionSummary:
        fetch = self.client.fetch_jobs(
            max_jobs=max_jobs,
            detail_workers=detail_workers,
        )

        return _summary_from_fetch(
            fetch=fetch,
            applied=False,
            run_id=None,
            max_jobs=max_jobs,
            detail_workers=detail_workers,
            ats_hints_detected=(
                _detect_ats_hints(
                    fetch.jobs
                )
            ),
            skipped=(
                fetch.closed_skipped
                + fetch.parse_failures
                + fetch.details_failed
            ),
        )

    def run(
        self,
        *,
        max_jobs: int,
        detail_workers: int,
    ) -> DynamiteJobsAcquisitionSummary:
        self._require_apply_dependencies()

        assert self.tracing_repository is not None

        run = self.tracing_repository.add_run(
            Run(
                command=(
                    "acquire_dynamite_jobs"
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
                        "dynamitejobs_"
                        "job_acquisition"
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
                detail_workers=detail_workers,
                started_at=started_at,
            )

            self.tracing_repository.finish_run_step(
                run_step_id=step.id,
                status=RunStatus.SUCCESS,
                items_success=1,
                items_failed=0,
                items_skipped=(
                    summary.skipped
                ),
                metadata=(
                    _metadata(summary)
                ),
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
                    "error_message": str(
                        error
                    ),
                    "scope": (
                        DYNAMITEJOBS_SCOPE_KEY
                    ),
                    "strategy": (
                        DYNAMITEJOBS_STRATEGY
                    ),
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
        detail_workers: int,
        started_at: datetime,
    ) -> DynamiteJobsAcquisitionSummary:
        assert self.company_import_service is not None
        assert self.job_lead_repository is not None
        assert self.ats_hint_repository is not None
        assert self.state_repository is not None

        fetch = self.client.fetch_jobs(
            max_jobs=max_jobs,
            detail_workers=detail_workers,
        )
        seen_at = utc_now()

        leads: list[JobLead] = []
        seen_company_ids: set[int] = set()
        created_company_ids: set[int] = set()
        skipped = (
            fetch.closed_skipped
            + fetch.parse_failures
            + fetch.details_failed
        )

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
                            website_url=(
                                source_job
                                .company_website_url
                            ),
                            source_type=(
                                SOURCE_TYPE
                            ),
                            external_id=(
                                source_job
                                .company_slug
                            ),
                            source_url=(
                                source_job
                                .canonical_url
                            ),
                        ),
                        source_metadata={
                            (
                                "broad_job_"
                                "acquisition"
                            ): True,
                            "scope": (
                                DYNAMITEJOBS_SCOPE_KEY
                            ),
                            "strategy": (
                                DYNAMITEJOBS_STRATEGY
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
                skipped += 1

        counts = (
            self.job_lead_repository
            .upsert_source_jobs(
                source_type=SOURCE_TYPE,
                jobs=leads,
                seen_at=seen_at,
            )
        )

        ats_hints_created = (
            self._record_hints(leads)
        )
        finished_at = utc_now()

        summary = _summary_from_fetch(
            fetch=fetch,
            applied=True,
            run_id=run_id,
            max_jobs=max_jobs,
            detail_workers=detail_workers,
            skipped=skipped,
            unique_companies=len(
                {
                    job.company_name.casefold()
                    for job in fetch.jobs
                }
            ),
            ats_hints_detected=(
                _detect_ats_hints(
                    fetch.jobs
                )
            ),
            companies_created=len(
                created_company_ids
            ),
            companies_existing=len(
                seen_company_ids
                - created_company_ids
            ),
            jobs_created=counts.created,
            jobs_updated=counts.updated,
            ats_hints_created=(
                ats_hints_created
            ),
        )

        self.state_repository.record_success(
            source_type=SOURCE_TYPE,
            scope_key=(
                DYNAMITEJOBS_SCOPE_KEY
            ),
            started_at=started_at,
            finished_at=finished_at,
            is_backfill=False,
            metadata=_metadata(summary),
        )

        return summary

    def _record_hints(
        self,
        leads: list[JobLead],
    ) -> int:
        assert self.job_lead_repository is not None
        assert self.ats_hint_repository is not None

        hints: list[JobAtsHint] = []
        seen_hint_keys: set[
            tuple[int, str, str, str]
        ] = set()

        for lead in leads:
            lead_id = (
                self.job_lead_repository
                .get_id(
                    source_type=(
                        lead.source_type
                    ),
                    external_id=(
                        lead.external_id
                    ),
                )
            )

            if lead_id is None:
                raise RuntimeError(
                    "Persisted job lead could "
                    "not be reloaded."
                )

            for url in (
                lead.apply_url,
                lead.job_url,
            ):
                if url is None:
                    continue

                hint = ats_hint_from_url(
                    job_lead_id=lead_id,
                    company_id=(
                        lead.company_id
                    ),
                    url=url,
                )

                if hint is None:
                    continue

                key = (
                    hint.job_lead_id,
                    hint.provider.value,
                    hint.external_identifier,
                    hint.source_url,
                )

                if key in seen_hint_keys:
                    continue

                seen_hint_keys.add(key)
                hints.append(hint)

        return self.ats_hint_repository.add_many(
            hints
        )

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
                    "ats_hint_repository",
                    self.ats_hint_repository,
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
    source_job: DynamiteJobsPosting,
    seen_at: datetime,
) -> JobLead:
    return JobLead(
        company_id=company_id,
        source_type=SOURCE_TYPE,
        external_id=(
            source_job.external_id
        ),
        title=source_job.title,
        description=(
            source_job.description
        ),
        location_text=(
            source_job.location_text
        ),
        workplace_type=(
            WorkplaceType.REMOTE
        ),
        employment_type=(
            source_job.employment_type
        ),
        job_url=(
            source_job.canonical_url
        ),
        apply_url=(
            source_job.apply_url
        ),
        published_at=(
            source_job.published_at
        ),
        expires_at=(
            source_job.expires_at
        ),
        first_seen_at=seen_at,
        last_seen_at=seen_at,
        is_active=True,
        raw_payload=(
            source_job.raw_payload
        ),
    )


def _detect_ats_hints(
    jobs: list[DynamiteJobsPosting],
) -> int:
    seen: set[tuple[str, str, str]] = set()

    for job in jobs:
        for url in (
            job.apply_url,
            job.canonical_url,
        ):
            if url is None:
                continue

            hint = ats_hint_from_url(
                job_lead_id=0,
                company_id=0,
                url=url,
            )

            if hint is None:
                continue

            seen.add(
                (
                    hint.provider.value,
                    hint.external_identifier,
                    hint.source_url,
                )
            )

    return len(seen)


def _summary_from_fetch(
    *,
    fetch: DynamiteJobsFetch,
    applied: bool,
    run_id: int | None,
    skipped: int,
    ats_hints_detected: int,
    max_jobs: int,
    detail_workers: int,
    unique_companies: int | None = None,
    companies_created: int = 0,
    companies_existing: int = 0,
    jobs_created: int = 0,
    jobs_updated: int = 0,
    ats_hints_created: int = 0,
) -> DynamiteJobsAcquisitionSummary:
    return DynamiteJobsAcquisitionSummary(
        applied=applied,
        run_id=run_id,
        index_pages_fetched=(
            fetch.index_pages_fetched
        ),
        links_discovered=(
            fetch.links_discovered
        ),
        unique_jobs=fetch.unique_jobs,
        duplicates_removed=(
            fetch.duplicates_removed
        ),
        details_attempted=(
            fetch.details_attempted
        ),
        details_succeeded=(
            fetch.details_succeeded
        ),
        details_failed=(
            fetch.details_failed
        ),
        closed_skipped=(
            fetch.closed_skipped
        ),
        parse_failures=(
            fetch.parse_failures
        ),
        normalized=len(fetch.jobs),
        skipped=skipped,
        unique_companies=(
            unique_companies
            if unique_companies is not None
            else len(
                {
                    job.company_name.casefold()
                    for job in fetch.jobs
                }
            )
        ),
        ats_hints_detected=(
            ats_hints_detected
        ),
        max_jobs=max_jobs,
        detail_workers=detail_workers,
        companies_created=(
            companies_created
        ),
        companies_existing=(
            companies_existing
        ),
        jobs_created=jobs_created,
        jobs_updated=jobs_updated,
        ats_hints_created=(
            ats_hints_created
        ),
    )


def _metadata(
    summary: DynamiteJobsAcquisitionSummary,
) -> dict:
    return {
        "scope": DYNAMITEJOBS_SCOPE_KEY,
        "strategy": DYNAMITEJOBS_STRATEGY,
        "snapshot_semantics": (
            "PARTIAL_CURATED_SOURCE_RESPONSE"
        ),
        "index_pages": list(
            DYNAMITEJOBS_INDEX_URLS
        ),
        "index_pages_fetched": (
            summary.index_pages_fetched
        ),
        "links_discovered": (
            summary.links_discovered
        ),
        "unique_jobs": summary.unique_jobs,
        "duplicates_removed": (
            summary.duplicates_removed
        ),
        "max_jobs": summary.max_jobs,
        "detail_workers": (
            summary.detail_workers
        ),
        "details_attempted": (
            summary.details_attempted
        ),
        "details_succeeded": (
            summary.details_succeeded
        ),
        "details_failed": (
            summary.details_failed
        ),
        "closed_skipped": (
            summary.closed_skipped
        ),
        "parse_failures": (
            summary.parse_failures
        ),
        "normalized": summary.normalized,
        "skipped": summary.skipped,
        "unique_companies": (
            summary.unique_companies
        ),
        "ats_hints_detected": (
            summary.ats_hints_detected
        ),
        "jobs_created": (
            summary.jobs_created
        ),
        "jobs_updated": (
            summary.jobs_updated
        ),
        "companies_created": (
            summary.companies_created
        ),
        "companies_existing": (
            summary.companies_existing
        ),
        "ats_hints_created": (
            summary.ats_hints_created
        ),
    }
