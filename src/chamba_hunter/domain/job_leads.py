from dataclasses import dataclass, field
from datetime import datetime

from chamba_hunter.domain.common import (
    JsonObject,
    utc_now,
)
from chamba_hunter.domain.enums import (
    AtsProvider,
    SourceType,
    WorkplaceType,
)


@dataclass(slots=True)
class JobLead:
    company_id: int
    source_type: SourceType
    external_id: str
    title: str

    id: int | None = None
    canonical_job_id: int | None = None

    description: str | None = None

    location_text: str | None = None
    workplace_type: WorkplaceType = (
        WorkplaceType.UNKNOWN
    )
    employment_type: str | None = None

    job_url: str | None = None
    apply_url: str | None = None

    published_at: datetime | None = None
    expires_at: datetime | None = None

    # Source-native "last updated" timestamp. This is
    # intentionally separate from original publication time
    # and from Chamba's own last_changed_at/content hash.
    source_updated_at: datetime | None = None

    first_seen_at: datetime = field(
        default_factory=utc_now
    )
    last_seen_at: datetime = field(
        default_factory=utc_now
    )

    is_active: bool = True

    raw_payload: JsonObject | None = None


@dataclass(frozen=True, slots=True)
class JobAtsHint:
    job_lead_id: int
    company_id: int

    provider: AtsProvider
    external_identifier: str
    source_url: str

    created_at: datetime = field(
        default_factory=utc_now
    )
