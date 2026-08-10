# Chamba Hunter — Project Context / Handoff operativo

**Fecha de actualización:** 2026-08-10
**Repositorio:** `Gtestino92/chamba-hunter`
**Rama operativa:** `main`
**Entorno habitual:** Windows + PowerShell + `.venv`

---

## 0. Fuente de verdad y estado actual

Código, GitHub actual y la DB local observada son siempre fuente de verdad frente a este documento.

Antes de recomendar o implementar:

1. verificar HEAD real de `main`;
2. verificar `git status --short`;
3. leer este archivo completo;
4. inspeccionar directamente los archivos del vertical a tocar;
5. reconciliar este handoff contra GitHub;
6. cuando el estado de DB sea relevante, usar una consulta read-only focalizada en vez de asumir conteos históricos;
7. distinguir explícitamente:
   - confirmado por código/GitHub;
   - confirmado por corrida manual/DB;
   - inferido;
   - pendiente de verificar.

### GitHub publicado al cierre de este handoff

```text
c7d82ef37193d3d3367f2e9b072751ddad08e6d5
add Jooble Argentina acquisition
```

Parent:

```text
c716e739c6af1bb21efc676a2bb5ac9170348cb8
add Jobicy and We Work Remotely acquisition
```

Slice OpenOffice anterior:

```text
7618f3238b303575fe828d5dc2b903e39d817873
application for xlsx
```

Contexto compacto previo a estos slices:

```text
ad4af3576c947d2ca12b212862184f798a4f39e8
context
```

Geo/recency V2:

```text
034fcf34b92c3cfe6e6a75cb7cff2033815b3921
final and fixes
```

Simplificación de application tracking:

```text
9760d76eceb755ce58ebc4bcdec56470bb3ef61c
simplify application tracking
```

Si `main` avanzó después de este documento, verificar el HEAD real y usar código/GitHub actual.

### Contexto histórico

El handoff histórico detallado pre-V2 sigue recuperable en:

```text
0902b45a91eb612c1afc77e785a05f59c32658c7
docs/PROJECT_CONTEXT.md
```

Usar este archivo como contexto operativo actual. Consultar el histórico sólo si hace falta reconstruir razonamiento detallado de slices viejos.

### Último estado operativo observado

Último operational priority observado después de incorporar Jooble:

```text
Run 131
OPERATIONAL_PRIORITY_V2
```

Último XLSX exportado observado:

```text
Report version:  SHORTLIST_REPORT_V2
OpenOffice:      OPENOFFICE_ACTIONS_V1
Priority run:    131

Focus:           121
High Value:      198
All Current:     1447
History:         41
```

Estos números son una foto de DB/corrida manual, no contratos permanentes.

Output local normal:

```text
output/chamba-shortlist.xlsx
```

`output/` no es source of truth.

---

## 1. Directivas operativas de trabajo

### Git / publicación

- No crear branches, commits, pushes, PRs ni writes a GitHub salvo pedido explícito.
- El usuario normalmente hace commit/push manualmente.
- Antes de recomendaciones concretas, verificar HEAD y archivos actuales.
- Trabajar en vertical slices pequeños, mecánicos y controlados.
- No modificar reglas estables silenciosamente; cambios materiales requieren versión explícita o evidencia suficiente.
- No ejecutar `refresh_search --apply` como simple validación de código: modifica DB y avanza watermark operacional.
- Antes de staging/commit, revisar temporales en la raíz.

### Limpieza antes de commit

Antes de dar comandos de staging/commit:

1. revisar `git status --short`;
2. identificar `.zip` y `.txt` no trackeados en raíz;
3. borrar sólo temporales no trackeados;
4. si un artefacto debe persistir, ignorarlo explícitamente cuando corresponda;
5. nunca borrar indiscriminadamente archivos trackeados por extensión;
6. confirmar que staging contiene únicamente los archivos intencionales.

### Idioma / estilo

- Explicaciones: español.
- Código, comentarios de código y prompts para agentes: inglés.
- Entorno operativo habitual: Windows + PowerShell.

### Diagnósticos / consultas Python

No pedir `.py` temporales para diagnósticos manejables.

Preferir:

```powershell
@'
# python
'@ | python -
```

Para output largo:

```text
→ escribir directamente a .txt
→ usuario sube el .txt
```

### Implementaciones / archivos

Cuando se entregue una implementación:

