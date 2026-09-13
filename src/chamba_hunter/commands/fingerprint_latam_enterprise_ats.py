import argparse
import json
from pathlib import Path
import sys

from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate
from chamba_hunter.domain.enums import (
    SourceType,
)
from chamba_hunter.domain.models import Company
from chamba_hunter.repositories.ats_fingerprint_repository import (
    AtsFingerprintRepository,
)
from chamba_hunter.repositories.company_repository import (
    CompanyRepository,
)
from chamba_hunter.repositories.company_source_repository import (
    CompanySourceRepository,
)
from chamba_hunter.repositories.tracing_repository import (
    TracingRepository,
)
from chamba_hunter.services.latam_enterprise_ats_fingerprinting_service import (
    LatamEnterpriseAtsFingerprintSummary,
    LatamEnterpriseAtsFingerprintingService,
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
            "Fingerprint ATS/recruiting "
            "platforms for LATAM enterprise "
            "companies without syncing jobs."
        )
    )

    parser.add_argument(
        "--country",
        help=(
            "Only scan LATAM enterprise "
            "companies for this country."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        help=(
            "Scan at most N selected "
            "companies."
        ),
    )
    parser.add_argument(
        "--company-id",
        type=int,
        help=(
            "Scan one company id, only if "
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

    companies = select_latam_enterprise_companies(
        company_repository=CompanyRepository(
            database
        ),
        source_repository=(
            CompanySourceRepository(
                database
            )
        ),
        country=args.country,
        limit=args.limit,
        company_id=args.company_id,
    )

    service = (
        LatamEnterpriseAtsFingerprintingService(
            tracing_repository=(
                TracingRepository(database)
            ),
            fingerprint_repository=(
                AtsFingerprintRepository(
                    database
                )
            ),
        )
    )

    summary = service.run(companies)

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


def select_latam_enterprise_companies(
    *,
    company_repository: CompanyRepository,
    source_repository: CompanySourceRepository,
    country: str | None = None,
    limit: int | None = None,
    company_id: int | None = None,
) -> list[Company]:
    company_by_id = {
        company.id: company
        for company
        in company_repository.list_all()
        if company.id is not None
    }

    sources = source_repository.list_by_source_type(
        SourceType.LATAM_ENTERPRISE
    )

    companies: list[Company] = []

    for source in sources:
        company = company_by_id.get(
            source.company_id
        )

        if company is None:
            continue

        if (
            company_id is not None
            and company.id != company_id
        ):
            continue

        if country is not None:
            selected_country = (
                country.strip().casefold()
            )
            company_country = (
                company.country or ""
            ).casefold()

            if (
                company_country
                != selected_country
            ):
                continue

        companies.append(company)

        if (
            limit is not None
            and len(companies) >= limit
        ):
            break

    return companies


def _print_summary(
    summary: LatamEnterpriseAtsFingerprintSummary,
) -> None:
    print(
        "LATAM enterprise ATS fingerprinting"
    )
    print(
        "==================================="
    )
    print(
        f"Companies selected: {summary.selected}"
    )
    print(
        f"Scanned:            {summary.scanned}"
    )
    print()

    _print_counter(
        title="Provider families",
        values=summary.by_provider_family,
    )
    _print_counter(
        title="Support status",
        values=summary.by_support_status,
    )
    _print_counter(
        title="Countries",
        values=summary.by_country,
    )

    print("Statuses")
    print("--------")
    print(f"DETECTED                 {summary.detected}")
    print(f"UNKNOWN                  {summary.unknown}")
    print(f"BLOCKED                  {summary.blocked}")
    print(f"ERROR                    {summary.errors}")
    print(f"NO_CAREERS_URL           {summary.no_careers_url}")
    print(
        "INSUFFICIENT_EVIDENCE    "
        f"{summary.insufficient_evidence}"
    )
    print()

    print("Per-company results")
    print("-------------------")
    for result in summary.results:
        provider = (
            result.provider_family
            or result.fingerprint_status.value
        )
        confidence = (
            f"{result.confidence:.2f}"
            if result.confidence
            is not None
            else "-"
        )
        print(
            f"{result.company_name} "
            f"({result.country or 'UNKNOWN'}): "
            f"{provider} / "
            f"{result.support_status.value} / "
            f"{confidence}"
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


def _print_counter(
    *,
    title: str,
    values,
) -> None:
    if not values:
        return

    print(title)
    print("-" * len(title))

    for key, count in sorted(
        values.items(),
        key=lambda item: (
            -item[1],
            item[0],
        ),
    ):
        print(f"{key:<24} {count}")

    print()


def _write_json(
    *,
    path: Path,
    summary: LatamEnterpriseAtsFingerprintSummary,
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
                    "country": result.country,
                    "input_url": result.input_url,
                    "final_url": result.final_url,
                    "fingerprint_status": (
                        result
                        .fingerprint_status
                        .value
                    ),
                    "provider_family": (
                        result.provider_family
                    ),
                    "support_status": (
                        result
                        .support_status
                        .value
                    ),
                    "confidence": (
                        result.confidence
                    ),
                    "detection_method": (
                        result.detection_method
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
