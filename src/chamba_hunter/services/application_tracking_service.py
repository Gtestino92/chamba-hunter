from dataclasses import dataclass

from chamba_hunter.domain.common import utc_now
from chamba_hunter.domain.enums import (
    ApplicationStatus,
)
from chamba_hunter.repositories.application_repository import (
    ApplicationOpportunity,
    ApplicationRecord,
    ApplicationRepository,
    JobApplicationWrite,
)


@dataclass(frozen=True, slots=True)
class ApplicationTrackingResult:
    opportunity: ApplicationOpportunity
    application: ApplicationRecord

    created: bool
    previous_status: str | None


class ApplicationTrackingService:
    def __init__(
        self,
        repository: ApplicationRepository,
    ) -> None:
        self.repository = repository

    def track_job(
        self,
        *,
        record_kind: str,
        record_id: int,
        status: ApplicationStatus,
        notes: str | None,
        notes_provided: bool,
    ) -> ApplicationTrackingResult:
        opportunity = (
            self.repository.get_opportunity(
                record_kind=record_kind,
                record_id=record_id,
            )
        )

        if opportunity is None:
            raise RuntimeError(
                "Opportunity not found: "
                f"{record_kind} {record_id}"
            )

        existing = (
            self.repository
            .get_job_application(
                record_kind=record_kind,
                record_id=record_id,
            )
        )

        now = utc_now()

        previous_status = (
            existing.status
            if existing
            is not None
            else None
        )

        if (
            existing is None
            or existing.status
            != status.value
        ):
            last_status_at = now
        else:
            last_status_at = (
                existing.last_status_at
                or now
            )

        applied_at = (
            existing.applied_at
            if existing
            is not None
            else None
        )

        if (
            applied_at is None
            and status
            == ApplicationStatus.APPLIED
        ):
            applied_at = now

        if notes_provided:
            normalized_notes = (
                notes.strip()
                if notes
                is not None
                else ""
            )

            final_notes = (
                normalized_notes
                or None
            )
        else:
            final_notes = (
                existing.notes
                if existing
                is not None
                else None
            )

        job_id = (
            record_id
            if record_kind == "ATS"
            else None
        )

        application, created = (
            self.repository
            .upsert_job_application(
                JobApplicationWrite(
                    company_id=(
                        opportunity.company_id
                    ),
                    record_kind=record_kind,
                    record_id=record_id,
                    job_id=job_id,
                    status=status.value,
                    applied_at=applied_at,
                    last_status_at=(
                        last_status_at
                    ),
                    notes=final_notes,
                    now=now,
                )
            )
        )

        return ApplicationTrackingResult(
            opportunity=opportunity,
            application=application,
            created=created,
            previous_status=previous_status,
        )
