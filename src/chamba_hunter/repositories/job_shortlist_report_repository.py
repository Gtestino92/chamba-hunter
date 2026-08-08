from dataclasses import dataclass
from datetime import datetime

from chamba_hunter.db.connection import Database
from chamba_hunter.db.converters import (
    datetime_from_db,
)


@dataclass(frozen=True, slots=True)
class ShortlistReportRow:
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

    application_channel: str
    application_target: str | None

    job_url: str | None
    apply_url: str | None
    general_application_url: str | None

    first_seen_at: datetime
    last_seen_at: datetime
    published_at: datetime | None
    last_changed_at: datetime | None

    priority_rule_version: str
    evaluated_at: datetime
    evaluated_run_id: int

    role_score: float | None
    skills_score: float | None
    seniority_score: float | None
    leadership_score: float | None
    technology_penalty: float | None
    score_ceiling: float | None

    professional_reasons_json: str | None
    operational_reasons_json: str | None

    application_type: str | None
    application_status: str | None
    application_applied_at: datetime | None
    application_updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class ShortlistReportSource:
    profile_id: int
    profile_name: str
    profile_active: bool

    priority_run_id: int
    priority_run_status: str
    priority_run_finished_at: datetime | None

    rows: tuple[
        ShortlistReportRow,
        ...
    ]


def _optional_datetime(
    value: str | None,
) -> datetime | None:
    if value is None:
        return None

    return datetime_from_db(
        str(value)
    )


