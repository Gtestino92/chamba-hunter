# Chamba Hunter — Project Context / Handoff operativo

**Fecha de actualización:** 2026-08-09
**Repositorio:** `Gtestino92/chamba-hunter`
**Rama operativa:** `main`
**Entorno habitual:** Windows + PowerShell + `.venv`

---

## 0. Fuente de verdad y estado actual

Código/GitHub actual es siempre fuente de verdad frente a este documento.

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
0902b45a91eb612c1afc77e785a05f59c32658c7
```

El commit publicado anterior que cerró manual application tracking + refresh fue:

```text
5f8d0b3bf65fb9799c0811d5eb7d4ec57b3c45b2
tracking
```

`0902b45...` sólo actualizó contexto; funcionalmente el baseline publicado sigue siendo el pipeline v1 de `5f8d0b3...`.

### Slice local validado pero todavía NO publicado

Existe un slice local ya aplicado y validado:

```text
Get on Board geography enrichment
+
source publication recency
+
OPERATIONAL_PRIORITY_V2
+
SHORTLIST_REPORT_V2
```

Archivos locales esperados antes de publicar:

```text
M  src/chamba_hunter/repositories/job_operational_priority_repository.py
M  src/chamba_hunter/services/broad_job_acquisition_service.py
M  src/chamba_hunter/services/job_operational_priority_service.py
M  src/chamba_hunter/services/job_shortlist_report_service.py
M  src/chamba_hunter/sources/getonboard_jobs.py
?? src/chamba_hunter/domain/job_recency.py
M  docs/PROJECT_CONTEXT.md
```

No asumir que este slice está en GitHub hasta verificar un commit posterior a `0902b45...`.

No hubo migration nueva para este slice.

---

## 1. Directivas operativas de trabajo

### Git / publicación

- No crear branches, commits, pushes, PRs ni writes a GitHub salvo pedido explícito.
- El usuario hace commit/push manualmente.
- Antes de cualquier recomendación concreta, verificar HEAD/worktree actuales.
- Trabajar en vertical slices pequeños.
- No modificar reglas estables silenciosamente; cambios materiales requieren nueva versión explícita.
- No ejecutar `refresh_search --apply` sólo como validación de código: modifica DB y avanza watermark operacional.

### Idioma / estilo

- Explicaciones: español.
- Código, comentarios y prompts de agentes: inglés.
- Entorno operativo habitual: Windows + PowerShell.

### Scripts de diagnóstico / consulta

No pedir al usuario que cree archivos `.py` temporales para diagnósticos manejables.

Entregar Python inline ejecutable directamente desde PowerShell:

```powershell
@'
# python
'@ | python -
```

Usar archivos `.txt` para salida larga que deba subirse.

### Implementaciones / archivos

Cuando se entregue una implementación:

- entregar **un ZIP**;
- el ZIP debe contener directamente rutas **repo-relative**, por ejemplo:

```text
src/chamba_hunter/...
docs/...
migrations/...
```

- no agregar `apply_*.py`;
- no agregar carpetas auxiliares como `files/`;
- no pedir que el usuario copie fragmentos manualmente.

Junto con cada ZIP, entregar **un único bloque PowerShell** que:

1. descomprima sobre la raíz del repo;
2. ejecute las validaciones/acciones necesarias;
3. falle sin ocultar errores;
4. borre el ZIP sólo si lo anterior salió bien;
5. muestre `git diff --stat` y `git status --short` cuando corresponda.

Si el único artefacto fuera un `.ps1`, también empaquetarlo en ZIP.

### Validación

No agregar ni ejecutar project tests salvo pedido explícito.

Validaciones baratas estándar:

```powershell
python -m compileall -q src
git diff --check
```

más validaciones funcionales/manuales focalizadas.

### Red / scraping

- No bypass anti-bot.
- No fake browser / evasión.
- No proxies para sortear protecciones.
- `401/403/429` son señales operativas, no una invitación a evadir.
- Evitar dependencias nuevas salvo necesidad clara.

---

## 2. Objetivo del producto

Chamba Hunter es una herramienta local de inteligencia para búsqueda laboral.

No aplica automáticamente y no envía emails automáticamente.

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
→ operational priority / source recency
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

Perfil:

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
retries / idempotency / distributed locks
resilience
PostgreSQL / Oracle / MongoDB
Flyway / JPA
AWS EC2 / RDS / S3 / SSM
Docker / Kubernetes / OpenShift
GitHub Actions / GitLab CI
TypeScript / Node.js / NestJS como stack secundario
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
→ OPERATIONAL_PRIORITY_V2
```

