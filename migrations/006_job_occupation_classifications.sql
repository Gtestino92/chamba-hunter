-- Current, recomputable occupation classification for geographically
-- eligible or unresolved active job candidates.
-- Raw jobs/job_leads records remain unchanged.

CREATE TABLE job_occupation_classifications (
    id INTEGER PRIMARY KEY,

    record_kind TEXT NOT NULL,
    record_id INTEGER NOT NULL,

    occupation_class TEXT NOT NULL,
    backend_relevance TEXT NOT NULL,

    reason TEXT NOT NULL,
    method TEXT NOT NULL,
    rule_version TEXT NOT NULL,

    evidence_json TEXT,

    classified_at TEXT NOT NULL,

    CHECK (
        record_kind IN ('ATS', 'LEAD')
    ),

    CHECK (
        occupation_class IN (
            'SOFTWARE_ENGINEERING',
            'IT_TECHNICAL',
            'TECH_ADJACENT',
            'NON_TECHNICAL',
            'UNKNOWN'
        )
    ),

    CHECK (
        backend_relevance IN (
            'BACKEND',
            'FULL_STACK',
            'NON_BACKEND',
            'UNKNOWN',
            'NOT_APPLICABLE'
        )
    ),

    CHECK (
        (
            occupation_class = 'SOFTWARE_ENGINEERING'
            AND backend_relevance IN (
                'BACKEND',
                'FULL_STACK',
                'NON_BACKEND',
                'UNKNOWN'
            )
        )
        OR
        (
            occupation_class <> 'SOFTWARE_ENGINEERING'
            AND backend_relevance = 'NOT_APPLICABLE'
        )
    ),

    UNIQUE (
        record_kind,
        record_id
    )
);

CREATE INDEX idx_job_occupation_class
    ON job_occupation_classifications(occupation_class);

CREATE INDEX idx_job_occupation_backend
    ON job_occupation_classifications(backend_relevance);

CREATE INDEX idx_job_occupation_reason
    ON job_occupation_classifications(reason);
