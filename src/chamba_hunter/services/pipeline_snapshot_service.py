from dataclasses import dataclass
from datetime import datetime, timedelta

from chamba_hunter.db.connection import Database
from chamba_hunter.db.converters import datetime_to_db
from chamba_hunter.domain.common import utc_now
from chamba_hunter.services.job_matching_service import MAX_PROFESSIONAL_MATCH_AGE_DAYS
from chamba_hunter.services.search_profile_registry import (
    LEGACY_PROFILE_NAME,
    expected_matching_rule,
)


EXPECTED_OCCUPATION_VERSION = "OCCUPATION_V3"
EXPECTED_SENIORITY_VERSION = "SENIORITY_V1"
EXPECTED_LEGACY_SKILL_VERSION = "SKILLS_V2"


@dataclass(frozen=True, slots=True)
class SnapshotIssue:
    severity: str
    code: str
    count: int
    detail: str


@dataclass(frozen=True, slots=True)
class PipelineSnapshotReport:
    profile_name: str
    scoped_candidates: int
    issues: tuple[SnapshotIssue, ...]

    @property
    def errors(self) -> tuple[SnapshotIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "ERROR")


def inspect_pipeline_snapshots(
    database: Database,
    profile_name: str,
    *,
    as_of: datetime | None = None,
) -> PipelineSnapshotReport:
    effective_as_of = as_of or utc_now()
    cutoff = datetime_to_db(
        effective_as_of
        - timedelta(days=MAX_PROFESSIONAL_MATCH_AGE_DAYS)
    )
    as_of_db = datetime_to_db(effective_as_of)
    expected_rule = expected_matching_rule(profile_name)
    issues: list[SnapshotIssue] = []
    with database.connection() as connection:
        scoped_cte = """
            WITH scoped AS (
                SELECT jc.record_kind, jc.record_id
                FROM job_candidates jc
                JOIN job_eligibility_classifications eligibility
                  ON eligibility.record_kind = jc.record_kind
                 AND eligibility.record_id = jc.record_id
                WHERE jc.is_active = 1
                  AND eligibility.status IN ('ELIGIBLE', 'UNKNOWN')
                  AND datetime(
                      COALESCE(jc.published_at, jc.first_seen_at)
                  ) >= datetime(?)
                  AND (
                      jc.record_kind != 'LEAD'
                      OR jc.expires_at IS NULL
                      OR datetime(jc.expires_at) > datetime(?)
                  )
            )
        """
        scoped = int(connection.execute(
            scoped_cte + "SELECT COUNT(*) FROM scoped",
            (cutoff, as_of_db),
        ).fetchone()[0])

        checks = (
            (
                "ERROR", "MISSING_OCCUPATION",
                """SELECT COUNT(*) FROM scoped s
                    LEFT JOIN job_occupation_classifications o
                      ON o.record_kind=s.record_kind AND o.record_id=s.record_id
                    WHERE o.id IS NULL""",
                "active eligible/unknown candidates lack occupation classification",
            ),
            (
                "ERROR", "MISSING_SENIORITY",
                """SELECT COUNT(*) FROM scoped s
                    LEFT JOIN job_seniority_classifications x
                      ON x.record_kind=s.record_kind AND x.record_id=s.record_id
                    WHERE x.id IS NULL""",
                "active eligible/unknown candidates lack seniority classification",
            ),
            (
                "ERROR", "OCCUPATION_VERSION_MISMATCH",
                """SELECT COUNT(*) FROM scoped s
                    JOIN job_occupation_classifications o
                      ON o.record_kind=s.record_kind AND o.record_id=s.record_id
                    WHERE o.rule_version <> 'OCCUPATION_V3'""",
                "scoped occupation rows are not OCCUPATION_V3",
            ),
            (
                "ERROR", "SENIORITY_VERSION_MISMATCH",
                """SELECT COUNT(*) FROM scoped s
                    JOIN job_seniority_classifications x
                      ON x.record_kind=s.record_kind AND x.record_id=s.record_id
                    WHERE x.rule_version <> 'SENIORITY_V1'""",
                "scoped seniority rows are not SENIORITY_V1",
            ),
            (
                "ERROR", "OCCUPATION_OLDER_THAN_ELIGIBILITY",
                """SELECT COUNT(*) FROM scoped s
                    JOIN job_eligibility_classifications e
                      ON e.record_kind=s.record_kind AND e.record_id=s.record_id
                    JOIN job_occupation_classifications o
                      ON o.record_kind=s.record_kind AND o.record_id=s.record_id
                    WHERE o.classified_at < e.classified_at""",
                "occupation evidence predates the current eligibility snapshot",
            ),
            (
                "ERROR", "SENIORITY_OLDER_THAN_ELIGIBILITY",
                """SELECT COUNT(*) FROM scoped s
                    JOIN job_eligibility_classifications e
                      ON e.record_kind=s.record_kind AND e.record_id=s.record_id
                    JOIN job_seniority_classifications x
                      ON x.record_kind=s.record_kind AND x.record_id=s.record_id
                    WHERE x.classified_at < e.classified_at""",
                "seniority evidence predates the current eligibility snapshot",
            ),
            (
                "WARNING", "NO_LEGACY_SKILL_ROWS",
                """SELECT COUNT(*) FROM scoped s
                    WHERE NOT EXISTS (
                        SELECT 1 FROM job_skill_classifications k
                        WHERE k.record_kind=s.record_kind AND k.record_id=s.record_id
                    )""",
                "candidates have no persisted skill row; zero evidence and incomplete V2 coverage are indistinguishable",
            ),
            (
                "WARNING", "LEGACY_SKILL_VERSION_MISMATCH",
                """SELECT COUNT(DISTINCT s.record_kind || ':' || s.record_id)
                    FROM scoped s JOIN job_skill_classifications k
                      ON k.record_kind=s.record_kind AND k.record_id=s.record_id
                    WHERE k.rule_version <> 'SKILLS_V2'""",
                "persisted skill rows intentionally remain a V2-only legacy snapshot",
            ),
        )
        for severity, code, sql, detail in checks:
            count = int(connection.execute(
                scoped_cte + sql,
                (cutoff, as_of_db),
            ).fetchone()[0])
            if count:
                issues.append(SnapshotIssue(severity, code, count, detail))

        profile = connection.execute(
            "SELECT id FROM search_profiles WHERE name=? AND is_active=1",
            (profile_name,),
        ).fetchone()
        if profile is None:
            issues.append(SnapshotIssue(
                "ERROR", "PROFILE_NOT_PERSISTED", 1,
                "the selected profile has no active persisted search_profile row",
            ))
        else:
            profile_id = int(profile["id"])
            wrong_matches = int(connection.execute(
                "SELECT COUNT(*) FROM job_professional_matches WHERE search_profile_id=? AND rule_version<>?",
                (profile_id, expected_rule),
            ).fetchone()[0])
            if wrong_matches:
                issues.append(SnapshotIssue(
                    "ERROR", "MATCH_RULE_MISMATCH", wrong_matches,
                    f"professional rows do not use {expected_rule}",
                ))

            stale_matches = int(connection.execute(
                """
                SELECT COUNT(*)
                FROM job_professional_matches pm
                JOIN job_occupation_classifications o
                  ON o.record_kind=pm.record_kind AND o.record_id=pm.record_id
                JOIN job_seniority_classifications s
                  ON s.record_kind=pm.record_kind AND s.record_id=pm.record_id
                WHERE pm.search_profile_id=?
                  AND (pm.matched_at < o.classified_at OR pm.matched_at < s.classified_at)
                """,
                (profile_id,),
            ).fetchone()[0])
            if stale_matches:
                issues.append(SnapshotIssue(
                    "ERROR", "MATCH_OLDER_THAN_CLASSIFICATION", stale_matches,
                    "professional matching predates occupation or seniority evidence",
                ))

            stale_priority = int(connection.execute(
                """
                SELECT COUNT(*)
                FROM job_operational_priorities p
                JOIN job_professional_matches pm
                  ON pm.search_profile_id=p.search_profile_id
                 AND pm.record_kind=p.record_kind AND pm.record_id=p.record_id
                WHERE p.search_profile_id=?
                  AND (p.professional_rule_version<>? OR p.evaluated_at < pm.matched_at)
                """,
                (profile_id, expected_rule),
            ).fetchone()[0])
            if stale_priority:
                issues.append(SnapshotIssue(
                    "ERROR", "PRIORITY_OLDER_OR_INCOMPATIBLE", stale_priority,
                    "operational priority predates or mismatches professional matching",
                ))

    if profile_name == LEGACY_PROFILE_NAME:
        issues = [
            SnapshotIssue(
                "WARNING" if issue.code in {
                    "OCCUPATION_VERSION_MISMATCH",
                    "MATCH_OLDER_THAN_CLASSIFICATION",
                    "PRIORITY_OLDER_OR_INCOMPATIBLE",
                } else issue.severity,
                issue.code,
                issue.count,
                issue.detail,
            )
            for issue in issues
        ]
    return PipelineSnapshotReport(profile_name, scoped, tuple(issues))


