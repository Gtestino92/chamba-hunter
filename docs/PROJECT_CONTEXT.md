# Chamba Hunter — Project Context / Handoff operativo

**Fecha de actualización:** 2026-08-09
**Repositorio:** `Gtestino92/chamba-hunter`
**Rama operativa:** `main`
**Entorno habitual:** Windows + PowerShell + `.venv`

---

## 0. Fuente de verdad y estado actual

Código y GitHub actual son siempre fuente de verdad frente a este documento.

Antes de recomendar o implementar:

1. verificar HEAD real de `main`;
2. verificar `git status --short`;
3. leer este archivo completo;
4. inspeccionar directamente los archivos del vertical a tocar;
5. distinguir:
   - publicado en GitHub;
   - cambio local pendiente;
   - observado en DB/corrida manual;
   - inferido;
   - pendiente de reproducción.

### GitHub publicado

Último `main` confirmado al cerrar este handoff:

```text
034fcf34b92c3cfe6e6a75cb7cff2033815b3921
final and fixes
```

Parent:

```text
0902b45a91eb612c1afc77e785a05f59c32658c7
context
```

Commit funcional anterior:

```text
5f8d0b3bf65fb9799c0811d5eb7d4ec57b3c45b2
tracking
```

`034fcf34...` publicó el slice:

```text
Get on Board geography enrichment
+
source publication recency
+
OPERATIONAL_PRIORITY_V2
+
SHORTLIST_REPORT_V2
```

No hubo migration nueva.

### Sobre este PROJECT_CONTEXT

El commit `034fcf34...` incluyó accidentalmente una compactación grande de este archivo junto con el slice funcional.

La decisión vigente es conservar un **handoff canónico compacto** para operación futura.

El handoff histórico detallado previo a esa compactación sigue recuperable en:

```text
0902b45a91eb612c1afc77e785a05f59c32658c7
docs/PROJECT_CONTEXT.md
```

Usar este archivo como contexto operativo actual.

Consultar `0902b45...` sólo si hace falta reconstruir razonamiento histórico muy detallado de un slice previo.

### Estado local observado

Último operational priority real:

```text
Run 114
OPERATIONAL_PRIORITY_V2
SUCCESS
```

Migration:

```text
012 applied = yes
```

Application tracking observado:

```text
8 rows creadas con status SENT
```

Shortlist:

```text
Focus          11
High Value     68
All Current  1079
History        41
```

Source priority run del XLSX:

```text
114
```

Output local:

```text
output/chamba-shortlist.xlsx
```

`output/` no es source of truth.

---

## 1. Directivas operativas de trabajo

### Git / publicación

- No crear branches, commits, pushes, PRs ni writes a GitHub salvo pedido explícito.
- El usuario hace commit/push manualmente.
- Antes de recomendaciones concretas, verificar HEAD/worktree actuales.
- Trabajar en vertical slices pequeños.
- No modificar reglas estables silenciosamente; cambios materiales requieren nueva versión explícita.
- No ejecutar `refresh_search --apply` sólo como validación: modifica DB y avanza watermark operacional.
- Antes de staging/commit, revisar temporales en la raíz.

### Limpieza antes de commit

Antes de dar comandos de staging/commit:

1. revisar `git status --short`;
2. identificar `.zip` y `.txt` no trackeados en la raíz;
3. borrar los que sean temporales;
4. si alguno debe persistir deliberadamente, agregarlo a `.gitignore`;
5. nunca borrar indiscriminadamente un `.txt` o `.zip` ya trackeado sólo por extensión;
6. confirmar que staging contiene únicamente los archivos intencionales.

La expectativa es:

```text
root temp .zip/.txt
→ deleted before commit
```

o, si realmente deben sobrevivir:

```text
explicitly ignored
```

### Idioma / estilo

- Explicaciones: español.
- Código, comentarios y prompts de agentes: inglés.
- Entorno operativo habitual: Windows + PowerShell.

### Diagnósticos / consultas Python

No pedir crear `.py` temporales para diagnósticos manejables.

Entregar Python inline ejecutable directamente desde PowerShell:

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

- entregar **un ZIP**;
- el ZIP debe contener directamente rutas **repo-relative**;
- no incluir wrapper directory;
- no incluir carpeta auxiliar `files/`;
- no incluir `apply_*.py`;
- no pedir copiar fragmentos manualmente.

