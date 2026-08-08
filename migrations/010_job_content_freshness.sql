-- Shared source-level content freshness.
-- Hashes are initialized by Python as a baseline because SQLite has no
-- built-in SHA-256. last_changed_at is intentionally left NULL for baseline
-- rows so migration time is never fabricated as historical change time.

ALTER TABLE jobs
    ADD COLUMN content_hash TEXT;

ALTER TABLE jobs
    ADD COLUMN content_hash_version TEXT;

ALTER TABLE jobs
    ADD COLUMN last_changed_at TEXT;

CREATE INDEX idx_jobs_last_changed_at
    ON jobs(last_changed_at);

ALTER TABLE job_leads
    ADD COLUMN content_hash TEXT;

ALTER TABLE job_leads
    ADD COLUMN content_hash_version TEXT;

ALTER TABLE job_leads
    ADD COLUMN last_changed_at TEXT;

CREATE INDEX idx_job_leads_last_changed_at
    ON job_leads(last_changed_at);
