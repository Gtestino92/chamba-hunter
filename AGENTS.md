# Chamba Hunter Agent Guide

## Project Purpose

Chamba Hunter is a local job-search intelligence tool. It discovers companies and job leads, enriches them through known ATS/job sources, classifies and prioritizes opportunities, exports operational XLSX views, and tracks manual applications. It does not auto-apply or auto-send email.

## Current Architecture

- Company acquisition populates `companies` and `company_sources`; CESSI, YC, manual import, broad job sources, and the LATAM enterprise registry all reuse `CompanyImportService`.
- Broad job acquisition creates companies when needed and writes source job leads for Himalayas, GetOnBoard, Jobicy, WeWorkRemotely, and Jooble.
- ATS discovery operates on companies, using known `website_url` or `careers_url` entry points and provider hints from broad job evidence.
- LATAM ATS fingerprinting measures recruiting-platform evidence for `LATAM_ENTERPRISE` companies and stores observations in `ats_fingerprints`; it does not register unsupported providers as syncable ATS integrations.
- ATS synchronization operates on `company_ats` records and writes canonical first-party `jobs`.
- SuccessFactors synchronization is implemented as an ATS provider command and participates in routine refresh; validated public Career Site Builder/custom-domain and direct/legacy surfaces use conservative snapshot semantics.
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
- LATAM enterprise dry-run does not create/update acquisition companies or source records, but standard command startup may still apply pending schema migrations.

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
- `SUCCESSFACTORS`

Planned coverage work, not implemented:

- Workday
- Avature
- Other LATAM enterprise ATS providers based on measured coverage

Fingerprint recognition for unsupported providers is measurement only. It does not mean job sync support exists.
SuccessFactors fingerprint recognition now maps to a supported ATS integration, but fingerprinting remains distinct from job synchronization.

## Important Commands

```powershell
python -m chamba_hunter.commands.refresh_search
python -m chamba_hunter.commands.refresh_search --apply
python -m chamba_hunter.commands.acquire_latam_enterprise_companies
python -m chamba_hunter.commands.acquire_latam_enterprise_companies --apply
python -m chamba_hunter.commands.acquire_latam_enterprise_companies --country Argentina --limit 10
python -m chamba_hunter.commands.fingerprint_latam_enterprise_ats
python -m chamba_hunter.commands.fingerprint_latam_enterprise_ats --country Argentina --limit 10
python -m chamba_hunter.commands.resolve_latam_enterprise_careers
python -m chamba_hunter.commands.resolve_latam_enterprise_careers --apply
python -m chamba_hunter.commands.discover_known_ats --company-id 3950
python -m chamba_hunter.commands.sync_successfactors_jobs --company-id 3950
```

The LATAM enterprise ingestion, careers-site resolution, and fingerprinting commands are intentionally isolated and are not part of `refresh_search`; SuccessFactors job sync now runs with the routine ATS sync group.
Without `--apply`, it previews acquisition changes only; pending migrations may still run at startup.

## Performance And Workflow

New acquisition features should initially be executable independently. Avoid automatically adding expensive or exploratory ingestion to the daily full refresh until its cost and value have been measured.

## Live Refresh And Search Safety

- Do not run `refresh_search --apply`, `refresh_search --apply --deep`, broad source acquisition, ATS discovery, or any other live job-search/acquisition command unless the user explicitly confirms that live searching is allowed in that turn.
- Prefer plan-only commands such as `python -m chamba_hunter.commands.refresh_search` and `python -m chamba_hunter.commands.refresh_search --deep` for validation unless live mutation is explicitly approved.
- If a live refresh/search command is accidentally started or interrupted, stop work immediately, verify no process is still running, and report any partial execution that may have occurred.

## Development Conventions

- Keep source/provider parsing isolated in `sources/`; keep business workflow in `services/`; keep CLI wiring in `commands/`.
- Maintain idempotency for ingestion and source tracking.
- Avoid destructive full-snapshot reconciliation unless acquisition was complete and successful.
- SuccessFactors sync must not deactivate disappeared jobs when listing, pagination, detail, blocked, or network states make snapshot completeness uncertain.
- Add focused tests for source/provider integrations.
- Do not implement new ATS providers, scraping, classification, matching, or export changes inside company-only acquisition slices.

## Current LATAM Expansion Roadmap

Slice 1 company ingestion, Slice 2 ATS fingerprinting, and Slice 3 SAP SuccessFactors support are implemented. Use post-resolution measured fingerprint coverage to choose the next provider implementation.

- Slice 1 — Argentina/LATAM enterprise company universe.
- Slice 2 — measure ATS fingerprints / unknown providers.
- Slice 3 — SAP SuccessFactors support.
- Slice 4 ? bounded LATAM careers-site resolution for missing `careers_url`.
- Slice 5 ? next ATS provider implementation based on measured coverage.
- Slice 6 ? decide whether/how regional acquisition or careers resolution enters routine refresh.

See `docs/latam-enterprise-acquisition.md` for the curated registry workflow, `docs/latam-careers-resolution.md` for careers-site resolution, `docs/latam-ats-fingerprinting.md` for measurement workflow, and `docs/successfactors.md` for SuccessFactors sync.
