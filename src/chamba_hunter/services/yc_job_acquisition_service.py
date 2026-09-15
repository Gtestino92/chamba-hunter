from dataclasses import dataclass, field
from datetime import datetime

from chamba_hunter.domain.common import utc_now
from chamba_hunter.domain.enums import (
    RunStatus,
    SourceType,
)
from chamba_hunter.domain.job_leads import JobLead
from chamba_hunter.domain.models import CompanySource
from chamba_hunter.domain.tracing import (
    Run,
    RunStep,
)
from chamba_hunter.repositories.company_source_repository import (
    CompanySourceRepository,
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
from chamba_hunter.sources.yc_jobs import (
    YcCompanyJobsFetch,
    YcJobsClient,
)


YC_PUBLIC_JOBS_SCOPE_KEY = "YC_PUBLIC_JOBS"


@dataclass(frozen=True, slots=True)
class YcCompanyJobsResult:
    company_id: int
    company_slug: str
    status: RunStatus

    job_links_discovered: int = 0
    details_fetched: int = 0
    normalized: int = 0
    skipped: int = 0

    jobs_created: int = 0
    jobs_updated: int = 0

    error_type: str | None = None
    error_message: str | None = None


@dataclass(slots=True)
class YcJobAcquisitionSummary:
    run_id: int
    started_at: datetime
    finished_at: datetime | None = None

    companies_considered: int = 0
    companies_skipped_not_hiring: int = 0
    companies_fetched: int = 0
    companies_failed: int = 0

    job_links_discovered: int = 0
    details_fetched: int = 0
    detail_failures: int = 0
    normalized: int = 0
    skipped: int = 0

    jobs_created: int = 0
    jobs_updated: int = 0

    requested_slugs: tuple[
        str,
        ...
    ] = ()
    missing_slugs: tuple[
        str,
        ...
    ] = ()

    results: list[
        YcCompanyJobsResult
    ] = field(default_factory=list)


class YcJobAcquisitionService:
    def __init__(
        self,
        *,
        client: YcJobsClient,
        company_source_repository: (
            CompanySourceRepository
        ),
        job_lead_repository: (
            JobLeadRepository
        ),
        state_repository: (
            SourceAcquisitionStateRepository
        ),
        tracing_repository: TracingRepository,
    ) -> None:
        self.client = client
        self.company_source_repository = (
            company_source_repository
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
        limit: int | None = None,
        include_not_hiring: bool = False,
        slugs: tuple[str, ...] = (),
    ) -> YcJobAcquisitionSummary:
        if limit is not None and limit < 1:
            raise ValueError(
                "limit must be at least 1."
            )

        started_at = utc_now()
        requested_slugs = _normalize_requested_slugs(
            slugs
        )
        sources, missing_slugs = self._target_sources(
            limit=limit,
            requested_slugs=requested_slugs,
        )

        run = self.tracing_repository.add_run(
            Run(
                command="acquire_yc_jobs"
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
                        "yc_public_jobs_acquisition"
                    ),
                    items_total=len(sources),
                )
            )
        )

        if step.id is None:
            raise RuntimeError(
                "Run step must have an id."
            )

        summary = YcJobAcquisitionSummary(
            run_id=run.id,
            started_at=started_at,
            companies_considered=len(sources),
            requested_slugs=requested_slugs,
            missing_slugs=missing_slugs,
        )

        seen_at = utc_now()

        for source in sources:
            slug = _source_slug(source)

            if slug is None:
                summary.skipped += 1
                continue

            if (
                not requested_slugs
                and not include_not_hiring
                and _is_explicitly_not_hiring(
                    source
                )
            ):
                (
                    summary
                    .companies_skipped_not_hiring
                ) += 1
                continue

            self._process_company(
                source=source,
                slug=slug,
                seen_at=seen_at,
                summary=summary,
            )

        finished_at = utc_now()
        summary.finished_at = finished_at

        status = _summary_status(
            summary
        )

        self.tracing_repository.finish_run_step(
            run_step_id=step.id,
            status=status,
            items_success=summary.companies_fetched,
            items_failed=summary.companies_failed,
            items_skipped=(
                summary.companies_skipped_not_hiring
                + summary.skipped
            ),
            metadata=_summary_metadata(
                summary
            ),
        )
        self.tracing_repository.finish_run(
            run_id=run.id,
            status=status,
        )

        if _should_record_success(
            summary
        ):
            self.state_repository.record_success(
                source_type=SourceType.YC,
                scope_key=(
                    YC_PUBLIC_JOBS_SCOPE_KEY
                ),
                started_at=started_at,
                finished_at=finished_at,
                is_backfill=False,
                metadata=_summary_metadata(
                    summary
                ),
            )

        return summary

    def _target_sources(
        self,
        *,
        limit: int | None,
        requested_slugs: tuple[str, ...],
    ) -> tuple[
        list[CompanySource],
        tuple[str, ...],
    ]:
        sources = (
            self.company_source_repository
            .list_active_by_source_type(
                SourceType.YC
            )
        )

        usable = [
            source
            for source in sources
            if _source_slug(source) is not None
        ]

        missing_slugs: tuple[
            str,
            ...
        ] = ()

        if requested_slugs:
            requested_keys = {
                _slug_key(slug)
                for slug in requested_slugs
            }
            found_keys: set[str] = set()

            filtered: list[
                CompanySource
            ] = []

            for source in usable:
                slug = _source_slug(source)

                if slug is None:
                    continue

                key = _slug_key(slug)

                if key not in requested_keys:
                    continue

                found_keys.add(key)
                filtered.append(source)

            missing_slugs = tuple(
                slug
                for slug in requested_slugs
                if _slug_key(slug)
                not in found_keys
            )
            usable = filtered

        return (
            (
                usable[:limit]
                if limit is not None
                else usable
            ),
            missing_slugs,
        )

    def _process_company(
        self,
        *,
        source: CompanySource,
        slug: str,
        seen_at: datetime,
        summary: YcJobAcquisitionSummary,
    ) -> None:
        try:
            fetch = (
                self.client
                .fetch_company_jobs(slug)
            )

            leads = [
                _posting_to_lead(
                    company_id=source.company_id,
                    posting=posting,
                    seen_at=seen_at,
                )
                for posting in fetch.jobs
            ]

            counts = (
                self.job_lead_repository
                .upsert_source_jobs(
                    source_type=SourceType.YC,
                    jobs=leads,
                    seen_at=seen_at,
                )
            )

            self._record_fetch_success(
                source=source,
                slug=slug,
                fetch=fetch,
                counts_created=counts.created,
                counts_updated=counts.updated,
                summary=summary,
            )

        except Exception as exc:
            summary.companies_failed += 1
            summary.results.append(
                YcCompanyJobsResult(
                    company_id=(
                        source.company_id
                    ),
                    company_slug=slug,
                    status=RunStatus.FAILED,
                    error_type=(
                        type(exc).__name__
                    ),
                    error_message=str(exc),
                )
            )

    def _record_fetch_success(
        self,
        *,
        source: CompanySource,
        slug: str,
        fetch: YcCompanyJobsFetch,
        counts_created: int,
        counts_updated: int,
        summary: YcJobAcquisitionSummary,
    ) -> None:
        skipped = (
            fetch.detail_failures
            + fetch.skipped_invalid
        )

        summary.companies_fetched += 1
        summary.job_links_discovered += (
            fetch.job_links_discovered
        )
        summary.details_fetched += (
            fetch.details_fetched
        )
        summary.detail_failures += (
            fetch.detail_failures
        )
        summary.normalized += len(
            fetch.jobs
        )
        summary.skipped += skipped
        summary.jobs_created += (
            counts_created
        )
        summary.jobs_updated += (
            counts_updated
        )

        status = (
            RunStatus.PARTIAL
            if skipped
            else RunStatus.SUCCESS
        )

        summary.results.append(
            YcCompanyJobsResult(
                company_id=source.company_id,
                company_slug=slug,
                status=status,
                job_links_discovered=(
                    fetch.job_links_discovered
                ),
                details_fetched=(
                    fetch.details_fetched
                ),
                normalized=len(
                    fetch.jobs
                ),
                skipped=skipped,
                jobs_created=counts_created,
                jobs_updated=counts_updated,
            )
        )


