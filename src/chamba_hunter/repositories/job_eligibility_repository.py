from dataclasses import dataclass
from datetime import datetime

from chamba_hunter.db.connection import Database
from chamba_hunter.db.converters import (
    datetime_to_db,
    json_to_db,
)
from chamba_hunter.domain.common import JsonObject


@dataclass(frozen=True, slots=True)
class EligibilityCandidateRow:
    record_kind: str
    record_id: int
    source_type: str

    title: str
    location_text: str | None
    workplace_type: str | None


@dataclass(frozen=True, slots=True)
class EligibilityClassificationWrite:
    record_kind: str
    record_id: int

    status: str
    reason: str

    method: str
    rule_version: str

    evidence: JsonObject


@dataclass(frozen=True, slots=True)
class EligibilityUpsertCounts:
    created: int
    updated: int
    deleted: int


class JobEligibilityRepository:
    def __init__(
        self,
        database: Database,
    ) -> None:
        self.database = database

    def list_active_candidates(
        self,
    ) -> list[EligibilityCandidateRow]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    record_kind,
                    record_id,
                    source_type,
                    title,
                    location_text,
                    workplace_type
                FROM job_candidates
                WHERE is_active = 1
                ORDER BY
                    record_kind,
                    record_id
                """
            ).fetchall()

        return [
            EligibilityCandidateRow(
                record_kind=str(
                    row["record_kind"]
                ),
                record_id=int(
                    row["record_id"]
                ),
                source_type=str(
                    row["source_type"]
                ),
                title=str(
                    row["title"]
                ),
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

    def upsert_classifications(
        self,
        classifications: list[
            EligibilityClassificationWrite
        ],
        classified_at: datetime,
    ) -> EligibilityUpsertCounts:
        if not classifications:
            with self.database.transaction() as connection:
                cursor = connection.execute(
                    """
                    DELETE FROM job_eligibility_classifications
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM job_candidates jc
                        WHERE jc.is_active = 1
                          AND jc.record_kind =
                              job_eligibility_classifications.record_kind
                          AND jc.record_id =
                              job_eligibility_classifications.record_id
                    )
                    """
                )

            return EligibilityUpsertCounts(
                created=0,
                updated=0,
                deleted=cursor.rowcount,
            )

        keys = {
            (
                classification.record_kind,
                classification.record_id,
            )
            for classification in classifications
        }

        if len(keys) != len(classifications):
            raise ValueError(
                "Duplicate eligibility candidate "
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
                FROM job_eligibility_classifications
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
                    INSERT INTO job_eligibility_classifications (
                        record_kind,
                        record_id,
                        status,
                        reason,
                        method,
                        rule_version,
                        evidence_json,
                        classified_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (
                        record_kind,
                        record_id
                    )
                    DO UPDATE SET
                        status = excluded.status,
                        reason = excluded.reason,
                        method = excluded.method,
                        rule_version = excluded.rule_version,
                        evidence_json = excluded.evidence_json,
                        classified_at = excluded.classified_at
                    """,
                    (
                        classification.record_kind,
                        classification.record_id,
                        classification.status,
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
                DELETE FROM job_eligibility_classifications
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM job_candidates jc
                    WHERE jc.is_active = 1
                      AND jc.record_kind =
                          job_eligibility_classifications.record_kind
                      AND jc.record_id =
                          job_eligibility_classifications.record_id
                )
                """
            )

        created = sum(
            1
            for key in keys
            if key not in existing_keys
        )

        return EligibilityUpsertCounts(
            created=created,
            updated=(
                len(classifications)
                - created
            ),
            deleted=delete_cursor.rowcount,
        )