Ejemplo correcto:

```text
src/chamba_hunter/...
docs/...
migrations/...
```

Junto con cada ZIP, entregar **un único bloque PowerShell** que:

1. `$ErrorActionPreference = "Stop"`;
2. descomprima sobre la raíz del repo;
3. ejecute validaciones/acciones necesarias;
4. controle `$LASTEXITCODE` cuando aplique;
5. borre el ZIP sólo después de éxito;
6. muestre `git diff --stat`;
7. muestre `git status --short`.

Si el único artefacto es un `.ps1`, empaquetarlo también dentro de un ZIP.

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
- `401/403/429` son señales operativas, no una invitación a evadir.
- Evitar dependencias nuevas salvo necesidad clara.

---

## 2. Objetivo del producto

Chamba Hunter es una herramienta local de inteligencia para búsqueda laboral.

No aplica automáticamente.

No envía emails automáticamente.

Construye y mantiene un corpus amplio para reducirlo de forma auditable hasta obtener oportunidades accionables.

Pipeline vigente:

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

## 4. Search profile actual

Profile:

```text
BACKEND_SOFTWARE_V1
```

Target profesional aproximado:

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

Orden conceptual:

```text
geography
→ occupation/backend
→ skills
→ seniority
→ MATCHING_V1
→ JOB_CONTENT_V1
→ OPERATIONAL_PRIORITY_V2
```

---

## 5. Versiones vigentes

Publicadas:

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
```

`ARGENTINA_V1` y `MATCHING_V1` no fueron modificadas para geo/recency V2.

No mezclar source recency dentro de `MATCHING_V1`.

---

## 6. Schema / migrations

Migraciones publicadas:

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

No hubo migration para geo/recency V2.

Tablas/vistas relevantes:

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
job_candidates            # view
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

## 7. Fuentes

### Broad

```text
HIMALAYAS
GETONBOARD
```

La adquisición broad es deliberadamente amplia.

No filtrar Argentina/backend dentro de los adapters.

### ATS ingestion

Activos:

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

`Bumeran Selecta` y `Jobint` entran vía Hiring Room.

---

## 8. Canonicalization

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

---

## 9. Argentina eligibility V1

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

`title` sólo funciona como fallback geográfico fuerte.

`description` no decide geography.

Remote sin scope:

```text
UNKNOWN / REMOTE_SCOPE_UNKNOWN
```

No forzar `UNKNOWN = 0` globalmente.

El cambio Get on Board V2 mejora `location_text`; no cambia la semántica de `ARGENTINA_V1`.

---

## 10. Occupation / backend V1

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

Sólo `SOFTWARE_ENGINEERING` usa backend relevance distinta de `NOT_APPLICABLE`.

No mezclar:

```text
skills
seniority
matching
recency
```

dentro de esta clasificación.

---

## 11. Skills V1

Una skill row significa únicamente:

```text
explicit skill mention in title and/or description
```

No significa:

```text
required
preferred
hard requirement
candidate must know it
```

Relaciones de transferibilidad pertenecen a matching, no a `SKILLS_V1`.

Ejemplos de canonical aliases:

```text
postgres / postgresql → POSTGRESQL
k8s / kubernetes      → KUBERNETES
node.js / nodejs      → NODEJS
```

No inferir:

```text
JAVA       → SPRING
AWS        → EC2
AWS        → S3
JAVASCRIPT → NODEJS
KUBERNETES → OPENSHIFT
```

---

## 12. Seniority V1

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

Leadership dimension separada:

```text
NONE
UNKNOWN
MANAGER
DIRECTOR
HEAD
VP
C_LEVEL
```

No inferir automáticamente seniority desde años de experiencia.

Títulos con varios niveles explícitos pueden quedar `UNKNOWN`.

Ejemplos:

```text
Senior/Staff/Principal Engineer
Junior / Semi Senior Developers
Semi Senior / Senior
JR/SSR
SSR/SR
```

No cambiar semántica de `SENIORITY_V1` sin versionar.

---

## 13. Professional matching V1

Rule version:

```text
MATCHING_V1
```

Profile:

```text
BACKEND_SOFTWARE_V1
```

Score máximo:

```text
100
```

Componentes:

```text
role / backend fit      max 45
skills / transfer      max 30
seniority fit           max 15
leadership fit          max 10
technology penalty      min -5
```

Thresholds:

```text
VERY_HIGH >= 80
HIGH      >= 65
MEDIUM    >= 45
LOW        < 45
```

No participan:

```text
first_seen_at
published_at
source recency
application channel
manual application status
```

### Role fit

Base principal:

```text
SOFTWARE_ENGINEERING + BACKEND      45
SOFTWARE_ENGINEERING + FULL_STACK   38
SOFTWARE_ENGINEERING + UNKNOWN      25
SOFTWARE_ENGINEERING + NON_BACKEND   8