- entregar un único ZIP;
- rutas directamente repo-relative;
- sin wrapper directory;
- sin carpeta auxiliar `files/`;
- sin `apply_*.py`;
- no pedir copiar fragmentos manualmente.

Ejemplo:

```text
src/chamba_hunter/...
docs/...
migrations/...
```

Junto con el ZIP, entregar un único bloque PowerShell que:

1. use `$ErrorActionPreference = "Stop"`;
2. verifique branch/HEAD y precondiciones relevantes;
3. descomprima sobre raíz del repo;
4. ejecute sólo validaciones focalizadas;
5. controle `$LASTEXITCODE`;
6. borre el ZIP sólo después de éxito;
7. muestre `git diff --stat`;
8. muestre `git status --short`.

Si el único artefacto fuera un `.ps1`, empaquetarlo también en ZIP.

### Validación

No agregar ni ejecutar project tests salvo pedido explícito.

Validaciones baratas estándar:

```powershell
python -m compileall -q src
git diff --check
```

más checks funcionales/manuales focalizados.

### Red / scraping

- No bypass anti-bot.
- No fake browser / evasión.
- No proxies para sortear protecciones.
- `401/403/429` son señales operativas.
- No scraping agresivo.
- `httpx` es la librería HTTP normal cuando aplica.
- Evitar dependencias nuevas salvo necesidad clara.

### Scope de producto

- No UI/web API por inercia.
- No auto-apply.
- No auto-email.
- Nunca inferir emails personales de recruiters.
- Outreach futuro sólo con evidencia pública explícita.

---

## 2. Objetivo del producto

Chamba Hunter es una herramienta local de inteligencia para búsqueda laboral.

No aplica automáticamente ni envía emails automáticamente.

Pipeline conceptual vigente:

```text
wide-net job sources
→ broad job leads
→ companies / public identity
→ optional careers / ATS discovery
→ ATS ingestion
→ canonicalization
→ Argentina eligibility
→ occupation / backend
→ skills
→ seniority
→ professional matching
→ content freshness
→ operational priority + source recency
→ shortlist XLSX
→ manual application tracking
→ repeatable refresh
```

Principio central:

```text
job understanding
!=
search-profile matching
!=
operational priority
!=
manual application state
```

No mezclar estas capas.

---

## 3. Stack

- Python 3.12.x.
- `.venv`.
- package `chamba_hunter`.
- SQLite local.
- `sqlite3`, sin SQLAlchemy.
- Pydantic v2 en boundaries externos.
- dataclasses en domain/tracing.
- `httpx`.
- `openpyxl`.
- migraciones SQL inmutables.
- services para reglas de negocio.
- commands para workflows manuales.
- tracing con `runs`, `run_steps`, `ats_syncs`.
- sin UI/web API.
- sin auto-apply.

---

## 4. Search profile y versiones vigentes

Profile:

```text
BACKEND_SOFTWARE_V1
```

Target aproximado:

```text
Backend Software Engineer
Java / Kotlin
Spring Boot
REST APIs
Distributed Systems
batch / schedulers
retries
idempotency
distributed locks
resilience
PostgreSQL / Oracle / MongoDB
Flyway / JPA
AWS EC2 / RDS / S3 / SSM
Docker / Kubernetes / OpenShift
GitHub Actions / GitLab CI
TypeScript / Node.js / NestJS como stack secundario
Android / Compose secundario
English C1
seniority objetivo: semisenior / mid-level
```

Versiones publicadas relevantes:

```text
BACKEND_SOFTWARE_V1
ARGENTINA_V1
OCCUPATION_V1
SKILLS_V1
SENIORITY_V1
MATCHING_V1
JOB_CONTENT_V1
OPERATIONAL_PRIORITY_V2
SHORTLIST_REPORT_V2
OPENOFFICE_ACTIONS_V1
```

No mezclar source recency dentro de `MATCHING_V1`.

---

## 5. Schema / migrations

Migraciones publicadas conocidas:

```text
001_initial_schema.sql
002_company_classifications.sql
003_broad_job_acquisition.sql
004_job_lead_canonicalization.sql
005_job_eligibility_classifications.sql
006_job_occupation_classifications.sql
007_job_skill_classifications.sql
008_job_seniority_classifications.sql
009_job_professional_matches.sql
010_job_content_freshness.sql
011_job_operational_priorities.sql
012_application_opportunity_identity.sql
```

No hubo migration para:

