# SAP SuccessFactors ATS Support

## Purpose

SuccessFactors support turns measured LATAM enterprise fingerprints into a real, standalone ATS sync path. It does not implement Workday, Avature, Oracle/Taleo, Gupy, Pandapé, broad acquisition, classification, matching, XLSX export, or `refresh_search` integration.

## Observed Variants

- `CAREER_SITE_BUILDER`: public custom domains such as `https://empleos.gruposancorseguros.com/`, `https://claroempleos-aup.com/`, and `https://empleos.molinos.com.ar/` expose candidate-facing boards with SuccessFactors resources and `/search/` listings.
- `DIRECT_LEGACY`: direct SAP career surfaces such as `https://career4.successfactors.com/career?company=edenor` are recognized and parsed when they expose public static job links.
- Custom public domains remain the preferred `board_url` when they are the candidate-facing board.

## Detection

Normal ATS discovery now recognizes `AtsProvider.SUCCESSFACTORS` from strong structural evidence:

- direct hosts such as `*.sapsf.com` and `career*.successfactors.com`;
- SuccessFactors resource/script hosts such as `rmkcdn.successfactors.com` and `performancemanager*.successfactors.*`;
- Career Site Builder markers such as `/platform/js/j2w/`, `/platform/js/search/`, `job-tile-list`, and `data-careersite-propertyid`.

Generic text-only matches are not sufficient.

## Identity

- `CompanyAts.external_identifier` uses the stable board identity rather than a speculative tenant id.
- Custom-domain boards use host or host/path, for example `claroempleos-aup.com`.
- Direct legacy boards preserve meaningful query identity when available, for example `career4.successfactors.com/career?company=edenor`.
- Job identity uses provider-issued public job/requisition IDs from job URLs or query parameters, not titles.

## Listing And Details

- Career Site Builder listings are discovered from `/search/` forms or links and paginated with observed `startrow` behavior.
- Job tiles are parsed from `job-tile` / `data-url` structures.
- Detail pages are fetched to extract title, description, location, date posted, employment type, and apply URL when available.
- Direct legacy pages are supported when public HTML exposes stable job links; static links alone do not prove the complete job set.
- JS-only or ambiguous direct/legacy surfaces are treated as incomplete rather than guessed.

## Snapshot Safety

SuccessFactors sync only deactivates disappeared jobs when the source produced a complete board snapshot. It does not deactivate jobs when listing fetch, pagination, detail fetch, parsing, blocked, or HTTP/network errors make completeness uncertain. Partial runs may still upsert successfully fetched jobs.

Direct/legacy SuccessFactors pages with static public job links can be ingested, but static links alone do not prove a complete snapshot. Such runs remain partial and never deactivate unseen jobs unless independent completeness evidence exists, such as a trustworthy total count or exhaustively traversed pagination.

An explicit empty board can safely reconcile to zero active jobs only when the parser recognizes a valid empty-board marker.

## Commands

Targeted discovery for one known company:

```powershell
python -m chamba_hunter.commands.discover_known_ats --company-id 3950
```

Sync one detected SuccessFactors company:

```powershell
python -m chamba_hunter.commands.sync_successfactors_jobs --company-id 3950
```

Sync a small batch of active SuccessFactors boards:

```powershell
python -m chamba_hunter.commands.sync_successfactors_jobs --limit 5
```

The SuccessFactors sync command is intentionally standalone and is not wired into `refresh_search`.

## Validation Notes

Initial live validation should focus on the measured SuccessFactors cohort: Grupo Sancor Seguros, Claro Argentina, Edenor, Molinos Río de la Plata, Movistar Argentina, and Globant. Report unsupported or incomplete surfaces explicitly instead of adding brittle special cases.

## Known Limitations

- The parser does not implement private or authenticated SAP APIs.
- JS-only boards without public static listing/detail evidence may be detected but not safely ingestible.
- `ats_fingerprints` remains measurement history; `company_ats` remains production sync state.
