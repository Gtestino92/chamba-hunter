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
    ApplicationTrackingService,
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
            "for one ATS or LEAD job opportunity."
        )
    )

    parser.add_argument(
        "--record-kind",
        required=True,
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
        required=True,
        type=int,
        help=(
            "Opportunity record id from "
            "the shortlist workbook."
        ),
    )

    parser.add_argument(
        "--status",
        required=True,
        choices=[
            status.value
            for status in ApplicationStatus
        ],
        help="Manual application status.",
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

    if args.record_id < 1:
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

    result = service.track_job(
        record_kind=args.record_kind,
        record_id=args.record_id,
        status=ApplicationStatus(
            args.status
        ),
        notes=args.notes,
        notes_provided=(
            args.notes
            is not None
        ),
    )

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


if __name__ == "__main__":
    main()