```text
geo/recency V2
batch application tracking
OpenOffice actions
A1 Jobicy/WWR
A2 Jooble
```

Tablas/vistas centrales:

```text
companies
company_sources
company_scans
ats_detections
company_ats
public_contacts
jobs
job_leads
job_ats_hints
job_candidates
job_eligibility_classifications
job_occupation_classifications
job_skill_classifications
job_seniority_classifications
search_profiles
job_professional_matches
job_operational_priorities
applications
runs
run_steps
ats_syncs
```

---

## 6. Fuentes actuales

### Broad

Código publicado al cierre incluye:

```text
HIMALAYAS
GETONBOARD
JOBICY
WEWORKREMOTELY
JOOBLE
```

La adquisición broad es deliberadamente amplia.

No filtrar Argentina/backend dentro de adapters sólo para reducir volumen; esas decisiones pertenecen al downstream.

La ausencia de una vacante en un snapshot broad limitado no prueba cierre y no debe desactivar automáticamente leads por ausencia.

### ATS ingestion actual

Providers con sync implementado:

```text
GREENHOUSE
LEVER
ASHBY
WORKABLE
SMARTRECRUITERS
BAMBOOHR
HIRINGROOM
```

`CUSTOM` existe como provider de detection, no como sync genérico equivalente.

Hiring Room es ATS, no broad.

Bumeran/ZonaJobs directos no se fuerzan con bypass.

### Candidate nuevo de Parte B

```text
RECRUITEE
```

Al cierre de este handoff no está implementado como `AtsProvider` ni como sync adapter.

No implementarlo por intuición: primero medir cobertura/valor marginal.

---

## 7. Broad acquisition previa — Himalayas / Get on Board

### Himalayas

Decisiones estables:

- `applicationLink` es página del job en Himalayas, no apply URL externo;
- guardar como `job_url`;
- `apply_url = None`;
- un incidente upstream con `companyName = "name"` fue reparado localmente;
- el código evita volver a fusionar esas identidades usando slug seguro;
- HTML directo de company profiles dio 403; no bypass;
- enrichment de websites usa el MCP público de Himalayas cuando corresponde.

No reintroducir one-shot repair/backfill utilities salvo necesidad explícita.

### Get on Board geography V2

La normalización preserva mejor la semántica de remote scope:

```text
fully_remote
→ location_text = Worldwide

remote_local
→ residencia explícita recuperada desde evidencia pública
```

Publication date sólo con evidencia segura.

No tomar cualquier fecha de description.

---

## 8. A1 — Jobicy + We Work Remotely

Estado:

```text
COMPLETE / PUBLISHED
```

Commit:

```text
c716e739c6af1bb21efc676a2bb5ac9170348cb8
add Jobicy and We Work Remotely acquisition
```

### Jobicy

API pública, sin key.

Configuración implementada:

```text
industry = engineering
geo = latam
max jobs default = 100
```

Primera adquisición observada:

```text
66 created
```

Downstream observado:

```text
ELIGIBLE     60
UNKNOWN       0
INELIGIBLE    6

VERY_HIGH     0
HIGH          3
MEDIUM       20
LOW          37
NO_MATCH      6
```

### We Work Remotely

RSS público:

```text
Programming
DevOps / Sysadmin
```

No detail-page scraping.

Dedupe entre feeds.

Primera adquisición observada:

```text
76 created
```

Downstream observado:

```text
ELIGIBLE     66
UNKNOWN       7
INELIGIBLE    3

VERY_HIGH      1
HIGH           5
MEDIUM         8
LOW           59
NO_MATCH       3
```

### A1 combinado

```text
142 acquired
126 eligible
7 unknown
9 ineligible

1 VERY_HIGH
8 HIGH
28 MEDIUM
96 LOW
9 NO_MATCH
```

High Value inicial observado:

```text
9
```

No modificar A1 salvo evidencia nueva.

---

## 9. A2 — Jooble Argentina

Estado:

```text
COMPLETE / PUBLISHED
```

Commit:

```text
c7d82ef37193d3d3367f2e9b072751ddad08e6d5
add Jooble Argentina acquisition
```

### API / secreto

Usa API oficial de Jooble Argentina.

La key se maneja sólo mediante:

```text
JOOBLE_API_KEY
```

Nunca pedir pegar la key en chat.

No imprimir endpoint completo porque contiene la key.

Portal/API usado:

```text
ar.jooble.org
```

