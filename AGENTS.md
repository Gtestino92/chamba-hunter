# Chamba Hunter Agent Guide

## Project Purpose

Chamba Hunter is a local job-search intelligence tool. It discovers companies and job leads, enriches them through known ATS/job sources, classifies and prioritizes opportunities, exports operational XLSX views, and tracks manual applications. It does not auto-apply or auto-send email.

## Current Architecture

- Company acquisition populates `companies` and `company_sources`; CESSI, YC, manual import, broad job sources, and the LATAM enterprise registry all reuse `CompanyImportService`.
- Broad job acquisition creates companies when needed and writes source job leads for Himalayas, GetOnBoard, Jobicy, WeWorkRemotely, and Jooble.
- ATS discovery operates on companies, using known `website_url` or `careers_url` entry points and provider hints from broad job evidence.
- ATS synchronization operates on `company_ats` records and writes canonical first-party `jobs`.
- Canonicalization links broad `job_leads` to canonical `jobs` when identity is sufficiently clear.
- Argentina eligibility, occupation classification, skills classification, seniority classification, professional matching, and operational priority operate on job opportunities.
- XLSX export is an operational/reporting view over SQLite state, not primary persistence.
- Applications track manual application/outreach state against companies and opportunities.

## Source Of Truth

SQLite under `data/` is the source of truth. XLSX files under `output/` are generated operational/export views and should not be treated as primary persistence.

## Company Ingestion

- Use `CompanyImportService` with `CompanySeedInput`; do not bypass it with raw SQL unless there is a clear reason.
- `CompanySource` records preserve source provenance using `SourceType`, `external_id`, `source_url`, raw name, and metadata.
- Source types are persisted as text in SQLite; adding a new enum value does not require a migration unless schema constraints are introduced.
- Deduplication order is source identity, domain, unique normalized name without a seed domain, then unique normalized name for a domainless existing company.
- Repeated ingestion must be idempotent and must not create duplicate companies or duplicate source records.

## Job Acquisition Sources

Implemented broad sources:

- `HIMALAYAS`
- `GETONBOARD`
- `JOBICY`
- `WEWORKREMOTELY`
- `JOOBLE`

## ATS Support

Implemented ATS providers:

- `GREENHOUSE`
- `LEVER`
- `ASHBY`
- `WORKABLE`
- `SMARTRECRUITERS`
- `BAMBOOHR`
- `HIRINGROOM`
- `TEAMTAILOR`
- `HIBOB`

Planned coverage work, not implemented:

- SAP SuccessFactors
- Workday
- Avature
- Other LATAM enterprise ATS providers based on measured coverage

## Important Commands

```powershell
python -m chamba_hunter.commands.refresh_search
python -m chamba_hunter.commands.refresh_search --apply
python -m chamba_hunter.commands.acquire_latam_enterprise_companies
python -m chamba_hunter.commands.acquire_latam_enterprise_companies --apply
python -m chamba_hunter.commands.acquire_latam_enterprise_companies --country Argentina --limit 10
```

The LATAM enterprise command is intentionally isolated and is not part of `refresh_search`.

## Performance And Workflow

New acquisition features should initially be executable independently. Avoid automatically adding expensive or exploratory ingestion to the daily full refresh until its cost and value have been measured.

## Development Conventions

- Keep source/provider parsing isolated in `sources/`; keep business workflow in `services/`; keep CLI wiring in `commands/`.
- Maintain idempotency for ingestion and source tracking.
- Avoid destructive full-snapshot reconciliation unless acquisition was complete and successful.
- Add focused tests for source/provider integrations.
- Do not implement new ATS providers, scraping, classification, matching, or export changes inside company-only acquisition slices.

## Current LATAM Expansion Roadmap

- Slice 1 — Argentina/LATAM enterprise company universe.
- Slice 2 — measure ATS fingerprints / unknown providers.
- Slice 3 — SAP SuccessFactors support.
- Slice 4 — Workday / Avature based on measured coverage.
- Slice 5 — decide whether/how regional acquisition enters routine refresh.

See `docs/latam-enterprise-acquisition.md` for the curated registry workflow.