def require_complete(report: PipelineSnapshotReport, operation: str) -> None:
    if report.errors:
        rendered = "; ".join(
            f"{issue.code}={issue.count}" for issue in report.errors
        )
        raise RuntimeError(f"{operation} blocked by incomplete pipeline: {rendered}")


def require_operational_priority_apply(
    report: PipelineSnapshotReport,
    operation: str,
) -> None:
    errors = tuple(
        issue
        for issue in report.errors
        if issue.code != "PRIORITY_OLDER_OR_INCOMPATIBLE"
    )
    if errors:
        rendered = "; ".join(
            f"{issue.code}={issue.count}" for issue in errors
        )
        raise RuntimeError(
            f"{operation} blocked by incomplete pipeline: {rendered}"
        )


def require_matching_upstream(
    report: PipelineSnapshotReport,
    operation: str,
) -> None:
    upstream_codes = {
        "MISSING_OCCUPATION",
        "MISSING_SENIORITY",
        "OCCUPATION_VERSION_MISMATCH",
        "SENIORITY_VERSION_MISMATCH",
        "OCCUPATION_OLDER_THAN_ELIGIBILITY",
        "SENIORITY_OLDER_THAN_ELIGIBILITY",
    }
    errors = tuple(
        issue for issue in report.errors if issue.code in upstream_codes
    )
    if errors:
        rendered = "; ".join(f"{issue.code}={issue.count}" for issue in errors)
        raise RuntimeError(f"{operation} blocked by incomplete upstream: {rendered}")
