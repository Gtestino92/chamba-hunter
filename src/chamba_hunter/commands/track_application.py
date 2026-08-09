import argparse
from pathlib import Path
import sys

from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate
from chamba_hunter.domain.enums import (
    ApplicationStatus,
)
from chamba_hunter.repositories.application_repository import (
    ApplicationRepository,
)
from chamba_hunter.services.application_tracking_service import (
    ApplicationTrackingResult,
    ApplicationTrackingService,
)


def _print_result(
    result: ApplicationTrackingResult,
) -> None:
    application = result.application
    opportunity = result.opportunity

    print(
        "Application tracking"
    )
    print(
        "--------------------"
    )
    print(
        "Action:       ",
        (
            "CREATED"
            if result.created
            else "UPDATED"
        ),
    )
    print(
        "Opportunity:  ",
        f"{opportunity.record_kind} "
        f"{opportunity.record_id}",
    )
    print(
        "Company:      ",
        opportunity.company_name,
    )
    print(
        "Title:        ",
        opportunity.title,
    )
    print(
        "Source active:",
        opportunity.is_active,
    )
    print(
        "Previous:     ",
        (
            result.previous_status
            or "<none>"
        ),
    )
    print(
        "Status:       ",
        application.status,
    )
    print(
        "Applied at:   ",
        (
            application.applied_at
            .isoformat()
            if application.applied_at
            is not None
            else "<none>"
        ),
    )
    print(
        "Notes:        ",
        (
            application.notes
            or "<none>"
        ),
    )
    print(
        "Application id:",
        application.id,
    )


def main() -> None:
    if hasattr(
        sys.stdout,
        "reconfigure",
    ):
        sys.stdout.reconfigure(
            encoding="utf-8",
            errors="replace",
        )

    parser = argparse.ArgumentParser(
        description=(
            "Create or update manual tracking "
            "for one job opportunity. Resolve "
            "it either by ATS/LEAD identity or "
            "by exact active company + title."
        )
    )

    parser.add_argument(
        "--record-kind",
        choices=[
            "ATS",
            "LEAD",
        ],
        help=(
            "Opportunity identity kind from "
            "the shortlist workbook."
        ),
    )

    parser.add_argument(
        "--record-id",
        type=int,
        help=(
            "Opportunity record id from "
            "the shortlist workbook."
        ),
    )

    parser.add_argument(
        "--company",
        help=(
            "Exact company name. Must be used "
            "together with --title."
        ),
    )

    parser.add_argument(
        "--title",
        help=(
            "Exact active job title. Must be "
            "used together with --company."
        ),
    )

    parser.add_argument(
        "--status",
        default=ApplicationStatus.APPLIED.value,
        choices=[
            status.value
            for status in ApplicationStatus
        ],
        help=(
            "Manual application status. "
            "Default: APPLIED."
        ),
    )

    parser.add_argument(
        "--notes",
        default=None,
        help=(
            "Optional notes. When omitted, "
            "existing notes are preserved. "
            "Pass an empty string to clear."
        ),
    )

    parser.add_argument(
        "--database",
        type=Path,
        default=None,
        help=(
            "Optional SQLite database path. "
            "Default: project database."
        ),
    )

    args = parser.parse_args()

    has_record_kind = (
        args.record_kind
        is not None
    )
    has_record_id = (
        args.record_id
        is not None
    )
    has_company = (
        args.company
        is not None
    )
    has_title = (
        args.title
        is not None
    )

    uses_record_identity = (
        has_record_kind
        or has_record_id
    )
    uses_text_identity = (
        has_company
        or has_title
    )

    if (
        uses_record_identity
        and uses_text_identity
    ):
        parser.error(
            "Use either --record-kind/"
            "--record-id or --company/--title, "
            "not both."
        )

    if not (
        uses_record_identity
        or uses_text_identity
    ):
        parser.error(
            "Provide either --record-kind and "
            "--record-id, or --company and "
            "--title."
        )

    if (
        uses_record_identity
        and not (
            has_record_kind
            and has_record_id
        )
    ):
        parser.error(
            "--record-kind and --record-id "
            "must be provided together."
        )

    if (
        uses_text_identity
        and not (
            has_company
            and has_title
        )
    ):
        parser.error(
            "--company and --title must be "
            "provided together."
        )

    if (
        args.record_id
        is not None
        and args.record_id < 1
    ):
        parser.error(
            "--record-id must be at least 1"
        )

    database = (
        Database(
            args.database
        )
        if args.database
        is not None
        else Database()
    )

    applied = migrate(
        database
    )

    if applied:
        for migration in applied:
            print(
                "Applied migration: "
                f"{migration}"
            )

        print()

    repository = (
        ApplicationRepository(
            database
        )
    )

    service = (
        ApplicationTrackingService(
            repository
        )
    )

    status = ApplicationStatus(
        args.status
    )

    if uses_record_identity:
        result = service.track_job(
            record_kind=args.record_kind,
            record_id=args.record_id,
            status=status,
            notes=args.notes,
            notes_provided=(
                args.notes
                is not None
            ),
        )
    else:
        result = (
            service
            .track_job_by_company_title(
                company_name=args.company,
                title=args.title,
                status=status,
                notes=args.notes,
                notes_provided=(
                    args.notes
                    is not None
                ),
            )
        )

    _print_result(
        result
    )


if __name__ == "__main__":
    main()