---

## 5. Versiones vigentes

Estables y publicadas:

```text
BACKEND_SOFTWARE_V1
ARGENTINA_V1
OCCUPATION_V1
SKILLS_V1
SENIORITY_V1
MATCHING_V1
JOB_CONTENT_V1
```

Localmente validadas, pendientes de publicación:

```text
OPERATIONAL_PRIORITY_V2
SHORTLIST_REPORT_V2
```

`ARGENTINA_V1` y `MATCHING_V1` NO fueron modificadas para el slice geo/recency.

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

Migration 012 está aplicada en la DB local.

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

No filtrar Argentina/backend en adapters.

### ATS

Soportados:

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

Hiring Room sigue modelado como ATS, no como broad.

Bumeran/ZonaJobs directos no se fuerzan con bypass; `Bumeran Selecta` y `Jobint` entran vía Hiring Room.

---

## 8. Freshness de contenido

`JOB_CONTENT_V1` persiste en `jobs` y `job_leads`:

```text
content_hash
content_hash_version
last_changed_at
```

Material hash incluye:

```text
title
description
location_text
workplace_type
employment_type
job_url
apply_url
published_at
expires_at   # leads
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
→ hash actual
→ last_changed_at NULL

same material content
→ preserve last_changed_at

material change
→ last_changed_at = seen_at
```

`jobs_updated` de un sync y `last_seen_at` significan re-observación/escritura; no prueban cambio material.

---

## 9. Get on Board geography enrichment — slice local validado

### Defecto que motivó el cambio

La API broad entregaba:

```text
remote
remote_modality
countries / remote_zone / location resources
```

pero la normalización anterior perdía `remote_modality`.

Eso hacía que muchos:

```text
remote_local
```

quedaran normalizados sólo como:

```text
Remote
```

y terminaran:

```text
ARGENTINA_V1
→ UNKNOWN / REMOTE_SCOPE_UNKNOWN
```

aunque la página pública exigiera residir en otro país.

### Implementación local

`getonboard_jobs.py` enriquece jobs remotos usando la página pública.

Reglas:

```text
fully_remote
→ location_text = Worldwide

remote_local
→ extraer residencia explícita de la página
   ej. "candidates must reside in Chile"
   → location_text = Chile
```

También captura fecha pública de publicación cuando hay evidencia segura.

El enrichment se persiste dentro de:

```text
raw_payload_json["_chamba_source_enrichment"]
```

con:

```text
location_text
published_date
remote_policy_text
source
```

No se fabrica `published_at` timestamp desde una fecha de calendario.

### Guardas operativas

- máximo 250 detail fetches por adquisición;
- request normal con `httpx`;
- sin evasión;
- `429` detiene detail enrichment;
- `401/403` se toleran sin bypass;
- redirects deben terminar en dominio Get on Board permitido.

### Extracción de fecha

Se endureció después de review.

Aceptar sólo:

- metadata explícita de publication segura; o
- fecha visible en la región previa al `<h1>` principal.

No buscar indiscriminadamente cualquier fecha de la descripción.

Validación real:

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

## 10. Resultado geográfico observado tras refresh

Refresh real del slice:

```text
Run 100 acquire_broad_jobs
...
Run 109 classify_argentina_eligibility
```

Run 100:

```text
HIMALAYAS
received   500
updated    500

GETONBOARD
received   339
updated    339

TOTAL received   839
created            0
updated          839

active unresolved leads  1005
raw active candidates    4664
```

Run 109 — `ARGENTINA_V1`:

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

### Get on Board específico

Current Get on Board observado:

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

ELIGIBLE
  ARGENTINA_LOCATION   18
  REMOTE_GLOBAL        56
  REMOTE_LATAM         12

UNKNOWN                 0
```

Esto corrige el defecto original: Get on Board ya no deja `remote_local` ambiguo sólo porque el normalizador perdió el scope.

### Casos 2BRAINS de aceptación

```text
LEAD 1003
Software Engineer Back-end (Senior)
location: Worldwide
eligibility: ELIGIBLE / REMOTE_GLOBAL
professional: HIGH 76.0

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

## 11. Occupation / skills / seniority — último refresh

Scope downstream actual:

```text
ARGENTINA ELIGIBLE + UNKNOWN = 1079
```

### Run 110 — OCCUPATION_V1

```text
Total          1079
Software        276
IT technical    142
Tech adjacent    59
Non technical   189
Unknown         413
```

Software backend relevance:

```text
BACKEND       87
FULL_STACK    79
NON_BACKEND   51
UNKNOWN       59
```

### Run 111 — SKILLS_V1

```text
Candidates   1079
With skills   564
No skills     515
Skill rows   3070
```

Software coverage:

```text
269 / 276
97.5%
```

### Run 112 — SENIORITY_V1

```text
UNKNOWN       779
SENIOR        182
MID            36
LEAD           30
JUNIOR         21
ENTRY           9
PRINCIPAL       9
STAFF           9
INTERN          4
```

No cambiar semánticas V1 por estos nuevos conteos; son estado observado.

---

## 12. Professional matching V1 — último refresh

Run:

```text
113
MATCHING_V1
BACKEND_SOFTWARE_V1
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

Score máximo 100:

```text
role/backend fit      45
skills/transfer       30
seniority             15
leadership            10
technology penalty    min -5
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

No cambiar `MATCHING_V1` silenciosamente.

---

## 13. Source recency — V2 local

Archivo nuevo:

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

Rank operacional:

```text
VERY_RECENT > RECENT > AGING > UNKNOWN > OLD
```

### Evidencia

Orden de preferencia:

```text
1. published_at exacto
2. Get on Board exact published_date
3. Hiring Room published_relative
4. UNKNOWN
```

### Edad exacta

```text
0-7 days     VERY_RECENT
8-30         RECENT
31-60        AGING
>60          OLD
```

### Hiring Room relative

No fabricar fecha exacta desde:

```text
Hace N días
Hace N semanas
Hace N meses
```

Se conserva un rango.

Ejemplos:

```text
Hace 1 mes
→ 28-31 days
→ AGING

Hace 2 meses
→ 56-62 days
→ AGING

Hace 3 meses
→ 84-93 days
→ OLD
```

Decisión conservadora:

```text
un rango sólo es OLD si su mínimo ya supera 60 días
```

Por eso `Hace 2 meses` NO se fuerza a `OLD`.

`UNKNOWN` es neutral/intermedio; no se interpreta como nuevo.

---

## 14. Operational priority V2 — local validado

Rule version:

```text
OPERATIONAL_PRIORITY_V2
```

Persiste en la tabla existente:

```text
job_operational_priorities
```

Sin migration nueva.

### Estados

```text
NEW
UPDATED
KNOWN
INACTIVE
SUPERSEDED
OUT_OF_SCOPE
```

Watermark sigue siendo el `finished_at` del último `prioritize_jobs SUCCESS`.

`NEW`:

```text
first_seen_at > previous watermark
```

`UPDATED`:

```text
last_changed_at > previous watermark
```

o reentrada al scope desde un estado no accionable.

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

La recencia ordena **dentro del mismo match level**.

No modifica professional score.

### Run 114

