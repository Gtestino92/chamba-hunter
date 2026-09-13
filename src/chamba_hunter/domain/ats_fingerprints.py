from dataclasses import dataclass, field
from datetime import datetime

from chamba_hunter.domain.common import JsonObject, utc_now
from chamba_hunter.domain.enums import (
    AtsFingerprintStatus,
    AtsSupportStatus,
)


@dataclass(slots=True)
class AtsFingerprint:
    company_id: int
    fingerprint_status: AtsFingerprintStatus
    support_status: AtsSupportStatus

    id: int | None = None
    run_step_id: int | None = None
    company_scan_id: int | None = None

    input_url: str | None = None
    final_url: str | None = None

    provider_family: str | None = None
    confidence: float | None = None
    detection_method: str | None = None
    evidence: str | None = None

    http_status: int | None = None
    error_type: str | None = None
    error_message: str | None = None

    scanned_at: datetime = field(
        default_factory=utc_now
    )
    metadata: JsonObject | None = None
