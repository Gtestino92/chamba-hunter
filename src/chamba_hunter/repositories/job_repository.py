from dataclasses import dataclass
from datetime import datetime

from chamba_hunter.db.connection import Database
from chamba_hunter.db.converters import (
    bool_to_db,
    datetime_to_db,
    json_to_db,
)
from chamba_hunter.domain.job_content import (
    JOB_CONTENT_HASH_VERSION,
    build_job_content_hash,
)
from chamba_hunter.domain.models import (
    CompanyAts,
    Job,
)


@dataclass(frozen=True, slots=True)
class JobSyncCounts:
    created: int
    updated: int
    deactivated: int


class JobRepository:
    def __init__(
        self,
        database: Database,
    ) -> None:
        self.database = database

    def sync_board_jobs(
        self,
        company_ats: CompanyAts,
        jobs: list[Job],
        seen_at: datetime,
    ) -> JobSyncCounts:
        if company_ats.id is None:
            raise ValueError(
                "Company ATS must have an id."
            )

        seen_at_db = datetime_to_db(
            seen_at
        )

        incoming_by_external_id: dict[
            str,
            Job,
        ] = {}

        for job in jobs:
            if (
                job.company_ats_id
                != company_ats.id
            ):
                raise ValueError(
                    "Job company_ats_id does "
                    "not match the sync target."
                )

            if (
                job.company_id
                != company_ats.company_id
            ):
                raise ValueError(
                    "Job company_id does not "
                    "match the sync target."
                )

            if (
                job.external_id
                in incoming_by_external_id
            ):
                raise ValueError(
                    "Duplicate external job id "
                    "in one ATS response: "
                    f"{job.external_id}"
                )

            incoming_by_external_id[
                job.external_id
            ] = job

        created = 0
        updated = 0

        with self.database.transaction() as connection:
            existing_rows = connection.execute(
                """
                SELECT
                    external_id,
                    is_active,
                    content_hash,
                    content_hash_version,
                    last_changed_at
                FROM jobs
                WHERE company_ats_id = ?
                """,
                (
                    company_ats.id,
                ),
            ).fetchall()

            existing_by_external_id = {
                str(row["external_id"]): row
                for row in existing_rows
            }

            existing_external_ids = set(
                existing_by_external_id
            )

            active_external_ids = {
                str(row["external_id"])
                for row in existing_rows
                if bool(row["is_active"])
            }

            for external_id, job in (
                incoming_by_external_id.items()
            ):
                published_at_db = (
                    datetime_to_db(
                        job.published_at
                    )
                    if job.published_at
                    is not None
                    else None
                )

                raw_payload_db = json_to_db(
                    job.raw_payload
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
                )

                if (
                    external_id
                    in existing_external_ids
                ):
                    existing = (
                        existing_by_external_id[
                            external_id
                        ]
                    )

                    previous_hash = (
                        existing["content_hash"]
                    )
                    previous_version = (
                        existing[
                            "content_hash_version"
                        ]
                    )
                    previous_changed_at = (
                        existing[
                            "last_changed_at"
                        ]
                    )

                    if (
                        previous_hash is None
                        or previous_version
                        != JOB_CONTENT_HASH_VERSION
                    ):
                        last_changed_at = (
                            previous_changed_at
                        )
                    elif (
                        str(previous_hash)
                        != content_hash
                    ):
                        last_changed_at = (
                            seen_at_db
                        )
                    else:
                        last_changed_at = (
                            previous_changed_at
                        )

                    connection.execute(
                        """
                        UPDATE jobs
                        SET
                            title = ?,
                            description = ?,
                            location_text = ?,
                            workplace_type = ?,
                            employment_type = ?,
                            job_url = ?,
                            apply_url = ?,
                            published_at = ?,
                            last_seen_at = ?,
                            is_active = ?,
                            raw_payload_json = ?,
                            content_hash = ?,
                            content_hash_version = ?,
                            last_changed_at = ?
                        WHERE company_ats_id = ?
                          AND external_id = ?
                        """,
                        (
                            job.title,
                            job.description,
                            job.location_text,
                            job.workplace_type.value,
                            job.employment_type,
                            job.job_url,
                            job.apply_url,
                            published_at_db,
                            seen_at_db,
                            bool_to_db(True),
                            raw_payload_db,
                            content_hash,
                            JOB_CONTENT_HASH_VERSION,
                            last_changed_at,
                            company_ats.id,
                            external_id,
                        ),
                    )

                    updated += 1
                    continue

                connection.execute(
                    """
                    INSERT INTO jobs (
                        company_id,
                        company_ats_id,
                        external_id,
                        title,
                        description,
                        location_text,
                        workplace_type,
                        employment_type,
                        job_url,
                        apply_url,
                        published_at,
                        first_seen_at,
                        last_seen_at,
                        is_active,
                        raw_payload_json,
                        content_hash,
                        content_hash_version,
                        last_changed_at
                    )
                    VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        job.company_id,
                        job.company_ats_id,
                        job.external_id,
                        job.title,
                        job.description,
                        job.location_text,
                        job.workplace_type.value,
                        job.employment_type,
                        job.job_url,
                        job.apply_url,
                        published_at_db,
                        seen_at_db,
                        seen_at_db,
                        bool_to_db(True),
                        raw_payload_db,
                        content_hash,
                        JOB_CONTENT_HASH_VERSION,
                        None,
                    ),
                )

                created += 1

            incoming_external_ids = set(
                incoming_by_external_id
            )

            missing_active_ids = (
                active_external_ids
                - incoming_external_ids
            )

            if missing_active_ids:
                connection.executemany(
                    """
                    UPDATE jobs
                    SET is_active = ?
                    WHERE company_ats_id = ?
                      AND external_id = ?
                    """,
                    [
                        (
                            bool_to_db(False),
                            company_ats.id,
                            external_id,
                        )
                        for external_id
                        in sorted(
                            missing_active_ids
                        )
                    ],
                )

        return JobSyncCounts(
            created=created,
            updated=updated,
            deactivated=len(
                missing_active_ids
            ),
        )
