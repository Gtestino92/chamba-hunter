from datetime import UTC, datetime, timedelta

from chamba_hunter.db.connection import Database
from chamba_hunter.db.converters import datetime_to_db
from chamba_hunter.db.migrations import migrate
from chamba_hunter.repositories.job_matching_repository import JobMatchingRepository
from chamba_hunter.repositories.job_retention_repository import JobRetentionRepository
from chamba_hunter.services import job_retention_service
from chamba_hunter.services.job_retention_service import JobRetentionService


NOW = datetime(2026, 10, 15, 12, tzinfo=UTC)


def _database(tmp_path) -> Database:
    database = Database(tmp_path / "retention.db")
    migrate(database)
    now = datetime_to_db(NOW)
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO companies (id,name,normalized_name,created_at,updated_at) VALUES (1,'Example','example',?,?)",
            (now, now),
        )
        connection.execute(
            "INSERT INTO company_ats (id,company_id,provider,external_identifier,detected_at) VALUES (1,1,'GREENHOUSE','example',?)",
            (now,),
        )
    return database


def _add_job(
    database: Database,
    *,
    job_id: int,
    published_at: datetime | None,
    first_seen_at: datetime,
    last_seen_at: datetime,
    active: bool = True,
) -> None:
    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO jobs (
                id,company_id,company_ats_id,external_id,title,description,
                published_at,first_seen_at,last_seen_at,is_active
            ) VALUES (?,1,1,?,?,'Build Java Spring Boot backend APIs.',?,?,?,?)
            """,
            (
                job_id,
                f"job-{job_id}",
                f"Backend Engineer {job_id}",
                datetime_to_db(published_at) if published_at else None,
                datetime_to_db(first_seen_at),
                datetime_to_db(last_seen_at),
                int(active),
            ),
        )
        for sql, values in (
            (
                "INSERT INTO job_eligibility_classifications (record_kind,record_id,status,reason,method,rule_version,classified_at) VALUES ('ATS',?,'ELIGIBLE','fixture','TITLE','ARGENTINA_V1',?)",
                (job_id, datetime_to_db(NOW)),
            ),
            (
                "INSERT INTO job_occupation_classifications (record_kind,record_id,occupation_class,backend_relevance,reason,method,rule_version,classified_at) VALUES ('ATS',?,'SOFTWARE_ENGINEERING','BACKEND','fixture','TITLE_DESCRIPTION','OCCUPATION_V3',?)",
                (job_id, datetime_to_db(NOW)),
            ),
            (
                "INSERT INTO job_seniority_classifications (record_kind,record_id,seniority_class,leadership_class,seniority_reason,leadership_reason,method,rule_version,classified_at) VALUES ('ATS',?,'MID','NONE','fixture','fixture','TITLE','SENIORITY_V1',?)",
                (job_id, datetime_to_db(NOW)),
            ),
        ):
            connection.execute(sql, values)


def _add_lead(
    database: Database,
    *,
    lead_id: int,
    first_seen_at: datetime,
    expires_at: datetime | None,
) -> None:
    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO job_leads (
                id,company_id,source_type,external_id,title,description,
                expires_at,first_seen_at,last_seen_at,is_active
            ) VALUES (?,1,'JOOBLE',?,?,'Build Java Spring Boot backend APIs.',?,?,?,1)
            """,
            (
                lead_id,
                f"lead-{lead_id}",
                f"Backend Lead {lead_id}",
                datetime_to_db(expires_at) if expires_at else None,
                datetime_to_db(first_seen_at),
                datetime_to_db(NOW),
            ),
        )
        connection.execute(
            "INSERT INTO job_eligibility_classifications (record_kind,record_id,status,reason,method,rule_version,classified_at) VALUES ('LEAD',?,'ELIGIBLE','fixture','TITLE','ARGENTINA_V1',?)",
            (lead_id, datetime_to_db(NOW)),
        )
        connection.execute(
            "INSERT INTO job_occupation_classifications (record_kind,record_id,occupation_class,backend_relevance,reason,method,rule_version,classified_at) VALUES ('LEAD',?,'SOFTWARE_ENGINEERING','BACKEND','fixture','TITLE_DESCRIPTION','OCCUPATION_V3',?)",
            (lead_id, datetime_to_db(NOW)),
        )
        connection.execute(
            "INSERT INTO job_seniority_classifications (record_kind,record_id,seniority_class,leadership_class,seniority_reason,leadership_reason,method,rule_version,classified_at) VALUES ('LEAD',?,'MID','NONE','fixture','fixture','TITLE','SENIORITY_V1',?)",
            (lead_id, datetime_to_db(NOW)),
        )


