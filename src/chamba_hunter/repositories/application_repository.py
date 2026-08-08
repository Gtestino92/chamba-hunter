from dataclasses import dataclass
from datetime import datetime

from chamba_hunter.db.connection import Database
from chamba_hunter.db.converters import (
    datetime_from_db,
    datetime_to_db,
)


@dataclass(frozen=True, slots=True)
class ApplicationOpportunity:
    record_kind: str
    record_id: int

    company_id: int
    company_name: str

    title: str
    is_active: bool

    job_url: str | None
    apply_url: str | None


@dataclass(frozen=True, slots=True)
class ApplicationRecord:
    id: int

    company_id: int

    record_kind: str
    record_id: int

    job_id: int | None
    public_contact_id: int | None

    application_type: str
    status: str

    applied_at: datetime | None
    last_status_at: datetime | None

    notes: str | None

    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class JobApplicationWrite:
    company_id: int

    record_kind: str
    record_id: int

    job_id: int | None

    status: str

    applied_at: datetime | None
    last_status_at: datetime

    notes: str | None

    now: datetime


def _optional_datetime(
    value: str | None,
) -> datetime | None:
    if value is None:
        return None

    return datetime_from_db(
        str(value)
    )


def _application_from_row(
    row,
) -> ApplicationRecord:
    return ApplicationRecord(
        id=int(
            row["id"]
        ),
        company_id=int(
            row["company_id"]
        ),
        record_kind=str(
            row["record_kind"]
        ),
        record_id=int(
            row["record_id"]
        ),
        job_id=(
            int(
                row["job_id"]
            )
            if row["job_id"]
            is not None
            else None
        ),
        public_contact_id=(
            int(
                row["public_contact_id"]
            )
            if row[
                "public_contact_id"
            ]
            is not None
            else None
        ),
        application_type=str(
            row["application_type"]
        ),
        status=str(
            row["status"]
        ),
        applied_at=_optional_datetime(
            row["applied_at"]
        ),
        last_status_at=(
            _optional_datetime(
                row["last_status_at"]
            )
        ),
        notes=(
            str(
                row["notes"]
            )
            if row["notes"]
            is not None
            else None
        ),
        created_at=datetime_from_db(
            str(
                row["created_at"]
            )
        ),
        updated_at=datetime_from_db(
            str(
                row["updated_at"]
            )
        ),
    )


class ApplicationRepository:
    def __init__(
        self,
        database: Database,
    ) -> None:
        self.database = database

    def get_opportunity(
        self,
        *,
        record_kind: str,
        record_id: int,
    ) -> ApplicationOpportunity | None:
        if record_kind == "ATS":
            sql = """
                SELECT
                    'ATS' AS record_kind,
                    jobs.id AS record_id,
                    jobs.company_id,
                    companies.name AS company_name,
                    jobs.title,
                    jobs.is_active,
                    jobs.job_url,
                    jobs.apply_url
                FROM jobs
                JOIN companies
                  ON companies.id =
                     jobs.company_id
                WHERE jobs.id = ?
            """
        elif record_kind == "LEAD":
            sql = """
                SELECT
                    'LEAD' AS record_kind,
                    job_leads.id AS record_id,
                    job_leads.company_id,
                    companies.name AS company_name,
                    job_leads.title,
                    job_leads.is_active,
                    job_leads.job_url,
                    job_leads.apply_url
                FROM job_leads
                JOIN companies
                  ON companies.id =
                     job_leads.company_id
                WHERE job_leads.id = ?
            """
        else:
            raise ValueError(
                "record_kind must be ATS or LEAD"
            )

        with self.database.connection() as connection:
            row = connection.execute(
                sql,
                (
                    record_id,
                ),
            ).fetchone()

        if row is None:
            return None

        return ApplicationOpportunity(
            record_kind=str(
                row["record_kind"]
            ),
            record_id=int(
                row["record_id"]
            ),
            company_id=int(
                row["company_id"]
            ),
            company_name=str(
                row["company_name"]
            ),
            title=str(
                row["title"]
            ),
            is_active=bool(
                row["is_active"]
            ),
            job_url=(
                str(
                    row["job_url"]
                )
                if row["job_url"]
                is not None
                else None
            ),
            apply_url=(
                str(
                    row["apply_url"]
                )
                if row["apply_url"]
                is not None
                else None
            ),
        )

    def get_job_application(
        self,
        *,
        record_kind: str,
        record_id: int,
    ) -> ApplicationRecord | None:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    company_id,
                    record_kind,
                    record_id,
                    job_id,
                    public_contact_id,
                    application_type,
                    status,
                    applied_at,
                    last_status_at,
                    notes,
                    created_at,
                    updated_at
                FROM applications
                WHERE application_type = 'JOB'
                  AND record_kind = ?
                  AND record_id = ?
                LIMIT 1
                """,
                (
                    record_kind,
                    record_id,
                ),
            ).fetchone()

        if row is None:
            return None

        return _application_from_row(
            row
        )

    def upsert_job_application(
        self,
        write: JobApplicationWrite,
    ) -> tuple[
        ApplicationRecord,
        bool,
    ]:
        now_db = datetime_to_db(
            write.now
        )

        applied_at_db = (
            datetime_to_db(
                write.applied_at
            )
            if write.applied_at
            is not None
            else None
        )

        last_status_at_db = (
            datetime_to_db(
                write.last_status_at
            )
        )

        with self.database.transaction() as connection:
            existing = connection.execute(
                """
                SELECT id
                FROM applications
                WHERE application_type = 'JOB'
                  AND record_kind = ?
                  AND record_id = ?
                LIMIT 1
                """,
                (
                    write.record_kind,
                    write.record_id,
                ),
            ).fetchone()

            created = (
                existing is None
            )

            if created:
                cursor = connection.execute(
                    """
                    INSERT INTO applications (
                        company_id,
                        job_id,
                        public_contact_id,
                        application_type,
                        status,
                        applied_at,
                        last_status_at,
                        notes,
                        created_at,
                        updated_at,
                        record_kind,
                        record_id
                    )
                    VALUES (
                        ?,
                        ?,
                        NULL,
                        'JOB',
                        ?,
                        ?,
                        ?,
                        ?,
                        ?,
                        ?,
                        ?,
                        ?
                    )
                    """,
                    (
                        write.company_id,
                        write.job_id,
                        write.status,
                        applied_at_db,
                        last_status_at_db,
                        write.notes,
                        now_db,
                        now_db,
                        write.record_kind,
                        write.record_id,
                    ),
                )

                application_id = int(
                    cursor.lastrowid
                )
            else:
                application_id = int(
                    existing["id"]
                )

                connection.execute(
                    """
                    UPDATE applications
                    SET
                        company_id = ?,
                        job_id = ?,
                        status = ?,
                        applied_at = ?,
                        last_status_at = ?,
                        notes = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        write.company_id,
                        write.job_id,
                        write.status,
                        applied_at_db,
                        last_status_at_db,
                        write.notes,
                        now_db,
                        application_id,
                    ),
                )

            row = connection.execute(
                """
                SELECT
                    id,
                    company_id,
                    record_kind,
                    record_id,
                    job_id,
                    public_contact_id,
                    application_type,
                    status,
                    applied_at,
                    last_status_at,
                    notes,
                    created_at,
                    updated_at
                FROM applications
                WHERE id = ?
                """,
                (
                    application_id,
                ),
            ).fetchone()

        if row is None:
            raise RuntimeError(
                "Application upsert did not "
                "return a persisted row."
            )

        return (
            _application_from_row(
                row
            ),
            created,
        )
