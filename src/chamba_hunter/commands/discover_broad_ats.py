import argparse
from collections import Counter
from dataclasses import dataclass
import json
from urllib.parse import urlsplit

from chamba_hunter.db.connection import (
    Database,
)
from chamba_hunter.db.migrations import (
    migrate,
)
from chamba_hunter.domain.enums import (
    AtsProvider,
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
from chamba_hunter.services.provider_hint_ats_detection_service import (
    ProviderHintAtsDetectionService,
    ProviderHintTarget,
)


@dataclass(frozen=True, slots=True)
class BroadAtsTarget:
    company: Company
    strategy: str

    source_types: tuple[str, ...]
    lead_count: int

    provider_hints: tuple[AtsProvider, ...] = ()
    provider_hint_sources: tuple[str, ...] = ()


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
            SourceType.JOOBLE.value,
        ],
        default="ALL",
        help=(
            "Restrict targets to companies with "
            "active leads from one broad source. "
            "Defaults to ALL."
        ),
    )

    parser.add_argument(
        "--provider-hint",
        choices=[
            provider.value
            for provider in AtsProvider
            if provider
            != AtsProvider.CUSTOM
        ],
        default=None,
        help=(
            "Restrict targets to one ATS provider "
            "present in Jooble source evidence."
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

    provider_hint_filter = (
        AtsProvider(args.provider_hint)
        if args.provider_hint
        is not None
        else None
    )

    (
        targets,
        companies_without_ats,
        skipped_no_entrypoint,
        previously_scanned,
        provider_hint_conflicts,
    ) = _build_targets(
        database=database,
        company_repository=(
            company_repository
        ),
        source_type=source_type,
        provider_hint_filter=(
            provider_hint_filter
        ),
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
        f"Provider hint filter:    "
        f"{args.provider_hint or 'ALL'}"
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
        f"Provider hint conflicts:"
        f" {provider_hint_conflicts}"
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
    print(
        f"{'PROVIDER_HINT':<18} "
        f"{strategy_counts.get('PROVIDER_HINT', 0)}"
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

    entrypoint_targets = [
        target
        for target in selected
        if target.strategy
        != "PROVIDER_HINT"
    ]

    provider_hint_targets = [
        target
        for target in selected
        if target.strategy
        == "PROVIDER_HINT"
    ]

    summaries = []

    if entrypoint_targets:
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

        summaries.append(
            service.run(
                [
                    target.company
                    for target
                    in entrypoint_targets
                ]
            )
        )

    if provider_hint_targets:
        hint_service = (
            ProviderHintAtsDetectionService(
                tracing_repository=(
                    tracing_repository
                ),
                company_ats_repository=(
                    company_ats_repository
                ),
            )
        )

        hint_inputs = []

        for target in provider_hint_targets:
            if len(target.provider_hints) != 1:
                raise RuntimeError(
                    "PROVIDER_HINT target must "
                    "have exactly one provider."
                )

            hint_inputs.append(
                ProviderHintTarget(
                    company=target.company,
                    provider=(
                        target.provider_hints[0]
                    ),
                    source_evidence=(
                        ", ".join(
                            target
                            .provider_hint_sources
                        )
                    ),
                )
            )

        summaries.append(
            hint_service.run(
                hint_inputs
            )
        )

    results = [
        result
        for summary in summaries
        for result in summary.results
    ]

    provider_counts: Counter[str] = (
        Counter()
    )

    print()
    print("Detections")
    print("----------")

    detected_lines = 0

    for result in results:
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
        for result in results
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

    processed = sum(
        summary.processed
        for summary in summaries
    )
    detected = sum(
        summary.detected
        for summary in summaries
    )
    not_detected = sum(
        summary.not_detected
        for summary in summaries
    )
    blocked = sum(
        summary.blocked
        for summary in summaries
    )
    failed = sum(
        summary.failed
        for summary in summaries
    )
    skipped = sum(
        summary.skipped
        for summary in summaries
    )

    print("Discovery finished")
    print("------------------")
    print(
        "Run ids:              "
        + ", ".join(
            str(summary.run_id)
            for summary in summaries
        )
    )
    print(
        f"Processed:            "
        f"{processed}"
    )
    print(
        f"Detected:             "
        f"{detected}"
    )
    print(
        f"Not detected:         "
        f"{not_detected}"
    )
    print(
        f"Blocked:              "
        f"{blocked}"
    )
    print(
        f"Failed:               "
        f"{failed}"
    )
    print(
        f"Skipped:              "
        f"{skipped}"
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
    provider_hint_filter: AtsProvider | None,
    include_scanned: bool,
) -> tuple[
    list[BroadAtsTarget],
    int,
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

    provider_evidence = (
        _load_jooble_provider_evidence(
            database
        )
    )

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
    provider_hint_conflicts = 0

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

        evidence_by_provider = (
            provider_evidence.get(
                company_id,
                {},
            )
        )

        provider_hints = tuple(
            sorted(
                evidence_by_provider,
                key=lambda item: item.value,
            )
        )

        if (
            provider_hint_filter
            is not None
            and provider_hint_filter
            not in provider_hints
        ):
            continue

        provider_hint_sources: tuple[
            str,
            ...,
        ] = ()

        if company.careers_url is not None:
            strategy = "KNOWN_CAREERS"

        elif company.website_url is not None:
            strategy = "HOMEPAGE"

        elif len(provider_hints) == 1:
            strategy = "PROVIDER_HINT"
            provider_hint_sources = tuple(
                sorted(
                    evidence_by_provider[
                        provider_hints[0]
                    ]
                )
            )

        else:
            if len(provider_hints) > 1:
                provider_hint_conflicts += 1

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
                provider_hints=provider_hints,
                provider_hint_sources=(
                    provider_hint_sources
                ),
            )
        )

    return (
        targets,
        len(rows),
        skipped_no_entrypoint,
        previously_scanned,
        provider_hint_conflicts,
    )


def _load_jooble_provider_evidence(
    database: Database,
) -> dict[
    int,
    dict[AtsProvider, set[str]],
]:
    with database.connection() as connection:
        rows = connection.execute(
            """
            SELECT
                company_id,
                raw_payload_json
            FROM job_leads
            WHERE source_type = ?
              AND is_active = 1
              AND canonical_job_id IS NULL
              AND raw_payload_json IS NOT NULL
            """,
            (
                SourceType.JOOBLE.value,
            ),
        ).fetchall()

    evidence: dict[
        int,
        dict[AtsProvider, set[str]],
    ] = {}

    for row in rows:
        raw_payload = row[
            "raw_payload_json"
        ]

        if not raw_payload:
            continue

        try:
            payload = json.loads(
                raw_payload
            )
        except (
            json.JSONDecodeError,
            TypeError,
        ):
            continue

        job = payload.get("job")

        if not isinstance(job, dict):
            continue

        source = job.get("source")

        if not isinstance(source, str):
            continue

        cleaned_source = source.strip()

        if not cleaned_source:
            continue

        provider = (
            _provider_from_jooble_source(
                cleaned_source
            )
        )

        if provider is None:
            continue

        company_id = int(
            row["company_id"]
        )

        (
            evidence
            .setdefault(
                company_id,
                {},
            )
            .setdefault(
                provider,
                set(),
            )
            .add(cleaned_source)
        )

    return evidence


def _provider_from_jooble_source(
    source: str,
) -> AtsProvider | None:
    cleaned = source.strip().casefold()

    if not cleaned:
        return None

    if "://" in cleaned:
        try:
            host = (
                urlsplit(cleaned)
                .hostname
                or ""
            ).casefold()
        except ValueError:
            return None
    else:
        host = cleaned.split("/", 1)[0]

    host = host.removeprefix("www.")

    if host in {
        "boards.greenhouse.io",
        "job-boards.greenhouse.io",
    }:
        return AtsProvider.GREENHOUSE

    if host == "jobs.lever.co":
        return AtsProvider.LEVER

    if host in {
        "workable.com",
        "apply.workable.com",
        "jobs.workable.com",
    }:
        return AtsProvider.WORKABLE

    if host in {
        "smartrecruiters.com",
        "jobs.smartrecruiters.com",
        "careers.smartrecruiters.com",
    }:
        return AtsProvider.SMARTRECRUITERS

    if (
        host == "hiringroom.com"
        or host.endswith(
            ".hiringroom.com"
        )
    ):
        return AtsProvider.HIRINGROOM

    if (
        host == "teamtailor.com"
        or host.endswith(
            ".teamtailor.com"
        )
    ):
        return AtsProvider.TEAMTAILOR

    return None


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
