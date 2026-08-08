import argparse
from collections import Counter
from dataclasses import dataclass

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
    strategy: str

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
        default=25,
        help=(
            "Maximum number of companies to "
            "scan. Defaults to 25."
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

    parser.add_argument(
        "--include-scanned",
        action="store_true",
        help=(
            "Also include companies already scanned "
            "from their current website. Historical "
            "scans against obsolete entry points do "
            "not count."
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

    (
        targets,
        companies_without_ats,
        skipped_no_entrypoint,
        previously_scanned,
    ) = _build_targets(
        database=database,
        company_repository=(
            company_repository
        ),
        source_type=source_type,
        include_scanned=(
            args.include_scanned
        ),
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
        f"{companies_without_ats}"
    )
    print(
        f"Usable scan targets:    "
        f"{len(targets)}"
    )
    print(
        f"No usable entry point:  "
        f"{skipped_no_entrypoint}"
    )
    print(
        f"Scanned current site:    "
        f"{previously_scanned}"
    )
    print()

    print("Target strategies")
    print("-----------------")
    print(
        f"{'KNOWN_CAREERS':<18} "
        f"{strategy_counts.get('KNOWN_CAREERS', 0)}"
    )
    print(
        f"{'HOMEPAGE':<18} "
        f"{strategy_counts.get('HOMEPAGE', 0)}"
    )
    print()

    selected = targets[
        :args.limit
    ]

    print(
        f"Selected for this run:  "
        f"{len(selected)}"
    )

    if args.dry_run:
        print()
        print(
            "Dry run; no scans executed."
        )
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
            target.company
            for target in selected
        ]
    )

    provider_counts: Counter[str] = (
        Counter()
    )

    print()
    print("Detections")
    print("----------")

    detected_lines = 0

    for result in summary.results:
        if (
            result.ats_status
            != AtsScanStatus.DETECTED
        ):
            continue

        provider = (
            result.provider.value
            if result.provider
            is not None
            else "UNKNOWN"
        )

        provider_counts[provider] += 1
        detected_lines += 1

        identifier = (
            result.external_identifier
            or "identifier unknown"
        )

        print(
            f"{result.company_name}: "
            f"{provider} "
            f"[{identifier}]"
        )

        if result.method is not None:
            print(
                f"  method:     "
                f"{result.method.value}"
            )

        if (
            result.confidence
            is not None
        ):
            print(
                f"  confidence: "
                f"{result.confidence:.2f}"
            )

        print(
            f"  careers:    "
            f"{result.careers_url}"
        )

        if result.warning:
            print(
                f"  warning:    "
                f"{result.warning}"
            )

        print()

    if detected_lines == 0:
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


def _build_targets(
    database: Database,
    company_repository: CompanyRepository,
    source_type: SourceType | None,
    include_scanned: bool,
) -> tuple[
    list[BroadAtsTarget],
    int,
    int,
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
                EXISTS (
                    SELECT 1
                    FROM company_scans existing_scan
                    WHERE
                        existing_scan.company_id = c.id
                        AND c.website_url IS NOT NULL
                        AND existing_scan.homepage_url = c.website_url
                ) AS previously_scanned

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
                    WHEN c.website_url
                         IS NOT NULL
                    THEN 1
                    ELSE 2
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

    targets: list[
        BroadAtsTarget
    ] = []

    skipped_no_entrypoint = 0
    previously_scanned = 0

    for row in rows:
        if bool(
            row["previously_scanned"]
        ):
            previously_scanned += 1

            if not include_scanned:
                continue

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

        if company.careers_url is not None:
            strategy = "KNOWN_CAREERS"

        elif company.website_url is not None:
            strategy = "HOMEPAGE"

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
                strategy=strategy,
                source_types=source_types,
                lead_count=int(
                    row["lead_count"]
                ),
            )
        )

    return (
        targets,
        len(rows),
        skipped_no_entrypoint,
        previously_scanned,
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


if __name__ == "__main__":
    main()
