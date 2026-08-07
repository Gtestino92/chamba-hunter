from dataclasses import replace

from chamba_hunter.db.connection import Database
from chamba_hunter.db.converters import (
    datetime_to_db,
    json_to_db,
)
from chamba_hunter.domain.models import (
    CompanyClassification,
)


class CompanyClassificationRepository:
    def __init__(
        self,
        database: Database,
    ) -> None:
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
                    json_to_db(
                        classification.evidence
                    ),
                    datetime_to_db(
                        classification.created_at
                    ),
                ),
            )

            classification_id = cursor.lastrowid

        if classification_id is None:
            raise RuntimeError(
                "SQLite did not return a "
                "classification id."
            )

        return replace(
            classification,
            id=classification_id,
        )

    def exists_for_company_and_method(
        self,
        company_id: int,
        method: str,
    ) -> bool:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM company_classifications
                WHERE company_id = ?
                  AND method = ?
                LIMIT 1
                """,
                (
                    company_id,
                    method,
                ),
            ).fetchone()

        return row is not None