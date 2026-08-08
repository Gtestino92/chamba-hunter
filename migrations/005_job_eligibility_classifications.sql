-- Current, recomputable geographic eligibility for active job candidates.
-- The raw jobs/job_leads records remain unchanged.

CREATE TABLE job_eligibility_classifications (
    id INTEGER PRIMARY KEY,

    record_kind TEXT NOT NULL,
    record_id INTEGER NOT NULL,

    status TEXT NOT NULL,
    reason TEXT NOT NULL,

    method TEXT NOT NULL,
    rule_version TEXT NOT NULL,

    evidence_json TEXT,

    classified_at TEXT NOT NULL,

    CHECK (
        record_kind IN ('ATS', 'LEAD')
    ),

    CHECK (
        status IN (
            'ELIGIBLE',
            'INELIGIBLE',
            'UNKNOWN'
        )
    ),

    UNIQUE (
        record_kind,
        record_id
    )
);

CREATE INDEX idx_job_eligibility_status
    ON job_eligibility_classifications(status);

CREATE INDEX idx_job_eligibility_reason
    ON job_eligibility_classifications(reason);
