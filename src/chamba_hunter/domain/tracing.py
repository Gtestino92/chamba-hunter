from dataclasses import dataclass, field
from datetime import datetime

from chamba_hunter.domain.common import JsonObject, utc_now
from chamba_hunter.domain.enums import (
    AtsDetectionMethod,
    AtsProvider,
    AtsScanStatus,
    RunCreatedBy,
    RunStatus,
    ScanReviewStatus,
)


@dataclass(slots=True)
class Run:
    command: str

    id: int | None = None

    started_at: datetime = field(default_factory=utc_now)
    finished_at: datetime | None = None

    status: RunStatus = RunStatus.RUNNING
    created_by: RunCreatedBy = RunCreatedBy.MANUAL

    notes: str | None = None


@dataclass(slots=True)
class RunStep:
    run_id: int
    step_name: str

    id: int | None = None

    started_at: datetime = field(default_factory=utc_now)
    finished_at: datetime | None = None

    status: RunStatus = RunStatus.RUNNING

    items_total: int = 0
    items_success: int = 0
    items_failed: int = 0
    items_skipped: int = 0

    metadata: JsonObject | None = None
    error_message: str | None = None


@dataclass(slots=True)
class CompanyScan:
    run_step_id: int
    company_id: int

    id: int | None = None

    started_at: datetime = field(default_factory=utc_now)
    finished_at: datetime | None = None

    status: RunStatus = RunStatus.RUNNING

    homepage_url: str | None = None
    homepage_http_status: int | None = None

    careers_url_found: str | None = None
    careers_discovery_method: str | None = None

    contacts_found_count: int = 0

    ats_status: AtsScanStatus | None = None

    review_status: ScanReviewStatus = ScanReviewStatus.UNREVIEWED
    expected_ats_provider: AtsProvider | None = None
    review_notes: str | None = None

    error_type: str | None = None
    error_message: str | None = None


@dataclass(slots=True)
class AtsDetection:
    company_scan_id: int
    provider: AtsProvider
    method: AtsDetectionMethod
    confidence: float

    id: int | None = None

    external_identifier: str | None = None

    source_url: str | None = None
    evidence: str | None = None

    selected: bool = False

    created_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class AtsSync:
    run_step_id: int
    company_ats_id: int

    id: int | None = None

    started_at: datetime = field(default_factory=utc_now)
    finished_at: datetime | None = None

    status: RunStatus = RunStatus.RUNNING

    http_status: int | None = None

    jobs_received: int = 0
    jobs_created: int = 0
    jobs_updated: int = 0
    jobs_deactivated: int = 0

    error_type: str | None = None
    error_message: str | None = None