### Query set aprobado

```text
backend
java developer
spring boot
```

Excluidas deliberadamente:

```text
developer
software engineer
kotlin developer
```

`kotlin developer` mostró alto solapamiento con Java y más ruido visible.

Default:

```text
50 results/page
2 pages/query
3 queries
6 requests
```

Dedupe global por Jooble `id`.

### Normalización

```text
id       → external_id
title    → title
snippet  → plain-text description
location → location_text
type     → employment_type
link     → job_url

workplace_type = UNKNOWN
published_at   = None
expires_at     = None
apply_url      = None
```

El campo Jooble `updated` indica última actualización, no publication date.

Decisión estable:

```text
updated stays in raw_payload_json
published_at stays None
```

No fabricar source recency desde `updated`.

### Primera adquisición real

```text
Run id:             123
Requests made:        6
Received unique:    251
Normalized:         247
Skipped:              4
Companies created:   95
Companies existing:  21
Jobs created:        247
Jobs updated:          0
```

Los 4 skipped no fueron diagnosticados individualmente; el porcentaje fue bajo y no bloqueó A2.

### Canonicalization

Dry-run observado después de adquisición:

```text
Total leads: 1394
Resolved:       11
Ambiguous:       3
Unmatched:    1380
```

Los 11 proposed links de Jooble parecían correctos, principalmente HiringRoom y un caso Lever.

Las 3 ambigüedades eran preexistentes, no introducidas por Jooble.

Después de aplicar canonicalization quedaron aproximadamente:

```text
236 Jooble unresolved
235 dentro del downstream current scope observado
```

### Downstream Jooble observado

Active Jooble leads:

```text
247
```

Eligibility:

```text
ELIGIBLE      186
UNKNOWN        49
INELIGIBLE      1
```

Matching:

```text
VERY_HIGH       3
HIGH          118
MEDIUM         78
LOW            36
NO_MATCH       12
```

High Value:

```text
121
```

Sobre los ~235 candidatos efectivos no canonicalizados, High/Very High fue aproximadamente 51.5%.

### Auditoría geográfica Jooble

Entre 186 `ELIGIBLE` unresolved se encontró un solo título con contradicción geográfica explícita:

```text
Senior Java Engineer - remote, within EU
location_text = Buenos Aires
ARGENTINA_V1 = ELIGIBLE / ARGENTINA_LOCATION
```

Decisión:

```text
no modificar ARGENTINA_V1
no agregar regla Jooble especial por 1 caso aislado
```

### Recency Jooble

Los candidatos Jooble quedaron:

```text
source_recency = UNKNOWN
```

Esto es deliberado.

`UNKNOWN` es un estado válido y neutral; no significa reciente.

No mapear `updated` a publication date.

---

## 10. Canonicalization

Cross-source identity:

```text
job_leads.canonical_job_id -> jobs.id
```

Principios V1:

```text
same company
→ normalized exact title
→ optional location disambiguation
→ optional workplace disambiguation
```

No:

```text
fuzzy cross-company linking
destructive merge
```

Broad provenance se preserva.

Jooble mostró valor de canonicalization real contra ATS existentes, por lo que debe seguir ejecutándose después de broad acquisition y ATS sync.

---

## 11. Argentina eligibility V1

Principio:

```text
REMOTE
!=
automatically workable from Argentina
```

Estados:

```text
ELIGIBLE
INELIGIBLE
UNKNOWN
```

Evidence principal:

```text
location_text
```

`workplace_type` es complementario.

`title` funciona sólo como fallback fuerte cuando location no resolvió scope.

`description` no decide geography.

Remote sin scope:

```text
UNKNOWN / REMOTE_SCOPE_UNKNOWN
```

No forzar `UNKNOWN = 0` globalmente.

No cambiar `ARGENTINA_V1` por peculiaridades aisladas de una fuente sin evidencia suficiente.

---

## 12. Occupation / skills / seniority

### OCCUPATION_V1

Taxonomía:

```text
SOFTWARE_ENGINEERING
IT_TECHNICAL
TECH_ADJACENT
NON_TECHNICAL
UNKNOWN
```

Backend relevance:

```text
BACKEND
FULL_STACK
NON_BACKEND
UNKNOWN
NOT_APPLICABLE
```

No mezclar skills/seniority/matching/recency en esta capa.

### SKILLS_V1

Una skill row significa:

```text
explicit skill mention in title and/or description
```

