from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

from pydantic import ValidationError

from chamba_hunter.domain.common import (
    utc_now,
)
from chamba_hunter.domain.enums import (
    RunStatus,
    SourceType,
    WorkplaceType,
)
from chamba_hunter.domain.job_leads import (
    JobLead,
)
from chamba_hunter.repositories.job_lead_repository import (
    JobLeadRepository,
)
from chamba_hunter.repositories.tracing_repository import (
    TracingRepository,
)
from chamba_hunter.schemas.inputs import (
    CompanySeedInput,
)
from chamba_hunter.services.company_import_service import (
    CompanyImportService,
)
from chamba_hunter.sources.jobicy_jobs import (
    JobicyJobPosting,
    JobicyJobsClient,
)
from chamba_hunter.sources.weworkremotely_jobs import (
    WeWorkRemotelyJobPosting,
    WeWorkRemotelyJobsClient,
)
from chamba_hunter.domain.tracing import (
    Run,
    RunStep,
)


@dataclass(frozen=True, slots=True)
class PublicSourceResult:
    source_type: SourceType
    status: RunStatus

    received: int = 0
    normalized: int = 0
    skipped: int = 0

    companies_created: int = 0
    companies_existing: int = 0

    jobs_created: int = 0
    jobs_updated: int = 0

    error_type: str | None = None
    error_message: str | None = None


@dataclass(slots=True)
class PublicAcquisitionSummary:
    run_id: int

    succeeded: int = 0
    failed: int = 0

    received: int = 0
    normalized: int = 0
    skipped: int = 0

    companies_created: int = 0
    companies_existing: int = 0

    jobs_created: int = 0
    jobs_updated: int = 0

    results: list[
        PublicSourceResult
    ] = field(
        default_factory=list
    )


