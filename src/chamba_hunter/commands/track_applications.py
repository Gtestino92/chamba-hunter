import argparse
from dataclasses import dataclass
from pathlib import Path
import sys

from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate
from chamba_hunter.domain.enums import (
    ApplicationStatus,
)
from chamba_hunter.repositories.application_repository import (
    ApplicationOpportunity,
    ApplicationRepository,
)
from chamba_hunter.repositories.job_shortlist_report_repository import (
    JobShortlistReportRepository,
)
from chamba_hunter.services.application_tracking_service import (
    ApplicationTrackingResult,
    ApplicationTrackingService,
    OpportunityResolutionError,
)
from chamba_hunter.services.job_shortlist_report_service import (
    DEFAULT_PROFILE_NAME,
    export_shortlist,
)


DEFAULT_OUTPUT = Path(
    "output/chamba-shortlist.xlsx"
)


@dataclass(frozen=True, slots=True)
class BatchRequest:
    company_name: str
    title: str


def _parse_requests(
    raw: str,
) -> list[BatchRequest]:
    requests: list[BatchRequest] = []
    seen: set[
        tuple[str, str]
    ] = set()

    for line_number, raw_line in enumerate(
        raw.splitlines(),
        start=1,
    ):
        line = raw_line.strip(
            "\r\n"
        )

        if not line.strip():
            continue

        parts = line.split(
            "\t"
        )

        if len(parts) != 2:
            raise ValueError(
                "Line "
                f"{line_number}: expected exactly "
                "two tab-separated columns "
                "(Company<TAB>Title)."
            )

        company_name = (
            parts[0].strip()
        )
        title = (
            parts[1].strip()
        )

        if (
            company_name.casefold()
            == "company"
            and title.casefold()
            == "title"
        ):
            continue

        if not company_name:
            raise ValueError(
                f"Line {line_number}: "
                "company is empty."
            )

        if not title:
            raise ValueError(
                f"Line {line_number}: "
                "title is empty."
            )

        key = (
            company_name.casefold(),
            title.casefold(),
        )

        if key in seen:
            continue

        seen.add(
            key
        )

        requests.append(
            BatchRequest(
                company_name=company_name,
                title=title,
            )
        )

    if not requests:
        raise ValueError(
            "No application rows found on stdin."
        )

    return requests


def _print_resolved(
    opportunities: list[
        ApplicationOpportunity
    ],
) -> None:
    print(
        "Resolved applications"
    )
    print(
        "---------------------"
    )

    for opportunity in opportunities:
        print(
            f"{opportunity.record_kind} "
            f"{opportunity.record_id} | "
            f"{opportunity.company_name} | "
            f"{opportunity.title}"
        )

    print()


def _print_result(
    result: ApplicationTrackingResult,
) -> None:
    application = result.application
    opportunity = result.opportunity

    print(
        f"{'CREATED' if result.created else 'UPDATED'}"
        f" | {opportunity.record_kind} "
        f"{opportunity.record_id}"
        f" | {opportunity.company_name}"
        f" | {opportunity.title}"
        f" | {result.previous_status or '<none>'}"
        f" -> {application.status}"
        f" | applied_at="
        f"{application.applied_at.isoformat() if application.applied_at else '<none>'}"
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

    if hasattr(
        sys.stderr,
        "reconfigure",
    ):
        sys.stderr.reconfigure(
            encoding="utf-8",
            errors="replace",
        )

    parser = argparse.ArgumentParser(
        description=(
            "Track multiple job applications "
            "from tab-separated Company + Title "
            "rows on stdin. All rows are resolved "
            "before any application write."
        )
    )

    parser.add_argument(
        "--status",
        default=ApplicationStatus.APPLIED.value,
        choices=[
            status.value
            for status in ApplicationStatus
        ],
        help=(
            "Status to apply to every row. "
            "Default: APPLIED."
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Resolve every row and print the "
            "canonical identities without "
            "writing applications or exporting."
        ),
    )

    parser.add_argument(
        "--skip-export",
        action="store_true",
        help=(
            "Do not regenerate the shortlist "
            "after successful writes."
        ),
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=(
            "Shortlist XLSX output path. "
            "Default: output/chamba-shortlist.xlsx"
        ),
    )

    parser.add_argument(
        "--profile",
        default=DEFAULT_PROFILE_NAME,
        help=(
            "Search profile used for export. "
            f"Default: {DEFAULT_PROFILE_NAME}"
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

    try:
        requests = _parse_requests(
            sys.stdin.read()
        )
    except ValueError as error:
        parser.error(
            str(error)
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

    resolved: list[
        ApplicationOpportunity
    ] = []
    failures: list[str] = []

    for request in requests:
        try:
            opportunity = (
                service.resolve_job(
                    company_name=(
                        request.company_name
                    ),
                    title=request.title,
                )
            )
        except (
            OpportunityResolutionError,
            ValueError,
        ) as error:
            failures.append(
                str(error)
            )
        else:
            resolved.append(
                opportunity
            )

    if failures:
        print(
            "Application batch aborted before "
            "writes because resolution was not "
            "unique:",
            file=sys.stderr,
        )

        for failure in failures:
            print(
                f"- {failure}",
                file=sys.stderr,
            )

        raise SystemExit(
            2
        )

    _print_resolved(
        resolved
    )

    if args.dry_run:
        print(
            "DRY RUN: no application rows "
            "were written."
        )
        return

    status = ApplicationStatus(
        args.status
    )

    print(
        "Application tracking"
    )
    print(
        "--------------------"
    )

    results: list[
        ApplicationTrackingResult
    ] = []

    for opportunity in resolved:
        result = (
            service.track_opportunity(
                opportunity=opportunity,
                status=status,
                notes=None,
                notes_provided=False,
            )
        )
        results.append(
            result
        )
        _print_result(
            result
        )

    print()
    print(
        "Tracked: ",
        len(results),
    )

    if args.skip_export:
        print(
            "Shortlist export skipped."
        )
        return

    report_repository = (
        JobShortlistReportRepository(
            database
        )
    )

    summary = export_shortlist(
        repository=report_repository,
        output_path=args.output,
        profile_name=args.profile,
    )

    print()
    print(
        "Shortlist regenerated"
    )
    print(
        "---------------------"
    )
    print(
        "Output:      ",
        args.output.resolve(),
    )
    print(
        "Focus:       ",
        len(
            summary.focus
        ),
    )
    print(
        "High Value:  ",
        len(
            summary.high_value
        ),
    )
    print(
        "All Current: ",
        len(
            summary.all_current
        ),
    )
    print(
        "History:     ",
        len(
            summary.history
        ),
    )


if __name__ == "__main__":
    main()
