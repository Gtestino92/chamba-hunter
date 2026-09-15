from datetime import UTC, datetime
from pathlib import Path

from chamba_hunter.db.connection import (
    Database,
)
from chamba_hunter.db.converters import (
    datetime_to_db,
)
from chamba_hunter.db.migrations import (
    migrate,
)
from chamba_hunter.repositories.job_freshness_repository import (
    JobFreshnessRepository,
)
from chamba_hunter.repositories.job_operational_priority_repository import (
    JobOperationalPriorityRepository,
)
from chamba_hunter.repositories.job_shortlist_report_repository import (
    JobShortlistReportRepository,
)
from chamba_hunter.repositories.tracing_repository import (
    TracingRepository,
)
from chamba_hunter.services.job_operational_priority_service import (
    JobOperationalPriorityService,
    RULE_VERSION,
)
from chamba_hunter.services.job_shortlist_report_service import (
    build_summary,
)


WATERMARK = datetime(
    2026,
    9,
    13,
    12,
    0,
    tzinfo=UTC,
)
BEFORE_WATERMARK = datetime(
    2026,
    9,
    2,
    12,
    0,
    tzinfo=UTC,
)
AFTER_WATERMARK = datetime(
    2026,
    9,
    14,
    12,
    0,
    tzinfo=UTC,
)
OLD_LEAD_SEEN = datetime(
    2026,
    8,
    1,
    12,
    0,
    tzinfo=UTC,
)


def _db_time(
    value: datetime,
) -> str:
    return datetime_to_db(
        value
    )


def _setup_database(
    tmp_path: Path,
) -> Database:
    database = Database(
        tmp_path / "test.db"
    )
    migrate(database)

    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO runs (
                command,
                started_at,
                finished_at,
                status,
                created_by
            )
            VALUES (
                'prioritize_jobs',
                ?,
                ?,
                'SUCCESS',
                'MANUAL'
            )
            """,
            (
                _db_time(
                    WATERMARK
                ),
                _db_time(
                    WATERMARK
                ),
            ),
        )
        connection.execute(
            """
            INSERT INTO search_profiles (
                id,
                name,
                description,
                rules_json,
                is_active,
                created_at,
                updated_at
            )
            VALUES (
                1,
                'BACKEND_SOFTWARE_V1',
                'test',
                '{}',
                1,
                ?,
                ?
            )
            """,
            (
                _db_time(
                    BEFORE_WATERMARK
                ),
                _db_time(
                    BEFORE_WATERMARK
                ),
            ),
        )

    return database


def _add_company(
    database: Database,
    company_id: int,
    name: str,
) -> None:
    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO companies (
                id,
                name,
                normalized_name,
                status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, 'ACTIVE', ?, ?)
            """,
            (
                company_id,
                name,
                name.casefold(),
                _db_time(
                    BEFORE_WATERMARK
                ),
                _db_time(
                    BEFORE_WATERMARK
                ),
            ),
        )
        connection.execute(
            """
            INSERT INTO company_ats (
                id,
                company_id,
                provider,
                external_identifier,
                board_url,
                detected_at
            )
            VALUES (?, ?, 'GREENHOUSE', ?, ?, ?)
            """,
            (
                company_id,
                company_id,
                f"company-{company_id}",
                f"https://example.com/{company_id}",
                _db_time(
                    AFTER_WATERMARK
                ),
            ),
        )


