-- Broad job acquisition keeps aggregator-originated postings separate
-- from canonical ATS snapshots while exposing one unified candidate view.

CREATE TABLE job_leads (
    id INTEGER PRIMARY KEY,

    company_id INTEGER NOT NULL,

    source_type TEXT NOT NULL,
    external_id TEXT NOT NULL,

    canonical_job_id INTEGER,

    title TEXT NOT NULL,
    description TEXT,

    location_text TEXT,
    workplace_type TEXT,
    employment_type TEXT,

    job_url TEXT,
    apply_url TEXT,

    published_at TEXT,
    expires_at TEXT,

    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,

    is_active INTEGER NOT NULL DEFAULT 1,

    raw_payload_json TEXT,

    FOREIGN KEY (company_id)
        REFERENCES companies(id)
        ON DELETE CASCADE,

    FOREIGN KEY (canonical_job_id)
        REFERENCES jobs(id)
        ON DELETE SET NULL,

    UNIQUE (source_type, external_id)
);

CREATE INDEX idx_job_leads_company_id
    ON job_leads(company_id);

CREATE INDEX idx_job_leads_source_type
    ON job_leads(source_type);

CREATE INDEX idx_job_leads_active
    ON job_leads(is_active);

CREATE INDEX idx_job_leads_canonical_job_id
    ON job_leads(canonical_job_id);

CREATE INDEX idx_job_leads_title
    ON job_leads(title);


CREATE TABLE job_ats_hints (
    id INTEGER PRIMARY KEY,

    job_lead_id INTEGER NOT NULL,
    company_id INTEGER NOT NULL,

    provider TEXT NOT NULL,
    external_identifier TEXT NOT NULL,

    source_url TEXT NOT NULL,

    created_at TEXT NOT NULL,

    FOREIGN KEY (job_lead_id)
        REFERENCES job_leads(id)
        ON DELETE CASCADE,

    FOREIGN KEY (company_id)
        REFERENCES companies(id)
        ON DELETE CASCADE,

    UNIQUE (
        job_lead_id,
        provider,
        external_identifier,
        source_url
    )
);

CREATE INDEX idx_job_ats_hints_company_id
    ON job_ats_hints(company_id);

CREATE INDEX idx_job_ats_hints_provider
    ON job_ats_hints(provider);


CREATE VIEW job_candidates AS

SELECT
    'ATS' AS record_kind,
    jobs.id AS record_id,
    jobs.company_id AS company_id,
    jobs.company_ats_id AS company_ats_id,
    'ATS' AS source_type,
    jobs.external_id AS external_id,
    jobs.title AS title,
    jobs.description AS description,
    jobs.location_text AS location_text,
    jobs.workplace_type AS workplace_type,
    jobs.employment_type AS employment_type,
    jobs.job_url AS job_url,
    jobs.apply_url AS apply_url,
    jobs.published_at AS published_at,
    NULL AS expires_at,
    jobs.first_seen_at AS first_seen_at,
    jobs.last_seen_at AS last_seen_at,
    jobs.is_active AS is_active,
    jobs.raw_payload_json AS raw_payload_json

FROM jobs

UNION ALL

SELECT
    'LEAD' AS record_kind,
    job_leads.id AS record_id,
    job_leads.company_id AS company_id,
    NULL AS company_ats_id,
    job_leads.source_type AS source_type,
    job_leads.external_id AS external_id,
    job_leads.title AS title,
    job_leads.description AS description,
    job_leads.location_text AS location_text,
    job_leads.workplace_type AS workplace_type,
    job_leads.employment_type AS employment_type,
    job_leads.job_url AS job_url,
    job_leads.apply_url AS apply_url,
    job_leads.published_at AS published_at,
    job_leads.expires_at AS expires_at,
    job_leads.first_seen_at AS first_seen_at,
    job_leads.last_seen_at AS last_seen_at,
    job_leads.is_active AS is_active,
    job_leads.raw_payload_json AS raw_payload_json

FROM job_leads

WHERE job_leads.canonical_job_id IS NULL;