def test_matching_scope_uses_inclusive_published_boundary(tmp_path) -> None:
    database = _database(tmp_path)
    _add_job(
        database,
        job_id=1,
        published_at=NOW - timedelta(days=60),
        first_seen_at=NOW - timedelta(days=10),
        last_seen_at=NOW,
    )
    _add_job(
        database,
        job_id=2,
        published_at=NOW - timedelta(days=60, seconds=1),
        first_seen_at=NOW - timedelta(days=1),
        last_seen_at=NOW,
    )

    rows = JobMatchingRepository(database).list_scoped_candidates(
        as_of=NOW,
        max_age_days=60,
    )
    assert [(row.record_kind, row.record_id) for row in rows] == [("ATS", 1)]


def test_matching_scope_falls_back_to_first_seen_and_never_last_seen(tmp_path) -> None:
    database = _database(tmp_path)
    _add_job(
        database,
        job_id=1,
        published_at=None,
        first_seen_at=NOW - timedelta(days=30),
        last_seen_at=NOW,
    )
    _add_job(
        database,
        job_id=2,
        published_at=None,
        first_seen_at=NOW - timedelta(days=61),
        last_seen_at=NOW,
    )

    rows = JobMatchingRepository(database).list_scoped_candidates(
        as_of=NOW,
        max_age_days=60,
    )
    assert [row.record_id for row in rows] == [1]


def test_expired_leads_are_excluded_even_when_recent(tmp_path) -> None:
    database = _database(tmp_path)
    _add_lead(
        database,
        lead_id=1,
        first_seen_at=NOW - timedelta(days=2),
        expires_at=NOW,
    )
    _add_lead(
        database,
        lead_id=2,
        first_seen_at=NOW - timedelta(days=2),
        expires_at=NOW + timedelta(seconds=1),
    )

    rows = JobMatchingRepository(database).list_scoped_candidates(
        as_of=NOW,
        max_age_days=60,
    )
    assert [(row.record_kind, row.record_id) for row in rows] == [("LEAD", 2)]


def test_reappearing_old_job_is_not_made_recent_by_last_seen(tmp_path) -> None:
    database = _database(tmp_path)
    _add_job(
        database,
        job_id=1,
        published_at=NOW - timedelta(days=200),
        first_seen_at=NOW - timedelta(days=190),
        last_seen_at=NOW,
        active=True,
    )
    assert JobMatchingRepository(database).list_scoped_candidates(
        as_of=NOW,
        max_age_days=60,
    ) == []


def test_cleanup_deletes_only_inactive_unprotected_old_records(
    tmp_path,
    monkeypatch,
) -> None:
    database = _database(tmp_path)
    old = NOW - timedelta(days=181)
    _add_job(database, job_id=1, published_at=old, first_seen_at=old, last_seen_at=old, active=False)
    _add_job(database, job_id=2, published_at=old, first_seen_at=old, last_seen_at=old, active=False)
    _add_job(database, job_id=3, published_at=old, first_seen_at=old, last_seen_at=NOW, active=True)

    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO applications (
                company_id,job_id,application_type,status,applied_at,
                last_status_at,created_at,updated_at,record_kind,record_id
            ) VALUES (1,2,'JOB','APPLIED',?,?,?,?, 'ATS',2)
            """,
            tuple(datetime_to_db(NOW) for _ in range(4)),
        )

    monkeypatch.setattr(job_retention_service, "utc_now", lambda: NOW)
    preview = JobRetentionService(JobRetentionRepository(database)).run()
    assert len(preview.candidates) == 3
    assert [item.record_id for item in preview.deletable] == [1]
    assert "APPLICATION_HISTORY" in next(
        item for item in preview.protected if item.record_id == 2
    ).protections
    assert "ACTIVE_SOURCE" in next(
        item for item in preview.protected if item.record_id == 3
    ).protections

    applied = JobRetentionService(JobRetentionRepository(database)).run(apply=True)
    assert applied.deleted.ats_jobs == 1
    with database.connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM jobs WHERE id=1").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM jobs WHERE id=2").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM applications WHERE record_kind='ATS' AND record_id=2").fetchone()[0] == 1
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_cleanup_uses_strict_180_day_boundary(tmp_path) -> None:
    database = _database(tmp_path)
    boundary = NOW - timedelta(days=180)
    _add_job(
        database,
        job_id=1,
        published_at=boundary,
        first_seen_at=boundary,
        last_seen_at=boundary,
        active=False,
    )
    _add_job(
        database,
        job_id=2,
        published_at=boundary - timedelta(seconds=1),
        first_seen_at=boundary - timedelta(seconds=1),
        last_seen_at=NOW,
        active=False,
    )

    candidates = JobRetentionRepository(database).list_old_candidates(
        as_of=NOW,
        retention_days=180,
    )
    assert [candidate.record_id for candidate in candidates] == [2]
