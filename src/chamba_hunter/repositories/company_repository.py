from dataclasses import replace
from datetime import datetime
import sqlite3

from chamba_hunter.db.connection import Database
from chamba_hunter.domain.enums import (
    CompanyStatus,
    CompanyType,
    TargetPriority,
)
from chamba_hunter.domain.models import Company


def _to_db_datetime(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _from_db_datetime(value: str) -> datetime:
    return datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )


def _from_db_bool(value: int | None) -> bool | None:
    if value is None:
        return None

    return bool(value)


def _row_to_company(row: sqlite3.Row) -> Company:
    return Company(
        id=row["id"],
        name=row["name"],
        normalized_name=row["normalized_name"],
        domain=row["domain"],
        website_url=row["website_url"],
        company_type=CompanyType(row["company_type"]),
        target_priority=TargetPriority(row["target_priority"]),
        careers_url=row["careers_url"],
        general_application_url=row["general_application_url"],
        country=row["country"],
        remote_latam=_from_db_bool(row["remote_latam"]),
        remote_argentina=_from_db_bool(row["remote_argentina"]),
        status=CompanyStatus(row["status"]),
        notes=row["notes"],
        created_at=_from_db_datetime(row["created_at"]),
        updated_at=_from_db_datetime(row["updated_at"]),
    )


class CompanyRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def add(self, company: Company) -> Company:
        if company.id is not None:
            raise ValueError(
                "Cannot add a Company that already has an id."
            )

        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO companies (
                    name,
                    normalized_name,
                    domain,
                    website_url,
                    company_type,
                    target_priority,
                    careers_url,
                    general_application_url,
                    country,
                    remote_latam,
                    remote_argentina,
                    status,
                    notes,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    company.name,
                    company.normalized_name,
                    company.domain,
                    company.website_url,
                    company.company_type.value,
                    company.target_priority.value,
                    company.careers_url,
                    company.general_application_url,
                    company.country,
                    company.remote_latam,
                    company.remote_argentina,
                    company.status.value,
                    company.notes,
                    _to_db_datetime(company.created_at),
                    _to_db_datetime(company.updated_at),
                ),
            )

            company_id = cursor.lastrowid

        if company_id is None:
            raise RuntimeError(
                "SQLite did not return an id for the inserted company."
            )

        return replace(
            company,
            id=company_id,
        )

    def get_by_id(self, company_id: int) -> Company | None:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM companies
                WHERE id = ?
                """,
                (company_id,),
            ).fetchone()

        if row is None:
            return None

        return _row_to_company(row)

    def get_by_domain(self, domain: str) -> Company | None:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM companies
                WHERE domain = ?
                """,
                (domain,),
            ).fetchone()

        if row is None:
            return None

        return _row_to_company(row)

    def list_all(self) -> list[Company]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM companies
                ORDER BY normalized_name
                """
            ).fetchall()

        return [
            _row_to_company(row)
            for row in rows
        ]