from dataclasses import dataclass, field
from datetime import datetime

from chamba_hunter.domain.common import JsonObject, utc_now
from chamba_hunter.domain.enums import (
    ApplicationStatus,
    ApplicationType,
    AtsProvider,
    CompanyStatus,
    CompanyType,
    ContactReviewStatus,
    ContactType,
    MatchLevel,
    SourceType,
    TargetPriority,
    WorkplaceType,
)


@dataclass(slots=True)
class Company:
    name: str
    normalized_name: str

    id: int | None = None

    domain: str | None = None
    website_url: str | None = None

    company_type: CompanyType = CompanyType.UNKNOWN
    target_priority: TargetPriority = TargetPriority.UNKNOWN

    careers_url: str | None = None
    general_application_url: str | None = None

    country: str | None = None

    remote_latam: bool | None = None
    remote_argentina: bool | None = None

    status: CompanyStatus = CompanyStatus.ACTIVE

    notes: str | None = None

    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class CompanySource:
    company_id: int
    source_type: SourceType

    id: int | None = None

    external_id: str | None = None
    source_url: str | None = None

    raw_name: str | None = None
    metadata: JsonObject | None = None

    first_seen_at: datetime = field(default_factory=utc_now)
    last_seen_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class CompanyAts:
    company_id: int
    provider: AtsProvider

    id: int | None = None

    external_identifier: str | None = None
    board_url: str | None = None

    is_primary: bool = True
    is_active: bool = True

    detected_at: datetime = field(default_factory=utc_now)
    last_validated_at: datetime | None = None
    last_successful_sync_at: datetime | None = None

    source_detection_id: int | None = None


@dataclass(slots=True)
class PublicContact:
    company_id: int
    contact_type: ContactType
    value: str

    id: int | None = None

    source_url: str | None = None

    first_seen_at: datetime = field(default_factory=utc_now)
    last_seen_at: datetime = field(default_factory=utc_now)

    is_active: bool = True
    review_status: ContactReviewStatus = ContactReviewStatus.UNREVIEWED

    notes: str | None = None


@dataclass(slots=True)
class Job:
    company_id: int
    company_ats_id: int
    external_id: str
    title: str

    id: int | None = None

    description: str | None = None

    location_text: str | None = None
    workplace_type: WorkplaceType = WorkplaceType.UNKNOWN
    employment_type: str | None = None

    job_url: str | None = None
    apply_url: str | None = None

    published_at: datetime | None = None

    first_seen_at: datetime = field(default_factory=utc_now)
    last_seen_at: datetime = field(default_factory=utc_now)

    is_active: bool = True

    raw_payload: JsonObject | None = None


@dataclass(slots=True)
class SearchProfile:
    name: str
    rules: JsonObject

    id: int | None = None

    description: str | None = None
    is_active: bool = True

    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class JobMatch:
    job_id: int
    search_profile_id: int
    run_step_id: int

    score: float
    match_level: MatchLevel

    id: int | None = None

    reasons: list[str] = field(default_factory=list)

    created_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class Application:
    company_id: int
    application_type: ApplicationType
    status: ApplicationStatus

    id: int | None = None

    job_id: int | None = None
    public_contact_id: int | None = None

    applied_at: datetime | None = None
    last_status_at: datetime | None = None

    notes: str | None = None

    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)