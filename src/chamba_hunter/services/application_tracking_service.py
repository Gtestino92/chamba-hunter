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


class OpportunityResolutionError(
    RuntimeError
):
    def __init__(
        self,
        *,
        company_name: str,
        title: str,
        matches: list[
            ApplicationOpportunity
        ],
    ) -> None:
        self.company_name = company_name
        self.title = title
        self.matches = tuple(
            matches
        )

        if not matches:
            detail = (
                "no active exact match"
            )
        else:
            identities = ", ".join(
                (
                    f"{match.record_kind} "
                    f"{match.record_id}"
                )
                for match in matches
            )
            detail = (
                f"{len(matches)} active "
                f"exact matches: {identities}"
            )

        super().__init__(
            "Could not resolve unique "
            "application opportunity for "
            f"{company_name!r} / {title!r}: "
            f"{detail}"
        )


class ApplicationTrackingService:
    def __init__(
        self,
        repository: ApplicationRepository,
    ) -> None:
        self.repository = repository

    def resolve_job(
        self,
        *,
        company_name: str,
        title: str,
    ) -> ApplicationOpportunity:
        normalized_company = (
            company_name.strip()
        )
        normalized_title = (
            title.strip()
        )

        if not normalized_company:
            raise ValueError(
                "company_name must not be empty"
            )

        if not normalized_title:
            raise ValueError(
                "title must not be empty"
            )

        matches = (
            self.repository
            .find_active_opportunities(
                company_name=(
                    normalized_company
                ),
                title=normalized_title,
            )
        )

        if len(matches) != 1:
            raise OpportunityResolutionError(
                company_name=(
                    normalized_company
                ),
                title=normalized_title,
                matches=matches,
            )

        return matches[0]

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

        return self.track_opportunity(
            opportunity=opportunity,
            status=status,
            notes=notes,
            notes_provided=notes_provided,
        )

    def track_job_by_company_title(
        self,
        *,
        company_name: str,
        title: str,
        status: ApplicationStatus,
        notes: str | None,
        notes_provided: bool,
    ) -> ApplicationTrackingResult:
        opportunity = self.resolve_job(
            company_name=company_name,
            title=title,
        )

        return self.track_opportunity(
            opportunity=opportunity,
            status=status,
            notes=notes,
            notes_provided=notes_provided,
        )

    def track_opportunity(
        self,
        *,
        opportunity: ApplicationOpportunity,
        status: ApplicationStatus,
        notes: str | None,
        notes_provided: bool,
    ) -> ApplicationTrackingResult:
        record_kind = (
            opportunity.record_kind
        )
        record_id = (
            opportunity.record_id
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