def _posting_to_lead(
    *,
    company_id: int,
    posting,
    seen_at: datetime,
) -> JobLead:
    return JobLead(
        company_id=company_id,
        source_type=SourceType.YC,
        external_id=posting.external_id,
        title=posting.title,
        description=posting.description,
        location_text=posting.location_text,
        workplace_type=posting.workplace_type,
        employment_type=posting.employment_type,
        job_url=posting.job_url,
        apply_url=posting.apply_url,
        published_at=posting.published_at,
        source_updated_at=(
            posting.source_updated_at
        ),
        first_seen_at=seen_at,
        last_seen_at=seen_at,
        is_active=True,
        raw_payload=posting.raw_payload,
    )


def _source_slug(
    source: CompanySource,
) -> str | None:
    if source.external_id is None:
        return None

    cleaned = source.external_id.strip()

    return cleaned or None


def _normalize_requested_slugs(
    slugs: tuple[str, ...],
) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()

    for slug in slugs:
        cleaned = slug.strip()

        if not cleaned:
            continue

        key = _slug_key(cleaned)

        if key in seen:
            continue

        seen.add(key)
        normalized.append(cleaned)

    return tuple(normalized)


def _slug_key(
    slug: str,
) -> str:
    return slug.strip().casefold()


def _is_explicitly_not_hiring(
    source: CompanySource,
) -> bool:
    metadata = source.metadata

    if not isinstance(metadata, dict):
        return False

    return metadata.get("is_hiring") is False


def _summary_status(
    summary: YcJobAcquisitionSummary,
) -> RunStatus:
    if summary.companies_failed == 0:
        return RunStatus.SUCCESS

    if summary.companies_fetched > 0:
        return RunStatus.PARTIAL

    if (
        summary.companies_considered
        == summary.companies_skipped_not_hiring
    ):
        return RunStatus.SUCCESS

    return RunStatus.FAILED


def _should_record_success(
    summary: YcJobAcquisitionSummary,
) -> bool:
    if (
        summary.requested_slugs
        and summary.companies_considered == 0
    ):
        return False

    if summary.companies_considered == 0:
        return True

    if (
        summary.companies_considered
        == summary.companies_skipped_not_hiring
    ):
        return True

    return summary.companies_fetched > 0


def _summary_metadata(
    summary: YcJobAcquisitionSummary,
) -> dict:
    return {
        "companies_considered": (
            summary.companies_considered
        ),
        "companies_skipped_not_hiring": (
            summary
            .companies_skipped_not_hiring
        ),
        "companies_fetched": (
            summary.companies_fetched
        ),
        "companies_failed": (
            summary.companies_failed
        ),
        "requested_slugs": list(
            summary.requested_slugs
        ),
        "missing_slugs": list(
            summary.missing_slugs
        ),
        "job_links_discovered": (
            summary.job_links_discovered
        ),
        "details_fetched": (
            summary.details_fetched
        ),
        "detail_failures": (
            summary.detail_failures
        ),
        "normalized": summary.normalized,
        "skipped": summary.skipped,
        "jobs_created": (
            summary.jobs_created
        ),
        "jobs_updated": (
            summary.jobs_updated
        ),
    }
