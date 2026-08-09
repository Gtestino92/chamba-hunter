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


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "OpenOffice bridge: mark one "
            "canonical ATS/LEAD opportunity "
            "as APPLIED and write a small "
            "machine-readable result file."
        )
    )
    parser.add_argument(
        "--record-kind",
        required=True,
        choices=[
            "ATS",
            "LEAD",
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
