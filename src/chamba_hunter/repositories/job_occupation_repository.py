from dataclasses import dataclass
from datetime import datetime

from chamba_hunter.db.connection import Database
from chamba_hunter.db.converters import (
    datetime_to_db,
    json_to_db,
)
from chamba_hunter.domain.common import JsonObject


@dataclass(frozen=True, slots=True)
class OccupationCandidateRow:
    record_kind: str
    record_id: int
    source_type: str
    origin: str
    company_name: str
    eligibility_status: str

    title: str
    description: str | None


@dataclass(frozen=True, slots=True)
class OccupationClassificationWrite:
    record_kind: str
    record_id: int

    occupation_class: str
    backend_relevance: str

    reason: str
    method: str
    rule_version: str

    evidence: JsonObject


@dataclass(frozen=True, slots=True)
class OccupationUpsertCounts:
    created: int
    updated: int
    deleted: int


class JobOccupationRepository:
    def __init__(
        self,
        database: Database,
    ) -> None:
        self.database = database

    def list_scoped_candidates(
        self,
    ) -> list[OccupationCandidateRow]:
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
            OccupationCandidateRow(
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
                title=str(
                    row["title"]
                ),
                description=(
                    str(row["description"])
                    if row["description"]
                    is not None
                    else None
                ),
            )
            for row in rows
        ]

    def upsert_classifications(
        self,
        classifications: list[
            OccupationClassificationWrite
        ],
        classified_at: datetime,
    ) -> OccupationUpsertCounts:
        keys = {
            (
                classification.record_kind,
                classification.record_id,
            )
            for classification in classifications
        }

        if len(keys) != len(classifications):
            raise ValueError(
                "Duplicate occupation candidate "
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
                FROM job_occupation_classifications
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
                    INSERT INTO job_occupation_classifications (
                        record_kind,
                        record_id,
                        occupation_class,
                        backend_relevance,
                        reason,
                        method,
                        rule_version,
                        evidence_json,
                        classified_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (
                        record_kind,
                        record_id
                    )
                    DO UPDATE SET
                        occupation_class = excluded.occupation_class,
                        backend_relevance = excluded.backend_relevance,
                        reason = excluded.reason,
                        method = excluded.method,
                        rule_version = excluded.rule_version,
                        evidence_json = excluded.evidence_json,
                        classified_at = excluded.classified_at
                    """,
                    (
                        classification.record_kind,
                        classification.record_id,
                        classification.occupation_class,
                        classification.backend_relevance,
                        classification.reason,
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
                DELETE FROM job_occupation_classifications
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
                          job_occupation_classifications.record_kind
                      AND jc.record_id =
                          job_occupation_classifications.record_id
                )
                """
            )

        created = sum(
            1
            for key in keys
            if key not in existing_keys
        )

        return OccupationUpsertCounts(
            created=created,
            updated=(
                len(classifications)
                - created
            ),
            deleted=delete_cursor.rowcount,
        )