No significa required/preferred/hard requirement.

Transferibilidad pertenece a matching.

### SENIORITY_V1

Seniority:

```text
INTERN
ENTRY
JUNIOR
MID
SENIOR
STAFF
PRINCIPAL
LEAD
UNKNOWN
```

Leadership separada:

```text
NONE
UNKNOWN
MANAGER
DIRECTOR
HEAD
VP
C_LEVEL
```

No cambiar semántica sin versionar.

---

## 13. MATCHING_V1

Profile:

```text
BACKEND_SOFTWARE_V1
```

Score máximo:

```text
100
```

Thresholds:

```text
VERY_HIGH >= 80
HIGH      >= 65
MEDIUM    >= 45
LOW        < 45
```

Componentes:

```text
role / backend fit      max 45
skills / transfer      max 30
seniority fit           max 15
leadership fit          max 10
technology penalty      min -5
```

No participan:

```text
first_seen_at
published_at
source recency
application channel
manual application status
```

No cambiar thresholds por una fuente nueva sin evidencia de falsos positivos/negativos del modelo de matching.

---

## 14. JOB_CONTENT_V1 / content freshness

Persiste:

```text
content_hash
content_hash_version
last_changed_at
```

en `jobs` y `job_leads`.

Material hash incluye contenido material del posting, no `last_seen_at`, `is_active` ni raw payload.

Semántica:

```text
new
→ current hash
→ last_changed_at NULL

same material content
→ preserve last_changed_at

material content changes
→ last_changed_at = seen_at
```

`jobs_updated` o `last_seen_at` no prueban cambio material.

---

## 15. Source recency

Helper:

```text
src/chamba_hunter/domain/job_recency.py
```

Buckets:

```text
VERY_RECENT
RECENT
AGING
UNKNOWN
OLD
```

Rank:

```text
VERY_RECENT > RECENT > AGING > UNKNOWN > OLD
```

Evidence precedence actual:

```text
1. published_at
2. Get on Board published_date enrichment
3. Hiring Room published_relative
4. UNKNOWN
```

Exact age:

```text
<= 7 days    VERY_RECENT
<= 30        RECENT
<= 60        AGING
> 60         OLD
```

Hiring Room relative usa rangos conservadores.

No fabricar fecha exacta.

`UNKNOWN` es neutral, no reciente.

Jooble permanece `UNKNOWN` porque no ofrece publication date confiable en la integración actual.

---

## 16. OPERATIONAL_PRIORITY_V2

Estados:

```text
NEW
UPDATED
KNOWN
INACTIVE
SUPERSEDED
OUT_OF_SCOPE
```

Watermark:

```text
finished_at of previous prioritize_jobs SUCCESS
```

`NEW` depende de `first_seen_at > previous watermark`.

`UPDATED` depende de cambio material/reentrada según reglas vigentes.

Orden conceptual:

```text
1 actionable
2 professional match level
3 source recency
4 operational state
5 professional score
6 application channel
7 first_seen_at
8 deterministic identity
```

Recency no modifica `MATCHING_V1`.

No correr `prioritize_jobs --apply` o full refresh sólo para validar código porque avanza el estado operativo.

### Snapshot más reciente observado

```text
Priority run 131
Focus        121
High Value   198
All Current 1447
History       41
```

No asumir estos conteos en sesiones futuras sin consultar DB si son relevantes.

---

## 17. SHORTLIST_REPORT_V2

Output default:

```text
output/chamba-shortlist.xlsx
```

Sheets:

```text
Overview
Focus
High Value
All Current
History
```

### Focus

```text
NEW or UPDATED
+
VERY_HIGH or HIGH
+
source_recency != OLD
```

Sólo excluye `OLD` demostrado.

`UNKNOWN` permanece viable.

### High Value

```text
all current VERY_HIGH/HIGH
```

No excluye `OLD`.

El XLSX es regenerable y no es source of truth.

---

## 18. OpenOffice actions

Version:

```text
OPENOFFICE_ACTIONS_V1
```

Commit de introducción:

```text
7618f3238b303575fe828d5dc2b903e39d817873
application for xlsx
```

Installer:

```text
openoffice/chamba-openoffice-actions-installer.ods
```

Macro global:

```text
My Macros -> Standard -> ChambaHunterActions
```

El XLSX generado agrega links `APPLY` que invocan `MarkApplied` y delegan el write a Python usando canonical `record_kind` + `record_id`.

