from dataclasses import replace
import sqlite3

from chamba_hunter.db.connection import Database
from chamba_hunter.db.converters import (
    bool_from_db,
    bool_to_db,
    datetime_from_db,
    datetime_to_db,
)
from chamba_hunter.domain.common import utc_now
from chamba_hunter.domain.enums import (
    CompanyStatus,
    CompanyType,
    TargetPriority,
)
from chamba_hunter.domain.models import Company


def _row_to_company(
    row: sqlite3.Row,
) -> Company:
    return Company(
        id=row["id"],
        name=row["name"],
        normalized_name=row["normalized_name"],
        domain=row["domain"],
        website_url=row["website_url"],
        company_type=CompanyType(
            row["company_type"]
        ),
        target_priority=TargetPriority(
            row["target_priority"]
        ),
        careers_url=row["careers_url"],
        general_application_url=(
            row["general_application_url"]
        ),
        country=row["country"],
        remote_latam=bool_from_db(
            row["remote_latam"]
        ),
        remote_argentina=bool_from_db(
            row["remote_argentina"]
        ),
        status=CompanyStatus(
            row["status"]
        ),
        notes=row["notes"],
        created_at=datetime_from_db(
            row["created_at"]
        ),
        updated_at=datetime_from_db(
            row["updated_at"]
        ),
    )


class CompanyRepository:
    def __init__(
        self,
        database: Database,
    ) -> None:
        self.database = database

    def add(
        self,
        company: Company,
    ) -> Company:
        if company.id is not None:
            raise ValueError(
                "Cannot add a Company that "
                "already has an id."
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
                VALUES (
                    ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?,
                    ?, ?, ?
                )
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
                    bool_to_db(
                        company.remote_latam
                    ),
                    bool_to_db(
                        company.remote_argentina
                    ),
                    company.status.value,
                    company.notes,
                    datetime_to_db(
                        company.created_at
                    ),
                    datetime_to_db(
                        company.updated_at
                    ),
                ),
            )

            company_id = cursor.lastrowid

        if company_id is None:
            raise RuntimeError(
                "SQLite did not return an id "
                "for the inserted company."
            )

        return replace(
            company,
            id=company_id,
        )

    def get_by_id(
        self,
        company_id: int,
    ) -> Company | None:
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

    def get_by_domain(
        self,
        domain: str,
    ) -> Company | None:
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

    def get_by_normalized_name(
        self,
        normalized_name: str,
    ) -> Company | None:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM companies
                WHERE normalized_name = ?
                ORDER BY id
                LIMIT 1
                """,
                (normalized_name,),
            ).fetchone()

        if row is None:
            return None

        return _row_to_company(row)

    def get_unique_by_normalized_name(
        self,
        normalized_name: str,
    ) -> Company | None:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM companies
                WHERE normalized_name = ?
                ORDER BY id
                LIMIT 2
                """,
                (normalized_name,),
            ).fetchall()

        if len(rows) != 1:
            return None

        return _row_to_company(
            rows[0]
        )

    def list_all(
        self,
    ) -> list[Company]:
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

    def fill_missing_discovery_fields(
        self,
        company_id: int,
        website_url: str | None = None,
        domain: str | None = None,
        careers_url: str | None = None,
        country: str | None = None,
    ) -> Company:
        company = self.get_by_id(
            company_id
        )

        if company is None:
            raise ValueError(
                f"Company does not exist: "
                f"{company_id}"
            )

        if (
            company.domain is None
            and domain is not None
        ):
            domain_owner = (
                self.get_by_domain(domain)
            )

            if (
                domain_owner is not None
                and domain_owner.id
                != company.id
            ):
                raise ValueError(
                    f"Domain {domain} already "
                    f"belongs to company "
                    f"{domain_owner.id}."
                )

        updated = replace(
            company,
            website_url=(
                company.website_url
                if company.website_url
                is not None
                else website_url
            ),
            domain=(
                company.domain
                if company.domain is not None
                else domain
            ),
            careers_url=(
                company.careers_url
                if company.careers_url
                is not None
                else careers_url
            ),
            country=(
                company.country
                if company.country is not None
                else country
            ),
            updated_at=utc_now(),
        )

        if (
            updated.website_url
            == company.website_url
            and updated.domain
            == company.domain
            and updated.careers_url
            == company.careers_url
            and updated.country
            == company.country
        ):
            return company

        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE companies
                SET
                    website_url = ?,
                    domain = ?,
                    careers_url = ?,
                    country = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    updated.website_url,
                    updated.domain,
                    updated.careers_url,
                    updated.country,
                    datetime_to_db(
                        updated.updated_at
                    ),
                    company_id,
                ),
            )

        return updated

    def update_enrichment(
        self,
        company_id: int,
        website_url: str | None = None,
        domain: str | None = None,
        company_type: CompanyType | None = None,
    ) -> Company:
        company = self.get_by_id(
            company_id
        )

        if company is None:
            raise ValueError(
                f"Company does not exist: "
                f"{company_id}"
            )

        updated = replace(
            company,
            website_url=(
                website_url
                if website_url is not None
                else company.website_url
            ),
            domain=(
                domain
                if domain is not None
                else company.domain
            ),
            company_type=(
                company_type
                if company_type is not None
                else company.company_type
            ),
            updated_at=utc_now(),
        )

        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE companies
                SET
                    website_url = ?,
                    domain = ?,
                    company_type = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    updated.website_url,
                    updated.domain,
                    updated.company_type.value,
                    datetime_to_db(
                        updated.updated_at
                    ),
                    company_id,
                ),
            )

        return updated

    def update_targeting(
        self,
        company_id: int,
        target_priority: TargetPriority | None = None,
        remote_latam: bool | None = None,
        remote_argentina: bool | None = None,
    ) -> Company:
        company = self.get_by_id(
            company_id
        )

        if company is None:
            raise ValueError(
                f"Company does not exist: "
                f"{company_id}"
            )

        updated = replace(
            company,
            target_priority=(
                target_priority
                if target_priority is not None
                else company.target_priority
            ),
            remote_latam=(
                remote_latam
                if remote_latam is not None
                else company.remote_latam
            ),
            remote_argentina=(
                remote_argentina
                if remote_argentina is not None
                else company.remote_argentina
            ),
            updated_at=utc_now(),
        )

        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE companies
                SET
                    target_priority = ?,
                    remote_latam = ?,
                    remote_argentina = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    updated.target_priority.value,
                    bool_to_db(
                        updated.remote_latam
                    ),
                    bool_to_db(
                        updated.remote_argentina
                    ),
                    datetime_to_db(
                        updated.updated_at
                    ),
                    company_id,
                ),
            )

        return updated