def _add_ats_job(
    database: Database,
    *,
    job_id: int,
    company_id: int,
    title: str = "Senior Java Developer",
    first_seen_at: datetime = AFTER_WATERMARK,
    published_at: datetime | None = AFTER_WATERMARK,
    last_changed_at: datetime | None = None,
) -> None:
    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO jobs (
                id,
                company_id,
                company_ats_id,
                external_id,
                title,
                job_url,
                apply_url,
                published_at,
                first_seen_at,
                last_seen_at,
                is_active,
                last_changed_at
            )
            VALUES (
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                1,
                ?
            )
            """,
            (
                job_id,
                company_id,
                company_id,
                f"ats-{job_id}",
                title,
                f"https://jobs.example/{job_id}",
                f"https://apply.example/{job_id}",
                (
                    _db_time(
                        published_at
                    )
                    if published_at
                    is not None
                    else None
                ),
                _db_time(
                    first_seen_at
                ),
                _db_time(
                    first_seen_at
                ),
                (
                    _db_time(
                        last_changed_at
                    )
                    if last_changed_at
                    is not None
                    else None
                ),
            ),
        )


def _add_lead(
    database: Database,
    *,
    lead_id: int,
    company_id: int,
    title: str = "Senior Java Developer",
    first_seen_at: datetime = BEFORE_WATERMARK,
    canonical_job_id: int | None = None,
) -> None:
    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO job_leads (
                id,
                company_id,
                source_type,
                external_id,
                canonical_job_id,
                title,
                job_url,
                apply_url,
                first_seen_at,
                last_seen_at,
                is_active
            )
            VALUES (
                ?,
                ?,
                'GETONBOARD',
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                1
            )
            """,
            (
                lead_id,
                company_id,
                f"lead-{lead_id}",
                canonical_job_id,
                title,
                f"https://lead.example/{lead_id}",
                f"https://lead-apply.example/{lead_id}",
                _db_time(
                    first_seen_at
                ),
                _db_time(
                    first_seen_at
                ),
            ),
        )


