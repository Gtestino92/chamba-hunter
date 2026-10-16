import hashlib
import sys

from chamba_hunter.commands import audit_search_recall
from chamba_hunter.db.connection import Database
from chamba_hunter.db.migrations import migrate


def _digest(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_read_only_audit_leaves_database_unchanged(tmp_path, monkeypatch, capsys) -> None:
    path = tmp_path / "audit.db"
    database = Database(path)
    migrate(database)
    now = "2026-01-01T00:00:00+00:00"
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO companies (id, name, normalized_name, created_at, updated_at) VALUES (1, 'Example', 'example', ?, ?)",
            (now, now),
        )
        connection.execute(
            "INSERT INTO company_ats (id, company_id, provider, external_identifier, detected_at) VALUES (1, 1, 'GREENHOUSE', 'example', ?)",
            (now,),
        )
        connection.execute(
            """
            INSERT INTO jobs (
                id, company_id, company_ats_id, external_id, title, description,
                first_seen_at, last_seen_at, is_active
            ) VALUES (1, 1, 1, 'job-1', 'Senior Java Backend Engineer',
                'Build Java Spring Boot REST APIs with retries and idempotency.', ?, ?, 1)
            """,
            (now, now),
        )
        connection.execute(
            "INSERT INTO job_eligibility_classifications (record_kind, record_id, status, reason, method, rule_version, classified_at) VALUES ('ATS', 1, 'ELIGIBLE', 'fixture', 'TITLE', 'ARGENTINA_V1', ?)",
            (now,),
        )
        connection.execute(
            "INSERT INTO job_occupation_classifications (record_kind, record_id, occupation_class, backend_relevance, reason, method, rule_version, classified_at) VALUES ('ATS', 1, 'SOFTWARE_ENGINEERING', 'BACKEND', 'fixture', 'TITLE', 'OCCUPATION_V3', ?)",
            (now,),
        )
        connection.execute(
            "INSERT INTO job_seniority_classifications (record_kind, record_id, seniority_class, leadership_class, seniority_reason, leadership_reason, method, rule_version, classified_at) VALUES ('ATS', 1, 'SENIOR', 'NONE', 'fixture', 'fixture', 'TITLE', 'SENIORITY_V1', ?)",
            (now,),
        )
        for skill, category in (("JAVA", "LANGUAGE"), ("SPRING_BOOT", "FRAMEWORK"), ("REST", "ARCHITECTURE")):
            connection.execute(
                "INSERT INTO job_skill_classifications (record_kind, record_id, skill_key, skill_category, title_match, description_match, rule_version, classified_at) VALUES ('ATS', 1, ?, ?, 0, 1, 'SKILLS_V2', ?)",
                (skill, category, now),
            )

    before = _digest(path)
    monkeypatch.setattr(
        sys,
        "argv",
        ["audit_search_recall", "--db", str(path), "--samples", "1"],
    )
    audit_search_recall.main()
    after = _digest(path)

    assert before == after
    output = capsys.readouterr().out
    assert "strictly read-only" in output
    assert "Candidates: 1" in output
    assert "MATCHING_V3 + in-memory SKILLS_V3" in output


def test_read_only_database_rejects_transactions(tmp_path) -> None:
    path = tmp_path / "empty.db"
    with Database(path).connection():
        pass
    read_only = Database(path, read_only=True)
    try:
        with read_only.transaction():
            pass
    except RuntimeError as error:
        assert "read-only" in str(error)
    else:
        raise AssertionError("Expected read-only transaction rejection")
