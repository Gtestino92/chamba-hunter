from dataclasses import dataclass
from datetime import datetime, timedelta

from chamba_hunter.db.connection import Database
from chamba_hunter.db.converters import (
    datetime_from_db,
    datetime_to_db,
    json_from_db,
    json_to_db,
)
from chamba_hunter.domain.common import utc_now
from chamba_hunter.domain.enums import (
    ApplicationStatus,
    ApplicationType,
    CompanyStatus,
    CompanyType,
    ContactReviewStatus,
    ContactType,
    SourceType,
    TargetPriority,
)
from chamba_hunter.domain.models import PublicContact
from chamba_hunter.repositories.public_contact_repository import (
    PublicContactRepository,
)


@dataclass(frozen=True, slots=True)
class CompanyOutreachCandidate:
    company_id: int
    company_name: str
    website_url: str | None
    careers_url: str | None
    general_application_url: str | None
    country: str | None
    remote_latam: bool | None
    remote_argentina: bool | None
    company_type: CompanyType
    target_priority: TargetPriority
    contacts: tuple[PublicContact, ...]
    cessi_activities: tuple[str, ...]
    manual_reference: bool
    current_max_match: float | None
    current_relevant_jobs: int
    historical_max_match: float | None
    contacted: bool


@dataclass(frozen=True, slots=True)
class OutreachPriorityWrite:
    company_id: int
    search_profile_id: int
    current_max_match: float | None
    historical_max_match: float | None
    current_relevant_jobs: int
    best_contact_id: int | None
    score: float
    level: str
    reasons: list[str]
    rule_version: str
    evaluated_at: datetime


@dataclass(frozen=True, slots=True)
class OutreachReportRow:
    company_id: int
    company_name: str
    score: float
    level: str
    best_contact_id: int | None
    contact_type: str | None
    contact_value: str | None
    contact_source_url: str | None
    website_url: str | None
    careers_url: str | None
    country: str | None
    company_type: str
    target_priority: str
    remote_argentina: bool | None
    remote_latam: bool | None
    current_max_match: float | None
    historical_max_match: float | None
    current_relevant_jobs: int
    manual_reference: bool
    cessi_source: bool
    reasons: tuple[str, ...]
    contacted: bool
    outreach_status: str | None
    outreach_at: str | None


@dataclass(frozen=True, slots=True)
class OutreachTrackingResult:
    application_id: int
    created: bool
    previous_status: str | None
    current_status: str


