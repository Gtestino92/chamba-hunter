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
from chamba_hunter.repositories.company_outreach_repository import (
    CompanyOutreachRepository,
)
from chamba_hunter.repositories.public_contact_repository import (
    PublicContactRepository,
)
from chamba_hunter.services.application_tracking_service import (
    ApplicationTrackingService,
)


def _clean(
    value: str,
) -> str:
    return (
        value
        .replace(
            "\r",
            " ",
        )
        .replace(
            "\n",
            " ",
        )
        .replace(
            "|",
            "/",
        )
    )


def _write_result(
    path: Path,
    line: str,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    path.write_text(
        line + "\n",
        encoding="utf-8",
    )


def _mark_outreach_sent(
    database: Database,
    *,
    contact_id: int,
) -> tuple[str, str]:
    contact_repository = (
        PublicContactRepository(
            database
        )
    )

    with database.connection() as connection:
        row = connection.execute(
            """
            SELECT company_id
            FROM public_contacts
            WHERE id = ?
              AND is_active = 1
              AND review_status != 'INVALID'
            """,
            (contact_id,),
        ).fetchone()

    if row is None:
        raise RuntimeError(
            "Active public outreach contact "
            f"not found: {contact_id}"
        )

    company_id = int(
        row["company_id"]
    )

    contact = next(
        (
            item
            for item in (
                contact_repository
                .list_active_for_company(
                    company_id
                )
            )
            if item.id == contact_id
        ),
        None,
    )

    if contact is None:
        raise RuntimeError(
            "Public outreach contact could "
            "not be resolved after lookup."
        )

    repository = CompanyOutreachRepository(
        database,
        contact_repository,
    )

    result = repository.track_outreach(
        company_id=company_id,
        contact=contact,
        status=ApplicationStatus.SENT,
        notes=(
            "Marked sent from the outreach "
            "workbook action."
        ),
    )

    return (
        result.current_status,
        str(result.application_id),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "OpenOffice bridge: persist one "
            "job application or company "
            "outreach action and write a "
            "machine-readable result file."
        )
    )
    parser.add_argument(
        "--record-kind",
        required=True,
        choices=[
            "ATS",
            "LEAD",
            "OUTREACH",
        ],
    )
    parser.add_argument(
        "--record-id",
        required=True,
        type=int,
    )
    parser.add_argument(
        "--result-file",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=None,
    )

    args = parser.parse_args()

    if args.record_id < 1:
        parser.error(
            "--record-id must be at least 1"
        )

    try:
        database = (
            Database(
                args.database
            )
            if args.database
            is not None
            else Database()
        )

        migrate(
            database
        )

        if args.record_kind == "OUTREACH":
            status, detail = (
                _mark_outreach_sent(
                    database,
                    contact_id=args.record_id,
                )
            )

            _write_result(
                args.result_file,
                f"OK|{status}|{detail}",
            )

            return 0

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
            status=(
                ApplicationStatus.APPLIED
            ),
            notes=None,
            notes_provided=False,
        )

        applied_at = (
            result.application
            .applied_at
        )

        _write_result(
            args.result_file,
            (
                "OK|APPLIED|"
                + (
                    applied_at.isoformat()
                    if applied_at
                    is not None
                    else ""
                )
            ),
        )

        return 0
    except Exception as error:
        _write_result(
            args.result_file,
            (
                "ERROR|"
                f"{type(error).__name__}|"
                f"{_clean(str(error))}"
            ),
        )

        print(
            str(error),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
