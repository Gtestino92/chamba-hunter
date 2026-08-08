-- Current, recomputable explicit skill mentions for geographically
-- eligible or unresolved active job candidates.
-- Raw jobs/job_leads records and freshness/application metadata remain unchanged.

CREATE TABLE job_skill_classifications (
    id INTEGER PRIMARY KEY,

    record_kind TEXT NOT NULL,
    record_id INTEGER NOT NULL,

    skill_key TEXT NOT NULL,
    skill_category TEXT NOT NULL,

    title_match INTEGER NOT NULL,
    description_match INTEGER NOT NULL,

    evidence_json TEXT,

    rule_version TEXT NOT NULL,
    classified_at TEXT NOT NULL,

    CHECK (
        record_kind IN ('ATS', 'LEAD')
    ),

    CHECK (
        skill_category IN (
            'LANGUAGE',
            'FRAMEWORK',
            'DATABASE',
            'DATABASE_TOOLING',
            'DATA_PLATFORM',
            'ANALYTICS',
            'CLOUD',
            'CLOUD_SERVICE',
            'INFRASTRUCTURE',
            'MESSAGING',
            'CI_CD',
            'ARCHITECTURE',
            'ENGINEERING_PRACTICE',
            'SECURITY',
            'TESTING',
            'OBSERVABILITY',
            'FRONTEND',
            'MOBILE',
            'BUSINESS_PLATFORM',
            'BUILD_TOOL',
            'REALTIME'
        )
    ),

    CHECK (
        title_match IN (0, 1)
    ),

    CHECK (
        description_match IN (0, 1)
    ),

    CHECK (
        title_match = 1
        OR description_match = 1
    ),

    UNIQUE (
        record_kind,
        record_id,
        skill_key
    )
);

CREATE INDEX idx_job_skill_key
    ON job_skill_classifications(skill_key);

CREATE INDEX idx_job_skill_category
    ON job_skill_classifications(skill_category);

CREATE INDEX idx_job_skill_candidate
    ON job_skill_classifications(record_kind, record_id);

CREATE INDEX idx_job_skill_rule_version
    ON job_skill_classifications(rule_version);