class PublicJobAcquisitionService:
    def __init__(
        self,
        jobicy_client: JobicyJobsClient,
        weworkremotely_client: (
            WeWorkRemotelyJobsClient
        ),
        company_import_service: (
            CompanyImportService
        ),
        job_lead_repository: (
            JobLeadRepository
        ),
        tracing_repository: (
            TracingRepository
        ),
    ) -> None:
        self.jobicy_client = (
            jobicy_client
        )
        self.weworkremotely_client = (
            weworkremotely_client
        )
        self.company_import_service = (
            company_import_service
        )
        self.job_lead_repository = (
            job_lead_repository
        )
        self.tracing_repository = (
            tracing_repository
        )

    def run(
        self,
        *,
        jobicy_max_jobs: int,
        wwr_max_jobs: int,
    ) -> PublicAcquisitionSummary:
        enabled_sources = sum(
            (
                jobicy_max_jobs > 0,
                wwr_max_jobs > 0,
            )
        )

        if enabled_sources == 0:
            raise ValueError(
                "At least one public broad "
                "source must be enabled."
            )

        run = (
            self.tracing_repository
            .add_run(
                Run(
                    command=(
                        "acquire_public_jobs"
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
                        "public_job_acquisition"
                    ),
                    items_total=(
                        enabled_sources
                    ),
                )
            )
        )

        if step.id is None:
            raise RuntimeError(
                "Run step must have an id."
            )

        summary = (
            PublicAcquisitionSummary(
                run_id=run.id
            )
        )

        if (
            jobicy_max_jobs
            > 0
        ):
            self._run_jobicy(
                max_jobs=(
                    jobicy_max_jobs
                ),
                summary=summary,
            )

        if wwr_max_jobs > 0:
            self._run_weworkremotely(
                max_jobs=wwr_max_jobs,
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
                items_skipped=0,
                metadata={
                    "received": (
                        summary.received
                    ),
                    "normalized": (
                        summary.normalized
                    ),
                    "skipped": (
                        summary.skipped
                    ),
                    "companies_created": (
                        summary
                        .companies_created
                    ),
                    "companies_existing": (
                        summary
                        .companies_existing
                    ),
                    "jobs_created": (
                        summary.jobs_created
                    ),
                    "jobs_updated": (
                        summary.jobs_updated
                    ),
                },
            )
        )

        self.tracing_repository.finish_run(
            run_id=run.id,
            status=status,
        )

        return summary

    def _run_jobicy(
        self,
        *,
        max_jobs: int,
        summary: PublicAcquisitionSummary,
    ) -> None:
        source_type = (
            SourceType.JOBICY
        )

        try:
            fetch = (
                self.jobicy_client
                .fetch_engineering_jobs(
                    max_jobs=(
                        max_jobs
                    )
                )
            )

            leads: list[
                JobLead
            ] = []

            seen_company_ids: set[
                int
            ] = set()
            created_company_ids: set[
                int
            ] = set()

            skipped = 0
            seen_at = utc_now()

            for source_job in (
                fetch.jobs
            ):
                try:
                    import_result = (
                        self
                        .company_import_service
                        .import_seed(
                            CompanySeedInput(
                                name=(
                                    _required_text(
                                        source_job
                                        .company_name,
                                        "companyName",
                                    )
                                ),
                                source_type=(
                                    source_type
                                ),
                            ),
                            source_metadata={
                                (
                                    "broad_job_"
                                    "acquisition"
                                ): True,
                            },
                        )
                    )

                    company = (
                        import_result.company
                    )

                    if company.id is None:
                        raise RuntimeError(
                            "Imported company "
                            "must have an id."
                        )

                    seen_company_ids.add(
                        company.id
                    )

                    if (
                        import_result.created
                    ):
                        (
                            created_company_ids
                            .add(
                                company.id
                            )
                        )

                    leads.append(
                        _jobicy_to_lead(
                            company_id=(
                                company.id
                            ),
                            source_job=(
                                source_job
                            ),
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
                    source_type=(
                        source_type
                    ),
                    jobs=leads,
                    seen_at=seen_at,
                )
            )

            result = PublicSourceResult(
                source_type=(
                    source_type
                ),
                status=(
                    RunStatus.SUCCESS
                ),
                received=len(
                    fetch.jobs
                ),
                normalized=len(
                    leads
                ),
                skipped=skipped,
                companies_created=len(
                    created_company_ids
                ),
                companies_existing=len(
                    seen_company_ids
                    - created_company_ids
                ),
                jobs_created=(
                    counts.created
                ),
                jobs_updated=(
                    counts.updated
                ),
            )

            self._record_success(
                result=result,
                summary=summary,
            )

        except Exception as error:
            self._record_failure(
                source_type=(
                    source_type
                ),
                error=error,
                summary=summary,
            )

    def _run_weworkremotely(
        self,
        *,
        max_jobs: int,
        summary: PublicAcquisitionSummary,
    ) -> None:
        source_type = (
            SourceType
            .WEWORKREMOTELY
        )

        try:
            fetch = (
                self
                .weworkremotely_client
                .fetch_jobs(
                    max_jobs=max_jobs
                )
            )

            leads: list[
                JobLead
            ] = []

            seen_company_ids: set[
                int
            ] = set()
            created_company_ids: set[
                int
            ] = set()

            skipped = 0
            seen_at = utc_now()

            for source_job in (
                fetch.jobs
            ):
                try:
                    import_result = (
                        self
                        .company_import_service
                        .import_seed(
                            CompanySeedInput(
                                name=(
                                    _required_text(
                                        source_job
                                        .company_name,
                                        "company",
                                    )
                                ),
                                source_type=(
                                    source_type
                                ),
                            ),
                            source_metadata={
                                (
                                    "broad_job_"
                                    "acquisition"
                                ): True,
                            },
                        )
                    )

                    company = (
                        import_result.company
                    )

                    if company.id is None:
                        raise RuntimeError(
                            "Imported company "
                            "must have an id."
                        )

                    seen_company_ids.add(
                        company.id
                    )

                    if (
                        import_result.created
                    ):
                        (
                            created_company_ids
                            .add(
                                company.id
                            )
                        )

                    leads.append(
                        (
                            _weworkremotely_to_lead(
                                company_id=(
                                    company.id
                                ),
                                source_job=(
                                    source_job
                                ),
                                seen_at=(
                                    seen_at
                                ),
                            )
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
                    source_type=(
                        source_type
                    ),
                    jobs=leads,
                    seen_at=seen_at,
                )
            )

            result = PublicSourceResult(
                source_type=(
                    source_type
                ),
                status=(
                    RunStatus.SUCCESS
                ),
                received=len(
                    fetch.jobs
                ),
                normalized=len(
                    leads
                ),
                skipped=skipped,
                companies_created=len(
                    created_company_ids
                ),
                companies_existing=len(
                    seen_company_ids
                    - created_company_ids
                ),
                jobs_created=(
                    counts.created
                ),
                jobs_updated=(
                    counts.updated
                ),
            )

            self._record_success(
                result=result,
                summary=summary,
            )

        except Exception as error:
            self._record_failure(
                source_type=(
                    source_type
                ),
                error=error,
                summary=summary,
            )

    @staticmethod
    def _record_success(
        result: PublicSourceResult,
        summary: PublicAcquisitionSummary,
    ) -> None:
        summary.succeeded += 1
        summary.received += (
            result.received
        )
        summary.normalized += (
            result.normalized
        )
        summary.skipped += (
            result.skipped
        )

        summary.companies_created += (
            result.companies_created
        )
        summary.companies_existing += (
            result.companies_existing
        )

        summary.jobs_created += (
            result.jobs_created
        )
        summary.jobs_updated += (
            result.jobs_updated
        )

        summary.results.append(
            result
        )

    @staticmethod
    def _record_failure(
        source_type: SourceType,
        error: Exception,
        summary: PublicAcquisitionSummary,
    ) -> None:
        summary.failed += 1

        summary.results.append(
            PublicSourceResult(
                source_type=(
                    source_type
                ),
                status=(
                    RunStatus.FAILED
                ),
                error_type=(
                    type(error).__name__
                ),
                error_message=str(
                    error
                ),
            )
        )


