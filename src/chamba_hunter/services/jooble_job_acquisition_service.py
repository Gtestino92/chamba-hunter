from dataclasses import dataclass
from datetime import datetime
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
from chamba_hunter.domain.tracing import (
    Run,
    RunStep,
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
from chamba_hunter.sources.jooble_jobs import (
    JoobleFetchedJob,
    JoobleJobsClient,
)


@dataclass(frozen=True, slots=True)
class JoobleAcquisitionSummary:
    run_id: int
    requests_made: int
    received: int
    normalized: int
    skipped: int
    companies_created: int
    companies_existing: int
    jobs_created: int
    jobs_updated: int


class JoobleJobAcquisitionService:
    def __init__(
        self,
        jooble_client: JoobleJobsClient,
        company_import_service: CompanyImportService,
        job_lead_repository: JobLeadRepository,
        tracing_repository: TracingRepository,
    ) -> None:
        self.jooble_client = jooble_client
        self.company_import_service = company_import_service
        self.job_lead_repository = job_lead_repository
        self.tracing_repository = tracing_repository

    def run(
        self,
        *,
        max_pages_per_query: int,
    ) -> JoobleAcquisitionSummary:
        run = self.tracing_repository.add_run(
            Run(
                command="acquire_jooble_jobs"
            )
        )

        if run.id is None:
            raise RuntimeError(
                "Run must have an id."
            )

        step = self.tracing_repository.add_run_step(
            RunStep(
                run_id=run.id,
                step_name="jooble_job_acquisition",
                items_total=1,
            )
        )

        if step.id is None:
            raise RuntimeError(
                "Run step must have an id."
            )

        try:
            summary = self._acquire(
                run_id=run.id,
                max_pages_per_query=(
                    max_pages_per_query
                ),
            )

            self.tracing_repository.finish_run_step(
                run_step_id=step.id,
                status=RunStatus.SUCCESS,
                items_success=1,
                items_failed=0,
                items_skipped=0,
                metadata={
                    "requests_made": summary.requests_made,
                    "received": summary.received,
                    "normalized": summary.normalized,
                    "skipped": summary.skipped,
                    "companies_created": (
                        summary.companies_created
                    ),
                    "companies_existing": (
                        summary.companies_existing
                    ),
                    "jobs_created": summary.jobs_created,
                    "jobs_updated": summary.jobs_updated,
                },
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
                    "error_type": type(error).__name__,
                    "error_message": str(error),
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
        max_pages_per_query: int,
    ) -> JoobleAcquisitionSummary:
        fetch = self.jooble_client.fetch_jobs(
            max_pages_per_query=(
                max_pages_per_query
            )
        )

        source_type = SourceType.JOOBLE
        seen_at = utc_now()
        leads: list[JobLead] = []
        skipped = 0

        seen_company_ids: set[int] = set()
        created_company_ids: set[int] = set()

        for fetched_job in fetch.jobs:
            try:
                posting = fetched_job.posting

                import_result = (
                    self.company_import_service
                    .import_seed(
                        CompanySeedInput(
                            name=_required_text(
                                posting.company,
                                "company",
                            ),
                            source_type=source_type,
                        ),
                        source_metadata={
                            "broad_job_acquisition": True,
                        },
                    )
                )

                company = import_result.company

                if company.id is None:
                    raise RuntimeError(
                        "Imported company must have an id."
                    )

                seen_company_ids.add(company.id)

                if import_result.created:
                    created_company_ids.add(
                        company.id
                    )

                leads.append(
                    _jooble_to_lead(
                        company_id=company.id,
                        fetched_job=fetched_job,
                        seen_at=seen_at,
                    )
                )

            except (
                ValidationError,
                ValueError,
                RuntimeError,
            ):
                skipped += 1

        counts = self.job_lead_repository.upsert_source_jobs(
            source_type=source_type,
            jobs=leads,
            seen_at=seen_at,
        )

        return JoobleAcquisitionSummary(
            run_id=run_id,
            requests_made=fetch.requests_made,
            received=len(fetch.jobs),
            normalized=len(leads),
            skipped=skipped,
            companies_created=len(
                created_company_ids
            ),
            companies_existing=len(
                seen_company_ids
                - created_company_ids
            ),
            jobs_created=counts.created,
            jobs_updated=counts.updated,
        )


def _jooble_to_lead(
    *,
    company_id: int,
    fetched_job: JoobleFetchedJob,
    seen_at: datetime,
) -> JobLead:
    posting = fetched_job.posting

    return JobLead(
        company_id=company_id,
        source_type=SourceType.JOOBLE,
        external_id=_required_text(
            str(posting.id),
            "id",
        ),
        title=_required_text(
            posting.title,
            "title",
        ),
        description=_html_to_text(
            posting.snippet
        ),
        location_text=_clean_text(
            posting.location
        ),
        workplace_type=WorkplaceType.UNKNOWN,
        employment_type=_clean_text(
            posting.job_type
        ),
        job_url=_clean_text(
            posting.link
        ),
        apply_url=None,
        published_at=None,
        expires_at=None,
        first_seen_at=seen_at,
        last_seen_at=seen_at,
        is_active=True,
        raw_payload={
            "matched_queries": list(
                fetched_job.matched_queries
            ),
            "job": posting.model_dump(
                mode="json",
                by_alias=True,
            ),
        },
    )


def _required_text(
    value: str | None,
    field: str,
) -> str:
    cleaned = _clean_text(value)

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

    return cleaned if cleaned else None


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(
            convert_charrefs=True
        )
        self.parts: list[str] = []

    def handle_data(
        self,
        data: str,
    ) -> None:
        cleaned = " ".join(
            data.split()
        )

        if cleaned:
            self.parts.append(cleaned)


def _html_to_text(
    value: str | None,
) -> str | None:
    cleaned = _clean_text(value)

    if cleaned is None:
        return None

    parser = _TextExtractor()
    parser.feed(value)

    text = " ".join(parser.parts)

    return text if text else cleaned
