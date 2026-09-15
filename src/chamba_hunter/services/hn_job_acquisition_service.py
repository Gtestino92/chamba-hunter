from dataclasses import dataclass
from datetime import datetime

from chamba_hunter.domain.common import utc_now
from chamba_hunter.domain.enums import (
    RunStatus,
    SourceType,
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
from chamba_hunter.sources.hn_who_is_hiring import (
    HnHiringPost,
    HnThreadFetch,
    HnWhoIsHiringClient,
)


HN_WHO_IS_HIRING_SCOPE_KEY = "HN_WHO_IS_HIRING"


@dataclass(slots=True)
class HnJobAcquisitionSummary:
    run_id: int
    started_at: datetime
    finished_at: datetime | None = None

    thread_id: int | None = None
    thread_title: str | None = None
    thread_published_at: datetime | None = None

    direct_comments_discovered: int = 0
    comments_fetched: int = 0
    deleted_dead_skipped: int = 0
    invalid_skipped: int = 0
    fetch_failures: int = 0

    companies_resolved: int = 0
    company_resolution_failures: int = 0
    companies_created: int = 0
    leads_normalized: int = 0

    jobs_created: int = 0
    jobs_updated: int = 0


class HnJobAcquisitionService:
    def __init__(
        self,
        *,
        client: HnWhoIsHiringClient,
        company_import_service: CompanyImportService,
        job_lead_repository: JobLeadRepository,
        state_repository: (
            SourceAcquisitionStateRepository
        ),
        tracing_repository: TracingRepository,
    ) -> None:
        self.client = client
        self.company_import_service = (
            company_import_service
        )
        self.job_lead_repository = (
            job_lead_repository
        )
        self.state_repository = (
            state_repository
        )
        self.tracing_repository = (
            tracing_repository
        )

    def run(
        self,
        *,
        thread_id: int | None = None,
        limit: int | None = None,
    ) -> HnJobAcquisitionSummary:
        if limit is not None and limit < 1:
            raise ValueError(
                "limit must be at least 1."
            )

        started_at = utc_now()
        run = self.tracing_repository.add_run(
            Run(
                command="acquire_hn_jobs"
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
                        "hn_who_is_hiring_acquisition"
                    ),
                )
            )
        )

        if step.id is None:
            raise RuntimeError(
                "Run step must have an id."
            )

        summary = HnJobAcquisitionSummary(
            run_id=run.id,
            started_at=started_at,
        )

        try:
            fetch = self._fetch(
                thread_id=thread_id,
                limit=limit,
            )
            self._apply_fetch(
                fetch=fetch,
                seen_at=utc_now(),
                summary=summary,
            )

            finished_at = utc_now()
            summary.finished_at = finished_at

            status = _summary_status(
                summary
            )
            metadata = _summary_metadata(
                summary
            )

            self.tracing_repository.finish_run_step(
                run_step_id=step.id,
                status=status,
                items_success=(
                    summary.leads_normalized
                ),
                items_failed=(
                    summary.fetch_failures
                    + summary
                    .company_resolution_failures
                ),
                items_skipped=(
                    summary.deleted_dead_skipped
                    + summary.invalid_skipped
                ),
                metadata=metadata,
            )
            self.tracing_repository.finish_run(
                run_id=run.id,
                status=status,
            )

            if _should_record_success(
                summary
            ):
                self.state_repository.record_success(
                    source_type=(
                        SourceType.HACKERNEWS
                    ),
                    scope_key=(
                        HN_WHO_IS_HIRING_SCOPE_KEY
                    ),
                    started_at=started_at,
                    finished_at=finished_at,
                    is_backfill=False,
                    metadata=metadata,
                )

            return summary

        except Exception as exc:
            finished_at = utc_now()
            summary.finished_at = finished_at
            metadata = _summary_metadata(
                summary
            ) | {
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
            self.tracing_repository.finish_run_step(
                run_step_id=step.id,
                status=RunStatus.FAILED,
                items_success=summary.leads_normalized,
                items_failed=1,
                items_skipped=(
                    summary.deleted_dead_skipped
                    + summary.invalid_skipped
                ),
                metadata=metadata,
            )
            self.tracing_repository.finish_run(
                run_id=run.id,
                status=RunStatus.FAILED,
            )
            raise

    def _fetch(
        self,
        *,
        thread_id: int | None,
        limit: int | None,
    ) -> HnThreadFetch:
        if thread_id is not None:
            return self.client.fetch_thread(
                thread_id,
                limit=limit,
            )

        return self.client.fetch_latest_thread(
            limit=limit,
        )

    def _apply_fetch(
        self,
        *,
        fetch: HnThreadFetch,
        seen_at: datetime,
        summary: HnJobAcquisitionSummary,
    ) -> None:
        summary.thread_id = fetch.thread.id
        summary.thread_title = fetch.thread.title
        summary.thread_published_at = (
            fetch.thread.posted_at
        )
        summary.direct_comments_discovered = (
            fetch.direct_comments_discovered
        )
        summary.comments_fetched = (
            fetch.comments_fetched
        )
        summary.deleted_dead_skipped = (
            fetch.deleted_dead_skipped
        )
        summary.invalid_skipped = (
            fetch.invalid_skipped
        )
        summary.fetch_failures = (
            fetch.fetch_failures
        )

        leads: list[JobLead] = []

        for post in fetch.posts:
            lead = self._post_to_lead(
                post=post,
                seen_at=seen_at,
                summary=summary,
            )

            if lead is not None:
                leads.append(
                    lead
                )

        counts = (
            self.job_lead_repository
            .upsert_source_jobs(
                source_type=SourceType.HACKERNEWS,
                jobs=leads,
                seen_at=seen_at,
            )
        )
        summary.leads_normalized = len(
            leads
        )
        summary.jobs_created = (
            counts.created
        )
        summary.jobs_updated = (
            counts.updated
        )

    def _post_to_lead(
        self,
        *,
        post: HnHiringPost,
        seen_at: datetime,
        summary: HnJobAcquisitionSummary,
    ) -> JobLead | None:
        try:
            result = (
                self.company_import_service
                .import_seed(
                    CompanySeedInput(
                        name=post.company_name,
                        website_url=(
                            post.website_url
                        ),
                        careers_url=(
                            post.apply_url
                            if _looks_like_careers_url(
                                post.apply_url
                            )
                            else None
                        ),
                        source_type=(
                            SourceType.HACKERNEWS
                        ),
                        external_id=str(
                            post.comment_id
                        ),
                        source_url=post.source_url,
                    ),
                    source_metadata={
                        "thread_id": (
                            post.thread_id
                        ),
                        "thread_title": (
                            post.thread_title
                        ),
                        "comment_id": (
                            post.comment_id
                        ),
                        "comment_author": (
                            post.author
                        ),
                        "posted_at": (
                            post.posted_at
                            .isoformat()
                            if post.posted_at
                            is not None
                            else None
                        ),
                        "extracted_urls": list(
                            post.extracted_urls
                        ),
                        "apply_url": (
                            post.apply_url
                        ),
                        "website_url": (
                            post.website_url
                        ),
                    },
                )
            )

        except Exception:
            summary.company_resolution_failures += 1
            return None

        if result.company.id is None:
            summary.company_resolution_failures += 1
            return None

        summary.companies_resolved += 1

        if result.created:
            summary.companies_created += 1

        return JobLead(
            company_id=result.company.id,
            source_type=SourceType.HACKERNEWS,
            external_id=str(
                post.comment_id
            ),
            title=post.title,
            description=post.description,
            location_text=post.location_text,
            workplace_type=post.workplace_type,
            employment_type=post.employment_type,
            job_url=post.source_url,
            apply_url=post.apply_url,
            published_at=post.posted_at,
            source_updated_at=None,
            first_seen_at=seen_at,
            last_seen_at=seen_at,
            is_active=True,
            raw_payload=post.raw_payload,
        )


def _looks_like_careers_url(
    url: str | None,
) -> bool:
    if url is None:
        return False

    lowered = url.casefold()

    return any(
        token in lowered
        for token in (
            "career",
            "job",
            "apply",
        )
    )


def _summary_status(
    summary: HnJobAcquisitionSummary,
) -> RunStatus:
    if (
        summary.fetch_failures == 0
        and summary.company_resolution_failures == 0
    ):
        return RunStatus.SUCCESS

    if summary.leads_normalized > 0:
        return RunStatus.PARTIAL

    return RunStatus.FAILED


def _should_record_success(
    summary: HnJobAcquisitionSummary,
) -> bool:
    if summary.thread_id is None:
        return False

    if summary.direct_comments_discovered == 0:
        return True

    return (
        summary.comments_fetched > 0
        or summary.leads_normalized > 0
    )


def _summary_metadata(
    summary: HnJobAcquisitionSummary,
) -> dict:
    return {
        "thread_id": summary.thread_id,
        "thread_title": summary.thread_title,
        "thread_published_at": (
            summary.thread_published_at.isoformat()
            if summary.thread_published_at
            is not None
            else None
        ),
        "direct_comments_discovered": (
            summary.direct_comments_discovered
        ),
        "comments_fetched": (
            summary.comments_fetched
        ),
        "deleted_dead_skipped": (
            summary.deleted_dead_skipped
        ),
        "invalid_skipped": (
            summary.invalid_skipped
        ),
        "fetch_failures": (
            summary.fetch_failures
        ),
        "companies_resolved": (
            summary.companies_resolved
        ),
        "company_resolution_failures": (
            summary.company_resolution_failures
        ),
        "companies_created": (
            summary.companies_created
        ),
        "leads_normalized": (
            summary.leads_normalized
        ),
        "jobs_created": (
            summary.jobs_created
        ),
        "jobs_updated": (
            summary.jobs_updated
        ),
    }