IT_TECHNICAL                         6
TECH_ADJACENT                        4
occupation UNKNOWN                   3
NON_TECHNICAL                        0
```

Existe boost muy acotado para backend `UNKNOWN` con evidencia core fuerte.

### Transferibilidad

Señales conceptuales:

```text
EXACT
PEER
RELATED
SECONDARY
```

Ejemplos:

```text
AWS              → exact
Azure/GCP        → peer cloud
Spring Boot      → exact
Quarkus/Micronaut→ peer JVM backend
PostgreSQL       → exact
MySQL/SQL Server → peer RDBMS
Node/Nest/TS     → secondary
```

### Alternate stack guard

Stacks alternativos observados:

```text
PYTHON
GO
DOTNET
ELIXIR
RUBY
PHP
RUST
SCALA
```

Si el stack alternativo está explícito en title y no hay core compatible explícito:

```text
technology penalty = -5
score ceiling = 64
```

No es hard rejection.

### Seniority fit

Base:

```text
MID        15
UNKNOWN    12
SENIOR     10
JUNIOR      8
ENTRY       5
LEAD        5
STAFF       4
PRINCIPAL   2
INTERN      1
```

Ceilings principales:

```text
JUNIOR      64
STAFF       64
LEAD        64
PRINCIPAL   60
ENTRY       55
INTERN      45
```

Architect title:

```text
ceiling 64
```

Leadership:

```text
MANAGER    ceiling 60
DIRECTOR   ceiling 55
HEAD       ceiling 50
VP         ceiling 45
C_LEVEL    ceiling 45
```

Educational-role title mismatch guard:

```text
Tutor
Instructor
Teacher
Professor
Docente
Trainer
→ ceiling 40
```

No cambiar estos thresholds silenciosamente.

### Último refresh

Run:

```text
113
```

Scope:

```text
1079
ATS   892
LEAD  187
```

Levels:

```text
VERY_HIGH   11
HIGH        57
MEDIUM     129
LOW        882
```

---

## 14. JOB_CONTENT_V1

Persiste:

```text
content_hash
content_hash_version
last_changed_at
```

en:

```text
jobs
job_leads
```

Material hash:

```text
title
description
location_text
workplace_type
employment_type
job_url
apply_url
published_at
expires_at   # leads only
```

No incluye:

```text
last_seen_at
is_active
raw_payload_json
```

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

`jobs_updated` y `last_seen_at` no prueban cambio material.

---

## 15. Get on Board geography enrichment

### Defecto corregido

La API broad entregaba:

```text
remote
remote_modality
countries
remote_zone
location resources
```

pero la normalización anterior perdía `remote_modality`.

Resultado previo frecuente:

```text
remote_local
→ location_text = Remote
→ ARGENTINA_V1 = UNKNOWN / REMOTE_SCOPE_UNKNOWN
```

aunque la página pública exigiera residir en otro país.

### Implementación publicada

Archivo principal:

```text
src/chamba_hunter/sources/getonboard_jobs.py
```

Broad normalization:

```text
src/chamba_hunter/services/broad_job_acquisition_service.py
```

Semántica:

```text
fully_remote
→ location_text = Worldwide

remote_local
→ extraer residencia explícita de página pública
```

Ejemplo:

```text
Position is 100% remote, but candidates must reside in Chile.
→ location_text = Chile
```

Enrichment:

```text
raw_payload_json["_chamba_source_enrichment"]
```

Campos:

```text
location_text
published_date
remote_policy_text
source
```

### Guardas

```text
MAX_DETAIL_FETCHES = 250
```

- request normal `httpx`;
- sin evasión;
- `429` detiene detail enrichment;
- `401/403` no se evaden;
- redirect final limitado a familia Get on Board.

### Publication date

Aceptar sólo evidencia segura:

- metadata explícita de publication; o
- fecha visible antes del `<h1>` principal.

No tomar cualquier fecha de la description.

Caso real validado:

```text
LEAD 1005
2BRAINS
Software Engineer Back-end (Senior)