class CompanyOutreachRepository:
    def __init__(
        self,
        database: Database,
        public_contact_repository: PublicContactRepository,
    ) -> None:
        self.database = database
        self.public_contact_repository = (
            public_contact_repository
        )

    def start_contact_scan(
        self,
        company_id: int,
    ) -> int:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO company_contact_scans (
                    company_id,
                    started_at,
                    status
                )
                VALUES (?, ?, 'RUNNING')
                """,
                (
                    company_id,
                    datetime_to_db(utc_now()),
                ),
            )
            scan_id = cursor.lastrowid

        if scan_id is None:
            raise RuntimeError(
                "SQLite did not return a contact scan id."
            )

        return int(scan_id)

    def finish_contact_scan(
        self,
        *,
        scan_id: int,
        status: str,
        pages_fetched: int,
        contacts_found: int,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE company_contact_scans
                SET
                    finished_at = ?,
                    status = ?,
                    pages_fetched = ?,
                    contacts_found = ?,
                    error_type = ?,
                    error_message = ?
                WHERE id = ?
                """,
                (
                    datetime_to_db(utc_now()),
                    status,
                    pages_fetched,
                    contacts_found,
                    error_type,
                    error_message,
                    scan_id,
                ),
            )

    def list_contact_scan_target_ids(
        self,
        *,
        search_profile_name: str,
        limit: int,
        rescan_after_days: int,
        force: bool,
    ) -> list[int]:
        if limit < 1:
            return []

        recent_sql = ""

        params: list[object] = [
            CompanyStatus.ACTIVE.value,
            ApplicationType.SPONTANEOUS_EMAIL.value,
            ApplicationType.GENERAL_APPLICATION.value,
            SourceType.CESSI.value,
            SourceType.MANUAL.value,
            search_profile_name,
            search_profile_name,
        ]

        if not force:
            recent_sql = """
                AND NOT EXISTS (
                    SELECT 1
                    FROM company_contact_scans ccs
                    WHERE ccs.company_id = c.id
                      AND ccs.finished_at IS NOT NULL
                      AND ccs.finished_at >= ?
                )
            """
            cutoff = (
                utc_now()
                - timedelta(days=rescan_after_days)
            )
            params.append(
                datetime_to_db(cutoff)
            )

        params.append(limit)

        sql = f"""
            SELECT DISTINCT c.id
            FROM companies c
            WHERE
                c.status = ?
                AND c.website_url IS NOT NULL
                AND TRIM(c.website_url) != ''

                AND NOT EXISTS (
                    SELECT 1
                    FROM applications a
                    WHERE a.company_id = c.id
                      AND a.application_type IN (?, ?)
                )

                AND NOT EXISTS (
                    SELECT 1
                    FROM public_contacts pc
                    WHERE pc.company_id = c.id
                      AND pc.is_active = 1
                      AND pc.review_status != 'INVALID'
                      AND pc.contact_type IN (
                          'RECRUITING_EMAIL',
                          'CAREERS_EMAIL',
                          'GENERAL_APPLICATION_URL'
                      )
                )

                AND (
                    EXISTS (
                        SELECT 1
                        FROM company_sources cs
                        WHERE cs.company_id = c.id
                          AND cs.source_type IN (?, ?)
                    )
                    OR c.target_priority IN (
                        'VERY_HIGH',
                        'HIGH'
                    )
                    OR EXISTS (
                        SELECT 1
                        FROM company_outreach_priorities cop
                        JOIN search_profiles osp
                          ON osp.id = cop.search_profile_id
                        WHERE cop.company_id = c.id
                          AND osp.name = ?
                          AND cop.historical_max_match >= 50
                    )
                    OR EXISTS (
                        SELECT 1
                        FROM job_professional_matches jpm
                        JOIN search_profiles sp
                          ON sp.id = jpm.search_profile_id
                        WHERE sp.name = ?
                          AND (
                              (
                                  jpm.record_kind = 'ATS'
                                  AND EXISTS (
                                      SELECT 1
                                      FROM jobs j
                                      WHERE j.id = jpm.record_id
                                        AND j.company_id = c.id
                                  )
                              )
                              OR
                              (
                                  jpm.record_kind = 'LEAD'
                                  AND EXISTS (
                                      SELECT 1
                                      FROM job_leads jl
                                      WHERE jl.id = jpm.record_id
                                        AND jl.company_id = c.id
                                  )
                              )
                          )
                    )
                )

                {recent_sql}

            ORDER BY
                CASE c.target_priority
                    WHEN 'VERY_HIGH' THEN 0
                    WHEN 'HIGH' THEN 1
                    ELSE 2
                END,
                c.name COLLATE NOCASE,
                c.id
            LIMIT ?
        """

        with self.database.connection() as connection:
            rows = connection.execute(
                sql,
                tuple(params),
            ).fetchall()

        return [
            int(row["id"])
            for row in rows
        ]

    def fill_general_application_url(
        self,
        *,
        company_id: int,
        url: str,
    ) -> None:
        cleaned = url.strip()

        if not cleaned:
            return

        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE companies
                SET
                    general_application_url =
                        COALESCE(
                            general_application_url,
                            ?
                        ),
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    cleaned,
                    datetime_to_db(utc_now()),
                    company_id,
                ),
            )

    def profile_id(
        self,
        name: str,
    ) -> int:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT id
                FROM search_profiles
                WHERE name = ?
                ORDER BY id
                LIMIT 1
                """,
                (name,),
            ).fetchone()

        if row is None:
            raise ValueError(
                f"Search profile does not exist: {name}"
            )

        return int(row["id"])

    def list_priority_candidates(
        self,
        *,
        search_profile_name: str,
    ) -> tuple[int, list[CompanyOutreachCandidate]]:
        profile_id = self.profile_id(
            search_profile_name
        )

        with self.database.connection() as connection:
            contact_rows = connection.execute(
                """
                SELECT
                    c.id AS company_id,
                    c.name AS company_name,
                    c.website_url,
                    c.careers_url,
                    c.general_application_url,
                    c.country,
                    c.remote_latam,
                    c.remote_argentina,
                    c.company_type,
                    c.target_priority,
                    pc.id AS contact_id,
                    pc.contact_type,
                    pc.value AS contact_value,
                    pc.source_url AS contact_source_url,
                    pc.first_seen_at,
                    pc.last_seen_at,
                    pc.review_status,
                    pc.notes AS contact_notes
                FROM companies c
                JOIN public_contacts pc
                  ON pc.company_id = c.id
                 AND pc.is_active = 1
                 AND pc.review_status != 'INVALID'
                WHERE c.status = 'ACTIVE'
                ORDER BY c.id, pc.id
                """
            ).fetchall()

            match_rows = connection.execute(
                """
                SELECT
                    evidence.company_id,
                    MAX(evidence.score) AS max_score,
                    COUNT(*) AS relevant_jobs
                FROM (
                    SELECT
                        j.company_id AS company_id,
                        jpm.score AS score
                    FROM job_professional_matches jpm
                    JOIN jobs j
                      ON jpm.record_kind = 'ATS'
                     AND j.id = jpm.record_id
                    WHERE jpm.search_profile_id = ?

                    UNION ALL

                    SELECT
                        jl.company_id AS company_id,
                        jpm.score AS score
                    FROM job_professional_matches jpm
                    JOIN job_leads jl
                      ON jpm.record_kind = 'LEAD'
                     AND jl.id = jpm.record_id
                    WHERE jpm.search_profile_id = ?
                ) evidence
                GROUP BY evidence.company_id
                """,
                (
                    profile_id,
                    profile_id,
                ),
            ).fetchall()

            prior_rows = connection.execute(
                """
                SELECT
                    company_id,
                    historical_max_match
                FROM company_outreach_priorities
                WHERE search_profile_id = ?
                """,
                (profile_id,),
            ).fetchall()

            cessi_rows = connection.execute(
                """
                SELECT
                    company_id,
                    metadata_json
                FROM company_sources
                WHERE source_type = ?
                """,
                (SourceType.CESSI.value,),
            ).fetchall()

            manual_rows = connection.execute(
                """
                SELECT DISTINCT company_id
                FROM company_sources
                WHERE source_type = ?
                """,
                (SourceType.MANUAL.value,),
            ).fetchall()

            contacted_rows = connection.execute(
                """
                SELECT DISTINCT company_id
                FROM applications
                WHERE application_type IN (?, ?)
                """,
                (
                    ApplicationType.SPONTANEOUS_EMAIL.value,
                    ApplicationType.GENERAL_APPLICATION.value,
                ),
            ).fetchall()

        matches = {
            int(row["company_id"]): (
                (
                    float(row["max_score"])
                    if row["max_score"] is not None
                    else None
                ),
                int(row["relevant_jobs"]),
            )
            for row in match_rows
        }

        historical = {
            int(row["company_id"]): (
                (
                    float(row["historical_max_match"])
                    if row["historical_max_match"]
                    is not None
                    else None
                )
            )
            for row in prior_rows
        }

        cessi_activities: dict[
            int,
            set[str],
        ] = {}

        for row in cessi_rows:
            metadata = json_from_db(
                row["metadata_json"]
            )

            if not isinstance(metadata, dict):
                continue

            activity = metadata.get(
                "activity"
            )

            if not isinstance(activity, str):
                continue

            cleaned = " ".join(
                activity.split()
            ).strip()

            if cleaned:
                cessi_activities.setdefault(
                    int(row["company_id"]),
                    set(),
                ).add(cleaned)

        manual_company_ids = {
            int(row["company_id"])
            for row in manual_rows
        }

        contacted_ids = {
            int(row["company_id"])
            for row in contacted_rows
        }

        company_data: dict[
            int,
            dict[str, object],
        ] = {}

        for row in contact_rows:
            company_id = int(
                row["company_id"]
            )

            entry = company_data.setdefault(
                company_id,
                {
                    "row": row,
                    "contacts": [],
                },
            )

            contact = PublicContact(
                id=int(row["contact_id"]),
                company_id=company_id,
                contact_type=ContactType(
                    row["contact_type"]
                ),
                value=str(
                    row["contact_value"]
                ),
                source_url=(
                    row["contact_source_url"]
                ),
                first_seen_at=datetime_from_db(
                    row["first_seen_at"]
                ),
                last_seen_at=datetime_from_db(
                    row["last_seen_at"]
                ),
                is_active=True,
                review_status=(
                    ContactReviewStatus(
                        row["review_status"]
                    )
                ),
                notes=row["contact_notes"],
            )

            contacts = entry["contacts"]
            assert isinstance(
                contacts,
                list,
            )
            contacts.append(contact)

        candidates: list[
            CompanyOutreachCandidate
        ] = []

        for company_id, entry in (
            company_data.items()
        ):
            row = entry["row"]
            contacts = entry["contacts"]

            current_max, current_jobs = (
                matches.get(
                    company_id,
                    (None, 0),
                )
            )

            candidates.append(
                CompanyOutreachCandidate(
                    company_id=company_id,
                    company_name=str(
                        row["company_name"]
                    ),
                    website_url=row["website_url"],
                    careers_url=row["careers_url"],
                    general_application_url=(
                        row[
                            "general_application_url"
                        ]
                    ),
                    country=row["country"],
                    remote_latam=(
                        None
                        if row["remote_latam"]
                        is None
                        else bool(
                            row["remote_latam"]
                        )
                    ),
                    remote_argentina=(
                        None
                        if row["remote_argentina"]
                        is None
                        else bool(
                            row[
                                "remote_argentina"
                            ]
                        )
                    ),
                    company_type=CompanyType(
                        row["company_type"]
                    ),
                    target_priority=TargetPriority(
                        row["target_priority"]
                    ),
                    contacts=tuple(contacts),
                    cessi_activities=tuple(
                        sorted(
                            cessi_activities.get(
                                company_id,
                                set(),
                            ),
                            key=str.casefold,
                        )
                    ),
                    manual_reference=(
                        company_id
                        in manual_company_ids
                    ),
                    current_max_match=current_max,
                    current_relevant_jobs=(
                        current_jobs
                    ),
                    historical_max_match=(
                        historical.get(
                            company_id
                        )
                    ),
                    contacted=(
                        company_id
                        in contacted_ids
                    ),
                )
            )

        return (
            profile_id,
            candidates,
        )

    def delete_priorities_not_in_company_ids(
        self,
        *,
        search_profile_id: int,
        company_ids: set[int],
    ) -> int:
        with self.database.transaction() as connection:
            if not company_ids:
                cursor = connection.execute(
                    """
                    DELETE FROM company_outreach_priorities
                    WHERE search_profile_id = ?
                    """,
                    (search_profile_id,),
                )
                return max(
                    cursor.rowcount,
                    0,
                )

            placeholders = ", ".join(
                "?"
                for _ in company_ids
            )

            cursor = connection.execute(
                f"""
                DELETE FROM company_outreach_priorities
                WHERE search_profile_id = ?
                  AND company_id NOT IN (
                      {placeholders}
                  )
                """,
                (
                    search_profile_id,
                    *sorted(
                        company_ids
                    ),
                ),
            )

            return max(
                cursor.rowcount,
                0,
            )

    def upsert_priority(
        self,
        value: OutreachPriorityWrite,
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO company_outreach_priorities (
                    company_id,
                    search_profile_id,
                    current_max_match,
                    historical_max_match,
                    current_relevant_jobs,
                    best_contact_id,
                    score,
                    level,
                    reasons_json,
                    rule_version,
                    evaluated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (
                    company_id,
                    search_profile_id
                )
                DO UPDATE SET
                    current_max_match =
                        excluded.current_max_match,
                    historical_max_match =
                        CASE
                            WHEN company_outreach_priorities
                                 .historical_max_match IS NULL
                                THEN excluded.historical_max_match
                            WHEN excluded.historical_max_match
                                 IS NULL
                                THEN company_outreach_priorities
                                     .historical_max_match
                            ELSE MAX(
                                company_outreach_priorities
                                .historical_max_match,
                                excluded.historical_max_match
                            )
                        END,
                    current_relevant_jobs =
                        excluded.current_relevant_jobs,
                    best_contact_id =
                        excluded.best_contact_id,
                    score = excluded.score,
                    level = excluded.level,
                    reasons_json =
                        excluded.reasons_json,
                    rule_version =
                        excluded.rule_version,
                    evaluated_at =
                        excluded.evaluated_at
                """,
                (
                    value.company_id,
                    value.search_profile_id,
                    value.current_max_match,
                    value.historical_max_match,
                    value.current_relevant_jobs,
                    value.best_contact_id,
                    value.score,
                    value.level,
                    json_to_db(value.reasons),
                    value.rule_version,
                    datetime_to_db(
                        value.evaluated_at
                    ),
                ),
            )

    def list_report_rows(
        self,
        *,
        search_profile_name: str,
        min_score: float,
    ) -> list[OutreachReportRow]:
        profile_id = self.profile_id(
            search_profile_name
        )

        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    cop.company_id,
                    c.name AS company_name,
                    cop.score,
                    cop.level,
                    cop.best_contact_id,
                    pc.contact_type,
                    pc.value AS contact_value,
                    pc.source_url AS contact_source_url,
                    c.website_url,
                    c.careers_url,
                    c.country,
                    c.company_type,
                    c.target_priority,
                    c.remote_argentina,
                    c.remote_latam,
                    cop.current_max_match,
                    cop.historical_max_match,
                    cop.current_relevant_jobs,
                    cop.reasons_json,

                    EXISTS (
                        SELECT 1
                        FROM company_sources mcs
                        WHERE mcs.company_id = c.id
                          AND mcs.source_type = 'MANUAL'
                    ) AS manual_reference,

                    EXISTS (
                        SELECT 1
                        FROM company_sources ccs
                        WHERE ccs.company_id = c.id
                          AND ccs.source_type = 'CESSI'
                    ) AS cessi_source,

                    EXISTS (
                        SELECT 1
                        FROM applications a
                        WHERE a.company_id = c.id
                          AND a.application_type IN (?, ?)
                    ) AS contacted,

                    (
                        SELECT a.status
                        FROM applications a
                        WHERE a.company_id = c.id
                          AND a.application_type IN (?, ?)
                        ORDER BY a.id DESC
                        LIMIT 1
                    ) AS outreach_status,

                    (
                        SELECT
                            COALESCE(
                                a.applied_at,
                                a.last_status_at,
                                a.created_at
                            )
                        FROM applications a
                        WHERE a.company_id = c.id
                          AND a.application_type IN (?, ?)
                        ORDER BY a.id DESC
                        LIMIT 1
                    ) AS outreach_at

                FROM company_outreach_priorities cop
                JOIN companies c
                  ON c.id = cop.company_id
                LEFT JOIN public_contacts pc
                  ON pc.id = cop.best_contact_id
                WHERE cop.search_profile_id = ?
                  AND cop.score >= ?
                ORDER BY
                    contacted ASC,
                    cop.score DESC,
                    c.name COLLATE NOCASE
                """,
                (
                    ApplicationType.SPONTANEOUS_EMAIL.value,
                    ApplicationType.GENERAL_APPLICATION.value,
                    ApplicationType.SPONTANEOUS_EMAIL.value,
                    ApplicationType.GENERAL_APPLICATION.value,
                    ApplicationType.SPONTANEOUS_EMAIL.value,
                    ApplicationType.GENERAL_APPLICATION.value,
                    profile_id,
                    min_score,
                ),
            ).fetchall()

        result: list[
            OutreachReportRow
        ] = []

        for row in rows:
            raw_reasons = json_from_db(
                row["reasons_json"]
            )

            reasons = (
                tuple(
                    str(item)
                    for item in raw_reasons
                )
                if isinstance(
                    raw_reasons,
                    list,
                )
                else ()
            )

            result.append(
                OutreachReportRow(
                    company_id=int(
                        row["company_id"]
                    ),
                    company_name=str(
                        row["company_name"]
                    ),
                    score=float(
                        row["score"]
                    ),
                    level=str(
                        row["level"]
                    ),
                    best_contact_id=(
                        int(
                            row["best_contact_id"]
                        )
                        if row["best_contact_id"]
                        is not None
                        else None
                    ),
                    contact_type=row["contact_type"],
                    contact_value=row["contact_value"],
                    contact_source_url=(
                        row[
                            "contact_source_url"
                        ]
                    ),
                    website_url=row["website_url"],
                    careers_url=row["careers_url"],
                    country=row["country"],
                    company_type=str(
                        row["company_type"]
                    ),
                    target_priority=str(
                        row["target_priority"]
                    ),
                    remote_argentina=(
                        None
                        if row["remote_argentina"]
                        is None
                        else bool(
                            row["remote_argentina"]
                        )
                    ),
                    remote_latam=(
                        None
                        if row["remote_latam"]
                        is None
                        else bool(
                            row["remote_latam"]
                        )
                    ),
                    current_max_match=(
                        float(
                            row[
                                "current_max_match"
                            ]
                        )
                        if row["current_max_match"]
                        is not None
                        else None
                    ),
                    historical_max_match=(
                        float(
                            row[
                                "historical_max_match"
                            ]
                        )
                        if row[
                            "historical_max_match"
                        ]
                        is not None
                        else None
                    ),
                    current_relevant_jobs=int(
                        row[
                            "current_relevant_jobs"
                        ]
                    ),
                    manual_reference=bool(
                        row[
                            "manual_reference"
                        ]
                    ),
                    cessi_source=bool(
                        row[
                            "cessi_source"
                        ]
                    ),
                    reasons=reasons,
                    contacted=bool(
                        row["contacted"]
                    ),
                    outreach_status=(
                        row["outreach_status"]
                    ),
                    outreach_at=row["outreach_at"],
                )
            )

        return result

    def best_active_contact(
        self,
        company_id: int,
    ) -> PublicContact | None:
        contacts = (
            self.public_contact_repository
            .list_active_for_company(
                company_id
            )
        )

        if not contacts:
            return None

        weight = {
            ContactType.RECRUITING_EMAIL: 4,
            ContactType.CAREERS_EMAIL: 3,
            ContactType.GENERAL_APPLICATION_URL: 2,
            ContactType.GENERAL_EMAIL: 1,
        }

        return max(
            contacts,
            key=lambda item: (
                weight.get(
                    item.contact_type,
                    0,
                ),
                -(
                    item.id
                    or 0
                ),
            ),
        )

    def track_outreach(
        self,
        *,
        company_id: int,
        contact: PublicContact,
        status: ApplicationStatus,
        notes: str | None,
    ) -> OutreachTrackingResult:
        if contact.id is None:
            raise ValueError(
                "Tracked contact must have an id."
            )

        application_type = (
            ApplicationType.GENERAL_APPLICATION
            if (
                contact.contact_type
                == ContactType.GENERAL_APPLICATION_URL
            )
            else ApplicationType.SPONTANEOUS_EMAIL
        )

        now = utc_now()

        with self.database.transaction() as connection:
            existing = connection.execute(
                """
                SELECT *
                FROM applications
                WHERE company_id = ?
                  AND application_type = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (
                    company_id,
                    application_type.value,
                ),
            ).fetchone()

            previous_status = (
                str(existing["status"])
                if existing is not None
                else None
            )

            applied_at = (
                existing["applied_at"]
                if existing is not None
                else None
            )

            if (
                applied_at is None
                and status
                != ApplicationStatus.PENDING
            ):
                applied_at = (
                    datetime_to_db(now)
                )

            normalized_notes = (
                notes.strip()
                if notes is not None
                else None
            )

            if (
                not normalized_notes
                and existing is not None
            ):
                normalized_notes = (
                    existing["notes"]
                )

            if existing is None:
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
                        ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?,
                        NULL, NULL
                    )
                    """,
                    (
                        company_id,
                        contact.id,
                        application_type.value,
                        status.value,
                        applied_at,
                        datetime_to_db(now),
                        normalized_notes,
                        datetime_to_db(now),
                        datetime_to_db(now),
                    ),
                )

                application_id = cursor.lastrowid

                if application_id is None:
                    raise RuntimeError(
                        "SQLite did not return an "
                        "outreach application id."
                    )

                return OutreachTrackingResult(
                    application_id=int(
                        application_id
                    ),
                    created=True,
                    previous_status=None,
                    current_status=status.value,
                )

            application_id = int(
                existing["id"]
            )

            connection.execute(
                """
                UPDATE applications
                SET
                    public_contact_id = ?,
                    status = ?,
                    applied_at = ?,
                    last_status_at = ?,
                    notes = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    contact.id,
                    status.value,
                    applied_at,
                    datetime_to_db(now),
                    normalized_notes,
                    datetime_to_db(now),
                    application_id,
                ),
            )

        return OutreachTrackingResult(
            application_id=application_id,
            created=False,
            previous_status=previous_status,
            current_status=status.value,
        )
