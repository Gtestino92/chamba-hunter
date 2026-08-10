from dataclasses import dataclass
from datetime import datetime

from chamba_hunter.db.connection import Database
from chamba_hunter.db.converters import (
    bool_to_db,
    datetime_to_db,
    json_to_db,
)
from chamba_hunter.domain.enums import (
    BROAD_JOB_SOURCE_TYPES,
    SourceType,
)
from chamba_hunter.domain.job_content import (
    JOB_CONTENT_HASH_VERSION,
    build_job_content_hash,
)
from chamba_hunter.domain.job_leads import JobLead


@dataclass(frozen=True, slots=True)
class JobLeadUpsertCounts:
    created: int
    updated: int


class JobLeadRepository:
    def __init__(
        self,
        database: Database,
    ) -> None:
        self.database = database

    def upsert_source_jobs(
        self,
        source_type: SourceType,
        jobs: list[JobLead],
        seen_at: datetime,
    ) -> JobLeadUpsertCounts:
        if source_type not in BROAD_JOB_SOURCE_TYPES:
            accepted = ", ".join(
                sorted(
                    source.value
                    for source in BROAD_JOB_SOURCE_TYPES
                )
            )
            raise ValueError(
                "Broad job acquisition only "
                "accepts configured broad sources: "
                f"{accepted}."
            )

        incoming: dict[str, JobLead] = {}

        for job in jobs:
            if job.source_type != source_type:
                raise ValueError(
                    "Job lead source does not "
                    "match the upsert source."
                )

            external_id = job.external_id.strip()

            if not external_id:
                raise ValueError(
                    "Job lead external_id "
                    "cannot be empty."
                )

            if external_id in incoming:
                raise ValueError(
                    "Duplicate job lead external "
                    "id in one source response: "
                    f"{external_id}"
                )

            incoming[external_id] = job

        if not incoming:
            return JobLeadUpsertCounts(
                created=0,
                updated=0,
            )

        seen_at_db = datetime_to_db(
            seen_at
        )

        with self.database.transaction() as connection:
            existing_rows = connection.execute(
                """
                SELECT external_id
                FROM job_leads
                WHERE source_type = ?
                """,
                (
                    source_type.value,
                ),
            ).fetchall()

            existing_ids = {
                str(row["external_id"])
                for row in existing_rows
            }

            for external_id, job in incoming.items():
                published_at_db = (
                    datetime_to_db(
                        job.published_at
                    )
                    if job.published_at
                    is not None
                    else None
                )

                expires_at_db = (
                    datetime_to_db(
                        job.expires_at
                    )
                    if job.expires_at
                    is not None
                    else None
                )

                content_hash = build_job_content_hash(
                    title=job.title,
                    description=job.description,
                    location_text=job.location_text,
                    workplace_type=job.workplace_type.value,
                    employment_type=job.employment_type,
                    job_url=job.job_url,
                    apply_url=job.apply_url,
                    published_at=published_at_db,
                    expires_at=expires_at_db,
                )

                connection.execute(
                    """
                    INSERT INTO job_leads (
                        company_id,
                        source_type,
                        external_id,
                        canonical_job_id,
                        title,
                        description,
                        location_text,
                        workplace_type,
                        employment_type,
                        job_url,
                        apply_url,
                        published_at,
                        expires_at,
                        first_seen_at,
                        last_seen_at,
                        is_active,
                        raw_payload_json,
                        content_hash,
                        content_hash_version,
                        last_changed_at
                    )
                    VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    ON CONFLICT (
                        source_type,
                        external_id
                    )
                    DO UPDATE SET
                        company_id = excluded.company_id,
                        title = excluded.title,
                        description = excluded.description,
                        location_text = excluded.location_text,
                        workplace_type = excluded.workplace_type,
                        employment_type = excluded.employment_type,
                        job_url = excluded.job_url,
                        apply_url = excluded.apply_url,
                        published_at = excluded.published_at,
                        expires_at = excluded.expires_at,
                        last_seen_at = excluded.last_seen_at,
                        is_active = excluded.is_active,
                        raw_payload_json = excluded.raw_payload_json,
                        last_changed_at = CASE
                            WHEN job_leads.content_hash IS NULL
                              OR job_leads.content_hash_version IS NULL
                              OR job_leads.content_hash_version
                                 <> excluded.content_hash_version
                                THEN job_leads.last_changed_at
                            WHEN job_leads.content_hash
                                 <> excluded.content_hash
                                THEN excluded.last_seen_at
                            ELSE job_leads.last_changed_at
                        END,
                        content_hash = excluded.content_hash,
                        content_hash_version =
                            excluded.content_hash_version
                    """,
                    (
                        job.company_id,
                        source_type.value,
                        external_id,
                        job.canonical_job_id,
                        job.title,
                        job.description,
                        job.location_text,
                        job.workplace_type.value,
                        job.employment_type,
                        job.job_url,
                        job.apply_url,
                        published_at_db,
                        expires_at_db,
                        seen_at_db,
                        seen_at_db,
                        bool_to_db(job.is_active),
                        json_to_db(job.raw_payload),
                        content_hash,
                        JOB_CONTENT_HASH_VERSION,
                        None,
                    ),
                )

        created = sum(
            1
            for external_id in incoming
            if external_id not in existing_ids
        )

        return JobLeadUpsertCounts(
            created=created,
            updated=len(incoming) - created,
        )

    def get_id(
        self,
        source_type: SourceType,
        external_id: str,
    ) -> int | None:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT id
                FROM job_leads
                WHERE source_type = ?
                  AND external_id = ?
                """,
                (
                    source_type.value,
                    external_id,
                ),
            ).fetchone()

        if row is None:
            return None

        return int(row["id"])

    def count_active_unresolved(
        self,
    ) -> int:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM job_leads
                WHERE is_active = 1
                  AND canonical_job_id IS NULL
                """
            ).fetchone()

        if row is None:
            return 0

        return int(row["count"])

    def count_active_candidates(
        self,
    ) -> int:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM job_candidates
                WHERE is_active = 1
                """
            ).fetchone()

        if row is None:
            return 0

        return int(row["count"])