La acción persiste `APPLIED` en DB y actualiza visualmente la fila.

No convertir OpenOffice en source of truth.

### Workbook lock

Antes de exportar/regenerar:

```text
cerrar output/chamba-shortlist.xlsx en OpenOffice/Excel
```

Si `openpyxl` falla con:

```text
PermissionError: [Errno 13] Permission denied: output\chamba-shortlist.xlsx
```

no repetir todo el refresh.

Cerrar workbook y ejecutar sólo:

```powershell
python -m chamba_hunter.commands.export_shortlist `
    --output output\chamba-shortlist.xlsx
```

---

## 19. Manual application tracking

DB = source of truth.

XLSX = review/action surface regenerable.

Para una postulación real a job:

```text
APPLIED
```

es el default.

`SENT` queda disponible para outreach/general application futuro, no como default de job applications.

### Single opportunity

Por identity:

```powershell
python -m chamba_hunter.commands.track_application `
    --record-kind <ATS|LEAD> `
    --record-id <ID>
```

También soporta exact company + title cuando resuelve de forma única.

### Batch normal

Input clipboard:

```text
Company<TAB>Title
Company<TAB>Title
...
```

Uso:

```powershell
Get-Clipboard | python -m chamba_hunter.commands.track_applications
```

Semántica:

```text
parse all
→ dedupe repeated company/title
→ resolve every row
→ abort before writes if any resolution is 0 or >1
→ track APPLIED
→ regenerate shortlist by default
```

Dry-run:

```powershell
Get-Clipboard |
    python -m chamba_hunter.commands.track_applications --dry-run
```

No hace falta correr `refresh_search` después de cada postulación.

Tracking y ranking permanecen separados.

---

## 20. Routine refresh actual

Command:

```powershell
python -m chamba_hunter.commands.refresh_search
```

Sin `--apply`:

```text
PLAN ONLY
```

Con ejecución real:

```powershell
python -m chamba_hunter.commands.refresh_search --apply
```

### Broad blocks publicados

El plan actual contiene tres bloques broad antes de canonicalization:

```text
1. acquire_broad_jobs
   - Himalayas
   - Get on Board

2. acquire_public_jobs
   - Jobicy
   - We Work Remotely

3. acquire_jooble_jobs
   - Jooble Argentina
