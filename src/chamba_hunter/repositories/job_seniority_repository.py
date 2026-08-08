from dataclasses import dataclass
from datetime import datetime

from chamba_hunter.db.connection import Database
from chamba_hunter.db.converters import (
    datetime_to_db,
    json_to_db,
)
from chamba_hunter.domain.common import JsonObject


@dataclass(frozen=True, slots=True)
class SeniorityCandidateRow:
    record_kind: str
    record_id: int
    source_type: str
    origin: str
    company_name: str
    eligibility_status: str

    occupation_class: str | None
    backend_relevance: str | None

    title: str
    description: str | None


@dataclass(frozen=True, slots=True)
class SeniorityClassificationWrite:
    record_kind: str
    record_id: int

    seniority_class: str
    leadership_class: str

    seniority_reason: str
    leadership_reason: str
    method: str
    rule_version: str

    evidence: JsonObject


@dataclass(frozen=True, slots=True)
class SeniorityUpsertCounts:
    created: int
    updated: int
    deleted: int


class JobSeniorityRepository:
    def __init__(
        self,
        database: Database,
    ) -> None:
        self.database = database

    def list_scoped_candidates(
        self,
    ) -> list[SeniorityCandidateRow]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    jc.record_kind,
                    jc.record_id,
                    jc.source_type,
                    CASE
                        WHEN jc.record_kind = 'ATS'
                            THEN company_ats.provider
                        ELSE jc.source_type
                    END AS origin,
                    companies.name AS company_name,
                    eligibility.status AS eligibility_status,
                    occupation.occupation_class AS occupation_class,
                    occupation.backend_relevance AS backend_relevance,
                    jc.title,
                    jc.description
                FROM job_candidates jc
                JOIN companies
                  ON companies.id = jc.company_id
                LEFT JOIN company_ats
                  ON company_ats.id = jc.company_ats_id
                JOIN job_eligibility_classifications eligibility
                  ON eligibility.record_kind = jc.record_kind
                 AND eligibility.record_id = jc.record_id
                LEFT JOIN job_occupation_classifications occupation
                  ON occupation.record_kind = jc.record_kind
                 AND occupation.record_id = jc.record_id
                WHERE jc.is_active = 1
                  AND eligibility.status IN (
                      'ELIGIBLE',
                      'UNKNOWN'
                  )
                ORDER BY
                    jc.record_kind,
                    jc.record_id
                """
            ).fetchall()

        return [
            SeniorityCandidateRow(
                record_kind=str(
                    row["record_kind"]
                ),
                record_id=int(
                    row["record_id"]
                ),
                source_type=str(
                    row["source_type"]
                ),
                origin=str(
                    row["origin"]
                ),
                company_name=str(
                    row["company_name"]
                ),
                eligibility_status=str(
                    row["eligibility_status"]
                ),
                occupation_class=(
                    str(row["occupation_class"])
                    if row["occupation_class"] is not None
                    else None
                ),
                backend_relevance=(
                    str(row["backend_relevance"])
                    if row["backend_relevance"] is not None
                    else None
                ),
                title=str(
                    row["title"]
                ),
                description=(
                    str(row["description"])
                    if row["description"] is not None
                    else None
                ),
            )
            for row in rows
        ]

    def upsert_classifications(
        self,
        classifications: list[
            SeniorityClassificationWrite
        ],
        classified_at: datetime,
    ) -> SeniorityUpsertCounts:
        keys = {
            (
                classification.record_kind,
                classification.record_id,
            )
            for classification in classifications
        }

        if len(keys) != len(classifications):
            raise ValueError(
                "Duplicate seniority candidate "
                "in one classification run."
            )

        classified_at_db = datetime_to_db(
            classified_at
        )

        with self.database.transaction() as connection:
            existing_rows = connection.execute(
                """
                SELECT
                    record_kind,
                    record_id
                FROM job_seniority_classifications
                """
            ).fetchall()

            existing_keys = {
                (
                    str(row["record_kind"]),
                    int(row["record_id"]),
                )
                for row in existing_rows
            }

            for classification in classifications:
                connection.execute(
                    """
                    INSERT INTO job_seniority_classifications (
                        record_kind,
                        record_id,
                        seniority_class,
                        leadership_class,
                        seniority_reason,
                        leadership_reason,
                        method,
                        rule_version,
                        evidence_json,
                        classified_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (
                        record_kind,
                        record_id
                    )
                    DO UPDATE SET
                        seniority_class = excluded.seniority_class,
                        leadership_class = excluded.leadership_class,
                        seniority_reason = excluded.seniority_reason,
                        leadership_reason = excluded.leadership_reason,
                        method = excluded.method,
                        rule_version = excluded.rule_version,
                        evidence_json = excluded.evidence_json,
                        classified_at = excluded.classified_at
                    """,
                    (
                        classification.record_kind,
                        classification.record_id,
                        classification.seniority_class,
                        classification.leadership_class,
                        classification.seniority_reason,
                        classification.leadership_reason,
                        classification.method,
                        classification.rule_version,
                        json_to_db(
                            classification.evidence
                        ),
                        classified_at_db,
                    ),
                )

            delete_cursor = connection.execute(
                """
                DELETE FROM job_seniority_classifications
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM job_candidates jc
                    JOIN job_eligibility_classifications eligibility
                      ON eligibility.record_kind = jc.record_kind
                     AND eligibility.record_id = jc.record_id
                    WHERE jc.is_active = 1
                      AND eligibility.status IN (
                          'ELIGIBLE',
                          'UNKNOWN'
                      )
                      AND jc.record_kind =
                          job_seniority_classifications.record_kind
                      AND jc.record_id =
                          job_seniority_classifications.record_id
                )
                """
            )

        created = sum(
            1
            for key in keys
            if key not in existing_keys
        )

        return SeniorityUpsertCounts(
            created=created,
            updated=(
                len(classifications)
                - created
            ),
            deleted=delete_cursor.rowcount,
        )
