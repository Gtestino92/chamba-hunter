import argparse

from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate
from chamba_hunter.domain.enums import CompanyStatus
from chamba_hunter.domain.models import Company
from chamba_hunter.repositories.company_ats_repository import CompanyAtsRepository
from chamba_hunter.repositories.company_repository import CompanyRepository
from chamba_hunter.repositories.tracing_repository import TracingRepository
from chamba_hunter.services.careers_ats_detection_service import CareersAtsDetectionService
from chamba_hunter.services.hibob_ats_detection_service import HiBobAtsDetectionService


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Discover careers ATS providers for known active companies "
            "that do not yet have an active ATS."
        )
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=25,
        help=(
            "Maximum number of companies to scan. Never-scanned companies "
            "are prioritized, then the least recently scanned. Defaults to 25."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print selected targets without making HTTP requests.",
    )
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be at least 1")

    database = Database()
    migrate(database)
    company_repository = CompanyRepository(database)
    company_ats_repository = CompanyAtsRepository(database)
    tracing_repository = TracingRepository(database)

    company_by_id = {
        company.id: company
        for company in company_repository.list_all()
        if company.id is not None
    }
    target_ids = _target_company_ids(database=database, limit=args.limit)
    targets = [
        company_by_id[company_id]
        for company_id in target_ids
        if company_id in company_by_id
    ]

    print("Known-company careers/ATS discovery")
    print("-----------------------------------")
    print(f"Selected: {len(targets)}")
    for company in targets:
        entrypoint = company.careers_url or company.website_url or "<none>"
        print(f"- {company.name}: {entrypoint}")

    if args.dry_run or not targets:
        return

    generic = CareersAtsDetectionService(
        company_repository=company_repository,
        tracing_repository=tracing_repository,
        company_ats_repository=company_ats_repository,
    ).run(targets)

    remaining_ids = _without_active_ats(
        database=database,
        company_ids=target_ids,
    )
    refreshed = {
        company.id: company
        for company in company_repository.list_all()
        if company.id is not None
    }
    hibob_targets: list[Company] = [
        refreshed[company_id]
        for company_id in remaining_ids
        if company_id in refreshed and refreshed[company_id].careers_url
    ]

    hibob = None
    if hibob_targets:
        hibob = HiBobAtsDetectionService(
            company_ats_repository=company_ats_repository,
            tracing_repository=tracing_repository,
        ).run(hibob_targets)

    print()
    print("Discovery summary")
    print("-----------------")
    print(f"Generic processed: {generic.processed}")
    print(f"Generic detected:  {generic.detected}")
    print(f"Generic blocked:   {generic.blocked}")
    print(f"Generic failed:    {generic.failed}")
    if hibob is not None:
        print(f"HiBob processed:   {hibob.processed}")
        print(f"HiBob detected:    {hibob.detected}")
        print(f"HiBob failed:      {hibob.failed}")
    else:
        print("HiBob processed:   0")
        print("HiBob detected:    0")
        print("HiBob failed:      0")


def _target_company_ids(*, database: Database, limit: int) -> list[int]:
    with database.connection() as connection:
        rows = connection.execute(
            """
            SELECT
                c.id AS company_id,
                MAX(cs.started_at) AS last_scanned_at
            FROM companies c
            LEFT JOIN company_scans cs
              ON cs.company_id = c.id
            WHERE c.status = ?
              AND (c.careers_url IS NOT NULL OR c.website_url IS NOT NULL)
              AND NOT EXISTS (
                    SELECT 1
                    FROM company_ats ca
                    WHERE ca.company_id = c.id
                      AND ca.is_active = 1
              )
            GROUP BY c.id
            ORDER BY
                CASE WHEN MAX(cs.started_at) IS NULL THEN 0 ELSE 1 END,
                MAX(cs.started_at) ASC,
                CASE WHEN c.careers_url IS NOT NULL THEN 0 ELSE 1 END,
                c.id
            LIMIT ?
            """,
            (CompanyStatus.ACTIVE.value, limit),
        ).fetchall()
    return [int(row["company_id"]) for row in rows]


def _without_active_ats(
    *,
    database: Database,
    company_ids: list[int],
) -> list[int]:
    if not company_ids:
        return []
    placeholders = ", ".join("?" for _ in company_ids)
    with database.connection() as connection:
        rows = connection.execute(
            f"""
            SELECT c.id AS company_id
            FROM companies c
            WHERE c.id IN ({placeholders})
              AND NOT EXISTS (
                    SELECT 1
                    FROM company_ats ca
                    WHERE ca.company_id = c.id
                      AND ca.is_active = 1
              )
            ORDER BY c.id
            """,
            tuple(company_ids),
        ).fetchall()
    return [int(row["company_id"]) for row in rows]


if __name__ == "__main__":
    main()
