-- Current, recomputable seniority and leadership-title classification for
-- geographically eligible or unresolved active job candidates.
-- Raw jobs/job_leads records and profile-specific matching remain unchanged.

CREATE TABLE job_seniority_classifications (
    id INTEGER PRIMARY KEY,

    record_kind TEXT NOT NULL,
    record_id INTEGER NOT NULL,

    seniority_class TEXT NOT NULL,
    leadership_class TEXT NOT NULL,

    seniority_reason TEXT NOT NULL,
    leadership_reason TEXT NOT NULL,
    method TEXT NOT NULL,
    rule_version TEXT NOT NULL,

    evidence_json TEXT,

    classified_at TEXT NOT NULL,

    CHECK (
        record_kind IN ('ATS', 'LEAD')
    ),

    CHECK (
        seniority_class IN (
            'INTERN',
            'ENTRY',
            'JUNIOR',
            'MID',
            'SENIOR',
            'STAFF',
            'PRINCIPAL',
            'LEAD',
            'UNKNOWN'
        )
    ),

    CHECK (
        leadership_class IN (
            'NONE',
            'MANAGER',
            'DIRECTOR',
            'HEAD',
            'VP',
            'C_LEVEL',
            'UNKNOWN'
        )
    ),

    CHECK (
        method IN (
            'TITLE',
            'DESCRIPTION',
            'TITLE_DESCRIPTION',
            'UNRESOLVED'
        )
    ),

    UNIQUE (
        record_kind,
        record_id
    )
);

CREATE INDEX idx_job_seniority_class
    ON job_seniority_classifications(seniority_class);

CREATE INDEX idx_job_seniority_leadership
    ON job_seniority_classifications(leadership_class);

CREATE INDEX idx_job_seniority_method
    ON job_seniority_classifications(method);

CREATE INDEX idx_job_seniority_rule_version
    ON job_seniority_classifications(rule_version);
