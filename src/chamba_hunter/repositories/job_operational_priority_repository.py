from dataclasses import dataclass
from datetime import datetime

from chamba_hunter.db.connection import Database
from chamba_hunter.db.converters import (
    datetime_from_db,
    datetime_to_db,
    json_to_db,
)
from chamba_hunter.domain.common import JsonObject


@dataclass(frozen=True, slots=True)
class OperationalCandidateRow:
    record_kind: str
    record_id: int

    company_id: int
    company_name: str

    source_type: str
    origin: str
    title: str

    current_professional_match: bool

    source_present: bool
    source_is_active: bool
    canonical_job_active: bool

    job_url: str | None
    apply_url: str | None
    general_application_url: str | None
    public_contact: str | None

    published_at: datetime | None
    expires_at: datetime | None
    first_seen_at: datetime
    last_seen_at: datetime
    last_changed_at: datetime | None

    professional_score: float
    professional_match_level: str
    professional_rule_version: str
    professional_matched_at: datetime | None

    previous_operational_state: str | None


@dataclass(frozen=True, slots=True)
class OperationalPriorityWrite:
    record_kind: str
    record_id: int

    company_id: int
    company_name: str

    source_type: str
    origin: str
    title: str

    operational_state: str

    professional_score: float
    professional_match_level: str
    professional_rule_version: str
    professional_matched_at: datetime | None

    application_channel: str
    application_target: str | None

    job_url: str | None
    apply_url: str | None
    general_application_url: str | None

    first_seen_at: datetime
    last_seen_at: datetime
    published_at: datetime | None
    last_changed_at: datetime | None

    reasons: JsonObject

    rule_version: str


@dataclass(frozen=True, slots=True)
class OperationalPriorityCounts:
    created: int
    updated: int


def _optional_datetime(
    value: str | None,
) -> datetime | None:
    if value is None:
        return None

    return datetime_from_db(
        str(value)
    )


