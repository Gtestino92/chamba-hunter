from pathlib import Path

import pytest

from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate
from chamba_hunter.services.retired_source_cleanup_service import (
    RetiredSourceCleanupService,
    open_cleanup_connection,
)


NOW = "2026-01-01T00:00:00+00:00"


def test_preview_is_read_only_and_targets_only_retired_sources(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    ids = _seed_cleanup_fixture(database)
    before = _table_counts(database)

    connection = open_cleanup_connection(
        database.path,
        read_only=True,
    )
    try:
        plan = RetiredSourceCleanupService(connection).build_plan()
    finally:
        connection.close()

    after = _table_counts(database)

    assert after == before
    assert sum(row.job_leads for row in plan.source_counts) == 3
    assert plan.source_acquisition_states == 3
    assert plan.source_specific_runs == 3
    assert plan.source_specific_run_steps == 3
    assert plan.company_sources == 3
    assert plan.companies.touched == 3
    assert plan.companies.safe_orphans == 1
    assert plan.companies.preserved == 2
    assert ids["dynamite_lead"] not in plan.target_lead_ids
    assert ids["himalayas_lead"] not in plan.target_lead_ids


def test_apply_removes_retired_data_and_preserves_unrelated_data(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    ids = _seed_cleanup_fixture(database)

    with database.connection() as connection:
        plan = RetiredSourceCleanupService(connection).apply()

    assert plan.applications == 0

    with database.connection() as connection:
        assert _count(
            connection,
            "job_leads",
            "source_type IN ('REMOTECO', 'REMOTIVE', 'REMOTEOK')",
        ) == 0
        assert _count(
            connection,
            "job_leads",
            "source_type = 'DYNAMITEJOBS'",
        ) == 1
        assert _count(
            connection,
            "job_leads",
            "source_type = 'HIMALAYAS'",
        ) == 1
        assert _exists(
            connection,
            "jobs",
            ids["canonical_job"],
        )
        assert _exists(
            connection,
            "companies",
            ids["mixed_company"],
        )
        assert _exists(
            connection,
            "companies",
            ids["ats_company"],
        )
        assert not _exists(
            connection,
            "companies",
            ids["orphan_company"],
        )
        assert _derived_count(
            connection,
            "job_eligibility_classifications",
            "LEAD",
            ids["remoteco_lead"],
        ) == 0
        assert _derived_count(
            connection,
            "job_occupation_classifications",
            "LEAD",
            ids["remoteco_lead"],
        ) == 0
        assert _derived_count(
            connection,
            "job_skill_classifications",
            "LEAD",
            ids["remoteco_lead"],
        ) == 0
        assert _derived_count(
            connection,
            "job_seniority_classifications",
            "LEAD",
            ids["remoteco_lead"],
        ) == 0
        assert _derived_count(
            connection,
            "job_professional_matches",
            "LEAD",
            ids["remoteco_lead"],
        ) == 0
        assert _derived_count(
            connection,
            "job_operational_priorities",
            "LEAD",
            ids["remoteco_lead"],
        ) == 0
        assert _derived_count(
            connection,
            "job_eligibility_classifications",
            "ATS",
            ids["canonical_job"],
        ) == 1
        assert _derived_count(
            connection,
            "job_professional_matches",
            "ATS",
            ids["canonical_job"],
        ) == 1
        assert _count(
            connection,
            "source_acquisition_states",
            "source_type IN ('REMOTECO', 'REMOTIVE', 'REMOTEOK')",
        ) == 0
        assert _count(
            connection,
            "source_acquisition_states",
            "source_type = 'DYNAMITEJOBS'",
        ) == 1
        assert _count(
            connection,
            "company_sources",
            "source_type IN ('REMOTECO', 'REMOTIVE', 'REMOTEOK')",
        ) == 0
        assert _count(
            connection,
            "company_sources",
            "source_type = 'DYNAMITEJOBS'",
        ) == 1
        assert _count(
            connection,
            "runs",
            "command IN ("
            "'acquire_remoteco_jobs', "
            "'acquire_remotive_jobs', "
            "'acquire_remoteok_jobs')",
        ) == 0
        assert _count(
            connection,
            "runs",
            "command = 'refresh_search'",
        ) == 1


def test_application_referencing_target_lead_blocks_apply(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    ids = _seed_cleanup_fixture(database)
    application_id = _insert_application(
        database,
        company_id=ids["orphan_company"],
        record_kind="LEAD",
        record_id=ids["remoteco_lead"],
    )

    with database.connection() as connection:
        with pytest.raises(RuntimeError, match="tracked application"):
            RetiredSourceCleanupService(connection).apply()

    with database.connection() as connection:
        assert _exists(
            connection,
            "applications",
            application_id,
        )
        assert _exists(
            connection,
            "job_leads",
            ids["remoteco_lead"],
        )


def test_apply_is_transactional(tmp_path: Path) -> None:
    database = _database(tmp_path)
    ids = _seed_cleanup_fixture(database)

    with database.connection() as connection:
        with pytest.raises(RuntimeError, match="Simulated"):
            RetiredSourceCleanupService(connection).apply(
                fail_after_derived_cleanup=True
            )

    with database.connection() as connection:
        assert _exists(
            connection,
            "job_leads",
            ids["remoteco_lead"],
        )
        assert _derived_count(
            connection,
            "job_eligibility_classifications",
            "LEAD",
            ids["remoteco_lead"],
        ) == 1
        assert _count(
            connection,
            "company_sources",
            "source_type = 'REMOTECO'",
        ) == 1


def test_apply_is_idempotent(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _seed_cleanup_fixture(database)

    with database.connection() as connection:
        first_plan = RetiredSourceCleanupService(connection).apply()
    with database.connection() as connection:
        second_plan = RetiredSourceCleanupService(connection).apply()

    assert sum(row.job_leads for row in first_plan.source_counts) == 3
    assert sum(row.job_leads for row in second_plan.source_counts) == 0
    assert second_plan.source_acquisition_states == 0
    assert second_plan.source_specific_runs == 0
    assert second_plan.company_sources == 0
    assert second_plan.companies.touched == 0


def _database(tmp_path: Path) -> Database:
    database = Database(tmp_path / "test.db")
    migrate(database)
    return database


def _seed_cleanup_fixture(
    database: Database,
) -> dict[str, int]:
    ids: dict[str, int] = {}
    with database.transaction() as connection:
        profile_id = _insert_search_profile(connection)
        shared_run_id = _insert_run(connection, "refresh_search")
        ids["source_run_remote"] = _insert_run(
            connection,
            "acquire_remoteco_jobs",
        )
        _insert_run(connection, "acquire_remotive_jobs")
        _insert_run(connection, "acquire_remoteok_jobs")
        _insert_run_step(connection, shared_run_id)
        _insert_run_step(connection, ids["source_run_remote"])
        _insert_run_step(
            connection,
            _run_id(connection, "acquire_remotive_jobs"),
        )
        _insert_run_step(
            connection,
            _run_id(connection, "acquire_remoteok_jobs"),
        )

        ids["orphan_company"] = _insert_company(
            connection,
            "Retired Only",
        )
        ids["mixed_company"] = _insert_company(
            connection,
            "Mixed Source",
        )
        ids["ats_company"] = _insert_company(
            connection,
            "ATS Backed",
        )
        ids["other_company"] = _insert_company(
            connection,
            "Other Source",
        )

        _insert_company_source(
            connection,
            ids["orphan_company"],
            "REMOTECO",
        )
        _insert_company_source(
            connection,
            ids["mixed_company"],
            "REMOTIVE",
        )
        _insert_company_source(
            connection,
            ids["mixed_company"],
            "DYNAMITEJOBS",
        )
        _insert_company_source(
            connection,
            ids["ats_company"],
            "REMOTEOK",
        )
        _insert_company_source(
            connection,
            ids["other_company"],
            "HIMALAYAS",
        )

        company_ats_id = _insert_company_ats(
            connection,
            ids["ats_company"],
        )
        ids["canonical_job"] = _insert_job(
            connection,
            ids["ats_company"],
            company_ats_id,
        )
        ids["remoteco_lead"] = _insert_job_lead(
            connection,
            ids["orphan_company"],
            "REMOTECO",
            "remote-1",
        )
        ids["remotive_lead"] = _insert_job_lead(
            connection,
            ids["mixed_company"],
            "REMOTIVE",
            "remotive-1",
        )
        ids["remoteok_lead"] = _insert_job_lead(
            connection,
            ids["ats_company"],
            "REMOTEOK",
            "remoteok-1",
            canonical_job_id=ids["canonical_job"],
        )
        ids["dynamite_lead"] = _insert_job_lead(
            connection,
            ids["mixed_company"],
            "DYNAMITEJOBS",
            "dynamite-1",
        )
        ids["himalayas_lead"] = _insert_job_lead(
            connection,
            ids["other_company"],
            "HIMALAYAS",
            "himalayas-1",
        )
        _insert_job_ats_hint(
            connection,
            ids["remoteco_lead"],
            ids["orphan_company"],
        )

        _insert_all_derived(
            connection,
            "LEAD",
            ids["remoteco_lead"],
            profile_id,
            shared_run_id,
            ids["orphan_company"],
            "REMOTECO",
        )
        _insert_all_derived(
            connection,
            "ATS",
            ids["canonical_job"],
            profile_id,
            shared_run_id,
            ids["ats_company"],
            "ATS",
        )

        for source_type in (
            "REMOTECO",
            "REMOTIVE",
            "REMOTEOK",
            "DYNAMITEJOBS",
        ):
            _insert_source_state(connection, source_type)

    return ids


def _insert_search_profile(
    connection,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO search_profiles (
            name,
            rules_json,
            is_active,
            created_at,
            updated_at
        )
        VALUES ('default', '{}', 1, ?, ?)
        """,
        (NOW, NOW),
    )
    return int(cursor.lastrowid)


def _insert_run(
    connection,
    command: str,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO runs (
            command,
            started_at,
            finished_at,
            status,
            created_by
        )
        VALUES (?, ?, ?, 'SUCCESS', 'MANUAL')
        """,
        (command, NOW, NOW),
    )
    return int(cursor.lastrowid)


def _run_id(
    connection,
    command: str,
) -> int:
    row = connection.execute(
        "SELECT id FROM runs WHERE command = ?",
        (command,),
    ).fetchone()
    return int(row["id"])


def _insert_run_step(
    connection,
    run_id: int,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO run_steps (
            run_id,
            step_name,
            started_at,
            finished_at,
            status
        )
        VALUES (?, 'step', ?, ?, 'SUCCESS')
        """,
        (run_id, NOW, NOW),
    )
    return int(cursor.lastrowid)


def _insert_company(
    connection,
    name: str,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO companies (
            name,
            normalized_name,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?)
        """,
        (name, name.lower(), NOW, NOW),
    )
    return int(cursor.lastrowid)


def _insert_company_source(
    connection,
    company_id: int,
    source_type: str,
) -> None:
    connection.execute(
        """
        INSERT INTO company_sources (
            company_id,
            source_type,
            external_id,
            first_seen_at,
            last_seen_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            company_id,
            source_type,
            f"{source_type}-{company_id}",
            NOW,
            NOW,
        ),
    )


def _insert_company_ats(
    connection,
    company_id: int,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO company_ats (
            company_id,
            provider,
            external_identifier,
            detected_at
        )
        VALUES (?, 'GREENHOUSE', ?, ?)
        """,
        (company_id, f"board-{company_id}", NOW),
    )
    return int(cursor.lastrowid)


def _insert_job(
    connection,
    company_id: int,
    company_ats_id: int,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO jobs (
            company_id,
            company_ats_id,
            external_id,
            title,
            first_seen_at,
            last_seen_at
        )
        VALUES (?, ?, 'ats-1', 'Backend Engineer', ?, ?)
        """,
        (company_id, company_ats_id, NOW, NOW),
    )
    return int(cursor.lastrowid)


def _insert_job_lead(
    connection,
    company_id: int,
    source_type: str,
    external_id: str,
    canonical_job_id: int | None = None,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO job_leads (
            company_id,
            source_type,
            external_id,
            canonical_job_id,
            title,
            first_seen_at,
            last_seen_at
        )
        VALUES (?, ?, ?, ?, 'Backend Engineer', ?, ?)
        """,
        (
            company_id,
            source_type,
            external_id,
            canonical_job_id,
            NOW,
            NOW,
        ),
    )
    return int(cursor.lastrowid)


def _insert_job_ats_hint(
    connection,
    job_lead_id: int,
    company_id: int,
) -> None:
    connection.execute(
        """
        INSERT INTO job_ats_hints (
            job_lead_id,
            company_id,
            provider,
            external_identifier,
            source_url,
            created_at
        )
        VALUES (?, ?, 'GREENHOUSE', 'board', 'https://example.com', ?)
        """,
        (job_lead_id, company_id, NOW),
    )


def _insert_all_derived(
    connection,
    record_kind: str,
    record_id: int,
    profile_id: int,
    run_id: int,
    company_id: int,
    source_type: str,
) -> None:
    connection.execute(
        """
        INSERT INTO job_eligibility_classifications (
            record_kind,
            record_id,
            status,
            reason,
            method,
            rule_version,
            classified_at
        )
        VALUES (?, ?, 'ELIGIBLE', 'ok', 'RULE', 'v1', ?)
        """,
        (record_kind, record_id, NOW),
    )
    connection.execute(
        """
        INSERT INTO job_occupation_classifications (
            record_kind,
            record_id,
            occupation_class,
            backend_relevance,
            reason,
            method,
            rule_version,
            classified_at
        )
        VALUES (
            ?,
            ?,
            'SOFTWARE_ENGINEERING',
            'BACKEND',
            'ok',
            'RULE',
            'v1',
            ?
        )
        """,
        (record_kind, record_id, NOW),
    )
    connection.execute(
        """
        INSERT INTO job_skill_classifications (
            record_kind,
            record_id,
            skill_key,
            skill_category,
            title_match,
            description_match,
            rule_version,
            classified_at
        )
        VALUES (?, ?, 'python', 'LANGUAGE', 1, 0, 'v1', ?)
        """,
        (record_kind, record_id, NOW),
    )
    connection.execute(
        """
        INSERT INTO job_seniority_classifications (
            record_kind,
            record_id,
            seniority_class,
            leadership_class,
            seniority_reason,
            leadership_reason,
            method,
            rule_version,
            classified_at
        )
        VALUES (
            ?,
            ?,
            'SENIOR',
            'NONE',
            'ok',
            'ok',
            'TITLE',
            'v1',
            ?
        )
        """,
        (record_kind, record_id, NOW),
    )
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
            rule_version,
            matched_at
        )
        VALUES (?, ?, ?, 90, 'HIGH', 40, 25, 15, 10, 0, 100, 'v1', ?)
        """,
        (record_kind, record_id, profile_id, NOW),
    )
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
            application_channel,
            first_seen_at,
            last_seen_at,
            rule_version,
            evaluated_at,
            evaluated_run_id
        )
        VALUES (
            ?,
            ?,
            ?,
            ?,
            'Company',
            ?,
            'SOURCE',
            'Backend Engineer',
            'NEW',
            90,
            'HIGH',
            'v1',
            'JOB_URL',
            ?,
            ?,
            'v1',
            ?,
            ?
        )
        """,
        (
            record_kind,
            record_id,
            profile_id,
            company_id,
            source_type,
            NOW,
            NOW,
            NOW,
            run_id,
        ),
    )


def _insert_source_state(
    connection,
    source_type: str,
) -> None:
    connection.execute(
        """
        INSERT INTO source_acquisition_states (
            source_type,
            scope_key,
            last_successful_started_at,
            last_successful_finished_at,
            metadata_json,
            created_at,
            updated_at
        )
        VALUES (?, 'default', ?, ?, '{}', ?, ?)
        """,
        (source_type, NOW, NOW, NOW, NOW),
    )


def _insert_application(
    database: Database,
    company_id: int,
    record_kind: str,
    record_id: int,
) -> int:
    with database.transaction() as connection:
        cursor = connection.execute(
            """
            INSERT INTO applications (
                company_id,
                application_type,
                status,
                created_at,
                updated_at,
                record_kind,
                record_id
            )
            VALUES (?, 'JOB', 'APPLIED', ?, ?, ?, ?)
            """,
            (
                company_id,
                NOW,
                NOW,
                record_kind,
                record_id,
            ),
        )
        return int(cursor.lastrowid)


def _table_counts(database: Database) -> dict[str, int]:
    tables = (
        "companies",
        "company_sources",
        "job_leads",
        "job_eligibility_classifications",
        "job_occupation_classifications",
        "job_skill_classifications",
        "job_seniority_classifications",
        "job_professional_matches",
        "job_operational_priorities",
        "source_acquisition_states",
        "runs",
        "run_steps",
    )
    with database.connection() as connection:
        return {
            table: _count(connection, table, "1 = 1")
            for table in tables
        }


def _count(
    connection,
    table: str,
    where: str,
) -> int:
    row = connection.execute(
        f"SELECT COUNT(*) AS count FROM {table} WHERE {where}"
    ).fetchone()
    return int(row["count"])


def _exists(
    connection,
    table: str,
    row_id: int,
) -> bool:
    return (
        connection.execute(
            f"SELECT 1 FROM {table} WHERE id = ?",
            (row_id,),
        ).fetchone()
        is not None
    )


def _derived_count(
    connection,
    table: str,
    record_kind: str,
    record_id: int,
) -> int:
    row = connection.execute(
        f"""
        SELECT COUNT(*) AS count
        FROM {table}
        WHERE record_kind = ?
          AND record_id = ?
        """,
        (record_kind, record_id),
    ).fetchone()
    return int(row["count"])
