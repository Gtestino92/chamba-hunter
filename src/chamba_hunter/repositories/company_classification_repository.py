from dataclasses import replace

from chamba_hunter.db.connection import Database
from chamba_hunter.db.converters import (
    datetime_to_db,
    json_to_db,
)
from chamba_hunter.domain.models import CompanyClassification


class CompanyClassificationRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def add(
        self,
        classification: CompanyClassification,
    ) -> CompanyClassification:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO company_classifications (
                    company_id,
                    company_type,
                    confidence,
                    method,
                    source_url,
                    evidence_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    classification.company_id,
                    classification.company_type.value,
                    classification.confidence,
                    classification.method,
                    classification.source_url,
                    json_to_db(classification.evidence),
                    datetime_to_db(classification.created_at),
                ),
            )

            classification_id = cursor.lastrowid

        if classification_id is None:
            raise RuntimeError(
                "SQLite did not return a classification id."
            )

        return replace(
            classification,
            id=classification_id,
        )