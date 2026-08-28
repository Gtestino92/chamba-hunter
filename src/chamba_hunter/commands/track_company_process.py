import argparse

from chamba_hunter.db.connection import Database
from chamba_hunter.db.converters import datetime_to_db
from chamba_hunter.db.migrations import migrate
from chamba_hunter.domain.common import utc_now
from chamba_hunter.domain.enums import ApplicationStatus
from chamba_hunter.repositories.company_repository import CompanyRepository
from chamba_hunter.services.company_import_service import normalize_company_name


_MARKER = "Company-level process tracking."


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Persist a pre-existing company "
            "selection process when no concrete "
            "ATS/LEAD application was tracked."
        )
    )
    parser.add_argument(
        "--company",
        required=True,
    )
    parser.add_argument(
        "--status",
        choices=[
            ApplicationStatus.APPLIED.value,
            ApplicationStatus.SENT.value,
            ApplicationStatus.INTERVIEW.value,
        ],
        default=ApplicationStatus.INTERVIEW.value,
    )
    parser.add_argument(
        "--notes",
        default=None,
    )
    args = parser.parse_args()

    database = Database()
    migrate(database)

    company_repository = CompanyRepository(
        database
    )
    company = (
        company_repository
        .get_unique_by_normalized_name(
            normalize_company_name(
                args.company
            )
        )
    )

    if company is None or company.id is None:
        raise SystemExit(
            "Could not resolve a unique company: "
            f"{args.company!r}"
        )

    with database.connection() as connection:
        alias_row = connection.execute(
            """
            SELECT canonical_company_id
            FROM company_aliases
            WHERE alias_company_id = ?
            """,
            (company.id,),
        ).fetchone()

    company_id = (
        int(alias_row["canonical_company_id"])
        if alias_row is not None
        else int(company.id)
    )

    now = utc_now()
    now_db = datetime_to_db(now)

    note_parts = [_MARKER]
    if args.notes:
        note_parts.append(
            args.notes.strip()
        )
    notes = " ".join(
        part
        for part in note_parts
        if part
    )

    with database.transaction() as connection:
        existing = connection.execute(
            """
            SELECT id, status
            FROM applications
            WHERE company_id = ?
              AND application_type = 'GENERAL_APPLICATION'
              AND public_contact_id IS NULL
              AND notes LIKE ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (
                company_id,
                _MARKER + "%",
            ),
        ).fetchone()

        if existing is None:
            cursor = connection.execute(
                """
                INSERT INTO applications (
                    company_id,
                    job_id,
                    public_contact_id,
                    application_type,
                    status,
                    applied_at,
                    last_status_at,
                    notes,
                    created_at,
                    updated_at,
                    record_kind,
                    record_id
                )
                VALUES (
                    ?, NULL, NULL,
                    'GENERAL_APPLICATION',
                    ?, NULL, ?, ?, ?, ?,
                    NULL, NULL
                )
                """,
                (
                    company_id,
                    args.status,
                    now_db,
                    notes,
                    now_db,
                    now_db,
                ),
            )
            application_id = int(
                cursor.lastrowid
            )
            previous = None
            created = True
        else:
            application_id = int(
                existing["id"]
            )
            previous = str(
                existing["status"]
            )
            created = False
            connection.execute(
                """
                UPDATE applications
                SET status = ?,
                    last_status_at = ?,
                    notes = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    args.status,
                    now_db,
                    notes,
                    now_db,
                    application_id,
                ),
            )

    print("Company process tracking")
    print("------------------------")
    print(f"Company:     {company.name}")
    print(f"Company id:  {company_id}")
    print(f"Application: {application_id}")
    print(f"Created:     {created}")
    print(f"Previous:    {previous or '-'}")
    print(f"Status:      {args.status}")


if __name__ == "__main__":
    main()