def _jobicy_to_lead(
    *,
    company_id: int,
    source_job: JobicyJobPosting,
    seen_at: datetime,
) -> JobLead:
    description = _html_to_text(
        source_job.job_description
    )

    if description is None:
        description = _clean_text(
            source_job.job_excerpt
        )

    return JobLead(
        company_id=company_id,
        source_type=(
            SourceType.JOBICY
        ),
        external_id=(
            _required_text(
                str(
                    source_job.id
                ),
                "id",
            )
        ),
        title=_required_text(
            source_job.job_title,
            "jobTitle",
        ),
        description=description,
        location_text=_clean_text(
            source_job.job_geo
        ),
        workplace_type=(
            WorkplaceType.REMOTE
        ),
        employment_type=(
            _string_or_joined(
                source_job.job_type
            )
        ),
        job_url=_clean_text(
            source_job.url
        ),
        apply_url=None,
        published_at=(
            _parse_iso_datetime(
                source_job.pub_date
            )
        ),
        expires_at=None,
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


def _weworkremotely_to_lead(
    *,
    company_id: int,
    source_job: (
        WeWorkRemotelyJobPosting
    ),
    seen_at: datetime,
) -> JobLead:
    return JobLead(
        company_id=company_id,
        source_type=(
            SourceType
            .WEWORKREMOTELY
        ),
        external_id=(
            _required_text(
                source_job
                .external_id,
                "guid/link",
            )
        ),
        title=_required_text(
            source_job.title,
            "title",
        ),
        description=(
            _html_to_text(
                source_job
                .description_html
            )
        ),
        location_text=_clean_text(
            source_job.region
        ),
        workplace_type=(
            WorkplaceType.REMOTE
        ),
        employment_type=(
            _clean_text(
                source_job
                .employment_type
            )
        ),
        job_url=_clean_text(
            source_job.link
        ),
        apply_url=None,
        published_at=(
            _parse_rfc_datetime(
                source_job.pub_date
            )
        ),
        expires_at=None,
        first_seen_at=seen_at,
        last_seen_at=seen_at,
        is_active=True,
        raw_payload={
            "feed_name": (
                source_job.feed_name
            ),
            "fields": (
                source_job.raw_fields
            ),
        },
    )


def _parse_iso_datetime(
    value: str | None,
) -> datetime | None:
    cleaned = _clean_text(
        value
    )

    if cleaned is None:
        return None

    normalized = (
        cleaned[:-1] + "+00:00"
        if cleaned.endswith("Z")
        else cleaned
    )

    parsed = datetime.fromisoformat(
        normalized
    )

    if parsed.tzinfo is None:
        raise ValueError(
            "Jobicy pubDate must "
            "include timezone information: "
            f"{value}"
        )

    return parsed.astimezone(
        UTC
    )


def _parse_rfc_datetime(
    value: str | None,
) -> datetime | None:
    cleaned = _clean_text(
        value
    )

    if cleaned is None:
        return None

    parsed = parsedate_to_datetime(
        cleaned
    )

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=UTC
        )

    return parsed.astimezone(
        UTC
    )


def _string_or_joined(
    value: list[str] | str | None,
) -> str | None:
    if value is None:
        return None

    if isinstance(
        value,
        str,
    ):
        return _clean_text(
            value
        )

    cleaned = [
        item_cleaned
        for item in value
        if (
            item_cleaned
            := _clean_text(
                item
            )
        )
        is not None
    ]

    return (
        "; ".join(cleaned)
        if cleaned
        else None
    )


def _required_text(
    value: str | None,
    field: str,
) -> str:
    cleaned = _clean_text(
        value
    )

    if cleaned is None:
        raise ValueError(
            f"{field} cannot be empty."
        )

    return cleaned


def _clean_text(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    cleaned = " ".join(
        str(value).split()
    )

    return (
        cleaned
        if cleaned
        else None
    )


class _TextExtractor(
    HTMLParser
):
    def __init__(self) -> None:
        super().__init__(
            convert_charrefs=True
        )
        self.parts: list[
            str
        ] = []

    def handle_data(
        self,
        data: str,
    ) -> None:
        cleaned = " ".join(
            data.split()
        )

        if cleaned:
            self.parts.append(
                cleaned
            )


def _html_to_text(
    value: str | None,
) -> str | None:
    cleaned = _clean_text(
        value
    )

    if cleaned is None:
        return None

    parser = _TextExtractor()
    parser.feed(value)

    text = " ".join(
        parser.parts
    )

    return (
        text
        if text
        else cleaned
    )


def _run_status(
    *,
    succeeded: int,
    failed: int,
) -> RunStatus:
    if failed == 0:
        return RunStatus.SUCCESS

    if succeeded == 0:
        return RunStatus.FAILED

    return RunStatus.PARTIAL
