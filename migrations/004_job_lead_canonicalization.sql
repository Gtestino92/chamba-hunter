-- Conservative broad-lead -> canonical ATS job linking.
-- Keep broad records intact and preserve their provenance. If the linked
-- canonical ATS job later becomes inactive, surface the broad lead again.

ALTER TABLE job_leads
    ADD COLUMN canonicalization_method TEXT;

ALTER TABLE job_leads
    ADD COLUMN canonicalized_at TEXT;

DROP VIEW job_candidates;

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

WHERE
    job_leads.canonical_job_id IS NULL
    OR NOT EXISTS (
        SELECT 1
        FROM jobs canonical_job
        WHERE canonical_job.id = job_leads.canonical_job_id
          AND canonical_job.is_active = 1
    );
