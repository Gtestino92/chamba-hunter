-- Direct company outreach: public contact scans plus one current
-- outreach priority per company/search profile.
--
-- public_contacts and the SPONTANEOUS_EMAIL / GENERAL_APPLICATION
-- application types already exist from the initial schema.

CREATE TABLE company_contact_scans (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    pages_fetched INTEGER NOT NULL DEFAULT 0,
    contacts_found INTEGER NOT NULL DEFAULT 0,
    error_type TEXT,
    error_message TEXT,
    FOREIGN KEY (company_id)
        REFERENCES companies(id)
        ON DELETE CASCADE,
    CHECK (
        status IN (
            'RUNNING',
            'SUCCESS',
            'PARTIAL',
            'FAILED'
        )
    )
);

CREATE INDEX idx_company_contact_scans_company
    ON company_contact_scans (
        company_id,
        finished_at
    );

CREATE INDEX idx_company_contact_scans_status
    ON company_contact_scans(status);

CREATE TABLE company_outreach_priorities (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL,
    search_profile_id INTEGER NOT NULL,
    current_max_match REAL,
    historical_max_match REAL,
    current_relevant_jobs INTEGER NOT NULL DEFAULT 0,
    best_contact_id INTEGER,
    score REAL NOT NULL,
    level TEXT NOT NULL,
    reasons_json TEXT,
    rule_version TEXT NOT NULL,
    evaluated_at TEXT NOT NULL,
    FOREIGN KEY (company_id)
        REFERENCES companies(id)
        ON DELETE CASCADE,
    FOREIGN KEY (search_profile_id)
        REFERENCES search_profiles(id)
        ON DELETE CASCADE,
    FOREIGN KEY (best_contact_id)
        REFERENCES public_contacts(id)
        ON DELETE SET NULL,
    UNIQUE (
        company_id,
        search_profile_id
    ),
    CHECK (
        score >= 0
        AND score <= 100
    ),
    CHECK (
        level IN (
            'VERY_HIGH',
            'HIGH',
            'MEDIUM',
            'LOW'
        )
    )
);

CREATE INDEX idx_company_outreach_priority_score
    ON company_outreach_priorities (
        search_profile_id,
        score DESC
    );

CREATE INDEX idx_company_outreach_priority_contact
    ON company_outreach_priorities(best_contact_id);