class JobShortlistReportRepository:
    def __init__(
        self,
        database: Database,
    ) -> None:
        self.database = database

    def _generalized_application_identity_available(
        self,
        connection,
    ) -> bool:
        columns = {
            str(
                row["name"]
            )
            for row in connection.execute(
                """
                PRAGMA table_info(applications)
                """
            ).fetchall()
        }

        return {
            "record_kind",
            "record_id",
        } <= columns

    def load(
        self,
        profile_name: str,
    ) -> ShortlistReportSource:
        with self.database.connection() as connection:
            profile = connection.execute(
                """
                SELECT
                    id,
                    name,
                    is_active
                FROM search_profiles
                WHERE name = ?
                """,
                (
                    profile_name,
                ),
            ).fetchone()

            if profile is None:
                raise RuntimeError(
                    "Search profile not found: "
                    f"{profile_name}"
                )

            profile_id = int(
                profile["id"]
            )

            evaluated_run = connection.execute(
                """
                SELECT
                    MAX(evaluated_run_id)
                        AS run_id
                FROM job_operational_priorities
                WHERE search_profile_id = ?
                """,
                (
                    profile_id,
                ),
            ).fetchone()

            if (
                evaluated_run is None
                or evaluated_run["run_id"]
                is None
            ):
                raise RuntimeError(
                    "No operational priority rows "
                    "exist for search profile: "
                    f"{profile_name}"
                )

            priority_run_id = int(
                evaluated_run["run_id"]
            )

            priority_run = connection.execute(
                """
                SELECT
                    id,
                    status,
                    finished_at
                FROM runs
                WHERE id = ?
                  AND command = 'prioritize_jobs'
                """,
                (
                    priority_run_id,
                ),
            ).fetchone()

            if priority_run is None:
                raise RuntimeError(
                    "Operational priority source "
                    "run not found: "
                    f"{priority_run_id}"
                )

            generalized_identity = (
                self
                ._generalized_application_identity_available(
                    connection
                )
            )

            if generalized_identity:
                application_cte = """
                    WITH ranked_applications AS (
                        SELECT
                            applications.*,
                            applications.record_kind
                                AS tracking_record_kind,
                            applications.record_id
                                AS tracking_record_id,
                            ROW_NUMBER() OVER (
                                PARTITION BY
                                    applications.record_kind,
                                    applications.record_id
                                ORDER BY
                                    applications.updated_at DESC,
                                    applications.id DESC
                            ) AS tracking_rank
                        FROM applications
                        WHERE applications.application_type = 'JOB'
                          AND applications.record_kind IS NOT NULL
                          AND applications.record_id IS NOT NULL
                    )
                """
            else:
                application_cte = """
                    WITH ranked_applications AS (
                        SELECT
                            applications.*,
                            'ATS' AS tracking_record_kind,
                            applications.job_id
                                AS tracking_record_id,
                            ROW_NUMBER() OVER (
                                PARTITION BY applications.job_id
                                ORDER BY
                                    applications.updated_at DESC,
                                    applications.id DESC
                            ) AS tracking_rank
                        FROM applications
                        WHERE applications.application_type = 'JOB'
                          AND applications.job_id IS NOT NULL
                    )
                """

            rows = connection.execute(
                application_cte
                + """
                SELECT
                    priority.record_kind,
                    priority.record_id,

                    priority.company_id,
                    priority.company_name,

                    priority.source_type,
                    priority.origin,
                    priority.title,

                    priority.operational_state,

                    priority.professional_score,
                    priority.professional_match_level,
                    priority.professional_rule_version,

                    priority.application_channel,
                    priority.application_target,

                    priority.job_url,
                    priority.apply_url,
                    priority.general_application_url,

                    priority.first_seen_at,
                    priority.last_seen_at,
                    priority.published_at,
                    priority.last_changed_at,

                    priority.rule_version
                        AS priority_rule_version,
                    priority.evaluated_at,
                    priority.evaluated_run_id,

                    matches.role_score,
                    matches.skills_score,
                    matches.seniority_score,
                    matches.leadership_score,
                    matches.technology_penalty,
                    matches.score_ceiling,
                    matches.reasons_json
                        AS professional_reasons_json,

                    priority.reasons_json
                        AS operational_reasons_json,

                    application.application_type,
                    application.status
                        AS application_status,
                    application.applied_at
                        AS application_applied_at,
                    application.updated_at
                        AS application_updated_at

                FROM job_operational_priorities priority

                LEFT JOIN job_professional_matches matches
                  ON matches.record_kind =
                     priority.record_kind
                 AND matches.record_id =
                     priority.record_id
                 AND matches.search_profile_id =
                     priority.search_profile_id

                LEFT JOIN ranked_applications application
                  ON application.tracking_rank = 1
                 AND application.tracking_record_kind =
                     priority.record_kind
                 AND application.tracking_record_id =
                     priority.record_id

                WHERE priority.search_profile_id = ?

                ORDER BY
                    priority.record_kind,
                    priority.record_id
                """,
                (
                    profile_id,
                ),
            ).fetchall()

        report_rows = tuple(
            ShortlistReportRow(
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
                source_type=str(
                    row["source_type"]
                ),
                origin=str(
                    row["origin"]
                ),
                title=str(
                    row["title"]
                ),
                operational_state=str(
                    row["operational_state"]
                ),
                professional_score=float(
                    row["professional_score"]
                ),
                professional_match_level=str(
                    row[
                        "professional_match_level"
                    ]
                ),
                professional_rule_version=str(
                    row[
                        "professional_rule_version"
                    ]
                ),
                application_channel=str(
                    row["application_channel"]
                ),
                application_target=(
                    str(
                        row[
                            "application_target"
                        ]
                    )
                    if row[
                        "application_target"
                    ]
                    is not None
                    else None
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
                first_seen_at=datetime_from_db(
                    str(
                        row["first_seen_at"]
                    )
                ),
                last_seen_at=datetime_from_db(
                    str(
                        row["last_seen_at"]
                    )
                ),
                published_at=_optional_datetime(
                    row["published_at"]
                ),
                last_changed_at=(
                    _optional_datetime(
                        row["last_changed_at"]
                    )
                ),
                priority_rule_version=str(
                    row[
                        "priority_rule_version"
                    ]
                ),
                evaluated_at=datetime_from_db(
                    str(
                        row["evaluated_at"]
                    )
                ),
                evaluated_run_id=int(
                    row["evaluated_run_id"]
                ),
                role_score=(
                    float(
                        row["role_score"]
                    )
                    if row["role_score"]
                    is not None
                    else None
                ),
                skills_score=(
                    float(
                        row["skills_score"]
                    )
                    if row["skills_score"]
                    is not None
                    else None
                ),
                seniority_score=(
                    float(
                        row["seniority_score"]
                    )
                    if row["seniority_score"]
                    is not None
                    else None
                ),
                leadership_score=(
                    float(
                        row["leadership_score"]
                    )
                    if row["leadership_score"]
                    is not None
                    else None
                ),
                technology_penalty=(
                    float(
                        row[
                            "technology_penalty"
                        ]
                    )
                    if row[
                        "technology_penalty"
                    ]
                    is not None
                    else None
                ),
                score_ceiling=(
                    float(
                        row["score_ceiling"]
                    )
                    if row["score_ceiling"]
                    is not None
                    else None
                ),
                professional_reasons_json=(
                    str(
                        row[
                            "professional_reasons_json"
                        ]
                    )
                    if row[
                        "professional_reasons_json"
                    ]
                    is not None
                    else None
                ),
                operational_reasons_json=(
                    str(
                        row[
                            "operational_reasons_json"
                        ]
                    )
                    if row[
                        "operational_reasons_json"
                    ]
                    is not None
                    else None
                ),
                application_type=(
                    str(
                        row["application_type"]
                    )
                    if row[
                        "application_type"
                    ]
                    is not None
                    else None
                ),
                application_status=(
                    str(
                        row[
                            "application_status"
                        ]
                    )
                    if row[
                        "application_status"
                    ]
                    is not None
                    else None
                ),
                application_applied_at=(
                    _optional_datetime(
                        row[
                            "application_applied_at"
                        ]
                    )
                ),
                application_updated_at=(
                    _optional_datetime(
                        row[
                            "application_updated_at"
                        ]
                    )
                ),
            )
            for row in rows
        )

        return ShortlistReportSource(
            profile_id=profile_id,
            profile_name=str(
                profile["name"]
            ),
            profile_active=bool(
                profile["is_active"]
            ),
            priority_run_id=int(
                priority_run["id"]
            ),
            priority_run_status=str(
                priority_run["status"]
            ),
            priority_run_finished_at=(
                _optional_datetime(
                    priority_run[
                        "finished_at"
                    ]
                )
            ),
            rows=report_rows,
        )
