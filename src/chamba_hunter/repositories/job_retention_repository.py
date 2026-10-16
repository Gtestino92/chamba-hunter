from dataclasses import dataclass
from datetime import datetime, timedelta

from chamba_hunter.db.connection import Database
from chamba_hunter.db.converters import datetime_from_db, datetime_to_db


@dataclass(frozen=True, slots=True)
class RetentionCandidateRow:
    record_kind: str
    record_id: int
    title: str
    reference_at: datetime
    protections: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RetentionDeleteCounts:
    ats_jobs: int
    job_leads: int
    classification_rows: int


class JobRetentionRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list_old_candidates(
        self,
        *,
        as_of: datetime,
        retention_days: int,
    ) -> list[RetentionCandidateRow]:
        cutoff = datetime_to_db(
            as_of - timedelta(days=retention_days)
        )

        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    'ATS' AS record_kind,
                    jobs.id AS record_id,
                    jobs.title,
                    COALESCE(jobs.published_at, jobs.first_seen_at)
                        AS reference_at,
                    jobs.is_active,
                    EXISTS (
                        SELECT 1 FROM applications application
                        WHERE application.application_type = 'JOB'
                          AND (
                              (
                                  application.record_kind = 'ATS'
                                  AND application.record_id = jobs.id
                              )
                              OR application.job_id = jobs.id
                          )
                    ) AS has_application,
                    EXISTS (
                        SELECT 1
                        FROM job_leads linked_lead
                        JOIN applications application
                          ON application.application_type = 'JOB'
                         AND application.record_kind = 'LEAD'
                         AND application.record_id = linked_lead.id
                        WHERE linked_lead.canonical_job_id = jobs.id
                    ) AS has_aliased_application,
                    EXISTS (
                        SELECT 1 FROM job_professional_matches match
                        WHERE match.record_kind = 'ATS'
                          AND match.record_id = jobs.id
                    ) AS has_professional_match,
                    EXISTS (
                        SELECT 1 FROM job_operational_priorities priority
                        WHERE priority.record_kind = 'ATS'
                          AND priority.record_id = jobs.id
                    ) AS has_operational_history,
                    EXISTS (
                        SELECT 1 FROM job_matches legacy_match
                        WHERE legacy_match.job_id = jobs.id
                    ) AS has_legacy_match,
                    EXISTS (
                        SELECT 1 FROM job_leads linked_lead
                        WHERE linked_lead.canonical_job_id = jobs.id
                    ) AS has_linked_record,
                    0 AS has_ats_hint
                FROM jobs
                WHERE datetime(
                    COALESCE(jobs.published_at, jobs.first_seen_at)
                ) < datetime(?)

                UNION ALL

                SELECT
                    'LEAD' AS record_kind,
                    job_leads.id AS record_id,
                    job_leads.title,
                    COALESCE(
                        job_leads.published_at,
                        job_leads.first_seen_at
                    ) AS reference_at,
                    job_leads.is_active,
                    EXISTS (
                        SELECT 1 FROM applications application
                        WHERE application.application_type = 'JOB'
                          AND application.record_kind = 'LEAD'
                          AND application.record_id = job_leads.id
                    ) AS has_application,
                    0 AS has_aliased_application,
                    EXISTS (
                        SELECT 1 FROM job_professional_matches match
                        WHERE match.record_kind = 'LEAD'
                          AND match.record_id = job_leads.id
                    ) AS has_professional_match,
                    EXISTS (
                        SELECT 1 FROM job_operational_priorities priority
                        WHERE priority.record_kind = 'LEAD'
                          AND priority.record_id = job_leads.id
                    ) AS has_operational_history,
                    0 AS has_legacy_match,
                    (job_leads.canonical_job_id IS NOT NULL)
                        AS has_linked_record,
                    EXISTS (
                        SELECT 1 FROM job_ats_hints hint
                        WHERE hint.job_lead_id = job_leads.id
                    ) AS has_ats_hint
                FROM job_leads
                WHERE datetime(
                    COALESCE(
                        job_leads.published_at,
                        job_leads.first_seen_at
                    )
                ) < datetime(?)

                ORDER BY record_kind, record_id
                """,
                (cutoff, cutoff),
            ).fetchall()

        result: list[RetentionCandidateRow] = []
        for row in rows:
            protections: list[str] = []
            for column, reason in (
                ("is_active", "ACTIVE_SOURCE"),
                ("has_application", "APPLICATION_HISTORY"),
                ("has_aliased_application", "ALIASED_APPLICATION_HISTORY"),
                ("has_professional_match", "PROFESSIONAL_MATCH_HISTORY"),
                ("has_operational_history", "OPERATIONAL_PRIORITY_HISTORY"),
                ("has_legacy_match", "LEGACY_MATCH_HISTORY"),
                ("has_linked_record", "CANONICALIZATION_HISTORY"),
                ("has_ats_hint", "ATS_HINT_HISTORY"),
            ):
                if bool(row[column]):
                    protections.append(reason)

            result.append(
                RetentionCandidateRow(
                    record_kind=str(row["record_kind"]),
                    record_id=int(row["record_id"]),
                    title=str(row["title"]),
                    reference_at=datetime_from_db(str(row["reference_at"])),
                    protections=tuple(protections),
                )
            )

        return result

    def delete_candidates(
        self,
        candidates: list[RetentionCandidateRow],
    ) -> RetentionDeleteCounts:
        if any(candidate.protections for candidate in candidates):
            raise ValueError("Protected retention candidates cannot be deleted.")

        ats_jobs = 0
        job_leads = 0
        classification_rows = 0

        with self.database.transaction() as connection:
            for candidate in candidates:
                for table in (
                    "job_skill_classifications",
                    "job_seniority_classifications",
                    "job_occupation_classifications",
                    "job_eligibility_classifications",
                ):
                    cursor = connection.execute(
                        f"DELETE FROM {table} WHERE record_kind = ? AND record_id = ?",
                        (candidate.record_kind, candidate.record_id),
                    )
                    classification_rows += cursor.rowcount

                if candidate.record_kind == "ATS":
                    cursor = connection.execute(
                        """
                        DELETE FROM jobs
                        WHERE id = ?
                          AND is_active = 0
                          AND datetime(
                              COALESCE(published_at, first_seen_at)
                          ) = datetime(?)
                          AND NOT EXISTS (
                              SELECT 1 FROM applications application
                              WHERE application.application_type = 'JOB'
                                AND (
                                    (
                                        application.record_kind = 'ATS'
                                        AND application.record_id = jobs.id
                                    )
                                    OR application.job_id = jobs.id
                                )
                          )
                          AND NOT EXISTS (
                              SELECT 1
                              FROM job_leads linked_lead
                              JOIN applications application
                                ON application.application_type = 'JOB'
                               AND application.record_kind = 'LEAD'
                               AND application.record_id = linked_lead.id
                              WHERE linked_lead.canonical_job_id = jobs.id
                          )
                          AND NOT EXISTS (
                              SELECT 1 FROM job_professional_matches match
                              WHERE match.record_kind = 'ATS'
                                AND match.record_id = jobs.id
                          )
                          AND NOT EXISTS (
                              SELECT 1 FROM job_operational_priorities priority
                              WHERE priority.record_kind = 'ATS'
                                AND priority.record_id = jobs.id
                          )
                          AND NOT EXISTS (
                              SELECT 1 FROM job_matches legacy_match
                              WHERE legacy_match.job_id = jobs.id
                          )
                          AND NOT EXISTS (
                              SELECT 1 FROM job_leads linked_lead
                              WHERE linked_lead.canonical_job_id = jobs.id
                          )
                        """,
                        (
                            candidate.record_id,
                            datetime_to_db(candidate.reference_at),
                        ),
                    )
                    ats_jobs += cursor.rowcount
                else:
                    cursor = connection.execute(
                        """
                        DELETE FROM job_leads
                        WHERE id = ?
                          AND is_active = 0
                          AND datetime(
                              COALESCE(published_at, first_seen_at)
                          ) = datetime(?)
                          AND canonical_job_id IS NULL
                          AND NOT EXISTS (
                              SELECT 1 FROM applications application
                              WHERE application.application_type = 'JOB'
                                AND application.record_kind = 'LEAD'
                                AND application.record_id = job_leads.id
                          )
                          AND NOT EXISTS (
                              SELECT 1 FROM job_professional_matches match
                              WHERE match.record_kind = 'LEAD'
                                AND match.record_id = job_leads.id
                          )
                          AND NOT EXISTS (
                              SELECT 1 FROM job_operational_priorities priority
                              WHERE priority.record_kind = 'LEAD'
                                AND priority.record_id = job_leads.id
                          )
                          AND NOT EXISTS (
                              SELECT 1 FROM job_ats_hints hint
                              WHERE hint.job_lead_id = job_leads.id
                          )
                        """,
                        (
                            candidate.record_id,
                            datetime_to_db(candidate.reference_at),
                        ),
                    )
                    job_leads += cursor.rowcount

                if cursor.rowcount != 1:
                    raise RuntimeError(
                        "Retention candidate changed or became protected: "
                        f"{candidate.record_kind} {candidate.record_id}"
                    )

            violations = connection.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
            if violations:
                raise RuntimeError(
                    "Foreign-key violations detected during retention cleanup."
                )

        return RetentionDeleteCounts(
            ats_jobs=ats_jobs,
            job_leads=job_leads,
            classification_rows=classification_rows,
        )