remote_modality: remote_local
location: Chile
published_date: 2026-02-23
policy:
Position is 100% remote, but candidates must reside in Chile.
```

---

## 16. Resultado geográfico post-V2

Run:

```text
109
ARGENTINA_V1
```

Global:

```text
Total        4664
Eligible      962
Ineligible   3585
Unknown       117
```

Reasons:

```text
ELIGIBLE
  ARGENTINA_LOCATION        617
  REMOTE_GLOBAL             183
  REMOTE_LATAM              154
  REMOTE_LATAM_TITLE          8

INELIGIBLE
  FOREIGN_LOCATION          645
  FOREIGN_ONSITE_HYBRID     371
  FOREIGN_REGION_SCOPE      203
  REMOTE_FOREIGN_LOCATION  2366

UNKNOWN
  LOCATION_UNRECOGNIZED       1
  NO_LOCATION                 1
  REMOTE_SCOPE_UNKNOWN      115
```

### Get on Board

Current:

```text
336
```

Eligibility:

```text
ELIGIBLE
  ARGENTINA_LOCATION          22
  REMOTE_GLOBAL               85
  REMOTE_LATAM                24

INELIGIBLE
  FOREIGN_LOCATION           164
  REMOTE_FOREIGN_LOCATION     41

UNKNOWN                        0
```

Get on Board `MEDIUM+`:

```text
86 total

ARGENTINA_LOCATION   18
REMOTE_GLOBAL        56
REMOTE_LATAM         12

UNKNOWN               0
```

Esto corrige el defecto original de geography Get on Board.

### 2BRAINS acceptance

```text
LEAD 1003
Software Engineer Back-end (Senior)
location: Worldwide
eligibility: ELIGIBLE / REMOTE_GLOBAL
professional: HIGH 76.0
published: 2026-02-24
source recency: OLD

LEAD 1004
Software Engineer Back-end (Semi Senior)
location: Chile
eligibility: INELIGIBLE / REMOTE_FOREIGN_LOCATION
professional snapshot: VERY_HIGH 81.0
operational: OUT_OF_SCOPE

LEAD 1005
Software Engineer Back-end (Senior)
location: Chile
eligibility: INELIGIBLE / REMOTE_FOREIGN_LOCATION
professional snapshot: HIGH 76.0
operational: OUT_OF_SCOPE
```

---

## 17. Source recency

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

Operational rank:

```text
VERY_RECENT > RECENT > AGING > UNKNOWN > OLD
```

Evidence precedence:

```text
1. published_at
2. Get on Board published_date
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

### Hiring Room relative

No fabricar fecha exacta.

Examples:

```text
Hace 1 mes
→ 28-31
→ AGING

Hace 2 meses
→ 56-62
→ AGING

Hace 3 meses
→ 84-93
→ OLD
```

Conservative rule:

```text
range is OLD only when min_age_days > 60
```

Por eso:

```text
Hace 2 meses
!= definitely OLD
```

`UNKNOWN` es neutral, no reciente.

---

## 18. OPERATIONAL_PRIORITY_V2

Rule:

```text
OPERATIONAL_PRIORITY_V2
```

No migration nueva.

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

`NEW`:

```text
first_seen_at > previous watermark
```

`UPDATED`:

```text
last_changed_at > previous watermark
```

o reentrada desde estado no accionable.

### Orden V2

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

Recency ordena dentro del mismo professional match level.

No modifica `MATCHING_V1`.

### Run 114

```text
Candidates persisted   1120
Watermark               2026-08-08T23:49:46.330238+00:00
Created                    0
Updated                 1120
```

States:

```text
NEW              0
UPDATED        127
KNOWN          952
INACTIVE         0
SUPERSEDED       0
OUT_OF_SCOPE    41
```

By match:

