from datetime import UTC, datetime

from chamba_hunter.db.connection import Database
from chamba_hunter.db.converters import datetime_to_db
from chamba_hunter.db.migrations import migrate
from chamba_hunter.repositories.job_freshness_repository import JobFreshnessRepository
from chamba_hunter.repositories.job_matching_repository import JobMatchingRepository
from chamba_hunter.repositories.job_operational_priority_repository import JobOperationalPriorityRepository
from chamba_hunter.repositories.job_shortlist_report_repository import JobShortlistReportRepository
from chamba_hunter.repositories.tracing_repository import TracingRepository
from chamba_hunter.services.job_matching_service import (
    JobMatchingService,
    SSR_SENIOR_BACKEND_SOFTWARE_V1,
)
from chamba_hunter.services.job_operational_priority_service import JobOperationalPriorityService
from chamba_hunter.services.job_shortlist_report_service import build_summary
from chamba_hunter.services.search_profile_registry import (
    LEGACY_PROFILE_NAME,
    SSR_SENIOR_PROFILE_NAME,
)


def _database(tmp_path) -> Database:
    database = Database(tmp_path / "profiles.db")
    migrate(database)
    now = datetime_to_db(datetime.now(UTC))
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO companies (id,name,normalized_name,created_at,updated_at) VALUES (1,'Example','example',?,?)",
            (now, now),
        )
        connection.execute(
            "INSERT INTO company_ats (id,company_id,provider,external_identifier,detected_at) VALUES (1,1,'GREENHOUSE','example',?)",
            (now,),
        )
        connection.execute(
            """INSERT INTO jobs (
                id,company_id,company_ats_id,external_id,title,description,
                job_url,published_at,first_seen_at,last_seen_at,is_active
            ) VALUES (1,1,1,'job-1','Semi Senior Java Backend Engineer',
                'Build Java Spring Boot REST APIs and distributed systems with PostgreSQL, AWS and Kubernetes.',
                'https://example.test/job-1',?,?,?,1)""",
            (now, now, now),
        )
        connection.execute(
            "INSERT INTO job_eligibility_classifications (record_kind,record_id,status,reason,method,rule_version,classified_at) VALUES ('ATS',1,'ELIGIBLE','fixture','TITLE','ARGENTINA_V1',?)",
            (now,),
        )
        connection.execute(
            "INSERT INTO job_occupation_classifications (record_kind,record_id,occupation_class,backend_relevance,reason,method,rule_version,classified_at) VALUES ('ATS',1,'SOFTWARE_ENGINEERING','BACKEND','fixture','TITLE_DESCRIPTION','OCCUPATION_V3',?)",
            (now,),
        )
        connection.execute(
            "INSERT INTO job_seniority_classifications (record_kind,record_id,seniority_class,leadership_class,seniority_reason,leadership_reason,method,rule_version,classified_at) VALUES ('ATS',1,'MID','NONE','fixture','fixture','TITLE','SENIORITY_V1',?)",
            (now,),
        )
        connection.execute(
            "INSERT INTO job_skill_classifications (record_kind,record_id,skill_key,skill_category,title_match,description_match,rule_version,classified_at) VALUES ('ATS',1,'JAVA','LANGUAGE',1,1,'SKILLS_V2',?)",
            (now,),
        )
        connection.execute(
            "INSERT INTO search_profiles (id,name,description,rules_json,is_active,created_at,updated_at) VALUES (1,?,'legacy','{}',1,?,?)",
            (LEGACY_PROFILE_NAME, now, now),
        )
        connection.execute(
            """INSERT INTO job_professional_matches (
                record_kind,record_id,search_profile_id,score,match_level,
                role_score,skills_score,seniority_score,leadership_score,
                technology_penalty,score_ceiling,reasons_json,rule_version,matched_at
            ) VALUES ('ATS',1,1,60,'MEDIUM',45,0,5,10,0,100,'{}','MATCHING_V2',?)""",
            (now,),
        )
    return database


def test_new_profile_persistence_isolated_and_propagates_to_priority_and_export(tmp_path) -> None:
    database = _database(tmp_path)
    matching = JobMatchingService(
        JobMatchingRepository(database),
        TracingRepository(database),
        profile=SSR_SENIOR_BACKEND_SOFTWARE_V1,
    ).run(apply=True)
    assert matching.relevant == 1

    with database.connection() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM job_skill_classifications WHERE rule_version='SKILLS_V2'"
        ).fetchone()[0] == 1
        rows = connection.execute(
            """SELECT sp.name, pm.rule_version
               FROM job_professional_matches pm JOIN search_profiles sp ON sp.id=pm.search_profile_id
               ORDER BY sp.name"""
        ).fetchall()
    assert {(row["name"], row["rule_version"]) for row in rows} == {
        (LEGACY_PROFILE_NAME, "MATCHING_V2"),
        (SSR_SENIOR_PROFILE_NAME, "MATCHING_V4"),
    }

    priority = JobOperationalPriorityService(
        repository=JobOperationalPriorityRepository(database),
        freshness_repository=JobFreshnessRepository(database),
        tracing_repository=TracingRepository(database),
        profile_name=SSR_SENIOR_PROFILE_NAME,
    ).run(apply=True)
    assert priority.total == 1

    report = build_summary(
        JobShortlistReportRepository(database).load(SSR_SENIOR_PROFILE_NAME)
    )
    assert report.source.profile_name == SSR_SENIOR_PROFILE_NAME
    assert report.all_current[0].source.professional_rule_version == "MATCHING_V4"