```text
Candidates persisted   1120
Watermark               2026-08-08T23:49:46.330238+00:00
Created                    0
Updated                 1120
```

Estados:

```text
NEW              0
UPDATED        127
KNOWN          952
INACTIVE         0
SUPERSEDED       0
OUT_OF_SCOPE    41
```

Por match:

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

### Recency distribution observada

Todas las priority rows:

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

Esto demuestra el valor de separar:

```text
Chamba discovery state
```

de:

```text
source market age
```

24 de las 35 oportunidades `NEW/UPDATED + VERY_HIGH/HIGH` eran definitivamente `OLD`.

### Nota sobre historical/out-of-scope recency

Una fila retenida como `OUT_OF_SCOPE` puede tener recency `UNKNOWN` si ya no forma parte del current candidate scope y su reconstrucción histórica no lleva `raw_payload_json`.

Ejemplo actual:

```text
LEAD 1004
LEAD 1005
```

Esto no afecta Focus porque ya son no accionables.

---

## 15. Credencial Payments — evidencia de recencia

Observado después de Run 114:

```text
ATS 3516
Senior Backend Developer
VERY_HIGH 83.75
KNOWN
HIRINGROOM_RELATIVE = "Hace 2 meses"
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

El caso que motivó el análisis no prueba una fecha exacta superior a 2 meses; el sistema conserva la evidencia real de Hiring Room y no inventa precisión.

---

## 16. Shortlist report V2 — local validado

Report version:

```text
SHORTLIST_REPORT_V2
```

Default:

```text
output/chamba-shortlist.xlsx
```

El XLSX es **output regenerable y read-only desde el punto de vista del workflow**.

No usar el XLSX como source of truth para tracking.

Hojas:

```text
Overview
Focus
High Value
All Current
History
```

### Focus V2

```text
NEW or UPDATED
+
VERY_HIGH or HIGH
+
source recency != OLD
```

Sólo excluye `OLD` demostrado.

`UNKNOWN` permanece elegible para Focus.

### High Value

```text
all current VERY_HIGH/HIGH
```

No excluye `OLD`.

Esto preserva oportunidades profesionalmente buenas aunque no sean prioridad inmediata.

### Columnas V2 agregadas

```text
Source Recency
Source Age (days)
Recency Evidence
```

La evidence puede mostrar, por ejemplo:

```text
GETONBOARD_PUBLISHED_DATE: 2026-02-24
HIRINGROOM_RELATIVE: Hace 2 meses
```

### Snapshot actual

Source priority run:

```text
114
```

Después de registrar aplicaciones y regenerar:

```text
Focus          11
High Value     68
All Current  1079
History        41
```

Antes de V2:

```text
Focus          34
High Value     82
All Current  1120
History         0
```

La reducción viene de:

- corrección geográfica;
- retención histórica `OUT_OF_SCOPE`;
- exclusión de `OLD` en Focus.

---

## 17. Manual application tracking

Migration 012 generaliza identidad:

```text
record_kind
record_id
```

Soporta:

```text
ATS
LEAD
```

Compatibilidad:

```text
ATS
→ job_id = record_id

LEAD
→ job_id = NULL
```

Un único row actual por job opportunity.

No hay historial por transición en V1.

Command:

```powershell
python -m chamba_hunter.commands.track_application `
    --record-kind <ATS|LEAD> `
    --record-id <ID> `
    --status <STATUS>
```

Estados existentes incluyen:

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

Regla operativa:

```text
DB   = source of truth para tracking
XLSX = review / output regenerable
```

No editar `Tracked Status` manualmente en OpenOffice/Excel esperando persistencia.

Después de trackear:

```powershell
python -m chamba_hunter.commands.export_shortlist
```

### Aplicaciones registradas al cierre

Se crearon 8 rows con status:

```text
SENT
```

Oportunidades:

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

El último create devolvió:

```text
Application id: 8
```

por lo que se observaron 8 applications creadas en esta carga.

### SENT vs APPLIED

