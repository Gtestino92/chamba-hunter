ALTER TABLE job_leads
    ADD COLUMN source_updated_at TEXT;

CREATE INDEX idx_job_leads_source_updated_at
    ON job_leads (
        source_type,
        source_updated_at
    );
