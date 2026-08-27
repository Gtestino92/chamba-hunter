from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urlparse

from pydantic import ValidationError

from chamba_hunter.domain.common import (
    utc_now,
)
from chamba_hunter.domain.enums import (
    AtsProvider,
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
from chamba_hunter.repositories.tracing_repository import (
    TracingRepository,
)
from chamba_hunter.schemas.inputs import (
    CompanySeedInput,
)
from chamba_hunter.services.company_import_service import (
    CompanyImportService,
)
from chamba_hunter.sources.getonboard import (
    GetOnBoardJobResource,
)
from chamba_hunter.sources.getonboard_jobs import (
    GetOnBoardJobEnrichment,
    GetOnBoardJobsClient,
)


SOURCE_TYPE = SourceType.GETONBOARD


@dataclass(frozen=True, slots=True)
class GetOnBoardAcquisitionSummary:
    run_id: int

    received: int
    normalized: int
    skipped: int

    companies_created: int
    companies_existing: int

    jobs_created: int
    jobs_updated: int

    ats_hints_created: int


class GetOnBoardJobAcquisitionService:
    def __init__(
        self,
        *,
        client: GetOnBoardJobsClient,
        company_import_service: (
            CompanyImportService
        ),
        job_lead_repository: (
            JobLeadRepository
        ),
        ats_hint_repository: (
            JobAtsHintRepository
        ),
        tracing_repository: (
            TracingRepository
        ),
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

    def run(
        self,
        *,
        max_pages: int,
    ) -> GetOnBoardAcquisitionSummary:
        if max_pages < 1:
            raise ValueError(
                "max_pages must be at least 1."
            )

        run = (
            self.tracing_repository
            .add_run(
                Run(
                    command=(
                        "acquire_getonboard_jobs"
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
                        "getonboard_job_acquisition"
                    ),
                    items_total=1,
                )
            )
        )

        if step.id is None:
            raise RuntimeError(
                "Run step must have an id."
            )

        try:
            summary = self._acquire(
                run_id=run.id,
                max_pages=max_pages,
            )

            self.tracing_repository.finish_run_step(
                run_step_id=step.id,
                status=RunStatus.SUCCESS,
                items_success=1,
                items_failed=0,
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
                    "ats_hints_created": (
                        summary
                        .ats_hints_created
                    ),
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
                    "error_type": (
                        type(error).__name__
                    ),
                    "error_message": str(
                        error
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
        max_pages: int,
    ) -> GetOnBoardAcquisitionSummary:
        fetch = (
            self.client
            .fetch_programming_jobs(
                max_pages=max_pages
            )
        )

        seen_at = utc_now()

        leads: list[JobLead] = []

        seen_company_ids: set[
            int
        ] = set()

        created_company_ids: set[
            int
        ] = set()

        skipped = 0

        for source_job in fetch.jobs:
            try:
                relationship = (
                    source_job
                    .attributes
                    .company
                )

                if (
                    relationship is None
                    or relationship.data is None
                ):
                    skipped += 1
                    continue

                company_resource = (
                    relationship.data
                )

                company_attributes = (
                    company_resource
                    .attributes
                )

                website_url = (
                    company_attributes.web
                )

                if not _is_http_url(
                    website_url
                ):
                    website_url = None

                import_result = (
                    self.company_import_service
                    .import_seed(
                        CompanySeedInput(
                            name=(
                                company_attributes
                                .name
                            ),
                            website_url=(
                                website_url
                            ),
                            country=(
                                company_attributes
                                .country
                            ),
                            source_type=(
                                SOURCE_TYPE
                            ),
                            external_id=(
                                company_resource.id
                            ),
                        ),
                        source_metadata={
                            "broad_job_acquisition": (
                                True
                            ),
                            "strategy": (
                                "FULL_CURRENT_SNAPSHOT"
                            ),
                        },
                    )
                )

                company = (
                    import_result.company
                )

                if company.id is None:
                    raise RuntimeError(
                        "Imported company must "
                        "have an id."
                    )

                seen_company_ids.add(
                    company.id
                )

                if import_result.created:
                    created_company_ids.add(
                        company.id
                    )

                leads.append(
                    _to_lead(
                        company_id=(
                            company.id
                        ),
                        source_job=(
                            source_job
                        ),
                        enrichment=(
                            fetch.enrichments.get(
                                source_job.id.strip()
                            )
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
                source_type=SOURCE_TYPE,
                jobs=leads,
                seen_at=seen_at,
            )
        )

        hints_created = (
            self._record_hints(
                leads
            )
        )

        return GetOnBoardAcquisitionSummary(
            run_id=run_id,
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
            ats_hints_created=(
                hints_created
            ),
        )

    def _record_hints(
        self,
        leads: list[JobLead],
    ) -> int:
        hints: list[
            JobAtsHint
        ] = []

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
                    "Persisted job lead "
                    "could not be reloaded."
                )

            urls = [
                url
                for url in (
                    lead.apply_url,
                    lead.job_url,
                )
                if url is not None
            ]

            for url in urls:
                hint = _ats_hint_from_url(
                    job_lead_id=lead_id,
                    company_id=(
                        lead.company_id
                    ),
                    url=url,
                )

                if hint is not None:
                    hints.append(
                        hint
                    )

        return (
            self.ats_hint_repository
            .add_many(
                hints
            )
        )


def _to_lead(
    *,
    company_id: int,
    source_job: GetOnBoardJobResource,
    enrichment: (
        GetOnBoardJobEnrichment
        | None
    ),
    seen_at: datetime,
) -> JobLead:
    attributes = source_job.attributes

    description_parts: list[
        str
    ] = []

    for value in (
        attributes.description,
        attributes.projects,
        attributes.functions,
    ):
        cleaned = _clean_text(
            value
        )

        if (
            cleaned is not None
            and cleaned
            not in description_parts
        ):
            description_parts.append(
                cleaned
            )

    locations: list[str] = []

    if (
        enrichment is not None
        and enrichment.location_text
        is not None
    ):
        _append_location(
            locations,
            enrichment.location_text,
        )

    countries = _countries(
        attributes.countries
    )

    for value in (
        *countries,
        attributes.remote_zone,
    ):
        cleaned = _clean_text(
            value
        )

        if cleaned is None:
            continue

        if (
            attributes.remote
            and cleaned.casefold()
            in {
                "remote",
                "remoto",
            }
            and locations
        ):
            continue

        _append_location(
            locations,
            cleaned,
        )

    workplace_type = (
        WorkplaceType.REMOTE
        if attributes.remote
        else WorkplaceType.UNKNOWN
    )

    return JobLead(
        company_id=company_id,
        source_type=(
            SOURCE_TYPE
        ),
        external_id=_required_text(
            source_job.id,
            "id",
        ),
        title=_required_text(
            attributes.title,
            "title",
        ),
        description=(
            "\n\n".join(
                description_parts
            )
            if description_parts
            else None
        ),
        location_text=(
            "; ".join(
                locations
            )
            if locations
            else None
        ),
        workplace_type=(
            workplace_type
        ),
        employment_type=None,
        job_url=_clean_text(
            source_job.links.public_url
        ),
        apply_url=None,
        published_at=None,
        expires_at=None,
        first_seen_at=seen_at,
        last_seen_at=seen_at,
        is_active=True,
        raw_payload=(
            _raw_payload(
                source_job,
                enrichment,
            )
        ),
    )


def _raw_payload(
    source_job: GetOnBoardJobResource,
    enrichment: (
        GetOnBoardJobEnrichment
        | None
    ),
) -> dict:
    payload = source_job.model_dump(
        mode="json"
    )

    if enrichment is None:
        return payload

    payload[
        "_chamba_source_enrichment"
    ] = {
        "location_text": (
            enrichment.location_text
        ),
        "published_date": (
            enrichment.published_date
        ),
        "remote_policy_text": (
            enrichment.remote_policy_text
        ),
        "source": enrichment.source,
    }

    return payload


def _ats_hint_from_url(
    *,
    job_lead_id: int,
    company_id: int,
    url: str,
) -> JobAtsHint | None:
    cleaned = _clean_text(
        url
    )

    if cleaned is None:
        return None

    parsed = urlparse(
        cleaned
    )

    host = (
        parsed.hostname.casefold()
        if parsed.hostname
        else ""
    )

    segments = [
        segment
        for segment in (
            parsed.path.split("/")
        )
        if segment
    ]

    provider: (
        AtsProvider
        | None
    ) = None

    identifier: (
        str
        | None
    ) = None

    if (
        host.endswith(
            "greenhouse.io"
        )
        and segments
    ):
        provider = (
            AtsProvider.GREENHOUSE
        )
        identifier = segments[0]

    elif (
        host == "jobs.ashbyhq.com"
        and segments
    ):
        provider = (
            AtsProvider.ASHBY
        )
        identifier = segments[0]

    elif (
        host == "jobs.lever.co"
        and segments
    ):
        provider = (
            AtsProvider.LEVER
        )
        identifier = segments[0]

    elif (
        host == "apply.workable.com"
        and segments
        and segments[0].casefold()
        not in {
            "j",
            "jobs",
        }
    ):
        provider = (
            AtsProvider.WORKABLE
        )
        identifier = segments[0]

    elif (
        host
        == "jobs.smartrecruiters.com"
        and segments
    ):
        provider = (
            AtsProvider.SMARTRECRUITERS
        )
        identifier = segments[0]

    elif host.endswith(
        ".bamboohr.com"
    ):
        subdomain = host.removesuffix(
            ".bamboohr.com"
        )

        if subdomain:
            provider = (
                AtsProvider.BAMBOOHR
            )
            identifier = subdomain

    identifier = _clean_text(
        identifier
    )

    if (
        provider is None
        or identifier is None
    ):
        return None

    return JobAtsHint(
        job_lead_id=job_lead_id,
        company_id=company_id,
        provider=provider,
        external_identifier=identifier,
        source_url=cleaned,
    )


def _append_location(
    locations: list[str],
    value: str,
) -> None:
    cleaned = _clean_text(
        value
    )

    if (
        cleaned is not None
        and cleaned not in locations
    ):
        locations.append(
            cleaned
        )


def _countries(
    value: list[str] | str | None,
) -> list[str]:
    if value is None:
        return []

    if isinstance(
        value,
        str,
    ):
        cleaned = _clean_text(
            value
        )

        return (
            [cleaned]
            if cleaned is not None
            else []
        )

    return [
        cleaned
        for item in value
        if (
            cleaned := _clean_text(
                item
            )
        )
        is not None
    ]


def _is_http_url(
    value: str | None,
) -> bool:
    if value is None:
        return False

    return value.startswith(
        (
            "http://",
            "https://",
        )
    )


def _required_text(
    value: str,
    field_name: str,
) -> str:
    cleaned = _clean_text(
        value
    )

    if cleaned is None:
        raise ValueError(
            f"{field_name} cannot be empty."
        )

    return cleaned


def _clean_text(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    cleaned = value.strip()

    return cleaned or None
