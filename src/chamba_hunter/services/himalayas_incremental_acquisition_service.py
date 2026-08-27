from dataclasses import dataclass
from datetime import datetime, timedelta
from html.parser import HTMLParser

from pydantic import ValidationError

from chamba_hunter.domain.common import (
    utc_now,
)
from chamba_hunter.domain.enums import (
    SourceType,
    WorkplaceType,
)
from chamba_hunter.domain.job_leads import (
    JobLead,
)
from chamba_hunter.repositories.job_lead_repository import (
    JobLeadRepository,
)
from chamba_hunter.repositories.source_acquisition_state_repository import (
    SourceAcquisitionStateRepository,
)
from chamba_hunter.schemas.inputs import (
    CompanySeedInput,
)
from chamba_hunter.services.company_import_service import (
    CompanyImportService,
)
from chamba_hunter.sources.himalayas_incremental_jobs import (
    HimalayasIncrementalJobsClient,
    HimalayasJobPosting,
    expiry_datetime,
    publication_datetime,
)


SOURCE_TYPE = SourceType.HIMALAYAS
SCOPE_KEY = "ARGENTINA_COMPATIBLE"

DEFAULT_BACKFILL_DAYS = 30
DEFAULT_OVERLAP_HOURS = 48


@dataclass(frozen=True, slots=True)
class HimalayasIncrementalAcquisitionSummary:
    mode: str

    started_at: datetime
    finished_at: datetime
    cutoff: datetime

    total_available: int
    requests_made: int
    pages_fetched: int
    cutoff_reached: bool

    received: int
    normalized: int
    skipped: int

    old_jobs_skipped: int
    undated_jobs_kept: int

    companies_created: int
    companies_existing: int

    jobs_created: int
    jobs_updated: int


class HimalayasIncrementalAcquisitionService:
    def __init__(
        self,
        *,
        client: HimalayasIncrementalJobsClient,
        company_import_service: (
            CompanyImportService
        ),
        job_lead_repository: (
            JobLeadRepository
        ),
        state_repository: (
            SourceAcquisitionStateRepository
        ),
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

    def run(
        self,
        *,
        backfill_days: int = (
            DEFAULT_BACKFILL_DAYS
        ),
        overlap_hours: int = (
            DEFAULT_OVERLAP_HOURS
        ),
    ) -> (
        HimalayasIncrementalAcquisitionSummary
    ):
        if backfill_days < 1:
            raise ValueError(
                "backfill_days must be "
                "at least 1."
            )

        if overlap_hours < 0:
            raise ValueError(
                "overlap_hours cannot "
                "be negative."
            )

        started_at = utc_now()

        state = (
            self.state_repository.get(
                source_type=SOURCE_TYPE,
                scope_key=SCOPE_KEY,
            )
        )

        backfill_floor = (
            started_at
            - timedelta(
                days=backfill_days
            )
        )

        if state is None:
            mode = "BACKFILL"
            cutoff = backfill_floor
        else:
            mode = "INCREMENTAL"

            incremental_cutoff = (
                state
                .last_successful_started_at
                - timedelta(
                    hours=overlap_hours
                )
            )

            cutoff = max(
                backfill_floor,
                incremental_cutoff,
            )

        fetch = self.client.fetch_since(
            cutoff=cutoff
        )

        seen_at = started_at
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
                import_result = (
                    self.company_import_service
                    .import_seed(
                        CompanySeedInput(
                            name=(
                                _company_seed_name(
                                    source_job
                                )
                            ),
                            source_type=(
                                SOURCE_TYPE
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
                            "incremental_acquisition": (
                                True
                            ),
                            "scope_key": (
                                SCOPE_KEY
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

        finished_at = utc_now()

        metadata = {
            "mode": mode,
            "cutoff": (
                cutoff.isoformat()
            ),
            "backfill_days": (
                backfill_days
            ),
            "overlap_hours": (
                overlap_hours
            ),
            "total_available": (
                fetch.total_available
            ),
            "requests_made": (
                fetch.requests_made
            ),
            "pages_fetched": (
                fetch.pages_fetched
            ),
            "cutoff_reached": (
                fetch.cutoff_reached
            ),
            "received": len(
                fetch.jobs
            ),
            "normalized": len(
                leads
            ),
            "skipped": skipped,
            "old_jobs_skipped": (
                fetch.old_jobs_skipped
            ),
            "undated_jobs_kept": (
                fetch.undated_jobs_kept
            ),
            "jobs_created": (
                counts.created
            ),
            "jobs_updated": (
                counts.updated
            ),
        }

        self.state_repository.record_success(
            source_type=SOURCE_TYPE,
            scope_key=SCOPE_KEY,
            started_at=started_at,
            finished_at=finished_at,
            is_backfill=(
                mode == "BACKFILL"
            ),
            metadata=metadata,
        )

        return (
            HimalayasIncrementalAcquisitionSummary(
                mode=mode,
                started_at=started_at,
                finished_at=finished_at,
                cutoff=cutoff,
                total_available=(
                    fetch.total_available
                ),
                requests_made=(
                    fetch.requests_made
                ),
                pages_fetched=(
                    fetch.pages_fetched
                ),
                cutoff_reached=(
                    fetch.cutoff_reached
                ),
                received=len(
                    fetch.jobs
                ),
                normalized=len(
                    leads
                ),
                skipped=skipped,
                old_jobs_skipped=(
                    fetch.old_jobs_skipped
                ),
                undated_jobs_kept=(
                    fetch.undated_jobs_kept
                ),
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
        )


def _company_seed_name(
    source_job: HimalayasJobPosting,
) -> str:
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


def _to_lead(
    *,
    company_id: int,
    source_job: HimalayasJobPosting,
    seen_at: datetime,
) -> JobLead:
    published_at = (
        publication_datetime(
            source_job
        )
    )

    expires_at = (
        expiry_datetime(
            source_job
        )
    )

    is_active = (
        expires_at is None
        or expires_at >= seen_at
    )

    locations: list[str] = []

    for restriction in (
        source_job.location_restrictions
    ):
        if isinstance(
            restriction,
            str,
        ):
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
            locations.append(
                value
            )

    description = _html_to_text(
        source_job.description
    )

    if description is None:
        description = _clean_text(
            source_job.excerpt
        )

    return JobLead(
        company_id=company_id,
        source_type=(
            SourceType.HIMALAYAS
        ),
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
    parser.feed(
        cleaned
    )

    text = " ".join(
        parser.parts
    )

    return text or None


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
