from dataclasses import dataclass
from datetime import datetime

from chamba_hunter.db.connection import Database
from chamba_hunter.db.converters import datetime_to_db


@dataclass(frozen=True, slots=True)
class ContactIntelligenceTarget:
    contact_id: int
    company_id: int
    company_name: str
    website_url: str | None
    contact_type: str
    value: str
    source_url: str | None


@dataclass(frozen=True, slots=True)
class ContactIntelligenceWrite:
    public_contact_id: int
    score: float
    label: str
    role_hint: str | None
    context: str | None
    source_kind: str
    rule_version: str
    evaluated_at: datetime


class ContactIntelligenceRepository:
    def __init__(
        self,
        database: Database,
    ) -> None:
        self.database = database

    def list_targets(
        self,
        *,
        rule_version: str,
        limit: int,
        force: bool,
    ) -> list[ContactIntelligenceTarget]:
        if limit < 1:
            return []

        stale_sql = ""
        params: list[object] = []

        if not force:
            stale_sql = """
                AND (
                    pci.public_contact_id IS NULL
                    OR pci.rule_version != ?
                )
            """
            params.append(rule_version)

        params.append(limit)

        with self.database.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    pc.id AS contact_id,
                    pc.company_id,
                    c.name AS company_name,
                    c.website_url,
                    pc.contact_type,
                    pc.value,
                    pc.source_url
                FROM public_contacts pc
                JOIN companies c
                  ON c.id = pc.company_id
                LEFT JOIN public_contact_intelligence pci
                  ON pci.public_contact_id = pc.id
                WHERE pc.is_active = 1
                  AND pc.review_status != 'INVALID'
                  {stale_sql}
                ORDER BY
                    CASE pc.contact_type
                        WHEN 'GENERAL_EMAIL' THEN 0
                        WHEN 'RECRUITING_EMAIL' THEN 1
                        WHEN 'CAREERS_EMAIL' THEN 2
                        WHEN 'GENERAL_APPLICATION_URL' THEN 3
                        ELSE 4
                    END,
                    pc.id
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()

        return [
            ContactIntelligenceTarget(
                contact_id=int(row["contact_id"]),
                company_id=int(row["company_id"]),
                company_name=str(row["company_name"]),
                website_url=row["website_url"],
                contact_type=str(row["contact_type"]),
                value=str(row["value"]),
                source_url=row["source_url"],
            )
            for row in rows
        ]

    def upsert(
        self,
        value: ContactIntelligenceWrite,
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO public_contact_intelligence (
                    public_contact_id,
                    score,
                    label,
                    role_hint,
                    context,
                    source_kind,
                    rule_version,
                    evaluated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (public_contact_id)
                DO UPDATE SET
                    score = excluded.score,
                    label = excluded.label,
                    role_hint = excluded.role_hint,
                    context = excluded.context,
                    source_kind = excluded.source_kind,
                    rule_version = excluded.rule_version,
                    evaluated_at = excluded.evaluated_at
                """,
                (
                    value.public_contact_id,
                    value.score,
                    value.label,
                    value.role_hint,
                    value.context,
                    value.source_kind,
                    value.rule_version,
                    datetime_to_db(value.evaluated_at),
                ),
            )