Estado actual elegido por el usuario:

```text
SENT
```

Con `SENT`, `applied_at` queda vacío porque la lógica actual sólo inicializa `applied_at` al entrar a:

```text
APPLIED
```

No cambiar automáticamente esta semántica.

Si más adelante se decide que las postulaciones a jobs deben ser `APPLIED` y `SENT` debe reservarse para outreach/email, hacer esa decisión explícita antes de migrar/corregir estados.

### Caso especial 2BRAINS 1004

`LEAD 1004` quedó `OUT_OF_SCOPE` después de corregir geography, pero la aplicación manual ya realizada se preserva.

Esto es correcto:

```text
operational eligibility
!=
historical fact that the user applied
```

---

## 18. End-to-end refresh

Command:

```powershell
python -m chamba_hunter.commands.refresh_search
```

Sin `--apply`:

```text
PLAN ONLY
```

Con:

```powershell
python -m chamba_hunter.commands.refresh_search --apply
```

ejecuta:

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

`--discover-broad-ats-limit` default:

```text
0
```

Por lo tanto routine refresh no hace broad ATS discovery salvo pedido explícito.

### Refresh real del slice V2

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

El export no crea run.

Hubo un failure parcial dentro de SmartRecruiters:

```text
Privia Health
Server disconnected without sending a response
```

Blend360 sí terminó correctamente y el command continuó; el refresh global llegó a Run 114 y exportó el report.

No tratar ese fallo aislado como defecto del slice geo/recency.

---

## 19. Workflow operativo recomendado

Routine:

```text
refresh_search --apply
→ abrir output/chamba-shortlist.xlsx
→ Focus
→ High Value
→ aplicar manualmente
→ track_application en DB
→ export_shortlist si se necesita reflejar tracking de inmediato
```

No modificar manualmente tracking dentro del XLSX.

Al revisar Focus:

```text
Tracked Status
```

permite detectar oportunidades ya gestionadas.

`Focus` no excluye automáticamente las aplicadas.

Razón:

```text
operational priority
!=
manual application state
```

---

## 20. Estado del MVP

Chamba Hunter sigue siendo:

```text
MVP local operativo = COMPLETE
```

El slice geo/recency corrige defectos observados durante uso real; no cambia esa conclusión.

No existe una vertical obligatoria inmediata.

Próximos trabajos deben surgir de evidencia real.

Posibles líneas:

### A. Operational usage / tuning

Seguir usando:

```text
Focus
High Value
track_application
```

y observar falsos positivos/negativos.

### B. Tracking semantics

Decidir sólo si aparece fricción real:

```text
SENT vs APPLIED
applied_at semantics
application history por transición
```

No rediseñar preventivamente.

### C. ATS discovery coverage

Medir costo/beneficio de nuevas companies broad sin ATS conocido.

No activar discovery indiscriminado en routine refresh.

### D. Outreach fallback

Sólo:

```text
public careers/recruiting email
explicit general application URL
```

Nunca inferir emails personales.

### E. Search profiles adicionales

Sólo ante un segundo caso real.

---

## 21. Qué NO hacer automáticamente

- no UI web por inercia;
- no auto-apply;
- no auto-email;
- no inferir recruiter emails;
- no bypass anti-bot;
- no refactor genérico de profesiones sin segundo caso;
- no cambiar thresholds sin evidencia;
- no modificar `MATCHING_V1` para meter recencia;
- no convertir XLSX en source of truth;
- no correr `refresh_search --apply` como simple test;
- no asumir que `NEW` significa publicación reciente;
- no asumir que `SENT` completa `applied_at`.

---

## 22. Prompt operativo para nueva conversación