def _add_match(
    database: Database,
    *,
    record_kind: str,
    record_id: int,
    score: float = 90.0,
    level: str = "HIGH",
) -> None:
    with database.transaction() as connection:
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
                ?,
                ?,
                1,
                ?,
                ?,
                40,
                25,
                15,
                10,
                0,
                100,
                '{}',
                'MATCHING_TEST',
                ?
            )
            """,
            (
                record_kind,
                record_id,
                score,
                level,
                _db_time(
                    AFTER_WATERMARK
                ),
            ),
        )


def _service(
    database: Database,
) -> JobOperationalPriorityService:
    return JobOperationalPriorityService(
        repository=(
            JobOperationalPriorityRepository(
                database
            )
        ),
        freshness_repository=(
            JobFreshnessRepository(
                database
            )
        ),
        tracing_repository=(
            TracingRepository(
                database
            )
        ),
    )


def _decision(
    database: Database,
    record_kind: str,
    record_id: int,
):
    summary = _service(
        database
    ).run(
        apply=False
    )

    return next(
        decision
        for decision in summary.decisions
        if decision.record_kind == record_kind
        and decision.record_id == record_id
    )


def test_canonical_transition_uses_lead_history_not_false_new(
    tmp_path: Path,
) -> None:
    database = _setup_database(
        tmp_path
    )
    _add_company(database, 1, "HistoryCo")
    _add_ats_job(
        database,
        job_id=101,
        company_id=1,
    )
    _add_lead(
        database,
        lead_id=102,
        company_id=1,
        canonical_job_id=101,
    )
    _add_match(
        database,
        record_kind="ATS",
        record_id=101,
    )

    decision = _decision(
        database,
        "ATS",
        101,
    )

    assert decision.operational_state == "KNOWN"
    assert decision.first_seen_at == BEFORE_WATERMARK
    assert decision.reasons["freshness"][
        "source_first_seen_at"
    ] == AFTER_WATERMARK.isoformat()
    assert decision.reasons["freshness"][
        "canonical_first_seen_at"
    ] == BEFORE_WATERMARK.isoformat()
    assert decision.reasons["freshness"][
        "first_seen_inherited_from_canonical_lead"
    ] is True


def test_truly_new_canonical_opportunity_remains_new(
    tmp_path: Path,
) -> None:
    database = _setup_database(
        tmp_path
    )
    _add_company(database, 1, "NewCo")
    _add_ats_job(
        database,
        job_id=201,
        company_id=1,
    )
    _add_lead(
        database,
        lead_id=202,
        company_id=1,
        first_seen_at=AFTER_WATERMARK,
        canonical_job_id=201,
    )
    _add_match(
        database,
        record_kind="ATS",
        record_id=201,
    )

    decision = _decision(
        database,
        "ATS",
        201,
    )

    assert decision.operational_state == "NEW"
    assert decision.first_seen_at == AFTER_WATERMARK


def test_multiple_canonical_leads_use_earliest_history(
    tmp_path: Path,
) -> None:
    database = _setup_database(
        tmp_path
    )
    _add_company(database, 1, "MultiLeadCo")
    _add_ats_job(
        database,
        job_id=301,
        company_id=1,
    )
    _add_lead(
        database,
        lead_id=302,
        company_id=1,
        first_seen_at=datetime(
            2026,
            9,
            4,
            12,
            0,
            tzinfo=UTC,
        ),
        canonical_job_id=301,
    )
    _add_lead(
        database,
        lead_id=303,
        company_id=1,
        first_seen_at=BEFORE_WATERMARK,
        canonical_job_id=301,
    )
    _add_match(
        database,
        record_kind="ATS",
        record_id=301,
    )

    decision = _decision(
        database,
        "ATS",
        301,
    )

    assert decision.first_seen_at == BEFORE_WATERMARK
    assert decision.operational_state == "KNOWN"


def test_ats_without_canonical_history_keeps_existing_new_behavior(
    tmp_path: Path,
) -> None:
    database = _setup_database(
        tmp_path
    )
    _add_company(database, 1, "DirectAtsCo")
    _add_ats_job(
        database,
        job_id=401,
        company_id=1,
    )
    _add_match(
        database,
        record_kind="ATS",
        record_id=401,
    )

    decision = _decision(
        database,
        "ATS",
        401,
    )

    assert decision.operational_state == "NEW"
    assert decision.first_seen_at == AFTER_WATERMARK


def test_uncanonicalized_lead_first_seen_behavior_is_unchanged(
    tmp_path: Path,
) -> None:
    database = _setup_database(
        tmp_path
    )
    _add_company(database, 1, "LeadOnlyCo")
    _add_lead(
        database,
        lead_id=501,
        company_id=1,
        first_seen_at=AFTER_WATERMARK,
    )
    _add_match(
        database,
        record_kind="LEAD",
        record_id=501,
    )

    decision = _decision(
        database,
        "LEAD",
        501,
    )

    assert decision.operational_state == "NEW"
    assert decision.first_seen_at == AFTER_WATERMARK


def test_content_update_survives_effective_first_seen_history(
    tmp_path: Path,
) -> None:
    database = _setup_database(
        tmp_path
    )
    _add_company(database, 1, "UpdatedCo")
    _add_ats_job(
        database,
        job_id=601,
        company_id=1,
        last_changed_at=AFTER_WATERMARK,
    )
    _add_lead(
        database,
        lead_id=602,
        company_id=1,
        canonical_job_id=601,
    )
    _add_match(
        database,
        record_kind="ATS",
        record_id=601,
    )

    decision = _decision(
        database,
        "ATS",
        601,
    )

    assert decision.operational_state == "UPDATED"
    assert (
        "CONTENT_CHANGED_AFTER_WATERMARK"
        in decision.reasons["state_reasons"]
    )


def test_unknown_recency_with_old_canonical_history_becomes_inactive(
    tmp_path: Path,
) -> None:
    database = _setup_database(
        tmp_path
    )
    _add_company(database, 1, "OldUnknownCo")
    _add_ats_job(
        database,
        job_id=701,
        company_id=1,
        published_at=None,
    )
    _add_lead(
        database,
        lead_id=702,
        company_id=1,
        first_seen_at=OLD_LEAD_SEEN,
        canonical_job_id=701,
    )
    _add_match(
        database,
        record_kind="ATS",
        record_id=701,
    )

    decision = _decision(
        database,
        "ATS",
        701,
    )

    assert decision.operational_state == "INACTIVE"
    assert decision.reasons["operational_staleness"][
        "reason"
    ] == (
        "UNKNOWN_RECENCY_FIRST_SEEN_"
        "AGE_EXCEEDED_30_DAYS"
    )


def test_unknown_recency_genuinely_new_ats_is_not_stale(
    tmp_path: Path,
) -> None:
    database = _setup_database(
        tmp_path
    )
    _add_company(database, 1, "NewUnknownCo")
    _add_ats_job(
        database,
        job_id=801,
        company_id=1,
        published_at=None,
    )
    _add_match(
        database,
        record_kind="ATS",
        record_id=801,
    )

    decision = _decision(
        database,
        "ATS",
        801,
    )

    assert decision.operational_state == "NEW"
    assert decision.reasons["operational_staleness"][
        "reason"
    ] is None


def test_physical_source_first_seen_timestamps_are_not_rewritten(
    tmp_path: Path,
) -> None:
    database = _setup_database(
        tmp_path
    )
    _add_company(database, 1, "PhysicalCo")
    _add_ats_job(
        database,
        job_id=901,
        company_id=1,
    )
    _add_lead(
        database,
        lead_id=902,
        company_id=1,
        canonical_job_id=901,
    )
    _add_match(
        database,
        record_kind="ATS",
        record_id=901,
    )

    _service(database).run(
        apply=True
    )

    with database.connection() as connection:
        row = connection.execute(
            """
            SELECT
                jobs.first_seen_at
                    AS job_first_seen_at,
                job_leads.first_seen_at
                    AS lead_first_seen_at
            FROM jobs
            JOIN job_leads
              ON job_leads.canonical_job_id =
                 jobs.id
            WHERE jobs.id = 901
            """
        ).fetchone()

    assert row["job_first_seen_at"] == _db_time(
        AFTER_WATERMARK
    )
    assert row["lead_first_seen_at"] == _db_time(
        BEFORE_WATERMARK
    )


def test_persisted_priority_first_seen_is_effective_first_seen(
    tmp_path: Path,
) -> None:
    database = _setup_database(
        tmp_path
    )
    _add_company(database, 1, "PersistCo")
    _add_ats_job(
        database,
        job_id=1001,
        company_id=1,
    )
    _add_lead(
        database,
        lead_id=1002,
        company_id=1,
        canonical_job_id=1001,
    )
    _add_match(
        database,
        record_kind="ATS",
        record_id=1001,
    )

    _service(database).run(
        apply=True
    )

    with database.connection() as connection:
        row = connection.execute(
            """
            SELECT first_seen_at, reasons_json, rule_version
            FROM job_operational_priorities
            WHERE record_kind = 'ATS'
              AND record_id = 1001
            """
        ).fetchone()

    assert row["first_seen_at"] == _db_time(
        BEFORE_WATERMARK
    )
    assert row["rule_version"] == RULE_VERSION
    assert "OPERATIONAL_PRIORITY_V5" == RULE_VERSION
    assert "effective_first_seen_at" in row[
        "reasons_json"
    ]


def test_historical_canonical_ats_no_longer_enters_focus(
    tmp_path: Path,
) -> None:
    database = _setup_database(
        tmp_path
    )
    _add_company(database, 1, "FocusCo")
    _add_ats_job(
        database,
        job_id=1101,
        company_id=1,
    )
    _add_lead(
        database,
        lead_id=1102,
        company_id=1,
        canonical_job_id=1101,
    )
    _add_match(
        database,
        record_kind="ATS",
        record_id=1101,
        level="HIGH",
    )

    _service(database).run(
        apply=True
    )

    summary = build_summary(
        JobShortlistReportRepository(
            database
        ).load(
            "BACKEND_SOFTWARE_V1"
        )
    )

    assert not summary.focus
    assert len(summary.high_value) == 1
    assert (
        summary.high_value[0]
        .source
        .operational_state
        == "KNOWN"
    )