```text
VERY_HIGH
  UPDATED       5
  KNOWN         6
  OUT_OF_SCOPE  3

HIGH
  UPDATED      30
  KNOWN        27
  OUT_OF_SCOPE 11

MEDIUM
  UPDATED      48
  KNOWN        81
  OUT_OF_SCOPE 16

LOW
  UPDATED      44
  KNOWN       838
  OUT_OF_SCOPE 11
```

Channels:

```text
DIRECT_APPLY_URL 606
JOB_URL          514
```

### Recency distribution

All priority rows:

```text
UNKNOWN       541
AGING         179
OLD           173
RECENT        117
VERY_RECENT   110
```

Actionable:

```text
UNKNOWN       500
AGING         179
OLD           173
RECENT        117
VERY_RECENT   110
```

High Value:

```text
OLD          27
UNKNOWN      20
AGING        10
RECENT        6
VERY_RECENT   5
```

`NEW/UPDATED + VERY_HIGH/HIGH`:

```text
OLD          24
RECENT        5
AGING         5
VERY_RECENT   1
```

Interpretation:

```text
Chamba discovery age
!=
source publication age
```

24 de 35 oportunidades high-value `NEW/UPDATED` tenían evidencia `OLD`.

### Historical/out-of-scope note

Una fila retenida como `OUT_OF_SCOPE` puede mostrar source recency `UNKNOWN` si su reconstrucción histórica ya no lleva `raw_payload_json`.

Esto no afecta Focus porque no es actionable.

---

## 19. Credencial Payments

Observado después de Run 114:

```text
ATS 3516
Senior Backend Developer
VERY_HIGH 83.75
KNOWN
HIRINGROOM_RELATIVE = Hace 2 meses
age range 56-62
AGING
```

Otros:

```text
ATS 3514
Desarrollador/a Backend Python
MEDIUM 64
Hace 1 mes
AGING

ATS 3520
Desarrollador/a Python
LOW
Hace 10 meses
OLD
```

No inventar precisión desde Hiring Room relative ages.

---

## 20. SHORTLIST_REPORT_V2

Version:

```text
SHORTLIST_REPORT_V2
```

Default output:

```text
output/chamba-shortlist.xlsx
```

El XLSX es output regenerable.

No es source of truth.

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

### New columns

```text
Source Recency
Source Age (days)
Recency Evidence
```

Examples:

```text
GETONBOARD_PUBLISHED_DATE: 2026-02-24
HIRINGROOM_RELATIVE: Hace 2 meses
```

### Snapshot actual

```text
Focus          11
High Value     68
All Current  1079
History        41
```

Before V2:

```text
Focus          34
High Value     82
All Current  1120
History         0
```

Reduction comes from:

- corrected geography;
- retained `OUT_OF_SCOPE` history;
- `OLD` exclusion from Focus.

---

## 21. Manual application tracking

Migration 012 identity:

```text
record_kind
record_id
```

Supports:

```text
ATS
LEAD
```

Compatibility:

```text
ATS
→ job_id = record_id

LEAD
→ job_id = NULL
```

One current row per job opportunity.

No transition-history table in V1.

Command:

```powershell
python -m chamba_hunter.commands.track_application `
    --record-kind <ATS|LEAD> `
    --record-id <ID> `
    --status <STATUS>
```

Statuses:

```text
PENDING
APPLIED
SENT
INTERVIEW
REJECTED
WITHDRAWN
NO_RESPONSE
```

### Source of truth

```text
DB   = source of truth for tracking
XLSX = review / regenerable output
```

Do not edit `Tracked Status` manually in OpenOffice/Excel expecting persistence.

After tracking:

```powershell
python -m chamba_hunter.commands.export_shortlist
```

### Applications observed

8 opportunities were created with:

```text
status = SENT
```

Rows:

```text
LEAD 828
Pomelo
Software Engineer

LEAD 1004
2BRAINS
Software Engineer Back-end (Semi Senior)

LEAD 168
Improving
Semi Senior Back-end Engineer: Java

ATS 8
Bitso
Software Engineer - Latam or Europe

ATS 3516
Credencial Payments
Senior Backend Developer

ATS 3353
ITSM Consulting
Desarrollador Backend - SSR

LEAD 46
PlainTech Solutions
Back-end Developer Kotlin/Java

ATS 3359
Grupo ST
Desarrollador/a Backend Ssr.
```

Last creation observed:

```text
Application id: 8
```

### SENT vs APPLIED

Current semantics:

```text
SENT
→ applied_at remains empty