```

Luego, salvo flags de skip:

```text
optional discover_broad_ats
ATS syncs
canonicalize_job_leads --apply
classify_argentina_eligibility --apply
classify_job_occupations --apply
classify_job_skills --apply
classify_job_seniority --apply
match_jobs --apply --top 0
prioritize_jobs --apply --top 0
export_shortlist
```

ATS syncs actuales:

```text
Greenhouse
Lever
Ashby
Workable
SmartRecruiters
BambooHR
HiringRoom
```

### Flags relevantes

Verificar firma actual antes de usar, pero al cierre existen:

```text
--skip-broad
--skip-ats
--skip-export
--discover-broad-ats-limit
--himalayas-max-jobs
--getonboard-max-pages
--jobicy-max-jobs
--wwr-max-jobs
--jooble-max-pages-per-query
```

Jooble default:

```text
--jooble-max-pages-per-query 2
```

Deshabilitar sólo Jooble:

```text
--jooble-max-pages-per-query 0
```

`--skip-broad` debe saltar las cinco broad sources.

Broad ATS discovery sigue deshabilitado por default:

```text
--discover-broad-ats-limit 0
```

### Precondiciones operativas para refresh real

Antes de un refresh real:

1. confirmar que se quiere nueva adquisición/repriorización;
2. cerrar `output/chamba-shortlist.xlsx`;
3. cargar `JOOBLE_API_KEY` en la sesión PowerShell;
4. ejecutar plan-only si se quiere inspeccionar secuencia;
5. recién entonces usar `--apply`.

No usar full refresh como validación de código.

---

## 21. Broad ATS discovery existente

Existe:

```text
src/chamba_hunter/commands/discover_broad_ats.py
```

Usa entry points legítimos:

```text
KNOWN_CAREERS
HOMEPAGE
```

No reintroducir por defecto:

```text
LEAD_APPLY_URL
LEAD_JOB_URL
```

No reescanea automáticamente una company ya escaneada contra su website actual salvo opción explícita.

`401/403/429` no se evaden.

Un bug previo por URLs HTML malformadas fue hardeneado para ignorar targets inválidos en vez de tumbar todo el scan.

Routine refresh no ejecuta broad ATS discovery salvo `--discover-broad-ats-limit > 0`.

---

## 22. Taxonomía de expansión acordada

Candidatos de expansión acordados para esta fase:

```text
1. Jobicy
2. We Work Remotely
3. Jooble
4. Recruitee
```

No agregar otras fuentes por inercia salvo pedido explícito o nueva evidencia que justifique revisar la decisión.

Ejes:

```text
A. nuevas broad sources
B. nuevo ATS
C. mejor explotación de empresas ya conocidas
```

Estado:

```text
A1 Jobicy + WWR   COMPLETE
A2 Jooble         COMPLETE
B  Recruitee      NEXT: RECON / VALUE TEST
C  first-party / outreach fallback  AFTER B
```

---

## 23. Próximo foco — Parte B: Recruitee

Recruitee debe tratarse como **nuevo ATS**, no broad aggregator.

### Regla principal de B

No implementar inmediatamente.

Primero comprobar que aporta suficiente cobertura marginal.

### Discovery inicial

Al arrancar una nueva conversación:

1. verificar HEAD real de `main` y worktree;
2. leer este `PROJECT_CONTEXT.md` completo;
3. confirmar que Recruitee sigue sin provider/adapter actual;
4. inspeccionar:
   - `AtsProvider`;
   - `company_ats` / repositories relevantes;
   - detection actual;
   - uno o dos adapters comparables;
   - sync commands;
   - `refresh_search`;
5. investigar interfaces públicas/oficiales de Recruitee;
6. determinar identidad estable de board/company;
7. medir evidencia real en el universo actual;
8. estimar cuántas companies/boards nuevos aportaría;
9. decidir recién entonces si construir adapter.

### Criterio de salida válido

Si la cobertura marginal es baja:

```text
close B without implementation
```

es una conclusión válida.

No construir un adapter sólo porque técnicamente sea posible.

### Si Recruitee vale la pena

Slice esperado, manteniendo arquitectura existente:

```text
provider enum/detection if needed
source client
ingestion service
sync command
refresh integration
```

No tocar salvo evidencia:

```text
matching
ranking
Argentina rules
skills
seniority
OpenOffice
application tracking
```

No migration salvo necesidad real del schema.

Validar con checks focalizados, no full refresh.

---

## 24. Después de B — Parte C

Objetivo: explotar mejor empresas ya conocidas sin ATS soportado.

Evaluar conservadoramente:

```text
custom first-party careers pages
explicit public recruiting/careers emails
explicit general application forms
```

Sólo evidencia pública explícita.

Nunca:

```text
infer personal recruiter emails
auto-email
auto-submit
anti-bot bypass
```

Para outreach/general application futuro puede usarse `SENT`, separado de job applications `APPLIED`.

---

## 25. Operación recurrente objetivo

Una vez estabilizados A/B/C:

```text
manual refresh
→ revisar Focus / High Value
→ postular manualmente
→ registrar APPLIED
→ repetir
```

No seguir agregando infraestructura si el cuello de botella pasa a ser revisión/postulación humana.

La herramienta debe reducir fricción de búsqueda, no convertirse en un sistema de auto-apply.

---

## 26. Qué NO hacer automáticamente

- no UI web por inercia;
- no auto-apply;
- no auto-email;
- no inferir recruiter emails;
- no anti-bot bypass;
- no generic profession framework sin segundo caso real;
- no threshold changes sin evidencia;
- no recency dentro de `MATCHING_V1`;
- no XLSX como source of truth;
- no `refresh_search --apply` como test;
- no asumir que `NEW` significa recently published;
- no usar `SENT` como default de job application;
- no project tests salvo pedido explícito;
- no nuevas broad sources fuera del set acordado sin pedido/evidencia;
- no Recruitee implementation antes de medir valor marginal.

---

## 27. Método operativo para próximas conversaciones

Trabajar de a un paso importante por vez:

```text
inspección
→ propuesta
→ comando focalizado/read-only
→ usuario pasa output
→ revisión
→ siguiente paso
```

No saltar directamente de discovery a implementación.

No correr full refresh salvo finalidad operacional real.

No alterar capas estables sólo para acomodar una fuente nueva.

En Parte B, empezar por responder:

```text
¿Recruitee aporta suficiente cobertura nueva para justificar un adapter?
```

Sólo después decidir implementación.
