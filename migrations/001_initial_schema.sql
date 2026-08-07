-- migrations/001_initial_schema.sql

PRAGMA foreign_keys = ON;

-- ============================================================
-- RUNS / TRACING
-- ============================================================

CREATE TABLE runs (
    id INTEGER PRIMARY KEY,
    command TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    created_by TEXT NOT NULL DEFAULT 'MANUAL',
    notes TEXT
);

CREATE TABLE run_steps (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL,

    step_name TEXT NOT NULL,

    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,

    items_total INTEGER,
    items_success INTEGER,
    items_failed INTEGER,
    items_skipped INTEGER,

    metadata_json TEXT,
    error_message TEXT,

    FOREIGN KEY (run_id)
        REFERENCES runs(id)
        ON DELETE CASCADE
);

CREATE INDEX idx_run_steps_run_id
    ON run_steps(run_id);

CREATE INDEX idx_run_steps_step_name
    ON run_steps(step_name);


-- ============================================================
-- COMPANIES
-- ============================================================

CREATE TABLE companies (
    id INTEGER PRIMARY KEY,

    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,

    domain TEXT,
    website_url TEXT,

    company_type TEXT NOT NULL DEFAULT 'UNKNOWN',
    target_priority TEXT NOT NULL DEFAULT 'UNKNOWN',

    careers_url TEXT,
    general_application_url TEXT,

    country TEXT,

    remote_latam INTEGER,
    remote_argentina INTEGER,

    status TEXT NOT NULL DEFAULT 'ACTIVE',

    notes TEXT,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    UNIQUE (domain)
);

CREATE INDEX idx_companies_normalized_name
    ON companies(normalized_name);

CREATE INDEX idx_companies_company_type
    ON companies(company_type);

CREATE INDEX idx_companies_status
    ON companies(status);


-- ============================================================
-- COMPANY SOURCES
-- ============================================================

