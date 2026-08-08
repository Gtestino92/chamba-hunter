-- Current professional match evaluation for normalized job candidates.
-- This table intentionally supports both ATS jobs and unresolved broad leads.
-- Legacy job_matches is left untouched because it is keyed only by jobs.id.

CREATE TABLE job_professional_matches (
    id INTEGER PRIMARY KEY,

    record_kind TEXT NOT NULL,
    record_id INTEGER NOT NULL,
    search_profile_id INTEGER NOT NULL,

    score REAL NOT NULL,
    match_level TEXT NOT NULL,

    role_score REAL NOT NULL,
    skills_score REAL NOT NULL,
    seniority_score REAL NOT NULL,
    leadership_score REAL NOT NULL,
    technology_penalty REAL NOT NULL,
    score_ceiling REAL NOT NULL,

    reasons_json TEXT,

    rule_version TEXT NOT NULL,
    matched_at TEXT NOT NULL,

    CHECK (
        record_kind IN ('ATS', 'LEAD')
    ),

    CHECK (
        score >= 0
        AND score <= 100
    ),

    CHECK (
        match_level IN (
            'VERY_HIGH',
            'HIGH',
            'MEDIUM',
            'LOW'
        )
    ),

    CHECK (
        role_score >= 0
        AND role_score <= 45
    ),

    CHECK (
        skills_score >= 0
        AND skills_score <= 30
    ),

    CHECK (
        seniority_score >= 0
        AND seniority_score <= 15
    ),

    CHECK (
        leadership_score >= 0
        AND leadership_score <= 10
    ),

    CHECK (
        technology_penalty <= 0
        AND technology_penalty >= -5
    ),

    CHECK (
        score_ceiling >= 0
        AND score_ceiling <= 100
    ),

    FOREIGN KEY (search_profile_id)
        REFERENCES search_profiles(id)
        ON DELETE CASCADE,

    UNIQUE (
        record_kind,
        record_id,
        search_profile_id
    )
);

CREATE INDEX idx_job_professional_matches_profile
    ON job_professional_matches(search_profile_id);

CREATE INDEX idx_job_professional_matches_candidate
    ON job_professional_matches(record_kind, record_id);

CREATE INDEX idx_job_professional_matches_score
    ON job_professional_matches(search_profile_id, score DESC);

CREATE INDEX idx_job_professional_matches_level
    ON job_professional_matches(search_profile_id, match_level);

CREATE INDEX idx_job_professional_matches_rule_version
    ON job_professional_matches(rule_version);
