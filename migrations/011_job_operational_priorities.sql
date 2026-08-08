-- Current operational/application priority state for one search profile.
-- Unlike professional matches, rows are retained when a source becomes
-- inactive, superseded, or leaves the current professional scope.

CREATE TABLE job_operational_priorities (
    id INTEGER PRIMARY KEY,

    record_kind TEXT NOT NULL,
    record_id INTEGER NOT NULL,
    search_profile_id INTEGER NOT NULL,

    company_id INTEGER NOT NULL,
    company_name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    origin TEXT NOT NULL,
    title TEXT NOT NULL,

    operational_state TEXT NOT NULL,

    professional_score REAL NOT NULL,
    professional_match_level TEXT NOT NULL,
    professional_rule_version TEXT NOT NULL,
    professional_matched_at TEXT,

    application_channel TEXT NOT NULL,
    application_target TEXT,

    job_url TEXT,
    apply_url TEXT,
    general_application_url TEXT,

    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    published_at TEXT,
    last_changed_at TEXT,

    reasons_json TEXT,

    rule_version TEXT NOT NULL,
    evaluated_at TEXT NOT NULL,
    evaluated_run_id INTEGER NOT NULL,

    CHECK (record_kind IN ('ATS', 'LEAD')),

    CHECK (
        operational_state IN (
            'NEW',
            'UPDATED',
            'KNOWN',
            'INACTIVE',
            'SUPERSEDED',
            'OUT_OF_SCOPE'
        )
    ),

    CHECK (
        professional_score >= 0
        AND professional_score <= 100
    ),

    CHECK (
        professional_match_level IN (
            'VERY_HIGH',
            'HIGH',
            'MEDIUM',
            'LOW'
        )
    ),

    CHECK (
        application_channel IN (
            'DIRECT_APPLY_URL',
            'JOB_URL',
            'GENERAL_APPLICATION_URL',
            'PUBLIC_CONTACT',
            'NONE'
        )
    ),

    FOREIGN KEY (search_profile_id)
        REFERENCES search_profiles(id)
        ON DELETE CASCADE,

    FOREIGN KEY (evaluated_run_id)
        REFERENCES runs(id)
        ON DELETE RESTRICT,

    UNIQUE (
        record_kind,
        record_id,
        search_profile_id
    )
);

CREATE INDEX idx_job_operational_priorities_profile
    ON job_operational_priorities(search_profile_id);

CREATE INDEX idx_job_operational_priorities_candidate
    ON job_operational_priorities(record_kind, record_id);

CREATE INDEX idx_job_operational_priorities_state
    ON job_operational_priorities(
        search_profile_id,
        operational_state
    );

CREATE INDEX idx_job_operational_priorities_match
    ON job_operational_priorities(
        search_profile_id,
        professional_match_level,
        professional_score DESC
    );

CREATE INDEX idx_job_operational_priorities_rule
    ON job_operational_priorities(rule_version);
