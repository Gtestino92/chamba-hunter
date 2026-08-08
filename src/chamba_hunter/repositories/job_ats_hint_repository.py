from chamba_hunter.db.connection import Database
from chamba_hunter.db.converters import datetime_to_db
from chamba_hunter.domain.job_leads import JobAtsHint


class JobAtsHintRepository:
    def __init__(
        self,
        database: Database,
    ) -> None:
        self.database = database

    def add_many(
        self,
        hints: list[JobAtsHint],
    ) -> int:
        created = 0

        with self.database.transaction() as connection:
            for hint in hints:
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO job_ats_hints (
                        job_lead_id,
                        company_id,
                        provider,
                        external_identifier,
                        source_url,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        hint.job_lead_id,
                        hint.company_id,
                        hint.provider.value,
                        hint.external_identifier,
                        hint.source_url,
                        datetime_to_db(
                            hint.created_at
                        ),
                    ),
                )

                if cursor.rowcount == 1:
                    created += 1

        return created

    def count_all(
        self,
    ) -> int:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM job_ats_hints
                """
            ).fetchone()

        if row is None:
            return 0

        return int(row["count"])