```text
Proyecto: Chamba Hunter
Repo: Gtestino92/chamba-hunter
Base: main

Fuente de verdad:
- verificar GitHub HEAD real y worktree local antes de asumir estado;
- leer docs/PROJECT_CONTEXT.md completo;
- código/GitHub actual manda sobre el handoff;
- DB local observada puede estar por delante de GitHub si hay cambios sin publicar.

GitHub publicado de referencia:
- main confirmado al cierre: 0902b45a91eb612c1afc77e785a05f59c32658c7.
- verificar si ya existe un commit posterior que publique geo/recency V2.

Slice local validado al cierre, pendiente de publicación si main sigue en 0902b45:
- Get on Board geography enrichment;
- src/chamba_hunter/domain/job_recency.py;
- OPERATIONAL_PRIORITY_V2;
- SHORTLIST_REPORT_V2;
- no migration nueva;
- ARGENTINA_V1 y MATCHING_V1 sin cambios.

Archivos funcionales locales esperados:
- src/chamba_hunter/repositories/job_operational_priority_repository.py
- src/chamba_hunter/services/broad_job_acquisition_service.py
- src/chamba_hunter/services/job_operational_priority_service.py
- src/chamba_hunter/services/job_shortlist_report_service.py
- src/chamba_hunter/sources/getonboard_jobs.py
- src/chamba_hunter/domain/job_recency.py

Último refresh real:
- Runs 100-114;
- Run 114 = OPERATIONAL_PRIORITY_V2 SUCCESS;
- downstream current scope = 1079;
- priority rows retained = 1120;
- operational states:
  UPDATED 127
  KNOWN 952
  OUT_OF_SCOPE 41
  NEW 0.

Shortlist actual:
- Focus 11
- High Value 68
- All Current 1079
- History 41
- source priority run 114.

Get on Board:
- current 336;
- UNKNOWN geography = 0;
- MEDIUM+ current = 86;
- MEDIUM+ eligible:
  Argentina 18
  Global 56
  LATAM 12.
- fully_remote normaliza a Worldwide;
- remote_local usa residencia explícita de página pública.

Recency:
- exact <=7 VERY_RECENT
- <=30 RECENT
- <=60 AGING
- >60 OLD
- UNKNOWN sin evidence.
- Hiring Room relative usa rangos conservadores.
- "Hace 2 meses" = 56-62 = AGING, no OLD.
- Focus V2 excluye sólo OLD demostrado.
- High Value conserva OLD.
- recency no modifica MATCHING_V1.

2BRAINS acceptance:
- LEAD 1003 Worldwide → ELIGIBLE REMOTE_GLOBAL → HIGH 76 → OLD.
- LEAD 1004 Chile → INELIGIBLE REMOTE_FOREIGN_LOCATION → OUT_OF_SCOPE.
- LEAD 1005 Chile → INELIGIBLE REMOTE_FOREIGN_LOCATION → OUT_OF_SCOPE.

Application tracking:
- DB es source of truth; XLSX es output regenerable.
- 8 oportunidades registradas como SENT:
  LEAD 828 Pomelo
  LEAD 1004 2BRAINS
  LEAD 168 Improving
  ATS 8 Bitso
  ATS 3516 Credencial Payments
  ATS 3353 ITSM Consulting
  LEAD 46 PlainTech Solutions
  ATS 3359 Grupo ST.
- SENT no completa applied_at con la semántica actual.
- no cambiar a APPLIED automáticamente sin decisión explícita.

Directivas de entrega:
- diagnósticos Python: inline PowerShell con @' ... '@ | python -;
- no pedir crear .py temporales manejables;
- implementaciones: un ZIP con rutas repo-relative directas;
- sin apply_*.py ni carpeta files/;
- junto al ZIP dar un único bloque PowerShell que:
  extrae en repo root,
  ejecuta validación/acción necesaria,
  borra ZIP sólo si todo salió bien,
  muestra diff/status cuando aplique;
- scripts .ps1 también dentro de ZIP;
- output largo a .txt;
- no project tests salvo pedido;
- usar compileall + diff-check + checks focalizados;
- usuario hace commit/push;
- no commit/push/PR sin pedido explícito.

No auto-apply, no auto-email, no anti-bot evasion, no emails personales inferidos.
```
