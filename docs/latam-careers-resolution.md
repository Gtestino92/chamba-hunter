# LATAM careers-site resolution

LATAM enterprise coverage now follows a measured bootstrap sequence:

```text
LATAM company universe
    ↓
careers-site resolution
    ↓
ATS fingerprinting
    ↓
provider implementation decision
```

The resolver is a standalone command for companies imported through
`SourceType.LATAM_ENTERPRISE`. It is intentionally separate from
`refresh_search` while cost, stability, and false-positive rate are measured.

```powershell
python -m chamba_hunter.commands.resolve_latam_enterprise_careers
python -m chamba_hunter.commands.resolve_latam_enterprise_careers --apply
python -m chamba_hunter.commands.resolve_latam_enterprise_careers --country Argentina --limit 10
python -m chamba_hunter.commands.resolve_latam_enterprise_careers --company-id 3950
```

By default the command selects LATAM enterprise companies where
`careers_url IS NULL` and `website_url IS NOT NULL`. It reuses the same cohort
selection helper as LATAM ATS fingerprinting, then filters to the unresolved
careers-url slice. Existing `careers_url` values are not overwritten.

Resolution is bounded and layered:

1. Existing homepage careers-link discovery.
2. Homepage anchors/resources/raw URLs already referenced by the official site.
3. A small fixed set of first-party common paths.
4. Public `robots.txt` and sitemap evidence with explicit document, URL, and
   depth limits.
5. First-party careers subdomains are supported by the service but disabled by
   default until they prove useful enough to justify the extra network cost.

HTTP `200` alone is never enough. Candidate pages must show careers/jobs
evidence through URL terms, page title/body/header terms, job-listing or
application UI markers, structured/fingerprint evidence, or known recruiting
platform redirects/references.

The resolver may use ATS/fingerprint recognition as validation evidence, but it
does not write `company_ats`, does not persist `ats_fingerprints`, does not sync
jobs, and does not implement unsupported providers.

Default bounds are 16 HTTP requests per company, 8 seconds per request, four
sitemap documents, 80 sitemap URLs inspected, one sitemap-index depth, and no
recursive crawling.

After safe review and `--apply`, rerun:

```powershell
python -m chamba_hunter.commands.fingerprint_latam_enterprise_ats --output-json output\latam-ats-fingerprints-after-careers-resolution.json
```

Use the new measured provider-family distribution to choose the next ATS
implementation. Do not document Workday, Avature, Oracle/Taleo, Gupy, or
Pandapé as chosen until the post-resolution measurement supports that decision.
