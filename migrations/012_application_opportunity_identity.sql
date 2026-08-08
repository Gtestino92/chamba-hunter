-- Generalize manual JOB application tracking so both ATS jobs and
-- broad LEAD opportunities can be tracked without inventing a jobs.id.
--
-- Existing job_id/public_contact_id columns remain for backward compatibility
-- with the original application/outreach model.

ALTER TABLE applications
ADD COLUMN record_kind TEXT
CHECK (
    record_kind IS NULL
    OR record_kind IN ('ATS', 'LEAD')
);

ALTER TABLE applications
ADD COLUMN record_id INTEGER;

-- Existing job-specific rows are ATS-backed by definition.
UPDATE applications
SET
    record_kind = 'ATS',
    record_id = job_id
WHERE application_type = 'JOB'
  AND job_id IS NOT NULL
  AND record_kind IS NULL
  AND record_id IS NULL;

CREATE INDEX idx_applications_record
    ON applications(record_kind, record_id);

-- One current tracking row per concrete job opportunity.
CREATE UNIQUE INDEX uq_applications_job_opportunity
    ON applications(record_kind, record_id)
    WHERE application_type = 'JOB'
      AND record_kind IS NOT NULL
      AND record_id IS NOT NULL;

-- A JOB application must always identify the source opportunity.
CREATE TRIGGER trg_applications_job_identity_insert
BEFORE INSERT ON applications
WHEN NEW.application_type = 'JOB'
 AND (
     NEW.record_kind IS NULL
     OR NEW.record_id IS NULL
 )
BEGIN
    SELECT RAISE(
        ABORT,
        'JOB application requires record_kind and record_id'
    );
END;

CREATE TRIGGER trg_applications_job_identity_update
BEFORE UPDATE OF application_type, record_kind, record_id
ON applications
WHEN NEW.application_type = 'JOB'
 AND (
     NEW.record_kind IS NULL
     OR NEW.record_id IS NULL
 )
BEGIN
    SELECT RAISE(
        ABORT,
        'JOB application requires record_kind and record_id'
    );
END;

-- Preserve legacy job_id compatibility for ATS rows and ensure the
-- polymorphic source exists.
CREATE TRIGGER trg_applications_source_insert
BEFORE INSERT ON applications
WHEN NEW.application_type = 'JOB'
BEGIN
    SELECT CASE
        WHEN NEW.record_kind = 'ATS'
         AND NOT EXISTS (
             SELECT 1
             FROM jobs
             WHERE id = NEW.record_id
         )
        THEN RAISE(
            ABORT,
            'ATS application record_id does not exist'
        )
    END;

    SELECT CASE
        WHEN NEW.record_kind = 'LEAD'
         AND NOT EXISTS (
             SELECT 1
             FROM job_leads
             WHERE id = NEW.record_id
         )
        THEN RAISE(
            ABORT,
            'LEAD application record_id does not exist'
        )
    END;

    SELECT CASE
        WHEN NEW.record_kind = 'ATS'
         AND (
             NEW.job_id IS NULL
             OR NEW.job_id != NEW.record_id
         )
        THEN RAISE(
            ABORT,
            'ATS application job_id must equal record_id'
        )
    END;

    SELECT CASE
        WHEN NEW.record_kind = 'LEAD'
         AND NEW.job_id IS NOT NULL
        THEN RAISE(
            ABORT,
            'LEAD application must not set job_id'
        )
    END;
END;

CREATE TRIGGER trg_applications_source_update
BEFORE UPDATE OF application_type, record_kind, record_id, job_id
ON applications
WHEN NEW.application_type = 'JOB'
BEGIN
    SELECT CASE
        WHEN NEW.record_kind = 'ATS'
         AND NOT EXISTS (
             SELECT 1
             FROM jobs
             WHERE id = NEW.record_id
         )
        THEN RAISE(
            ABORT,
            'ATS application record_id does not exist'
        )
    END;

    SELECT CASE
        WHEN NEW.record_kind = 'LEAD'
         AND NOT EXISTS (
             SELECT 1
             FROM job_leads
             WHERE id = NEW.record_id
         )
        THEN RAISE(
            ABORT,
            'LEAD application record_id does not exist'
        )
    END;

    SELECT CASE
        WHEN NEW.record_kind = 'ATS'
         AND (
             NEW.job_id IS NULL
             OR NEW.job_id != NEW.record_id
         )
        THEN RAISE(
            ABORT,
            'ATS application job_id must equal record_id'
        )
    END;

    SELECT CASE
        WHEN NEW.record_kind = 'LEAD'
         AND NEW.job_id IS NOT NULL
        THEN RAISE(
            ABORT,
            'LEAD application must not set job_id'
        )
    END;
END;
