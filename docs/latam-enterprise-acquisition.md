# LATAM Enterprise Company Acquisition

## Purpose

The LATAM enterprise registry adds high-confidence Argentina/LATAM employers to the existing company universe. It targets companies that may have substantial internal software/backend teams but may not appear reliably in startup-oriented or international job feeds.

This slice only registers companies. It does not discover ATS providers, sync jobs, scrape jobs, classify jobs, match profiles, reprioritize opportunities, export XLSX files, or run the full refresh.

## Registry

Registry file:

```text
data/latam_enterprise_companies.json
```

The registry is version-controlled and is sufficient for normal ingestion. Runtime ingestion should not depend on live website verification.

## Inclusion Criteria

- Official company identity can be verified from an official company or careers domain.
- Company is based in Argentina or broader LATAM.
- Employer plausibly has software, data, infrastructure, security, payments, logistics, ecommerce, or internal platform roles accessible from Argentina/LATAM.
- Precision is more important than maximizing count.

## Exclusion Criteria

- LinkedIn-only evidence.
- Job aggregators, SEO directories, or scraped company databases as authoritative provenance.
- Unverified careers URLs.
- Companies whose official website cannot be confidently identified.

If the official company website is known but the careers page is uncertain, keep `careers_url` as `null` and let later ATS/careers discovery handle it.

## Schema

Each entry supports:

```text
name
country
website_url
careers_url
external_id
source_url
sector
```

- `name`: public company name to import.
- `country`: primary country for this registry entry.
- `website_url`: official company website.
- `careers_url`: official careers entry point, or `null` when uncertain.
- `external_id`: stable deterministic registry identity, usually `<country-code>:<slug>`.
- `source_url`: official provenance URL used to justify the entry.
- `sector`: lightweight metadata for review and future analysis.

Unknown fields are rejected to keep the registry explicit.

## Import Path

The command loads the registry through `load_latam_enterprise_registry`, creates `CompanySeedInput` records with `SourceType.LATAM_ENTERPRISE`, and imports them through `CompanyImportService`.

Deduplication and source recording are therefore shared with other company acquisition flows:

```text
CompanySeedInput
-> CompanyImportService
-> CompanyRepository
-> CompanySourceRepository
```

Dry-run uses `CompanyImportService.preview_seed`, which applies the same matching rules without writing companies or source records.

## Commands

Preview all entries:

```powershell
python -m chamba_hunter.commands.acquire_latam_enterprise_companies
```

Apply all entries:

```powershell
python -m chamba_hunter.commands.acquire_latam_enterprise_companies --apply
```

Preview only Argentina:

```powershell
python -m chamba_hunter.commands.acquire_latam_enterprise_companies --country Argentina
```

Preview a small sample:

```powershell
python -m chamba_hunter.commands.acquire_latam_enterprise_companies --limit 10
```

The command reports registry entries, selected entries, created companies, existing/matched companies, skipped entries, failed entries, and match-method counts when existing companies are found.

## Validation

Focused tests:

```powershell
python -m pytest tests\test_company_import_service.py tests\test_latam_enterprise_company_acquisition.py
```

Broader tests:

```powershell
python -m pytest
```

Quick preview after code changes:

```powershell
python -m chamba_hunter.commands.acquire_latam_enterprise_companies --limit 5
```

## Intentional Non-Goals

This slice intentionally does not add:

- SAP SuccessFactors support.
- Workday support.
- Avature support.
- Oracle Recruiting / Taleo support.
- Gupy or Pandapé support.
- Any new ATS provider.
- ATS fingerprinting beyond existing discovery.
- ATS synchronization.
- Job scraping or job ingestion.
- Classification, matching, prioritization, or XLSX export changes.
- Automatic integration into `refresh_search`.
