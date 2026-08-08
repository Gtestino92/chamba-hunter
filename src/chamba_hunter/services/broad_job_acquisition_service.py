from dataclasses import dataclass, field
from datetime import UTC, datetime
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
    JobLeadUpsertCounts,
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
    GetOnBoardJobsClient,
)
from chamba_hunter.sources.himalayas_jobs import (
    HimalayasJobPosting,
    HimalayasJobsClient,
)


@dataclass(frozen=True, slots=True)
class BroadSourceResult:
    source_type: SourceType
    status: RunStatus

    received: int = 0
    normalized: int = 0
    skipped: int = 0

    companies_created: int = 0
    companies_existing: int = 0

    jobs_created: int = 0
    jobs_updated: int = 0

    ats_hints_created: int = 0

    error_type: str | None = None
    error_message: str | None = None


@dataclass(slots=True)
class BroadAcquisitionSummary:
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

    ats_hints_created: int = 0

    results: list[
        BroadSourceResult
    ] = field(
        default_factory=list
    )


class BroadJobAcquisitionService:
    def __init__(
        self,
        himalayas_client: HimalayasJobsClient,
        getonboard_client: GetOnBoardJobsClient,
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
        self.himalayas_client = (
            himalayas_client
        )
        self.getonboard_client = (
            getonboard_client
        )
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
        himalayas_max_jobs: int,
        getonboard_max_pages: int,
    ) -> BroadAcquisitionSummary:
        enabled_sources = sum(
            (
                himalayas_max_jobs > 0,
                getonboard_max_pages > 0,
            )
        )

        if enabled_sources == 0:
            raise ValueError(
                "At least one broad job "
                "source must be enabled."
            )

        run = (
            self.tracing_repository
            .add_run(
                Run(
                    command=(
                        "acquire_broad_jobs"
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
                        "broad_job_acquisition"
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

        summary = BroadAcquisitionSummary(
            run_id=run.id
        )

        if himalayas_max_jobs > 0:
            self._run_himalayas(
                max_jobs=(
                    himalayas_max_jobs
                ),
                summary=summary,
            )

        if getonboard_max_pages > 0:
            self._run_getonboard(
                max_pages=(
                    getonboard_max_pages
                ),
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
        )

        self.tracing_repository.finish_run(
            run_id=run.id,
            status=status,
        )

        return summary

    def _run_himalayas(
        self,
        max_jobs: int,
        summary: BroadAcquisitionSummary,
    ) -> None:
        source_type = SourceType.HIMALAYAS

        try:
            fetch = (
                self.himalayas_client
                .browse_jobs(
                    max_jobs=max_jobs
                )
            )

            leads: list[JobLead] = []

            seen_company_ids: set[int] = set()
            created_company_ids: set[int] = set()
            skipped = 0

            seen_at = utc_now()

            for source_job in fetch.jobs:
                try:
                    import_result = (
                        self.company_import_service
                        .import_seed(
                            CompanySeedInput(
                                name=(
                                    _himalayas_company_seed_name(
                                        source_job
                                    )
                                ),
                                source_type=(
                                    source_type
                                ),
                                external_id=(
                                    source_job
                                    .company_slug
                                ),
                                source_url=(
                                    "https://"
                                    "himalayas.app/"
                                    "companies/"
                                    f"{source_job.company_slug}"
                                ),
                            ),
                            source_metadata={
                                "broad_job_acquisition": (
                                    True
                                ),
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

                    if import_result.created:
                        created_company_ids.add(
                            company.id
                        )

                    leads.append(
                        _himalayas_to_lead(
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
                    source_type=source_type,
                    jobs=leads,
                    seen_at=seen_at,
                )
            )

            hints_created = (
                self._record_hints(
                    leads
                )
            )

            result = BroadSourceResult(
                source_type=source_type,
                status=RunStatus.SUCCESS,
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
                ats_hints_created=(
                    hints_created
                ),
            )

            self._record_success(
                result=result,
                summary=summary,
            )

        except Exception as error:
            self._record_failure(
                source_type=source_type,
                error=error,
                summary=summary,
            )

    def _run_getonboard(
        self,
        max_pages: int,
        summary: BroadAcquisitionSummary,
    ) -> None:
        source_type = SourceType.GETONBOARD

        try:
            fetch = (
                self.getonboard_client
                .fetch_programming_jobs(
                    max_pages=max_pages
                )
            )

            leads: list[JobLead] = []

            seen_company_ids: set[int] = set()
            created_company_ids: set[int] = set()
            skipped = 0

            seen_at = utc_now()

            for source_job in fetch.jobs:
                try:
                    relationship = (
                        source_job
                        .attributes
                        .company
                    )

                    if (
                        relationship is None
                        or relationship.data
                        is None
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
                                    source_type
                                ),
                                external_id=(
                                    company_resource.id
                                ),
                            ),
                            source_metadata={
                                "broad_job_acquisition": (
                                    True
                                ),
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

                    if import_result.created:
                        created_company_ids.add(
                            company.id
                        )

                    leads.append(
                        _getonboard_to_lead(
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
                    source_type=source_type,
                    jobs=leads,
                    seen_at=seen_at,
                )
            )

            hints_created = (
                self._record_hints(
                    leads
                )
            )

            result = BroadSourceResult(
                source_type=source_type,
                status=RunStatus.SUCCESS,
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
                ats_hints_created=(
                    hints_created
                ),
            )

            self._record_success(
                result=result,
                summary=summary,
            )

        except Exception as error:
            self._record_failure(
                source_type=source_type,
                error=error,
                summary=summary,
            )

    def _record_hints(
        self,
        leads: list[JobLead],
    ) -> int:
        hints: list[JobAtsHint] = []

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
                    hints.append(hint)

        return (
            self.ats_hint_repository
            .add_many(hints)
        )

    @staticmethod
    def _record_success(
        result: BroadSourceResult,
        summary: BroadAcquisitionSummary,
    ) -> None:
        summary.succeeded += 1
        summary.received += result.received
        summary.normalized += result.normalized
        summary.skipped += result.skipped

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
        summary.ats_hints_created += (
            result.ats_hints_created
        )

        summary.results.append(result)

    @staticmethod
    def _record_failure(
        source_type: SourceType,
        error: Exception,
        summary: BroadAcquisitionSummary,
    ) -> None:
        summary.failed += 1

        summary.results.append(
            BroadSourceResult(
                source_type=source_type,
                status=RunStatus.FAILED,
                error_type=(
                    type(error).__name__
                ),
                error_message=str(error),
            )
        )



def _himalayas_company_seed_name(
    source_job: HimalayasJobPosting,
) -> str:
    """
    Himalayas has occasionally returned the literal placeholder
    "name" in companyName for otherwise unrelated companies.

    companySlug is the stable source identity, so never collapse
    unrelated slugs merely because the display name is that
    placeholder. Use a readable slug-derived fallback instead.
    """
    raw_name = _clean_text(
        source_job.company_name
    )

    if (
        raw_name is not None
        and raw_name.casefold() != "name"
    ):
        return raw_name

    slug = _required_text(
        source_job.company_slug,
        "companySlug",
    )

    readable = " ".join(
        part
        for part in slug.replace(
            "_",
            "-",
        ).split("-")
        if part
    ).strip()

    if not readable:
        raise ValueError(
            "Himalayas companySlug cannot "
            "produce a fallback company name."
        )

    return readable

def _himalayas_to_lead(
    company_id: int,
    source_job: HimalayasJobPosting,
    seen_at: datetime,
) -> JobLead:
    published_at = _timestamp_ms(
        source_job.pub_date
    )

    expires_at = _timestamp_ms(
        source_job.expiry_date
    )

    is_active = (
        expires_at is None
        or expires_at >= seen_at
    )

    locations: list[str] = []

    for restriction in (
        source_job.location_restrictions
    ):
        if isinstance(restriction, str):
            raw_location = restriction
        else:
            raw_location = (
                restriction.name
                or restriction.alpha2
                or restriction.slug
            )

        value = _clean_text(
            raw_location
        )

        if (
            value is not None
            and value not in locations
        ):
            locations.append(value)

    description = _html_to_text(
        source_job.description
    )

    if description is None:
        description = _clean_text(
            source_job.excerpt
        )

    return JobLead(
        company_id=company_id,
        source_type=SourceType.HIMALAYAS,
        external_id=_required_text(
            source_job.guid,
            "guid",
        ),
        title=_required_text(
            source_job.title,
            "title",
        ),
        description=description,
        location_text=(
            "; ".join(locations)
            if locations
            else None
        ),
        workplace_type=(
            WorkplaceType.REMOTE
        ),
        employment_type=_clean_text(
            source_job.employment_type
        ),
        # Himalayas documents applicationLink as the
        # job's application page on Himalayas itself,
        # not as the employer's external ATS URL.
        job_url=_clean_text(
            source_job.application_link
        ),
        apply_url=None,
        published_at=published_at,
        expires_at=expires_at,
        first_seen_at=seen_at,
        last_seen_at=seen_at,
        is_active=is_active,
        raw_payload=(
            source_job.model_dump(
                mode="json",
                by_alias=True,
            )
        ),
    )


def _getonboard_to_lead(
    company_id: int,
    source_job: GetOnBoardJobResource,
    seen_at: datetime,
) -> JobLead:
    attributes = source_job.attributes

    description_parts: list[str] = []

    for value in (
        attributes.description,
        attributes.projects,
        attributes.functions,
    ):
        cleaned = _clean_text(value)

        if (
            cleaned is not None
            and cleaned
            not in description_parts
        ):
            description_parts.append(
                cleaned
            )

    locations: list[str] = []

    countries = _countries(
        attributes.countries
    )

    for value in (
        *countries,
        attributes.remote_zone,
    ):
        cleaned = _clean_text(value)

        if (
            cleaned is not None
            and cleaned not in locations
        ):
            locations.append(cleaned)

    workplace_type = (
        WorkplaceType.REMOTE
        if attributes.remote
        else WorkplaceType.UNKNOWN
    )

    return JobLead(
        company_id=company_id,
        source_type=(
            SourceType.GETONBOARD
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
            "; ".join(locations)
            if locations
            else None
        ),
        workplace_type=workplace_type,
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
            source_job.model_dump(
                mode="json"
            )
        ),
    )


def _ats_hint_from_url(
    job_lead_id: int,
    company_id: int,
    url: str,
) -> JobAtsHint | None:
    cleaned = _clean_text(url)

    if cleaned is None:
        return None

    parsed = urlparse(cleaned)

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

    provider: AtsProvider | None = None
    identifier: str | None = None

    if (
        host.endswith(
            "greenhouse.io"
        )
        and segments
    ):
        provider = AtsProvider.GREENHOUSE
        identifier = segments[0]

    elif (
        host == "jobs.ashbyhq.com"
        and segments
    ):
        provider = AtsProvider.ASHBY
        identifier = segments[0]

    elif (
        host == "jobs.lever.co"
        and segments
    ):
        provider = AtsProvider.LEVER
        identifier = segments[0]

    elif (
        host == "apply.workable.com"
        and segments
        and segments[0].casefold()
        not in {"j", "jobs"}
    ):
        provider = AtsProvider.WORKABLE
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

    elif (
        host.endswith(
            ".bamboohr.com"
        )
    ):
        subdomain = host.removesuffix(
            ".bamboohr.com"
        )

        if subdomain:
            provider = (
                AtsProvider.BAMBOOHR
            )
            identifier = subdomain

    identifier = _clean_text(identifier)

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


def _timestamp_ms(
    value: int | float | str | None,
) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, str):
        cleaned = value.strip()

        if not cleaned:
            return None

        try:
            numeric = float(cleaned)
        except ValueError:
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
                    "Himalayas timestamp must "
                    "include timezone information: "
                    f"{value}"
                )

            return parsed.astimezone(UTC)
    else:
        numeric = float(value)

    # Himalayas' live browse feed currently returns Unix
    # timestamps in seconds (e.g. ~1.786e9), while its
    # documentation has also described these fields as
    # milliseconds. Support both representations.
    seconds = (
        numeric / 1000
        if abs(numeric) >= 100_000_000_000
        else numeric
    )

    return datetime.fromtimestamp(
        seconds,
        tz=UTC,
    )


def _countries(
    value: list[str] | str | None,
) -> list[str]:
    if value is None:
        return []

    if isinstance(value, str):
        cleaned = _clean_text(value)

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


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
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
    parser.feed(cleaned)

    text = " ".join(parser.parts)

    return text or None


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
    cleaned = _clean_text(value)

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


def _run_status(
    succeeded: int,
    failed: int,
) -> RunStatus:
    if failed == 0:
        return RunStatus.SUCCESS

    if succeeded == 0:
        return RunStatus.FAILED

    return RunStatus.PARTIAL
