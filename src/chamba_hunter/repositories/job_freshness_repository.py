from dataclasses import dataclass

from chamba_hunter.db.connection import Database
from chamba_hunter.domain.job_content import (
    JOB_CONTENT_HASH_VERSION,
    build_job_content_hash,
)


@dataclass(frozen=True, slots=True)
class FreshnessBaselineCounts:
    jobs_initialized: int
    leads_initialized: int

    @property
    def total_initialized(
        self,
    ) -> int:
        return (
            self.jobs_initialized
            + self.leads_initialized
        )


class JobFreshnessRepository:
    def __init__(
        self,
        database: Database,
    ) -> None:
        self.database = database

    def schema_available(
        self,
    ) -> bool:
        with self.database.connection() as connection:
            job_columns = {
                str(row["name"])
                for row in connection.execute(
                    "PRAGMA table_info(jobs)"
                ).fetchall()
            }

            lead_columns = {
                str(row["name"])
                for row in connection.execute(
                    "PRAGMA table_info(job_leads)"
                ).fetchall()
            }

        required = {
            "content_hash",
            "content_hash_version",
            "last_changed_at",
        }

        return (
            required <= job_columns
            and required <= lead_columns
        )

    def count_missing_baseline(
        self,
    ) -> FreshnessBaselineCounts:
        if not self.schema_available():
            return FreshnessBaselineCounts(
                jobs_initialized=0,
                leads_initialized=0,
            )

        with self.database.connection() as connection:
            jobs = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM jobs
                WHERE content_hash IS NULL
                   OR content_hash_version IS NULL
                   OR content_hash_version <> ?
                """,
                (
                    JOB_CONTENT_HASH_VERSION,
                ),
            ).fetchone()

            leads = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM job_leads
                WHERE content_hash IS NULL
                   OR content_hash_version IS NULL
                   OR content_hash_version <> ?
                """,
                (
                    JOB_CONTENT_HASH_VERSION,
                ),
            ).fetchone()

        return FreshnessBaselineCounts(
            jobs_initialized=(
                int(jobs["count"])
                if jobs is not None
                else 0
            ),
            leads_initialized=(
                int(leads["count"])
                if leads is not None
                else 0
            ),
        )

    def initialize_missing_baseline(
        self,
    ) -> FreshnessBaselineCounts:
        if not self.schema_available():
            raise RuntimeError(
                "Freshness schema is not available. "
                "Apply migration 010 first."
            )

        with self.database.transaction() as connection:
            job_rows = connection.execute(
                """
                SELECT
                    id,
                    title,
                    description,
                    location_text,
                    workplace_type,
                    employment_type,
                    job_url,
                    apply_url,
                    published_at
                FROM jobs
                WHERE content_hash IS NULL
                   OR content_hash_version IS NULL
                   OR content_hash_version <> ?
                ORDER BY id
                """,
                (
                    JOB_CONTENT_HASH_VERSION,
                ),
            ).fetchall()

            for row in job_rows:
                content_hash = build_job_content_hash(
                    title=str(row["title"]),
                    description=(
                        str(row["description"])
                        if row["description"]
                        is not None
                        else None
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
                    employment_type=(
                        str(row["employment_type"])
                        if row["employment_type"]
                        is not None
                        else None
                    ),
                    job_url=(
                        str(row["job_url"])
                        if row["job_url"]
                        is not None
                        else None
                    ),
                    apply_url=(
                        str(row["apply_url"])
                        if row["apply_url"]
                        is not None
                        else None
                    ),
                    published_at=(
                        str(row["published_at"])
                        if row["published_at"]
                        is not None
                        else None
                    ),
                )

                connection.execute(
                    """
                    UPDATE jobs
                    SET
                        content_hash = ?,
                        content_hash_version = ?
                    WHERE id = ?
                    """,
                    (
                        content_hash,
                        JOB_CONTENT_HASH_VERSION,
                        int(row["id"]),
                    ),
                )

            lead_rows = connection.execute(
                """
                SELECT
                    id,
                    title,
                    description,
                    location_text,
                    workplace_type,
                    employment_type,
                    job_url,
                    apply_url,
                    published_at,
                    expires_at
                FROM job_leads
                WHERE content_hash IS NULL
                   OR content_hash_version IS NULL
                   OR content_hash_version <> ?
                ORDER BY id
                """,
                (
                    JOB_CONTENT_HASH_VERSION,
                ),
            ).fetchall()

            for row in lead_rows:
                content_hash = build_job_content_hash(
                    title=str(row["title"]),
                    description=(
                        str(row["description"])
                        if row["description"]
                        is not None
                        else None
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
                    employment_type=(
                        str(row["employment_type"])
                        if row["employment_type"]
                        is not None
                        else None
                    ),
                    job_url=(
                        str(row["job_url"])
                        if row["job_url"]
                        is not None
                        else None
                    ),
                    apply_url=(
                        str(row["apply_url"])
                        if row["apply_url"]
                        is not None
                        else None
                    ),
                    published_at=(
                        str(row["published_at"])
                        if row["published_at"]
                        is not None
                        else None
                    ),
                    expires_at=(
                        str(row["expires_at"])
                        if row["expires_at"]
                        is not None
                        else None
                    ),
                )

                connection.execute(
                    """
                    UPDATE job_leads
                    SET
                        content_hash = ?,
                        content_hash_version = ?
                    WHERE id = ?
                    """,
                    (
                        content_hash,
                        JOB_CONTENT_HASH_VERSION,
                        int(row["id"]),
                    ),
                )

        return FreshnessBaselineCounts(
            jobs_initialized=len(job_rows),
            leads_initialized=len(lead_rows),
        )
