import argparse
from collections import Counter
from dataclasses import dataclass, replace

from chamba_hunter.db.connection import (
    Database,
)
from chamba_hunter.db.migrations import (
    migrate,
)
from chamba_hunter.domain.enums import (
    AtsScanStatus,
    CompanyStatus,
    SourceType,
)
from chamba_hunter.domain.models import (
    Company,
)
from chamba_hunter.repositories.company_ats_repository import (
    CompanyAtsRepository,
)
from chamba_hunter.repositories.company_repository import (
    CompanyRepository,
)
from chamba_hunter.repositories.tracing_repository import (
    TracingRepository,
)
from chamba_hunter.services.careers_ats_detection_service import (
    CareersAtsDetectionService,
)


@dataclass(frozen=True, slots=True)
class BroadAtsTarget:
    company: Company
    scan_company: Company

    strategy: str
    reference_url: str | None

    source_types: tuple[str, ...]
    lead_count: int


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Discover careers pages and ATS "
            "providers for companies surfaced "
            "by broad job acquisition."
        )
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help=(
            "Maximum number of companies to "
            "scan. Defaults to 50."
        ),
    )

    parser.add_argument(
        "--source",
        choices=[
            "ALL",
            SourceType.HIMALAYAS.value,
            SourceType.GETONBOARD.value,
        ],
        default="ALL",
        help=(
            "Restrict targets to companies with "
            "active leads from one broad source. "
            "Defaults to ALL."
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Show target counts and strategies "
            "without making HTTP requests."
        ),
    )

    args = parser.parse_args()

    if args.limit < 1:
        parser.error(
            "--limit must be at least 1"
        )

    database = Database()
    migrate(database)

    company_repository = (
        CompanyRepository(database)
    )

    company_ats_repository = (
        CompanyAtsRepository(database)
    )

    tracing_repository = (
        TracingRepository(database)
    )

    source_type = (
        None
        if args.source == "ALL"
        else SourceType(args.source)
    )

    targets, skipped_no_entrypoint = (
        _build_targets(
            database=database,
            company_repository=(
                company_repository
            ),
            source_type=source_type,
        )
    )

    strategy_counts = Counter(
        target.strategy
        for target in targets
    )

    print(
        "Broad careers/ATS discovery..."
    )
    print(
        f"Source filter:           "
        f"{args.source}"
    )
    print(
        f"Companies without ATS:  "
        f"{len(targets) + skipped_no_entrypoint}"
    )
    print(
        f"Usable scan targets:    "
        f"{len(targets)}"
    )
    print(
        f"No usable entry point:  "
        f"{skipped_no_entrypoint}"
    )
    print()

    print("Target strategies")
    print("-----------------")

    for strategy in (
        "KNOWN_CAREERS",
        "LEAD_APPLY_URL",
        "HOMEPAGE",
        "LEAD_JOB_URL",
    ):
        print(
            f"{strategy:<18} "
            f"{strategy_counts.get(strategy, 0)}"
        )

    print()

    selected = targets[:args.limit]

    print(
        f"Selected for this run:  "
        f"{len(selected)}"
    )

    if args.dry_run:
        print()
        print("Dry run; no scans executed.")
        return

    if not selected:
        print()
        print(
            "No eligible broad companies "
            "to scan."
        )
        return

    before_active_ats = (
        _count_active_ats_companies(
            database
        )
    )

    strategy_by_company_id = {
        target.company.id: (
            target.strategy
        )
        for target in selected
        if target.company.id is not None
    }

    service = CareersAtsDetectionService(
        company_repository=(
            company_repository
        ),
        tracing_repository=(
            tracing_repository
        ),
        company_ats_repository=(
            company_ats_repository
        ),
    )

    summary = service.run(
        [
            target.scan_company
            for target in selected
        ]
    )

    provider_counts: Counter[str] = (
        Counter()
    )

    print()
    print("Detections")
    print("----------")

    detection_lines = 0

    for result in summary.results:
        if (
            result.ats_status
            == AtsScanStatus.DETECTED
        ):
            provider = (
                result.provider.value
                if result.provider
                is not None
                else "UNKNOWN"
            )

            provider_counts[provider] += 1

            original_company = (
                _find_company(
                    selected,
                    result.company_name,
                )
            )

            strategy = (
                strategy_by_company_id.get(
                    (
                        original_company.id
                        if original_company
                        is not None
                        else None
                    ),
                    "UNKNOWN",
                )
            )

            identifier = (
                result.external_identifier
                or "identifier unknown"
            )

            print(
                f"{result.company_name}: "
                f"{provider} "
                f"[{identifier}]"
            )
            print(
                f"  strategy:   "
                f"{strategy}"
            )
            print(
                f"  method:     "
                f"{result.method.value}"
                if result.method
                is not None
                else "  method:     unknown"
            )
            print(
                f"  confidence: "
                f"{result.confidence:.2f}"
                if result.confidence
                is not None
                else "  confidence: unknown"
            )

            if result.warning:
                print(
                    f"  warning:    "
                    f"{result.warning}"
                )

            print()
            detection_lines += 1

    if detection_lines == 0:
        print("No ATS detected.")
        print()

    problem_results = [
        result
        for result in summary.results
        if result.ats_status
        in {
            AtsScanStatus.BLOCKED,
            AtsScanStatus.ERROR,
        }
    ]

    if problem_results:
        print("Blocked / errors")
        print("----------------")

        for result in problem_results[
            :10
        ]:
            print(
                f"{result.company_name}: "
                f"{result.ats_status.value}"
            )

            if result.warning:
                print(
                    f"  {result.warning}"
                )

            if result.error:
                print(
                    f"  {result.error}"
                )

        if len(problem_results) > 10:
            print(
                f"... and "
                f"{len(problem_results) - 10} "
                f"more."
            )

        print()

    after_active_ats = (
        _count_active_ats_companies(
            database
        )
    )

    print("Discovery finished")
    print("------------------")
    print(
        f"Run id:               "
        f"{summary.run_id}"
    )
    print(
        f"Processed:            "
        f"{summary.processed}"
    )
    print(
        f"Detected:             "
        f"{summary.detected}"
    )
    print(
        f"Not detected:         "
        f"{summary.not_detected}"
    )
    print(
        f"Blocked:              "
        f"{summary.blocked}"
    )
    print(
        f"Failed:               "
        f"{summary.failed}"
    )
    print(
        f"Skipped:              "
        f"{summary.skipped}"
    )
    print(
        f"Active ATS companies: "
        f"{before_active_ats} -> "
        f"{after_active_ats}"
    )

    if provider_counts:
        print()
        print("Detected by provider")
        print("--------------------")

        for provider, count in sorted(
            provider_counts.items(),
            key=lambda item: (
                -item[1],
                item[0],
            ),
        ):
            print(
                f"{provider:<18} "
                f"{count}"
            )

    print()
    print(
        "Next: sync newly discovered "
        "GREENHOUSE / ASHBY / LEVER "
        "boards with the existing "
        "provider commands. Other "
        "providers remain discovery "
        "evidence until their ingestion "
        "adapter exists."
    )