APPLIED
→ first transition initializes applied_at
```

Do not automatically convert current rows.

If later deciding:

```text
job applications → APPLIED
outreach/email   → SENT
```

make it an explicit product decision first.

### 2BRAINS 1004

`LEAD 1004` is now `OUT_OF_SCOPE` after geography correction.

Its manual tracking remains valid.

```text
operational eligibility
!=
historical fact that the user applied
```

---

## 22. End-to-end refresh

Command:

```powershell
python -m chamba_hunter.commands.refresh_search
```

Without `--apply`:

```text
PLAN ONLY
```

With:

```powershell
python -m chamba_hunter.commands.refresh_search --apply
```

Steps:

```text
1  acquire_broad_jobs
2  sync_greenhouse_jobs
3  sync_lever_jobs
4  sync_ashby_jobs
5  sync_workable_jobs
6  sync_smartrecruiters_jobs
7  sync_bamboohr_jobs
8  sync_hiringroom_jobs
9  canonicalize_job_leads --apply
10 classify_argentina_eligibility --apply
11 classify_job_occupations --apply
12 classify_job_skills --apply
13 classify_job_seniority --apply
14 match_jobs --apply
15 prioritize_jobs --apply
16 export_shortlist
```

Default:

```text
--discover-broad-ats-limit 0
```

Routine refresh does not run broad ATS discovery unless explicitly requested.

### V2 real refresh

Runs:

```text
100 acquire_broad_jobs
101 sync_greenhouse_jobs
102 sync_lever_jobs
103 sync_ashby_jobs
104 sync_workable_jobs
105 sync_smartrecruiters_jobs
106 sync_bamboohr_jobs
107 sync_hiringroom_jobs
108 canonicalize_job_leads
109 classify_argentina_eligibility
110 classify_job_occupations
111 classify_job_skills
112 classify_job_seniority
113 match_jobs
114 prioritize_jobs
```

Export does not create a run.

SmartRecruiters had a partial failure:

```text
Privia Health
REQUEST_ERROR:
Server disconnected without sending a response.
```

Blend360 succeeded.

Pipeline continued through Run 114.

Do not treat this isolated failure as a geo/recency defect.

---

## 23. Workflow operativo

Routine:

```text
refresh_search --apply
→ open output/chamba-shortlist.xlsx
→ Focus
→ High Value
→ apply manually
→ track_application in DB
→ export_shortlist if tracking must appear immediately
```

Do not modify tracking manually inside XLSX.

`Tracked Status` is visible for review/filtering.

Focus does not automatically exclude already-applied opportunities.

Reason:

```text
operational priority
!=
manual application state
```

---

## 24. Estado del MVP

```text
Chamba Hunter MVP local operativo = COMPLETE
```

V2 fixed defects observed during real usage.

There is no mandatory next engineering vertical.

Possible future lines:

### A. Operational usage / tuning

Continue using:

```text
Focus
High Value
track_application
```

and collect real false-positive/false-negative evidence.

### B. Tracking semantics

Only if real friction appears:

```text
SENT vs APPLIED
applied_at semantics
status transition history
```

### C. ATS discovery coverage

Measure marginal value of discovering ATS for new broad companies.

Do not enable indiscriminately in routine refresh.

### D. Outreach fallback

Only:

```text
public careers/recruiting email
explicit general application URL
```

Never infer personal recruiter emails.

Never auto-send.

### E. Additional search profiles

Only when a real second use case exists.

---

## 25. Qué NO hacer automáticamente

- no UI web por inercia;
- no auto-apply;
- no auto-email;
- no inferir recruiter emails;
- no anti-bot bypass;
- no generic profession framework without a real second profile;
- no threshold changes without evidence;
- no recency inside `MATCHING_V1`;
- no XLSX as source of truth;
- no `refresh_search --apply` as a simple code test;
- no assumption that `NEW` means recently published;
- no assumption that `SENT` fills `applied_at`;
- no project tests unless explicitly requested.

---

## 26. Published geo/recency V2 files

Commit:

```text
034fcf34b92c3cfe6e6a75cb7cff2033815b3921
final and fixes
```

Functional files:

```text
src/chamba_hunter/domain/job_recency.py
src/chamba_hunter/repositories/job_operational_priority_repository.py
src/chamba_hunter/services/broad_job_acquisition_service.py
src/chamba_hunter/services/job_operational_priority_service.py
src/chamba_hunter/services/job_shortlist_report_service.py
src/chamba_hunter/sources/getonboard_jobs.py
```

The same commit also contained the previous compacted `docs/PROJECT_CONTEXT.md`.

This docs-only follow-up exists to make that compact handoff canonical and accurate.

---

## 27. Prompt operativo para nueva conversación

```text
Proyecto: Chamba Hunter
Repo: Gtestino92/chamba-hunter
Base: main

