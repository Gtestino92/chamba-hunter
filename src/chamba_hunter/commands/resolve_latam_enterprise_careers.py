import argparse
import json
from pathlib import Path
import sys

from chamba_hunter.commands.fingerprint_latam_enterprise_ats import (
    select_latam_enterprise_companies,
)
from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate
from chamba_hunter.repositories.company_repository import (
    CompanyRepository,
)
from chamba_hunter.repositories.company_source_repository import (
    CompanySourceRepository,
)
from chamba_hunter.services.latam_enterprise_careers_resolution_service import (
    CareersResolutionSummary,
    LatamEnterpriseCareersResolutionService,
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
            "Resolve high-confidence careers "
            "entry points for LATAM enterprise "
            "companies without syncing jobs or "
            "registering ATS integrations."
        )
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Fill missing companies.careers_url "
            "for high-confidence resolutions. "
            "Without this flag, only measure."
        ),
    )
    parser.add_argument(
        "--country",
        help=(
            "Only process LATAM enterprise "
            "companies for this country."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        help=(
            "Process at most N selected "
            "companies."
        ),
    )
    parser.add_argument(
        "--company-id",
        type=int,
        help=(
            "Process one company id, only if "
            "it belongs to the LATAM "
            "enterprise cohort."
        ),
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        help=(
            "Optional path for compact "
            "per-company JSON diagnostics."
        ),
    )

    args = parser.parse_args()

    if (
        args.limit is not None
        and args.limit < 1
    ):
        parser.error(
            "--limit must be at least 1"
        )

    if (
        args.company_id is not None
        and args.company_id < 1
    ):
        parser.error(
            "--company-id must be at least 1"
        )

    database = Database()
    applied = migrate(database)

    if applied:
        for migration in applied:
            print(
                "Applied migration:",
                migration,
            )
        print()

    company_repository = CompanyRepository(
        database
    )

    companies = select_latam_enterprise_companies(
        company_repository=company_repository,
        source_repository=(
            CompanySourceRepository(
                database
            )
        ),
        country=args.country,
        limit=args.limit,
        company_id=args.company_id,
    )

    if args.company_id is None:
        companies = [
            company
            for company in companies
            if (
                company.careers_url is None
                and company.website_url
                is not None
            )
        ]

    service = (
        LatamEnterpriseCareersResolutionService(
            company_repository=(
                company_repository
            )
        )
    )

    summary = service.run(
        companies,
        apply=args.apply,
    )

    _print_summary(summary)

    if args.output_json is not None:
        _write_json(
            path=args.output_json,
            summary=summary,
        )
        print()
        print(
            "JSON diagnostics:",
            args.output_json,
        )


def _print_summary(
    summary: CareersResolutionSummary,
) -> None:
    print(
        "LATAM enterprise careers resolution"
    )
    print(
        "==================================="
    )
    print(
        "Mode:       "
        + (
            "APPLY"
            if summary.apply
            else "DRY RUN"
        )
    )
    print(
        f"Selected:   {summary.selected}"
    )
    print(
        f"Resolved:   {summary.resolved}"
    )
    print(
        f"Unresolved: {summary.unresolved}"
    )
    print(
        f"Blocked:    {summary.blocked}"
    )
    print(
        f"Errors:     {summary.errors}"
    )
    print(
        f"Skipped:    {summary.skipped}"
    )
    print(
        f"Applied:    {summary.applied}"
    )
    print(
        f"Overwritten:{summary.overwritten}"
    )

    if summary.by_method:
        print()
        print("Resolution methods")
        print("------------------")
        for method, count in sorted(
            summary.by_method.items(),
            key=lambda item: (
                -item[1],
                item[0],
            ),
        ):
            print(f"{method:<24} {count}")

    print()
    print("Per-company results")
    print("-------------------")
    for result in summary.results:
        confidence = (
            f"{result.confidence:.2f}"
            if result.confidence
            is not None
            else "-"
        )
        destination = (
            result.resolved_careers_url
            or result.final_url
            or "-"
        )
        print(
            f"{result.company_name}: "
            f"{result.status} / "
            f"{result.method or '-'} / "
            f"{confidence} / {destination}"
        )
        if result.evidence:
            print(
                f"  evidence: {result.evidence}"
            )
        if result.error_message:
            print(
                "  error: "
                f"{result.error_type}: "
                f"{result.error_message}"
            )

    if not summary.apply:
        print()
        print(
            "Dry run; companies.careers_url "
            "was not modified."
        )
        print(
            "Use --apply to persist high-"
            "confidence missing careers URLs."
        )


def _write_json(
    *,
    path: Path,
    summary: CareersResolutionSummary,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    path.write_text(
        json.dumps(
            [
                {
                    "company_id": (
                        result.company_id
                    ),
                    "company_name": (
                        result.company_name
                    ),
                    "website_url": (
                        result.website_url
                    ),
                    "existing_careers_url": (
                        result
                        .existing_careers_url
                    ),
                    "resolved_careers_url": (
                        result
                        .resolved_careers_url
                    ),
                    "final_url": (
                        result.final_url
                    ),
                    "status": result.status,
                    "method": result.method,
                    "confidence": (
                        result.confidence
                    ),
                    "evidence": result.evidence,
                    "http_status": (
                        result.http_status
                    ),
                    "error_type": (
                        result.error_type
                    ),
                    "error_message": (
                        result.error_message
                    ),
                    "applied": (
                        result.applied
                    ),
                }
                for result in summary.results
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