CREATE TABLE company_sources (
    id INTEGER PRIMARY KEY,

    company_id INTEGER NOT NULL,

    source_type TEXT NOT NULL,
    external_id TEXT,
    source_url TEXT,

    raw_name TEXT,
    metadata_json TEXT,

    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,

    FOREIGN KEY (company_id)
        REFERENCES companies(id)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX uq_company_sources_external
    ON company_sources(source_type, external_id)
    WHERE external_id IS NOT NULL;

CREATE UNIQUE INDEX uq_company_sources_url
    ON company_sources(company_id, source_type, source_url)
    WHERE source_url IS NOT NULL;

CREATE INDEX idx_company_sources_company_id
    ON company_sources(company_id);

CREATE INDEX idx_company_sources_source_type
    ON company_sources(source_type);


-- ============================================================
-- COMPANY SCANS
-- ============================================================

CREATE TABLE company_scans (
    id INTEGER PRIMARY KEY,

    run_step_id INTEGER NOT NULL,
    company_id INTEGER NOT NULL,

    started_at TEXT NOT NULL,
    finished_at TEXT,

    status TEXT NOT NULL,

    homepage_url TEXT,
    homepage_http_status INTEGER,

    careers_url_found TEXT,
    careers_discovery_method TEXT,

    contacts_found_count INTEGER NOT NULL DEFAULT 0,

    ats_status TEXT,

    review_status TEXT NOT NULL DEFAULT 'UNREVIEWED',
    expected_ats_provider TEXT,
    review_notes TEXT,

    error_type TEXT,
    error_message TEXT,

    FOREIGN KEY (run_step_id)
        REFERENCES run_steps(id)
        ON DELETE CASCADE,

    FOREIGN KEY (company_id)
        REFERENCES companies(id)
        ON DELETE CASCADE
);

CREATE INDEX idx_company_scans_run_step_id
    ON company_scans(run_step_id);

CREATE INDEX idx_company_scans_company_id
    ON company_scans(company_id);

CREATE INDEX idx_company_scans_status
    ON company_scans(status);

CREATE INDEX idx_company_scans_review_status
    ON company_scans(review_status);


-- ============================================================
-- ATS DETECTIONS
-- ============================================================

CREATE TABLE ats_detections (
    id INTEGER PRIMARY KEY,

    company_scan_id INTEGER NOT NULL,

    provider TEXT NOT NULL,
    external_identifier TEXT,

    method TEXT NOT NULL,

    source_url TEXT,
    evidence TEXT,

    confidence REAL NOT NULL,

    selected INTEGER NOT NULL DEFAULT 0,

    created_at TEXT NOT NULL,

    FOREIGN KEY (company_scan_id)
        REFERENCES company_scans(id)
        ON DELETE CASCADE
);

CREATE INDEX idx_ats_detections_company_scan_id
    ON ats_detections(company_scan_id);

CREATE INDEX idx_ats_detections_provider
    ON ats_detections(provider);

CREATE INDEX idx_ats_detections_selected
    ON ats_detections(selected);


-- ============================================================
-- CURRENT ATS STATE FOR A COMPANY
-- ============================================================

CREATE TABLE company_ats (
    id INTEGER PRIMARY KEY,

    company_id INTEGER NOT NULL,

    provider TEXT NOT NULL,
    external_identifier TEXT,
    board_url TEXT,

    is_primary INTEGER NOT NULL DEFAULT 1,
    is_active INTEGER NOT NULL DEFAULT 1,

    detected_at TEXT NOT NULL,
    last_validated_at TEXT,
    last_successful_sync_at TEXT,

    source_detection_id INTEGER,

    FOREIGN KEY (company_id)
        REFERENCES companies(id)
        ON DELETE CASCADE,

    FOREIGN KEY (source_detection_id)
        REFERENCES ats_detections(id)
        ON DELETE SET NULL
);

CREATE UNIQUE INDEX uq_company_ats_identity
    ON company_ats(company_id, provider, external_identifier)
    WHERE external_identifier IS NOT NULL;

CREATE INDEX idx_company_ats_company_id
    ON company_ats(company_id);

CREATE INDEX idx_company_ats_provider
    ON company_ats(provider);

CREATE INDEX idx_company_ats_active
    ON company_ats(is_active);


-- ============================================================
-- PUBLIC CONTACTS
-- ============================================================

CREATE TABLE public_contacts (
    id INTEGER PRIMARY KEY,

    company_id INTEGER NOT NULL,

    contact_type TEXT NOT NULL,
    value TEXT NOT NULL,

    source_url TEXT,

    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,

    is_active INTEGER NOT NULL DEFAULT 1,

    review_status TEXT NOT NULL DEFAULT 'UNREVIEWED',

    notes TEXT,

    FOREIGN KEY (company_id)
        REFERENCES companies(id)
        ON DELETE CASCADE,

    UNIQUE (company_id, contact_type, value)
);

CREATE INDEX idx_public_contacts_company_id
    ON public_contacts(company_id);

CREATE INDEX idx_public_contacts_contact_type
    ON public_contacts(contact_type);

CREATE INDEX idx_public_contacts_review_status
    ON public_contacts(review_status);


-- ============================================================
-- JOBS
-- ============================================================

CREATE TABLE jobs (
    id INTEGER PRIMARY KEY,

    company_id INTEGER NOT NULL,
    company_ats_id INTEGER NOT NULL,

    external_id TEXT NOT NULL,

    title TEXT NOT NULL,
    description TEXT,

    location_text TEXT,
    workplace_type TEXT,
    employment_type TEXT,

    job_url TEXT,
    apply_url TEXT,

    published_at TEXT,

    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,

    is_active INTEGER NOT NULL DEFAULT 1,

    raw_payload_json TEXT,

    FOREIGN KEY (company_id)
        REFERENCES companies(id)
        ON DELETE CASCADE,

    FOREIGN KEY (company_ats_id)
        REFERENCES company_ats(id)
        ON DELETE CASCADE,

    UNIQUE (company_ats_id, external_id)
);

CREATE INDEX idx_jobs_company_id
    ON jobs(company_id);

CREATE INDEX idx_jobs_company_ats_id
    ON jobs(company_ats_id);

CREATE INDEX idx_jobs_active
    ON jobs(is_active);

CREATE INDEX idx_jobs_title
    ON jobs(title);


-- ============================================================
-- ATS SYNCHRONIZATION TRACING
-- ============================================================

CREATE TABLE ats_syncs (
    id INTEGER PRIMARY KEY,

    run_step_id INTEGER NOT NULL,
    company_ats_id INTEGER NOT NULL,

    started_at TEXT NOT NULL,
    finished_at TEXT,

    status TEXT NOT NULL,

    http_status INTEGER,

    jobs_received INTEGER NOT NULL DEFAULT 0,
    jobs_created INTEGER NOT NULL DEFAULT 0,
    jobs_updated INTEGER NOT NULL DEFAULT 0,
    jobs_deactivated INTEGER NOT NULL DEFAULT 0,

    error_type TEXT,
    error_message TEXT,

    FOREIGN KEY (run_step_id)
        REFERENCES run_steps(id)
        ON DELETE CASCADE,

    FOREIGN KEY (company_ats_id)
        REFERENCES company_ats(id)
        ON DELETE CASCADE
);

CREATE INDEX idx_ats_syncs_run_step_id
    ON ats_syncs(run_step_id);

CREATE INDEX idx_ats_syncs_company_ats_id
    ON ats_syncs(company_ats_id);

CREATE INDEX idx_ats_syncs_status
    ON ats_syncs(status);


-- ============================================================
-- SEARCH PROFILES
-- ============================================================

CREATE TABLE search_profiles (
    id INTEGER PRIMARY KEY,

    name TEXT NOT NULL UNIQUE,
    description TEXT,

    rules_json TEXT NOT NULL,

    is_active INTEGER NOT NULL DEFAULT 1,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);


-- ============================================================
-- JOB MATCHING RESULTS
-- ============================================================

CREATE TABLE job_matches (
    id INTEGER PRIMARY KEY,

    job_id INTEGER NOT NULL,
    search_profile_id INTEGER NOT NULL,
    run_step_id INTEGER NOT NULL,

    score REAL NOT NULL,
    match_level TEXT NOT NULL,

    reasons_json TEXT,

    created_at TEXT NOT NULL,

    FOREIGN KEY (job_id)
        REFERENCES jobs(id)
        ON DELETE CASCADE,

    FOREIGN KEY (search_profile_id)
        REFERENCES search_profiles(id)
        ON DELETE CASCADE,

    FOREIGN KEY (run_step_id)
        REFERENCES run_steps(id)
        ON DELETE CASCADE,

    UNIQUE (job_id, search_profile_id, run_step_id)
);

CREATE INDEX idx_job_matches_job_id
    ON job_matches(job_id);

CREATE INDEX idx_job_matches_profile_id
    ON job_matches(search_profile_id);

CREATE INDEX idx_job_matches_run_step_id
    ON job_matches(run_step_id);

CREATE INDEX idx_job_matches_score
    ON job_matches(score DESC);

CREATE INDEX idx_job_matches_level
    ON job_matches(match_level);


-- ============================================================
-- APPLICATIONS / MANUAL OUTREACH TRACKING
-- ============================================================

CREATE TABLE applications (
    id INTEGER PRIMARY KEY,

    company_id INTEGER NOT NULL,

    job_id INTEGER,
    public_contact_id INTEGER,

    application_type TEXT NOT NULL,
    status TEXT NOT NULL,

    applied_at TEXT,
    last_status_at TEXT,

    notes TEXT,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY (company_id)
        REFERENCES companies(id)
        ON DELETE CASCADE,

    FOREIGN KEY (job_id)
        REFERENCES jobs(id)
        ON DELETE SET NULL,

    FOREIGN KEY (public_contact_id)
        REFERENCES public_contacts(id)
        ON DELETE SET NULL
);

CREATE INDEX idx_applications_company_id
    ON applications(company_id);

CREATE INDEX idx_applications_job_id
    ON applications(job_id);

CREATE INDEX idx_applications_status
    ON applications(status);