Source of truth:
- verify actual GitHub main HEAD and local worktree first;
- read docs/PROJECT_CONTEXT.md completely;
- code/GitHub current state wins over handoff;
- DB counts are observed state, not permanent contracts.

Published reference at this handoff:
- 034fcf34b92c3cfe6e6a75cb7cff2033815b3921 (`final and fixes`);
- contains published Get on Board geography enrichment;
- contains job_recency.py;
- contains OPERATIONAL_PRIORITY_V2;
- contains SHORTLIST_REPORT_V2;
- no new migration;
- ARGENTINA_V1 and MATCHING_V1 unchanged.

Historical detailed handoff:
- if detailed pre-V2 reasoning is needed, inspect
  docs/PROJECT_CONTEXT.md at
  0902b45a91eb612c1afc77e785a05f59c32658c7.
- current compact context is the canonical operational handoff.

Current observed DB:
- latest operational priority: Run 114 SUCCESS;
- current downstream scope: 1079;
- retained priority rows: 1120;
- UPDATED 127;
- KNOWN 952;
- OUT_OF_SCOPE 41;
- NEW 0.

Shortlist:
- Focus 11;
- High Value 68;
- All Current 1079;
- History 41;
- source run 114.

Get on Board:
- current 336;
- geography UNKNOWN = 0;
- MEDIUM+ = 86;
- Argentina 18;
- Global 56;
- LATAM 12;
- fully_remote → Worldwide;
- remote_local → explicit residency from public page.

Recency:
- <=7 VERY_RECENT;
- <=30 RECENT;
- <=60 AGING;
- >60 OLD;
- UNKNOWN neutral;
- Hiring Room relative uses conservative age ranges;
- Hace 2 meses = 56-62 = AGING;
- Focus excludes only definite OLD;
- High Value retains OLD;
- recency does not modify MATCHING_V1.

2BRAINS acceptance:
- LEAD 1003 Worldwide → ELIGIBLE REMOTE_GLOBAL → HIGH 76 → OLD;
- LEAD 1004 Chile → INELIGIBLE REMOTE_FOREIGN_LOCATION → OUT_OF_SCOPE;
- LEAD 1005 Chile → INELIGIBLE REMOTE_FOREIGN_LOCATION → OUT_OF_SCOPE.

Application tracking:
- DB = source of truth;
- XLSX = regenerable output;
- 8 opportunities recorded as SENT:
  LEAD 828 Pomelo;
  LEAD 1004 2BRAINS;
  LEAD 168 Improving;
  ATS 8 Bitso;
  ATS 3516 Credencial Payments;
  ATS 3353 ITSM Consulting;
  LEAD 46 PlainTech Solutions;
  ATS 3359 Grupo ST.
- SENT currently does not initialize applied_at.
- do not convert to APPLIED without explicit decision.

Delivery directives:
- diagnostic Python inline in PowerShell using @' ... '@ | python -;
- do not ask to create manageable temp .py files;
- implementations in one ZIP with direct repo-relative paths;
- no apply helper, no wrapper/files directory;
- one PowerShell block extracts, validates/actions, removes ZIP after success, shows diff/status;
- package standalone .ps1 in ZIP;
- long output to .txt for upload;
- no project tests unless requested;
- use compileall + diff-check + focused checks;
- user commits/pushes manually;
- no commit/push/PR unless explicitly requested.

Before commit:
- inspect root .zip/.txt;
- delete untracked temporary ones;
- if a root artifact must persist, ignore it explicitly;
- never delete tracked files only by extension;
- verify staging contains only intended files.

No auto-apply.
No auto-email.
No anti-bot evasion.
Never infer personal recruiter emails.
```