class JobOperationalPriorityRepository:
    def __init__(
        self,
        database: Database,
    ) -> None:
        self.database = database

    def priority_schema_available(
        self,
    ) -> bool:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM sqlite_master
                WHERE type = 'table'
                  AND name = 'job_operational_priorities'
                """
            ).fetchone()

        return row is not None

    def freshness_schema_available(
        self,
    ) -> bool:
        with self.database.connection() as connection:
            columns = {
                str(row["name"])
                for row in connection.execute(
                    "PRAGMA table_info(jobs)"
                ).fetchall()
            }

        return {
            "content_hash",
            "content_hash_version",
            "last_changed_at",
        } <= columns

    def get_search_profile_id(
        self,
        profile_name: str,
    ) -> int:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT id
                FROM search_profiles
                WHERE name = ?
                  AND is_active = 1
                """,
                (
                    profile_name,
                ),
            ).fetchone()

        if row is None:
            raise RuntimeError(
                "Active search profile not found: "
                f"{profile_name}"
            )

        return int(row["id"])

    def previous_successful_watermark(
        self,
    ) -> datetime | None:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT finished_at
                FROM runs
                WHERE command = 'prioritize_jobs'
                  AND status = 'SUCCESS'
                  AND finished_at IS NOT NULL
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()

        if row is None:
            return None

        return datetime_from_db(
            str(row["finished_at"])
        )

    def list_candidates(
        self,
        search_profile_id: int,
    ) -> list[OperationalCandidateRow]:
        freshness_available = (
            self.freshness_schema_available()
        )
        priority_available = (
            self.priority_schema_available()
        )

        last_changed_expression = (
            """
            CASE
                WHEN pm.record_kind = 'ATS'
                    THEN jobs.last_changed_at
                ELSE job_leads.last_changed_at
            END
            """
            if freshness_available
            else "NULL"
        )

        previous_join = (
            """
            LEFT JOIN job_operational_priorities previous
              ON previous.record_kind = pm.record_kind
             AND previous.record_id = pm.record_id
             AND previous.search_profile_id =
                 pm.search_profile_id
            """
            if priority_available
            else ""
        )

        previous_expression = (
            "previous.operational_state"
            if priority_available
            else "NULL"
        )

        current_sql = f"""
            SELECT
                pm.record_kind,
                pm.record_id,
                jc.company_id,
                companies.name AS company_name,
                jc.source_type,
                CASE
                    WHEN jc.record_kind = 'ATS'
                        THEN company_ats.provider
                    ELSE jc.source_type
                END AS origin,
                jc.title,
                1 AS current_professional_match,
                1 AS source_present,
                jc.is_active AS source_is_active,
                0 AS canonical_job_active,
                jc.job_url,
                jc.apply_url,
                COALESCE(
                    companies.general_application_url,
                    (
                        SELECT public_contacts.value
                        FROM public_contacts
                        WHERE public_contacts.company_id =
                              jc.company_id
                          AND public_contacts.is_active = 1
                          AND public_contacts.contact_type =
                              'GENERAL_APPLICATION_URL'
                          AND public_contacts.review_status =
                              'VALID'
                        ORDER BY public_contacts.id
                        LIMIT 1
                    )
                ) AS general_application_url,
                (
                    SELECT public_contacts.value
                    FROM public_contacts
                    WHERE public_contacts.company_id =
                          jc.company_id
                      AND public_contacts.is_active = 1
                      AND public_contacts.contact_type IN (
                          'CAREERS_EMAIL',
                          'RECRUITING_EMAIL'
                      )
                      AND public_contacts.review_status =
                          'VALID'
                    ORDER BY public_contacts.id
                    LIMIT 1
                ) AS public_contact,
                jc.published_at,
                jc.expires_at,
                jc.first_seen_at,
                jc.last_seen_at,
                {last_changed_expression}
                    AS last_changed_at,
                pm.score AS professional_score,
                pm.match_level
                    AS professional_match_level,
                pm.rule_version
                    AS professional_rule_version,
                pm.matched_at
                    AS professional_matched_at,
                {previous_expression}
                    AS previous_operational_state
            FROM job_professional_matches pm
            JOIN job_candidates jc
              ON jc.record_kind = pm.record_kind
             AND jc.record_id = pm.record_id
            JOIN companies
              ON companies.id = jc.company_id
            LEFT JOIN company_ats
              ON company_ats.id = jc.company_ats_id
            LEFT JOIN jobs
              ON pm.record_kind = 'ATS'
             AND jobs.id = pm.record_id
            LEFT JOIN job_leads
              ON pm.record_kind = 'LEAD'
             AND job_leads.id = pm.record_id
            {previous_join}
            WHERE pm.search_profile_id = ?
              AND jc.is_active = 1
            ORDER BY
                pm.record_kind,
                pm.record_id
        """

        with self.database.connection() as connection:
            current_rows = connection.execute(
                current_sql,
                (
                    search_profile_id,
                ),
            ).fetchall()

        result = [
            self._candidate_from_row(row)
            for row in current_rows
        ]

        if not priority_available:
            return result

        current_keys = {
            (
                candidate.record_kind,
                candidate.record_id,
            )
            for candidate in result
        }

        with self.database.connection() as connection:
            previous_rows = connection.execute(
                """
                SELECT *
                FROM job_operational_priorities
                WHERE search_profile_id = ?
                ORDER BY
                    record_kind,
                    record_id
                """,
                (
                    search_profile_id,
                ),
            ).fetchall()

            for previous in previous_rows:
                key = (
                    str(previous["record_kind"]),
                    int(previous["record_id"]),
                )

                if key in current_keys:
                    continue

                result.append(
                    self._stale_candidate(
                        connection=connection,
                        previous=previous,
                    )
                )

        return sorted(
            result,
            key=lambda item: (
                item.record_kind,
                item.record_id,
            ),
        )

    def _candidate_from_row(
        self,
        row,
    ) -> OperationalCandidateRow:
        return OperationalCandidateRow(
            record_kind=str(row["record_kind"]),
            record_id=int(row["record_id"]),
            company_id=int(row["company_id"]),
            company_name=str(row["company_name"]),
            source_type=str(row["source_type"]),
            origin=str(row["origin"]),
            title=str(row["title"]),
            current_professional_match=bool(
                row["current_professional_match"]
            ),
            source_present=bool(
                row["source_present"]
            ),
            source_is_active=bool(
                row["source_is_active"]
            ),
            canonical_job_active=bool(
                row["canonical_job_active"]
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
            general_application_url=(
                str(
                    row[
                        "general_application_url"
                    ]
                )
                if row[
                    "general_application_url"
                ]
                is not None
                else None
            ),
            public_contact=(
                str(row["public_contact"])
                if row["public_contact"]
                is not None
                else None
            ),
            published_at=_optional_datetime(
                row["published_at"]
            ),
            expires_at=_optional_datetime(
                row["expires_at"]
            ),
            first_seen_at=datetime_from_db(
                str(row["first_seen_at"])
            ),
            last_seen_at=datetime_from_db(
                str(row["last_seen_at"])
            ),
            last_changed_at=_optional_datetime(
                row["last_changed_at"]
            ),
            professional_score=float(
                row["professional_score"]
            ),
            professional_match_level=str(
                row["professional_match_level"]
            ),
            professional_rule_version=str(
                row["professional_rule_version"]
            ),
            professional_matched_at=(
                _optional_datetime(
                    row["professional_matched_at"]
                )
            ),
            previous_operational_state=(
                str(
                    row[
                        "previous_operational_state"
                    ]
                )
                if row[
                    "previous_operational_state"
                ]
                is not None
                else None
            ),
        )

    def _stale_candidate(
        self,
        connection,
        previous,
    ) -> OperationalCandidateRow:
        record_kind = str(
            previous["record_kind"]
        )
        record_id = int(
            previous["record_id"]
        )

        source_present = False
        source_is_active = False
        canonical_job_active = False

        company_id = int(
            previous["company_id"]
        )
        company_name = str(
            previous["company_name"]
        )
        source_type = str(
            previous["source_type"]
        )
        origin = str(
            previous["origin"]
        )
        title = str(
            previous["title"]
        )

        job_url = (
            str(previous["job_url"])
            if previous["job_url"]
            is not None
            else None
        )
        apply_url = (
            str(previous["apply_url"])
            if previous["apply_url"]
            is not None
            else None
        )
        general_application_url = (
            str(
                previous[
                    "general_application_url"
                ]
            )
            if previous[
                "general_application_url"
            ]
            is not None
            else None
        )

        published_at = _optional_datetime(
            previous["published_at"]
        )
        expires_at = None
        last_changed_at = _optional_datetime(
            previous["last_changed_at"]
        )
        first_seen_at = datetime_from_db(
            str(previous["first_seen_at"])
        )
        last_seen_at = datetime_from_db(
            str(previous["last_seen_at"])
        )

        if record_kind == "ATS":
            row = connection.execute(
                """
                SELECT
                    jobs.company_id,
                    companies.name AS company_name,
                    companies.general_application_url,
                    company_ats.provider AS origin,
                    jobs.title,
                    jobs.job_url,
                    jobs.apply_url,
                    jobs.published_at,
                    jobs.first_seen_at,
                    jobs.last_seen_at,
                    jobs.is_active,
                    jobs.last_changed_at
                FROM jobs
                JOIN companies
                  ON companies.id = jobs.company_id
                LEFT JOIN company_ats
                  ON company_ats.id =
                     jobs.company_ats_id
                WHERE jobs.id = ?
                """,
                (
                    record_id,
                ),
            ).fetchone()

            if row is not None:
                source_present = True
                source_is_active = bool(
                    row["is_active"]
                )
                company_id = int(
                    row["company_id"]
                )
                company_name = str(
                    row["company_name"]
                )
                source_type = "ATS"
                origin = (
                    str(row["origin"])
                    if row["origin"]
                    is not None
                    else "ATS"
                )
                title = str(row["title"])
                job_url = (
                    str(row["job_url"])
                    if row["job_url"]
                    is not None
                    else None
                )
                apply_url = (
                    str(row["apply_url"])
                    if row["apply_url"]
                    is not None
                    else None
                )
                general_application_url = (
                    str(
                        row[
                            "general_application_url"
                        ]
                    )
                    if row[
                        "general_application_url"
                    ]
                    is not None
                    else None
                )
                published_at = _optional_datetime(
                    row["published_at"]
                )
                first_seen_at = datetime_from_db(
                    str(row["first_seen_at"])
                )
                last_seen_at = datetime_from_db(
                    str(row["last_seen_at"])
                )
                last_changed_at = _optional_datetime(
                    row["last_changed_at"]
                )

        else:
            row = connection.execute(
                """
                SELECT
                    job_leads.company_id,
                    companies.name AS company_name,
                    companies.general_application_url,
                    job_leads.source_type,
                    job_leads.title,
                    job_leads.job_url,
                    job_leads.apply_url,
                    job_leads.published_at,
                    job_leads.expires_at,
                    job_leads.first_seen_at,
                    job_leads.last_seen_at,
                    job_leads.is_active,
                    job_leads.last_changed_at,
                    CASE
                        WHEN canonical_job.id IS NOT NULL
                         AND canonical_job.is_active = 1
                            THEN 1
                        ELSE 0
                    END AS canonical_job_active
                FROM job_leads
                JOIN companies
                  ON companies.id =
                     job_leads.company_id
                LEFT JOIN jobs canonical_job
                  ON canonical_job.id =
                     job_leads.canonical_job_id
                WHERE job_leads.id = ?
                """,
                (
                    record_id,
                ),
            ).fetchone()

            if row is not None:
                source_present = True
                source_is_active = bool(
                    row["is_active"]
                )
                canonical_job_active = bool(
                    row["canonical_job_active"]
                )
                company_id = int(
                    row["company_id"]
                )
                company_name = str(
                    row["company_name"]
                )
                source_type = str(
                    row["source_type"]
                )
                origin = source_type
                title = str(row["title"])
                job_url = (
                    str(row["job_url"])
                    if row["job_url"]
                    is not None
                    else None
                )
                apply_url = (
                    str(row["apply_url"])
                    if row["apply_url"]
                    is not None
                    else None
                )
                general_application_url = (
                    str(
                        row[
                            "general_application_url"
                        ]
                    )
                    if row[
                        "general_application_url"
                    ]
                    is not None
                    else None
                )
                published_at = _optional_datetime(
                    row["published_at"]
                )
                expires_at = _optional_datetime(
                    row["expires_at"]
                )
                first_seen_at = datetime_from_db(
                    str(row["first_seen_at"])
                )
                last_seen_at = datetime_from_db(
                    str(row["last_seen_at"])
                )
                last_changed_at = _optional_datetime(
                    row["last_changed_at"]
                )

        general_contact_row = connection.execute(
            """
            SELECT value
            FROM public_contacts
            WHERE company_id = ?
              AND is_active = 1
              AND contact_type =
                  'GENERAL_APPLICATION_URL'
              AND review_status = 'VALID'
            ORDER BY id
            LIMIT 1
            """,
            (
                company_id,
            ),
        ).fetchone()

        if (
            general_application_url is None
            and general_contact_row
            is not None
        ):
            general_application_url = str(
                general_contact_row["value"]
            )

        public_contact_row = connection.execute(
            """
            SELECT value
            FROM public_contacts
            WHERE company_id = ?
              AND is_active = 1
              AND contact_type IN (
                  'CAREERS_EMAIL',
                  'RECRUITING_EMAIL'
              )
              AND review_status = 'VALID'
            ORDER BY id
            LIMIT 1
            """,
            (
                company_id,
            ),
        ).fetchone()

        public_contact = (
            str(
                public_contact_row["value"]
            )
            if public_contact_row
            is not None
            else None
        )

        return OperationalCandidateRow(
            record_kind=record_kind,
            record_id=record_id,
            company_id=company_id,
            company_name=company_name,
            source_type=source_type,
            origin=origin,
            title=title,
            current_professional_match=False,
            source_present=source_present,
            source_is_active=source_is_active,
            canonical_job_active=(
                canonical_job_active
            ),
            job_url=job_url,
            apply_url=apply_url,
            general_application_url=(
                general_application_url
            ),
            public_contact=public_contact,
            published_at=published_at,
            expires_at=expires_at,
            first_seen_at=first_seen_at,
            last_seen_at=last_seen_at,
            last_changed_at=last_changed_at,
            professional_score=float(
                previous["professional_score"]
            ),
            professional_match_level=str(
                previous[
                    "professional_match_level"
                ]
            ),
            professional_rule_version=str(
                previous[
                    "professional_rule_version"
                ]
            ),
            professional_matched_at=(
                _optional_datetime(
                    previous[
                        "professional_matched_at"
                    ]
                )
            ),
            previous_operational_state=str(
                previous["operational_state"]
            ),
        )

    def upsert_priorities(
        self,
        *,
        search_profile_id: int,
        writes: list[
            OperationalPriorityWrite
        ],
        evaluated_at: datetime,
        evaluated_run_id: int,
    ) -> OperationalPriorityCounts:
        keys = {
            (
                write.record_kind,
                write.record_id,
            )
            for write in writes
        }

        if len(keys) != len(writes):
            raise ValueError(
                "Duplicate candidate key in one "
                "operational priority run."
            )

        evaluated_at_db = datetime_to_db(
            evaluated_at
        )

        with self.database.transaction() as connection:
            existing_rows = connection.execute(
                """
                SELECT
                    record_kind,
                    record_id
                FROM job_operational_priorities
                WHERE search_profile_id = ?
                """,
                (
                    search_profile_id,
                ),
            ).fetchall()

            existing_keys = {
                (
                    str(row["record_kind"]),
                    int(row["record_id"]),
                )
                for row in existing_rows
            }

            for write in writes:
                connection.execute(
                    """
                    INSERT INTO job_operational_priorities (
                        record_kind,
                        record_id,
                        search_profile_id,
                        company_id,
                        company_name,
                        source_type,
                        origin,
                        title,
                        operational_state,
                        professional_score,
                        professional_match_level,
                        professional_rule_version,
                        professional_matched_at,
                        application_channel,
                        application_target,
                        job_url,
                        apply_url,
                        general_application_url,
                        first_seen_at,
                        last_seen_at,
                        published_at,
                        last_changed_at,
                        reasons_json,
                        rule_version,
                        evaluated_at,
                        evaluated_run_id
                    )
                    VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?
                    )
                    ON CONFLICT (
                        record_kind,
                        record_id,
                        search_profile_id
                    )
                    DO UPDATE SET
                        company_id = excluded.company_id,
                        company_name = excluded.company_name,
                        source_type = excluded.source_type,
                        origin = excluded.origin,
                        title = excluded.title,
                        operational_state =
                            excluded.operational_state,
                        professional_score =
                            excluded.professional_score,
                        professional_match_level =
                            excluded.professional_match_level,
                        professional_rule_version =
                            excluded.professional_rule_version,
                        professional_matched_at =
                            excluded.professional_matched_at,
                        application_channel =
                            excluded.application_channel,
                        application_target =
                            excluded.application_target,
                        job_url = excluded.job_url,
                        apply_url = excluded.apply_url,
                        general_application_url =
                            excluded.general_application_url,
                        first_seen_at =
                            excluded.first_seen_at,
                        last_seen_at =
                            excluded.last_seen_at,
                        published_at =
                            excluded.published_at,
                        last_changed_at =
                            excluded.last_changed_at,
                        reasons_json =
                            excluded.reasons_json,
                        rule_version =
                            excluded.rule_version,
                        evaluated_at =
                            excluded.evaluated_at,
                        evaluated_run_id =
                            excluded.evaluated_run_id
                    """,
                    (
                        write.record_kind,
                        write.record_id,
                        search_profile_id,
                        write.company_id,
                        write.company_name,
                        write.source_type,
                        write.origin,
                        write.title,
                        write.operational_state,
                        write.professional_score,
                        write.professional_match_level,
                        write.professional_rule_version,
                        (
                            datetime_to_db(
                                write
                                .professional_matched_at
                            )
                            if write
                            .professional_matched_at
                            is not None
                            else None
                        ),
                        write.application_channel,
                        write.application_target,
                        write.job_url,
                        write.apply_url,
                        write.general_application_url,
                        datetime_to_db(
                            write.first_seen_at
                        ),
                        datetime_to_db(
                            write.last_seen_at
                        ),
                        (
                            datetime_to_db(
                                write.published_at
                            )
                            if write.published_at
                            is not None
                            else None
                        ),
                        (
                            datetime_to_db(
                                write.last_changed_at
                            )
                            if write.last_changed_at
                            is not None
                            else None
                        ),
                        json_to_db(
                            write.reasons
                        ),
                        write.rule_version,
                        evaluated_at_db,
                        evaluated_run_id,
                    ),
                )

        return OperationalPriorityCounts(
            created=len(
                keys - existing_keys
            ),
            updated=len(
                keys & existing_keys
            ),
        )
