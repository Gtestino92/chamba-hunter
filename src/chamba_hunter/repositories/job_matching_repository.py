from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from chamba_hunter.db.connection import Database
from chamba_hunter.db.converters import (
    datetime_to_db,
    json_to_db,
)
from chamba_hunter.domain.common import JsonObject


@dataclass(frozen=True, slots=True)
class MatchingCandidateRow:
    record_kind: str
    record_id: int

    source_type: str
    origin: str

    company_name: str
    title: str

    eligibility_status: str
    occupation_class: str
    backend_relevance: str
    seniority_class: str
    leadership_class: str

    skills: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProfessionalMatchWrite:
    record_kind: str
    record_id: int

    score: float
    match_level: str

    role_score: float
    skills_score: float
    seniority_score: float
    leadership_score: float
    technology_penalty: float
    score_ceiling: float

    reasons: JsonObject

    rule_version: str


@dataclass(frozen=True, slots=True)
class MatchUpsertCounts:
    created: int
    updated: int
    deleted: int


class JobMatchingRepository:
    def __init__(
        self,
        database: Database,
    ) -> None:
        self.database = database

    def list_scoped_candidates(
        self,
    ) -> list[MatchingCandidateRow]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    jc.record_kind,
                    jc.record_id,
                    jc.source_type,
                    CASE
                        WHEN jc.record_kind = 'ATS'
                            THEN company_ats.provider
                        ELSE jc.source_type
                    END AS origin,
                    companies.name AS company_name,
                    jc.title,
                    eligibility.status AS eligibility_status,
                    occupation.occupation_class,
                    occupation.backend_relevance,
                    seniority.seniority_class,
                    seniority.leadership_class
                FROM job_candidates jc
                JOIN companies
                  ON companies.id = jc.company_id
                LEFT JOIN company_ats
                  ON company_ats.id = jc.company_ats_id
                JOIN job_eligibility_classifications eligibility
                  ON eligibility.record_kind = jc.record_kind
                 AND eligibility.record_id = jc.record_id
                JOIN job_occupation_classifications occupation
                  ON occupation.record_kind = jc.record_kind
                 AND occupation.record_id = jc.record_id
                JOIN job_seniority_classifications seniority
                  ON seniority.record_kind = jc.record_kind
                 AND seniority.record_id = jc.record_id
                WHERE jc.is_active = 1
                  AND eligibility.status IN (
                      'ELIGIBLE',
                      'UNKNOWN'
                  )
                ORDER BY
                    jc.record_kind,
                    jc.record_id
                """
            ).fetchall()

            skill_rows = connection.execute(
                """
                SELECT
                    skills.record_kind,
                    skills.record_id,
                    skills.skill_key
                FROM job_skill_classifications skills
                JOIN job_candidates jc
                  ON jc.record_kind = skills.record_kind
                 AND jc.record_id = skills.record_id
                JOIN job_eligibility_classifications eligibility
                  ON eligibility.record_kind = jc.record_kind
                 AND eligibility.record_id = jc.record_id
                WHERE jc.is_active = 1
                  AND eligibility.status IN (
                      'ELIGIBLE',
                      'UNKNOWN'
                  )
                ORDER BY
                    skills.record_kind,
                    skills.record_id,
                    skills.skill_key
                """
            ).fetchall()

        skills_by_candidate: dict[
            tuple[str, int],
            list[str],
        ] = defaultdict(list)

        for row in skill_rows:
            skills_by_candidate[
                (
                    str(row["record_kind"]),
                    int(row["record_id"]),
                )
            ].append(
                str(row["skill_key"])
            )

        result = []

        for row in rows:
            key = (
                str(row["record_kind"]),
                int(row["record_id"]),
            )

            result.append(
                MatchingCandidateRow(
                    record_kind=key[0],
                    record_id=key[1],
                    source_type=str(
                        row["source_type"]
                    ),
                    origin=str(
                        row["origin"]
                    ),
                    company_name=str(
                        row["company_name"]
                    ),
                    title=str(
                        row["title"]
                    ),
                    eligibility_status=str(
                        row["eligibility_status"]
                    ),
                    occupation_class=str(
                        row["occupation_class"]
                    ),
                    backend_relevance=str(
                        row["backend_relevance"]
                    ),
                    seniority_class=str(
                        row["seniority_class"]
                    ),
                    leadership_class=str(
                        row["leadership_class"]
                    ),
                    skills=tuple(
                        skills_by_candidate.get(
                            key,
                            [],
                        )
                    ),
                )
            )

        return result

    def upsert_search_profile(
        self,
        name: str,
        description: str,
        rules: JsonObject,
        now: datetime,
    ) -> int:
        now_db = datetime_to_db(now)

        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO search_profiles (
                    name,
                    description,
                    rules_json,
                    is_active,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, 1, ?, ?)
                ON CONFLICT(name)
                DO UPDATE SET
                    description = excluded.description,
                    rules_json = excluded.rules_json,
                    is_active = 1,
                    updated_at = excluded.updated_at
                """,
                (
                    name,
                    description,
                    json_to_db(rules),
                    now_db,
                    now_db,
                ),
            )

            row = connection.execute(
                """
                SELECT id
                FROM search_profiles
                WHERE name = ?
                """,
                (
                    name,
                ),
            ).fetchone()

        if row is None:
            raise RuntimeError(
                "Search profile upsert did not return a row."
            )

        return int(row["id"])

    def upsert_matches(
        self,
        search_profile_id: int,
        matches: list[ProfessionalMatchWrite],
        matched_at: datetime,
    ) -> MatchUpsertCounts:
        keys = {
            (
                match.record_kind,
                match.record_id,
            )
            for match in matches
        }

        if len(keys) != len(matches):
            raise ValueError(
                "Duplicate candidate key in one "
                "professional matching run."
            )

        matched_at_db = datetime_to_db(
            matched_at
        )

        with self.database.transaction() as connection:
            existing_rows = connection.execute(
                """
                SELECT
                    record_kind,
                    record_id
                FROM job_professional_matches
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

            connection.execute(
                """
                CREATE TEMP TABLE
                current_professional_match_keys (
                    record_kind TEXT NOT NULL,
                    record_id INTEGER NOT NULL,
                    PRIMARY KEY (
                        record_kind,
                        record_id
                    )
                )
                """
            )

            if keys:
                connection.executemany(
                    """
                    INSERT INTO
                    current_professional_match_keys (
                        record_kind,
                        record_id
                    )
                    VALUES (?, ?)
                    """,
                    sorted(keys),
                )

            for match in matches:
                connection.execute(
                    """
                    INSERT INTO job_professional_matches (
                        record_kind,
                        record_id,
                        search_profile_id,
                        score,
                        match_level,
                        role_score,
                        skills_score,
                        seniority_score,
                        leadership_score,
                        technology_penalty,
                        score_ceiling,
                        reasons_json,
                        rule_version,
                        matched_at
                    )
                    VALUES (
                        ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?,
                        ?, ?
                    )
                    ON CONFLICT (
                        record_kind,
                        record_id,
                        search_profile_id
                    )
                    DO UPDATE SET
                        score = excluded.score,
                        match_level = excluded.match_level,
                        role_score = excluded.role_score,
                        skills_score = excluded.skills_score,
                        seniority_score = excluded.seniority_score,
                        leadership_score = excluded.leadership_score,
                        technology_penalty = excluded.technology_penalty,
                        score_ceiling = excluded.score_ceiling,
                        reasons_json = excluded.reasons_json,
                        rule_version = excluded.rule_version,
                        matched_at = excluded.matched_at
                    """,
                    (
                        match.record_kind,
                        match.record_id,
                        search_profile_id,
                        match.score,
                        match.match_level,
                        match.role_score,
                        match.skills_score,
                        match.seniority_score,
                        match.leadership_score,
                        match.technology_penalty,
                        match.score_ceiling,
                        json_to_db(
                            match.reasons
                        ),
                        match.rule_version,
                        matched_at_db,
                    ),
                )

            delete_cursor = connection.execute(
                """
                DELETE FROM job_professional_matches
                WHERE search_profile_id = ?
                  AND NOT EXISTS (
                      SELECT 1
                      FROM current_professional_match_keys current
                      WHERE current.record_kind =
                            job_professional_matches.record_kind
                        AND current.record_id =
                            job_professional_matches.record_id
                  )
                """,
                (
                    search_profile_id,
                ),
            )

            connection.execute(
                """
                DROP TABLE current_professional_match_keys
                """
            )

        return MatchUpsertCounts(
            created=len(
                keys - existing_keys
            ),
            updated=len(
                keys & existing_keys
            ),
            deleted=delete_cursor.rowcount,
        )
