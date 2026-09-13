# LATAM ATS Fingerprinting

## Purpose

LATAM ATS fingerprinting measures recruiting-platform evidence for companies that entered through `SourceType.LATAM_ENTERPRISE`. It answers which unsupported ATS family should be implemented next.

This command performs live HTTP requests but does not sync jobs, does not create job leads, and does not update `company_ats`.

## Command

```powershell
python -m chamba_hunter.commands.fingerprint_latam_enterprise_ats
python -m chamba_hunter.commands.fingerprint_latam_enterprise_ats --country Argentina
python -m chamba_hunter.commands.fingerprint_latam_enterprise_ats --limit 10
python -m chamba_hunter.commands.fingerprint_latam_enterprise_ats --company-id 123
python -m chamba_hunter.commands.fingerprint_latam_enterprise_ats --output-json output\latam-ats-fingerprints.json
```

The command is intentionally independent from `refresh_search`.

## Scope

Only companies with a `company_sources` record for `LATAM_ENTERPRISE` are selected. The command prefers `careers_url`; if absent, it uses `website_url` only to find a plausible careers link or ATS fingerprint. It follows redirects and keeps request count bounded; it does not crawl job detail pages.

## Recognized Families

Supported ATS fingerprints:

- `GREENHOUSE`
- `LEVER`
- `ASHBY`
- `WORKABLE`
- `SMARTRECRUITERS`
- `BAMBOOHR`
- `HIRINGROOM`
- `TEAMTAILOR`
- `HIBOB`

Unsupported measurement-only fingerprints:

- `SUCCESSFACTORS`
- `WORKDAY`
- `AVATURE`
- `ORACLE_TALEO`
- `GUPY`
- `PANDAPE`

Unsupported fingerprints must not be added to `AtsProvider` or treated as syncable until an ingestion adapter exists.

## Status Meanings

- `DETECTED`: a supported or known unsupported provider family was identified from structural evidence.
- `UNKNOWN`: a careers-like page was fetched but no known provider fingerprint was found.
- `BLOCKED`: HTTP status such as `401`, `403`, or `429` prevented useful inspection.
- `ERROR`: network or non-blocking HTTP failure prevented inspection.
- `NO_CAREERS_URL`: the company has neither `careers_url` nor `website_url`.
- `INSUFFICIENT_EVIDENCE`: a website was fetched but no careers URL or ATS fingerprint was found.

Support status is separate:

- `SUPPORTED`: Chamba already has an ATS integration for this family.
- `UNSUPPORTED`: fingerprint recognized, but no sync integration exists.
- `UNKNOWN`: no provider family was confidently detected.

## Evidence And Confidence

Detection uses provider-specific URL, redirect, iframe, form, script/resource, and structural HTML evidence. Generic visible text is not enough for unsupported-provider detection. Custom career domains can be classified when they link to, redirect to, or load resources from provider-specific infrastructure.

## Persistence

Each scan creates normal run/step/company-scan trace records and an `ats_fingerprints` history row. The fingerprint table preserves observations, including input/final URLs, status, provider family, support status, confidence, evidence, HTTP status, errors, and scan timestamp.

`ats_fingerprints` is measurement state. `company_ats` remains the production synchronization state.

## Interpreting Results

Rank next implementation work by unsupported provider-family counts, country coverage, confidence, and evidence quality. Do not implement a provider based on one ambiguous custom page; rescan or inspect manually when evidence is weak.
