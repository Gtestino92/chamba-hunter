from dataclasses import dataclass
from datetime import datetime

from chamba_hunter.db.connection import Database
from chamba_hunter.db.converters import (
    datetime_to_db,
)


@dataclass(frozen=True, slots=True)
class CanonicalizationLeadRow:
    id: int
    company_id: int
    source_type: str
    company_name: str
    title: str
    location_text: str | None
    workplace_type: str | None


@dataclass(frozen=True, slots=True)
class CanonicalizationJobRow:
    id: int
    company_id: int
    provider: str
    title: str
    location_text: str | None
    workplace_type: str | None


@dataclass(frozen=True, slots=True)
class CanonicalizationWrite:
    lead_id: int
    job_id: int
    method: str


class JobLeadCanonicalizationRepository:
    def __init__(
        self,
        database: Database,
    ) -> None:
        self.database = database

    def list_active_unresolved(
        self,
    ) -> list[CanonicalizationLeadRow]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    jl.id,
                    jl.company_id,
                    jl.source_type,
                    c.name AS company_name,
                    jl.title,
                    jl.location_text,
                    jl.workplace_type
                FROM job_leads jl
                JOIN companies c
                  ON c.id = jl.company_id
                WHERE jl.is_active = 1
                  AND jl.canonical_job_id IS NULL
                ORDER BY jl.id
                """
            ).fetchall()

        return [
            CanonicalizationLeadRow(
                id=int(row["id"]),
                company_id=int(
                    row["company_id"]
                ),
                source_type=str(
                    row["source_type"]
                ),
                company_name=str(
                    row["company_name"]
                ),
                title=str(row["title"]),
                location_text=(
                    str(row["location_text"])
                    if row["location_text"]
                    is not None
                    else None
                ),
                workplace_type=(
                    str(row["workplace_type"])
                    if row["workplace_type"]
                    is not None
                    else None
                ),
            )
            for row in rows
        ]

    def list_active_jobs(
        self,
    ) -> list[CanonicalizationJobRow]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    j.id,
                    j.company_id,
                    ca.provider,
                    j.title,
                    j.location_text,
                    j.workplace_type
                FROM jobs j
                JOIN company_ats ca
                  ON ca.id = j.company_ats_id
                WHERE j.is_active = 1
                ORDER BY j.id
                """
            ).fetchall()

        return [
            CanonicalizationJobRow(
                id=int(row["id"]),
                company_id=int(
                    row["company_id"]
                ),
                provider=str(
                    row["provider"]
                ),
                title=str(row["title"]),
                location_text=(
                    str(row["location_text"])
                    if row["location_text"]
                    is not None
                    else None
                ),
                workplace_type=(
                    str(row["workplace_type"])
                    if row["workplace_type"]
                    is not None
                    else None
                ),
            )
            for row in rows
        ]

    def apply_links(
        self,
        links: list[CanonicalizationWrite],
        canonicalized_at: datetime,
    ) -> int:
        if not links:
            return 0

        canonicalized_at_db = datetime_to_db(
            canonicalized_at
        )

        with self.database.transaction() as connection:
            applied = 0

            for link in links:
                cursor = connection.execute(
                    """
                    UPDATE job_leads
                    SET
                        canonical_job_id = ?,
                        canonicalization_method = ?,
                        canonicalized_at = ?
                    WHERE id = ?
                      AND is_active = 1
                      AND canonical_job_id IS NULL
                      AND EXISTS (
                          SELECT 1
                          FROM jobs j
                          WHERE j.id = ?
                            AND j.company_id =
                                job_leads.company_id
                            AND j.is_active = 1
                      )
                    """,
                    (
                        link.job_id,
                        link.method,
                        canonicalized_at_db,
                        link.lead_id,
                        link.job_id,
                    ),
                )

                if cursor.rowcount != 1:
                    raise RuntimeError(
                        "Canonicalization target "
                        "changed before apply: "
                        f"lead_id={link.lead_id}, "
                        f"job_id={link.job_id}"
                    )

                applied += 1

        return applied