def _build_targets(
    database: Database,
    company_repository: CompanyRepository,
    source_type: SourceType | None,
) -> tuple[
    list[BroadAtsTarget],
    int,
]:
    source_filter_sql = ""
    params: list[str] = []

    if source_type is not None:
        source_filter_sql = (
            "AND EXISTS ("
            " SELECT 1"
            " FROM job_leads filter_lead"
            " WHERE filter_lead.company_id = c.id"
            " AND filter_lead.is_active = 1"
            " AND filter_lead.canonical_job_id IS NULL"
            " AND filter_lead.source_type = ?"
            ")"
        )
        params.append(
            source_type.value
        )

    with database.connection() as connection:
        rows = connection.execute(
            f"""
            SELECT
                c.id AS company_id,

                COUNT(jl.id) AS lead_count,

                GROUP_CONCAT(
                    DISTINCT jl.source_type
                ) AS source_types,

                (
                    SELECT jl_apply.apply_url
                    FROM job_leads jl_apply
                    WHERE
                        jl_apply.company_id = c.id
                        AND jl_apply.is_active = 1
                        AND jl_apply.canonical_job_id
                            IS NULL
                        AND jl_apply.apply_url
                            IS NOT NULL
                        AND TRIM(
                            jl_apply.apply_url
                        ) != ''
                    ORDER BY
                        CASE
                            WHEN jl_apply.published_at
                                 IS NULL
                            THEN 1
                            ELSE 0
                        END,
                        jl_apply.published_at DESC,
                        jl_apply.last_seen_at DESC,
                        jl_apply.id DESC
                    LIMIT 1
                ) AS best_apply_url,

                (
                    SELECT jl_job.job_url
                    FROM job_leads jl_job
                    WHERE
                        jl_job.company_id = c.id
                        AND jl_job.is_active = 1
                        AND jl_job.canonical_job_id
                            IS NULL
                        AND jl_job.job_url
                            IS NOT NULL
                        AND TRIM(
                            jl_job.job_url
                        ) != ''
                    ORDER BY
                        CASE
                            WHEN jl_job.published_at
                                 IS NULL
                            THEN 1
                            ELSE 0
                        END,
                        jl_job.published_at DESC,
                        jl_job.last_seen_at DESC,
                        jl_job.id DESC
                    LIMIT 1
                ) AS best_job_url

            FROM companies c

            JOIN job_leads jl
              ON jl.company_id = c.id
             AND jl.is_active = 1
             AND jl.canonical_job_id IS NULL

            WHERE
                c.status = ?
                AND NOT EXISTS (
                    SELECT 1
                    FROM company_ats ca
                    WHERE ca.company_id = c.id
                      AND ca.is_active = 1
                )
                {source_filter_sql}

            GROUP BY c.id

            ORDER BY
                CASE
                    WHEN c.careers_url
                         IS NOT NULL
                    THEN 0
                    WHEN (
                        SELECT COUNT(*)
                        FROM job_leads p
                        WHERE
                            p.company_id = c.id
                            AND p.is_active = 1
                            AND p.apply_url
                                IS NOT NULL
                            AND TRIM(
                                p.apply_url
                            ) != ''
                    ) > 0
                    THEN 1
                    WHEN c.website_url
                         IS NOT NULL
                    THEN 2
                    ELSE 3
                END,
                lead_count DESC,
                c.id
            """,
            (
                CompanyStatus.ACTIVE.value,
                *params,
            ),
        ).fetchall()

    companies = {
        company.id: company
        for company
        in company_repository.list_all()
        if company.id is not None
    }

    targets: list[BroadAtsTarget] = []
    skipped_no_entrypoint = 0

    for row in rows:
        company_id = int(
            row["company_id"]
        )

        company = companies.get(
            company_id
        )

        if company is None:
            raise RuntimeError(
                "Broad job lead references "
                "a missing company: "
                f"{company_id}"
            )

        best_apply_url = (
            _clean_optional(
                row["best_apply_url"]
            )
        )

        best_job_url = (
            _clean_optional(
                row["best_job_url"]
            )
        )

        if company.careers_url:
            strategy = "KNOWN_CAREERS"
            reference_url = (
                company.careers_url
            )
            scan_company = company

        elif best_apply_url is not None:
            strategy = "LEAD_APPLY_URL"
            reference_url = (
                best_apply_url
            )
            scan_company = replace(
                company,
                careers_url=(
                    best_apply_url
                ),
            )

        elif company.website_url:
            strategy = "HOMEPAGE"
            reference_url = (
                company.website_url
            )
            scan_company = company

        elif best_job_url is not None:
            strategy = "LEAD_JOB_URL"
            reference_url = (
                best_job_url
            )
            scan_company = replace(
                company,
                careers_url=(
                    best_job_url
                ),
            )

        else:
            skipped_no_entrypoint += 1
            continue

        source_types_raw = (
            row["source_types"]
            or ""
        )

        source_types = tuple(
            sorted(
                {
                    item.strip()
                    for item
                    in source_types_raw.split(
                        ","
                    )
                    if item.strip()
                }
            )
        )

        targets.append(
            BroadAtsTarget(
                company=company,
                scan_company=(
                    scan_company
                ),
                strategy=strategy,
                reference_url=(
                    reference_url
                ),
                source_types=source_types,
                lead_count=int(
                    row["lead_count"]
                ),
            )
        )

    return (
        targets,
        skipped_no_entrypoint,
    )


def _count_active_ats_companies(
    database: Database,
) -> int:
    with database.connection() as connection:
        row = connection.execute(
            """
            SELECT COUNT(
                DISTINCT company_id
            ) AS count
            FROM company_ats
            WHERE is_active = 1
            """
        ).fetchone()

    if row is None:
        return 0

    return int(row["count"])


def _find_company(
    targets: list[BroadAtsTarget],
    company_name: str,
) -> Company | None:
    matches = [
        target.company
        for target in targets
        if (
            target.company.name
            == company_name
        )
    ]

    if len(matches) != 1:
        return None

    return matches[0]


def _clean_optional(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    cleaned = value.strip()

    return cleaned or None


if __name__ == "__main__":
    main()
