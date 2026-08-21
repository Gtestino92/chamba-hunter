from dataclasses import dataclass
from datetime import datetime, timedelta

from pydantic import ValidationError

from chamba_hunter.domain.common import (
    utc_now,
)
from chamba_hunter.domain.enums import (
    SourceType,
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
from chamba_hunter.services.broad_job_acquisition_service import (
    _himalayas_company_seed_name,
    _himalayas_to_lead,
)
from chamba_hunter.services.company_import_service import (
    CompanyImportService,
)
from chamba_hunter.sources.himalayas_incremental_jobs import (
    HimalayasIncrementalJobsClient,
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

        leads = []

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
                                _himalayas_company_seed_name(
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
