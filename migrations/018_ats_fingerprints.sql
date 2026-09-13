-- migrations/018_ats_fingerprints.sql

PRAGMA foreign_keys = ON;

CREATE TABLE ats_fingerprints (
    id INTEGER PRIMARY KEY,

    run_step_id INTEGER,
    company_scan_id INTEGER,
    company_id INTEGER NOT NULL,

    input_url TEXT,
    final_url TEXT,

    fingerprint_status TEXT NOT NULL,
    provider_family TEXT,
    support_status TEXT NOT NULL,

    confidence REAL,
    detection_method TEXT,
    evidence TEXT,

    http_status INTEGER,
    error_type TEXT,
    error_message TEXT,

    scanned_at TEXT NOT NULL,
    metadata_json TEXT,

    FOREIGN KEY (run_step_id)
        REFERENCES run_steps(id)
        ON DELETE SET NULL,

    FOREIGN KEY (company_scan_id)
        REFERENCES company_scans(id)
        ON DELETE SET NULL,

    FOREIGN KEY (company_id)
        REFERENCES companies(id)
        ON DELETE CASCADE
);

CREATE INDEX idx_ats_fingerprints_company_id
    ON ats_fingerprints(company_id);

CREATE INDEX idx_ats_fingerprints_run_step_id
    ON ats_fingerprints(run_step_id);

CREATE INDEX idx_ats_fingerprints_provider_family
    ON ats_fingerprints(provider_family);

CREATE INDEX idx_ats_fingerprints_status
    ON ats_fingerprints(fingerprint_status);

CREATE INDEX idx_ats_fingerprints_scanned_at
    ON ats_fingerprints(scanned_at);
