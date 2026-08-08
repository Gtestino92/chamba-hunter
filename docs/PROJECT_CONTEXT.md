# Chamba Hunter — Project Context / Handoff operativo

**Fecha de actualización:** 2026-08-08  
**Repositorio:** `Gtestino92/chamba-hunter`  
**Rama operativa:** `main`

## Estado de GitHub y worktree al generar este documento

Último `main` confirmado en GitHub durante esta sesión:

```text
37ce669e9f929bedf1575d05ff105bfbe90f66e3
eligibility
```

Ese commit ya contiene:

- Hiring Room;
- cross-source canonicalization v1;
- Argentina eligibility v1;
- migraciones `004` y `005`.

El trabajo de **occupation / IT / backend classification v1** descrito en este documento fue implementado y validado en el worktree local después de ese commit y todavía no estaba publicado en GitHub al momento de generar este handoff.

El estado local confirmado antes de actualizar este documento era:

```text
?? migrations/006_job_occupation_classifications.sql
?? src/chamba_hunter/commands/classify_job_occupations.py
?? src/chamba_hunter/repositories/job_occupation_repository.py
?? src/chamba_hunter/services/job_occupation_classification_service.py
```

Los ZIP y diagnósticos temporales usados durante discovery fueron eliminados.

Por lo tanto:

1. antes de iniciar una sesión nueva, verificar siempre el HEAD real de `main`;
2. si `main` ya contiene la migración `006` y los archivos de occupation descritos abajo, tratar ese código como fuente de verdad;
3. si todavía no están en `main`, revisar el worktree local antes de asumir que el trabajo se perdió;
4. GitHub/código actual gana siempre frente a este documento;
5. la base SQLite local contiene estado operativo y resultados de corridas manuales que no están versionados.

Los conteos de este documento son evidencia observada de esa DB local, no datos reproducibles sólo desde GitHub.

---

## 1. Reglas obligatorias al iniciar una nueva sesión

Antes de recomendar, diseñar o escribir código:

1. Conectarse a `Gtestino92/chamba-hunter`.
2. Verificar:
   - default branch;
   - HEAD actual de `main`;
   - últimos commits;
   - working tree si el usuario provee salida local.
3. Leer este `docs/PROJECT_CONTEXT.md`.
4. Inspeccionar directamente los archivos reales relacionados con el próximo vertical.
5. Como mínimo, cuando sean relevantes:
   - `pyproject.toml`
   - `migrations/`
   - `src/chamba_hunter/domain/`
   - `src/chamba_hunter/db/`
   - `src/chamba_hunter/repositories/`
   - `src/chamba_hunter/services/`
   - `src/chamba_hunter/sources/`
   - `src/chamba_hunter/commands/`
6. Distinguir siempre:
   - confirmado por código;
   - confirmado por corrida manual;
   - inferido;
   - pendiente.
7. No asumir que un conteo histórico sigue vigente sin consultar la DB local.
8. No crear branches, commits, pushes, PRs ni writes a GitHub salvo pedido explícito.
9. El usuario hace el commit/push manualmente.
10. Trabajar en vertical slices pequeños.

---

## 2. Preferencias operativas

- Conversación y explicación: español.
- Código, nombres técnicos y comentarios: inglés.
- Windows + PowerShell es el shell preferido actualmente.
- Para scripts inline en PowerShell, preferir:

```powershell
@'
...
'@ | python -
```

- Cuando se entregue un script para ejecutar o un archivo para reemplazar, entregarlo completo; no pasar sólo fragmentos/parches.
- Python 3.12.x.
- venv `.venv`.
- package `chamba_hunter`.
- SQLite local.
- Repositories explícitos con `sqlite3`; no SQLAlchemy.
- Pydantic v2 en boundaries externos.
- dataclasses en domain/tracing.
- `httpx` como HTTP client.
- Sin UI/web API por ahora.
- Sin automated applications.
- No agregar tests por ahora salvo pedido.
- Validaciones baratas estándar cuando se modifica código:

```powershell
python -m compileall -q src
git diff --check
```

más una corrida funcional/manual focalizada.

- Para cambios multiarchivo, preferir ZIP con rutas repo-relative.
- No hacer bypass anti-bot, fake browser ni scraping agresivo.
- 401/403/429 son señales operativas, no una invitación a evadir protección.
- Evitar dependencias nuevas salvo necesidad clara.

---

## 3. Objetivo del producto

Chamba Hunter es una herramienta local de inteligencia para búsqueda laboral.

No aplica automáticamente. Construye y mantiene un corpus amplio para luego reducirlo de manera auditable hasta obtener oportunidades accionables.

Pipeline conceptual vigente:

```text
wide-net job sources
    ↓
broad job leads
    ↓
companies / public identity
    ↓
careers discovery
    ↓
ATS evidence
    ↓
full ATS board sync
    ↓
normalized raw corpus
    ↓
cross-source canonicalization
    ↓
Argentina eligibility
    ↓
occupation / IT / backend classification
    ↓
skills                                      ← PRÓXIMO VERTICAL
    ↓
seniority
    ↓
matching / ranking
    ↓
Excel report / manual action
```

Outreach futuro y separado:

```text
company
    ↓
no matching job
    ↓
public recruiting/careers email
or explicit general application URL
    ↓
manual outreach candidate
```

Nunca inferir ni adivinar emails personales de recruiters.

---

## 4. Perfil profesional objetivo futuro

Perfil resumido para matching posterior:

- Backend Software Engineer
- Java
- Kotlin
- Spring Boot
- REST APIs
- Distributed Systems
- batch / schedulers
- retries
- idempotency
- distributed locks
- resilience
- PostgreSQL
- Oracle
- MongoDB
- Flyway / JPA
- AWS EC2 / RDS / S3 / SSM
- Docker
- Kubernetes
- OpenShift
- GitHub Actions
- GitLab CI/CD
- TypeScript / Node.js / NestJS como stack secundario
- Android / Compose secundario
- English C1
- seniority objetivo aproximado: semisenior / mid-level

No usar este perfil para filtrar adquisición.

Orden correcto:

```text
geography
→ occupation/backend
→ skills
→ seniority
→ matching/ranking
```

No mezclar estas capas. Una tecnología puede servir como evidencia ocupacional en casos acotados sin convertirse todavía en una regla de matching.

---

## 5. Foundation y schema

Arquitectura:

- package bajo `src/chamba_hunter`;
- SQLite;
- migraciones SQL inmutables;
- repositories explícitos;
- services para reglas de negocio;
- commands para workflows manuales;
- tracing con `runs`, `run_steps`, `ats_syncs`.

Migraciones confirmadas en GitHub `main` al inicio de este slice:

```text
001_initial_schema.sql
002_company_classifications.sql
003_broad_job_acquisition.sql
004_job_lead_canonicalization.sql
005_job_eligibility_classifications.sql
```

Migración local implementada y aplicada, pendiente de publicación al momento de este handoff:

```text
006_job_occupation_classifications.sql
```

Tablas/vistas relevantes:

```text
companies
company_sources
company_scans
ats_detections
company_ats
public_contacts
jobs
search_profiles
job_matches
applications
runs
run_steps
ats_syncs
company_classifications
job_leads
job_ats_hints
job_eligibility_classifications
job_occupation_classifications
view job_candidates
```

---

## 6. Companies y broad acquisition

Fuentes broad implementadas:

```text
HIMALAYAS
GETONBOARD
```

La adquisición es deliberadamente amplia.

No filtrar por Argentina ni por IT/backend en los adapters.

Principios:

- preservar provenance;
- `UNIQUE(source_type, external_id)` para leads;
- broad pagination puede ser parcial;
- ausencia en una corrida broad no implica cierre;
- broad leads no usan snapshot-deactivation de ATS;
- `first_seen_at` se preserva;
- `last_seen_at` se actualiza.

Último corpus broad confirmado localmente:

```text
GETONBOARD   active 200
HIMALAYAS    active 200
TOTAL        active 400
```

Antes de canonicalization:

```text
400 unresolved
0 ATS hints
```

`job_ats_hints` sigue en cero para el corpus observado.

---

## 7. ATS detection

Providers soportados actualmente:

```text
GREENHOUSE
ASHBY
LEVER
SMARTRECRUITERS
WORKABLE
BAMBOOHR
HIRINGROOM
CUSTOM
```

Principios de detección:

- no blind probing;
- provider probes sólo con evidencia pública previa;
- `company_ats` representa estado actual;
- `ats_detections` preserva evidencia histórica;
- 401/403/429 se registran y no se evaden;
- no promover un ATS sólo por una URL dudosa.

---

## 8. ATS ingestion implementado

Adapters/sync activos:

```text
GREENHOUSE
LEVER
ASHBY
WORKABLE
SMARTRECRUITERS
BAMBOOHR
HIRINGROOM
```

Último snapshot local confirmado:

```text
GREENHOUSE       1662
LEVER            1139
HIRINGROOM        485
SMARTRECRUITERS   197
ASHBY              90
WORKABLE           65
BAMBOOHR           24
----------------------
ATS TOTAL        3662
```

Estos números son DB local observada y pueden cambiar en futuras sincronizaciones.

---

## 9. Hiring Room — vertical terminado

Hiring Room se modela como:

```text
AtsProvider.HIRINGROOM
```

No como broad `SourceType`.

Archivos relevantes publicados en GitHub:

```text
src/chamba_hunter/sources/hiringroom.py
src/chamba_hunter/services/hiringroom_job_ingestion_service.py
src/chamba_hunter/commands/sync_hiringroom_jobs.py
```

Contrato público utilizado:

```text
https://{tenant}.hiringroom.com/jobs
POST https://{tenant}.hiringroom.com/jobs/getVacanciesForPortal/{page}
GET  https://{tenant}.hiringroom.com/jobs/get_vacancy/{id}
```

No se fabrican timestamps exactos desde edades relativas del sitio.

La ingestión:

- obtiene todas las páginas antes del sync;
- valida total/uniqueness;
- obtiene todos los detalles antes de mutar DB;
- una falla de detail aborta antes del board sync;
- preserva snapshot semantics del ATS.

Última corrida confirmada:

```text
Run 76
Tenants:       28
Succeeded:     28
Failed:         0
Jobs received: 485
Created:       213
Updated:       272
Deactivated:     0
```

Hiring Room discovery manual/indexado queda cerrado por ahora por diminishing returns.

---

## 10. Bumeran / ZonaJobs

Se intentó usar HTML público directo de:

```text
bumeran.com.ar
zonajobs.com.ar
```

Con `httpx` sólo se obtuvo el shell SPA y no los listings útiles.

No implementar bypass de Cloudflare/browser/proxies para sortearlo.

Conclusión:

- no son fuentes directas viables bajo las restricciones actuales;
- `Bumeran Selecta` sí se incorporó a través de su board Hiring Room público;
- `Jobint` también fue incorporado vía Hiring Room.

---

## 11. Cross-source canonicalization v1 — TERMINADO

Objetivo:

```text
job_leads.canonical_job_id -> jobs.id
```

sin destruir provenance del lead.

Archivos publicados en GitHub:

```text
migrations/004_job_lead_canonicalization.sql
src/chamba_hunter/repositories/job_lead_canonicalization_repository.py
src/chamba_hunter/services/job_lead_canonicalization_service.py
src/chamba_hunter/commands/canonicalize_job_leads.py
```

Reglas v1 conservadoras:

1. misma `company_id`;
2. título normalizado;
3. si hay exactamente un candidato → `TITLE`;
4. si hay varios → desempatar por location;
5. si aún hay varios → desempatar por workplace;
6. nada de fuzzy title;
7. nada de cross-company matching;
8. nada de borrado del lead.

Métodos persistidos:

```text
TITLE
TITLE_LOCATION
TITLE_LOCATION_WORKPLACE
```

La migración `004` agrega:

```text
canonicalization_method
canonicalized_at
```

y ajusta `job_candidates` para que un broad lead canonicalizado vuelva a aparecer si su ATS canonical deja de estar activo.

Última corrida confirmada:

```text
Run 77
Total leads:   400
Linked:         23
Unresolved:    377
Broken links:    0
```

Métodos:

```text
TITLE                     19
TITLE_LOCATION             3
TITLE_LOCATION_WORKPLACE   1
```

Casos ambiguos deliberadamente NO resueltos incluyeron:

- Bluelight Consulting;
- Mood Health;
- Remote.

Después de canonicalization:

```text
ATS candidates   3662
LEAD candidates   377
----------------------
job_candidates   4039
```

---

## 12. Argentina eligibility v1 — TERMINADO

Principio central:

**`REMOTE` no significa automáticamente “trabajable desde Argentina”.**

Clasificación separada y recomputable. No se modifican `jobs` ni `job_leads`.

Archivos publicados en GitHub:

```text
migrations/005_job_eligibility_classifications.sql
src/chamba_hunter/repositories/job_eligibility_repository.py
src/chamba_hunter/services/argentina_eligibility_service.py
src/chamba_hunter/commands/classify_argentina_eligibility.py
```

Tabla:

```text
job_eligibility_classifications
```

Identidad:

```text
UNIQUE(record_kind, record_id)
```

Estados:

```text
ELIGIBLE
INELIGIBLE
UNKNOWN
```

También persiste:

```text
reason
method
rule_version
evidence_json
classified_at
```

Rule version actual:

```text
ARGENTINA_V1
```

Fuentes de evidencia:

- `location_text` tiene precedencia;
- `workplace_type` sirve como señal complementaria;
- `title` sólo se usa como fallback para señales geográficas fuertes de Argentina/LATAM/remote-global;
- `description` NO se usa para clasificar geography;
- un `Remote` sin scope queda `UNKNOWN`.

No intentar forzar `UNKNOWN = 0`.

### Último resultado confirmado

Run 79:

```text
Total:       4039
Eligible:     831
Ineligible:  3046
Unknown:      162
Created:        0
Updated:     4039
Deleted:        0
```

Reasons:

```text
ELIGIBLE
  ARGENTINA_LOCATION       590
  REMOTE_GLOBAL             98
  REMOTE_LATAM             130
  REMOTE_LATAM_TITLE        13

INELIGIBLE
  FOREIGN_LOCATION         588
  FOREIGN_ONSITE_HYBRID    371
  FOREIGN_REGION_SCOPE     198
  REMOTE_FOREIGN_LOCATION 1889

UNKNOWN
  LOCATION_UNRECOGNIZED      1
  NO_LOCATION                1
  REMOTE_SCOPE_UNKNOWN     160
```

DB invariants confirmados:

```text
classifications total: 4039
stale:                    0
missing:                  0
rule versions:            1
```

Toda la tabla está en:

```text
ARGENTINA_V1
```

Run 79 y su step:

```text
SUCCESS
items_total   4039
items_success 4039
items_skipped    0
```

La versión final del repository elimina clasificaciones stale en futuros `--apply` y hace upsert de la clasificación actual.

---

## 13. Corpus efectivo después de geography

No trabajar sobre los 4039 indiscriminadamente.

El universo procesado por occupation fue:

```text
ELIGIBLE   831
UNKNOWN    162
----------------
TOTAL      993
```

Los 3046 `INELIGIBLE` geográficos se conservan en DB pero no consumieron occupation.

---

## 14. Occupation / IT / backend classification v1 — TERMINADO

### Objetivo

Clasificar de manera provider-independent, auditable y recomputable los candidatos geográficamente `ELIGIBLE` o `UNKNOWN`, sin modificar `jobs`, `job_leads` ni `job_candidates`.

Archivos locales implementados y validados, pendientes de publicación al momento de este handoff:

```text
migrations/006_job_occupation_classifications.sql
src/chamba_hunter/repositories/job_occupation_repository.py
src/chamba_hunter/services/job_occupation_classification_service.py
src/chamba_hunter/commands/classify_job_occupations.py
```

Tabla:

```text
job_occupation_classifications
```

Identidad:

```text
UNIQUE(record_kind, record_id)
```

Campos principales:

```text
occupation_class
backend_relevance
reason
method
rule_version
evidence_json
classified_at
```

Rule version aplicada:

```text
OCCUPATION_V1
```

### Taxonomía ocupacional

```text
SOFTWARE_ENGINEERING
IT_TECHNICAL
TECH_ADJACENT
NON_TECHNICAL
UNKNOWN
```

Semántica:

- `SOFTWARE_ENGINEERING`: construcción/mantenimiento de software y liderazgo técnico directo de software;
- `IT_TECHNICAL`: data/AI, SRE/platform/infra, security, cloud, DBA, NOC, systems, support, etc.;
- `TECH_ADJACENT`: product/project técnico, functional analysis, solution/technical consulting, technical account/program roles y funciones cercanas a engineering sin ser software engineering;
- `NON_TECHNICAL`: sales, HR, finance, accounting, legal, marketing, general operations, etc.;
- `UNKNOWN`: evidencia insuficiente o título deliberadamente ambiguo.

### Backend relevance

```text
BACKEND
FULL_STACK
NON_BACKEND
UNKNOWN
NOT_APPLICABLE
```

Regla de consistencia:

- sólo `SOFTWARE_ENGINEERING` puede tener `BACKEND`, `FULL_STACK`, `NON_BACKEND` o `UNKNOWN`;
- cualquier otra `occupation_class` debe tener `NOT_APPLICABLE`;
- la migración lo protege con `CHECK`.

### Principios de clasificación

Orden conceptual:

```text
specific title
    ↓
classification

generic / ambiguous title
    ↓
description fallback
    ↓
classification or UNKNOWN
```

Decisiones importantes:

- `provider/source` NO es evidencia ocupacional;
- title específico tiene precedencia;
- `description` sólo decide occupation para familias de títulos realmente ambiguas;
- no usar una bolsa global de keywords de description;
- las descriptions largas pueden contener boilerplate con `software`, `AI`, `cloud`, etc. aunque la vacante sea sales/finance/HR;
- usar patterns de roles/frases, no tokens genéricos aislados;
- preservar `UNKNOWN`;
- no mezclar todavía skills, seniority ni matching;
- `Engineering Manager`, `Staff`, `Principal`, etc. no se descartan por seniority en este vertical;
- `backend_relevance=UNKNOWN` NO debe convertirse en filtro excluyente del siguiente pipeline;
- lenguajes como Java/Python/C# pueden confirmar que un título es de software en casos acotados, pero no determinan automáticamente backend ni matching por skills.

Ejemplos conceptuales:

```text
Desarrollador/a Backend Ssr.
→ SOFTWARE_ENGINEERING / BACKEND

Senior Software Developer Java/Spring Boot
→ SOFTWARE_ENGINEERING / BACKEND si la evidencia del rol lo determina

React Engineer
→ SOFTWARE_ENGINEERING / NON_BACKEND

Senior Software Engineer
→ SOFTWARE_ENGINEERING / UNKNOWN si no hay evidencia suficiente

Desarrollador Full-Stack
→ SOFTWARE_ENGINEERING / FULL_STACK

Senior Data Engineer
→ IT_TECHNICAL / NOT_APPLICABLE

Site Reliability Engineer
→ IT_TECHNICAL / NOT_APPLICABLE

Technical Product Manager
→ TECH_ADJACENT / NOT_APPLICABLE

Business Development Representative
→ NON_TECHNICAL / NOT_APPLICABLE
```

### Discovery y refinamiento

El corpus real mostró:

```text
993 candidates
901 exact titles
894 normalized titles
```

Por lo tanto el problema es long-tail y no se resolvió con una tabla de “top titles”.

Durante discovery se hicieron varias corridas dry-run y se corrigieron falsos positivos causados por descriptions genéricas. Se pasó por revisiones r1-r5 antes de aplicar.

La versión final evita casos observados como:

```text
Chief Revenue Officer
Community Engineer
Cloud Professional Services Manager
Project Manager
Technical Author
```

siendo promovidos incorrectamente a software por boilerplate de description.

También se mejoró recall técnico para casos como:

```text
Staff Engineer (Java)
Payments Engineer
Ingeniero de Plataforma
AI Engineering Lead
Data Quality Engineer
Pasante IT
Auditor/a IT
Arquitecto Especialista AI GCP
```

sin intentar forzar `UNKNOWN = 0`.

### Última corrida confirmada — Run 80

Apply:

```text
Rule version: OCCUPATION_V1
Scope:        Argentina ELIGIBLE + UNKNOWN
Mode:         APPLY
Total:        993

Software:       246
IT technical:   137
Tech adjacent:   55
Non technical:  180
Unknown:        375

Created:        993
Updated:          0
Deleted:          0
Run id:           80
```

Backend relevance dentro de software:

```text
BACKEND          75
FULL_STACK       58
NON_BACKEND      49
UNKNOWN          64
-------------------
TOTAL           246
```

Methods:

```text
DESCRIPTION          21
TITLE               551
TITLE_DESCRIPTION    46
UNRESOLVED          375
-----------------------
TOTAL               993
```

Reasons:

```text
IT_TECHNICAL
  DESCRIPTION_IT_TECHNICAL             5
  TITLE_IT_TECHNICAL                 132

NON_TECHNICAL
  DESCRIPTION_NON_TECHNICAL            5
  TITLE_NON_TECHNICAL                175

SOFTWARE_ENGINEERING
  DESCRIPTION_SOFTWARE_ENGINEERING     11
  TITLE_BACKEND                        56
  TITLE_FULL_STACK                     36
  TITLE_NON_BACKEND_SOFTWARE           40
  TITLE_SOFTWARE                      103

TECH_ADJACENT
  TITLE_TECH_ADJACENT                  55

UNKNOWN
  UNRESOLVED_OCCUPATION               375
```

DB invariants confirmados después de apply:

```text
classifications total: 993
scoped candidates:      993
missing:                  0
stale:                    0
invalid backend:          0
rule versions:            1
```

Toda la tabla está en:

```text
OCCUPATION_V1
```

### Regla de versionado desde Run 80

`OCCUPATION_V1` ya fue persistida.

No seguir cambiando materialmente sus reglas manteniendo el mismo `rule_version`.

Un refinamiento futuro de reglas ocupacionales debe:

```text
OCCUPATION_V2
```

o una versión posterior, con decisión explícita de recalcular.

---

## 15. Próximo vertical: skills

### Estado

NO implementado todavía.

No empezar directamente con seniority ni matching/ranking.

Objetivo conceptual:

```text
occupation-classified candidates
    ↓
skills extraction / classification
    ↓
seniority
    ↓
matching / ranking
```

### Scope recomendado

Para skills no asumir que sólo `BACKEND` y `FULL_STACK` importan.

Como mínimo, conservar para análisis:

```text
SOFTWARE_ENGINEERING / BACKEND
SOFTWARE_ENGINEERING / FULL_STACK
SOFTWARE_ENGINEERING / UNKNOWN
```

El grupo:

```text
SOFTWARE_ENGINEERING / NON_BACKEND
```

puede seguir almacenándose/clasificándose, pero su prioridad futura para matching backend será menor.

No descartar automáticamente `IT_TECHNICAL`: algunos roles de platform/SRE/cloud/distributed systems pueden ser profesionalmente relevantes, pero esa decisión pertenece al matching posterior, no a occupation.

### Objetivos de skills v1

Diseñar una representación provider-independent y recomputable de skills explícitas observables en:

```text
title
description
```

Separar, como mínimo, conceptos de:

```text
programming languages
frameworks / libraries
databases
cloud / infrastructure
containers / orchestration
CI/CD
architecture / distributed systems concepts
APIs / integration
```

Antes de fijar schema definitivo, medir sobre el corpus real:

- frecuencia de skills explícitas;
- qué parte aparece en title vs description;
- aliases/sinónimos reales;
- co-ocurrencias;
- cobertura para Java/Kotlin/Spring;
- cobertura de stacks backend alternativos;
- ruido causado por boilerplate;
- casos donde una tecnología sólo aparece como “nice to have” vs requisito principal.

### Principios recomendados

- preservar evidencia exacta;
- skills no deben reemplazar occupation;
- no convertir todavía skills en score;
- no introducir seniority aquí;
- no usar el CV/perfil completo para decidir si una skill “existe” en una vacante;
- extracción determinista/auditable primero;
- aliases explícitos y versionados;
- evitar inferencias agresivas:
  - `Spring` puede necesitar distinguir Spring Framework/Spring Boot;
  - `AWS` no implica EC2/RDS/S3 específicos;
  - `Kubernetes` no implica OpenShift;
  - `JavaScript` no implica Node.js;
  - `Java` no implica Spring;
- conservar skills desconocidas/interesantes para diagnóstico futuro si el diseño lo permite.

### Primera tarea sugerida

Sólo discovery/diseño antes de escribir código:

1. verificar si `006` ya fue publicado;
2. leer este documento;
3. inspeccionar directamente el código de occupation;
4. consultar DB local usando occupation actual;
5. obtener una muestra/distribución de tecnologías mencionadas en los roles relevantes;
6. separar aliases seguros de inferencias;
7. diseñar taxonomy/schema de skills v1;
8. recién después implementar.

---

## 16. Qué NO hacer en el próximo vertical

- No volver a ampliar acquisition antes de necesidad concreta.
- No hacer más Hiring Room discovery manual por ahora.
- No implementar Bumeran/ZonaJobs con evasión anti-bot.
- No eliminar los 3046 geographic `INELIGIBLE`.
- No asumir `UNKNOWN geography` como eligible.
- No eliminar los 375 occupation `UNKNOWN`.
- No tratar `backend_relevance=UNKNOWN` como rechazo.
- No volver a mutar materialmente `OCCUPATION_V1`; usar nueva versión si se revisa.
- No arrancar matching/scoring por Java/Kotlin todavía.
- No mezclar skills y seniority.
- No hacer fuzzy canonicalization adicional salvo evidencia de que aporta valor.
- No cambiar semantics de ATS snapshot.
- No tocar outreach todavía.
- No agregar UI.

---

## 17. Validaciones operativas acumuladas

Últimos runs relevantes:

```text
70 broad ATS rediscovery
71 Hiring Room detection batch
72 Hiring Room sync initial batch
73 Hiring Room detection second batch
74 Hiring Room sync 17 tenants
75 Hiring Room detection third batch
76 Hiring Room sync 28 tenants
77 cross-source canonicalization apply
78 Argentina eligibility initial apply
79 Argentina eligibility resync/current-state validation
80 occupation / IT / backend classification apply
```

Estados actuales de clasificación confirmados:

```text
ARGENTINA_V1
  total        4039
  eligible      831
  ineligible   3046
  unknown       162
  missing         0
  stale           0

OCCUPATION_V1
  scope          993
  software       246
  it technical   137
  tech adjacent   55
  non technical  180
  unknown        375
  missing          0
  stale            0
```

Run 80 es el último estado de occupation confirmado.

---

## 18. Checklist antes de publicar occupation

El worktree debería contener, además del código ya publicado:

```text
migrations/006_job_occupation_classifications.sql

src/chamba_hunter/repositories/job_occupation_repository.py
src/chamba_hunter/services/job_occupation_classification_service.py
src/chamba_hunter/commands/classify_job_occupations.py

docs/PROJECT_CONTEXT.md
```

No versionar artefactos temporales como:

```text
chamba-hunter-occupation-v1*.zip
occupation-ambiguous-diagnostic.txt
```

Antes de commit/push:

```powershell
python -m compileall -q src
git diff --check
git status --short
git diff --stat
```

Opcionalmente revisar el diff completo:

```powershell
git diff -- migrations/006_job_occupation_classifications.sql
git diff -- src/chamba_hunter/repositories/job_occupation_repository.py
git diff -- src/chamba_hunter/services/job_occupation_classification_service.py
git diff -- src/chamba_hunter/commands/classify_job_occupations.py
git diff -- docs/PROJECT_CONTEXT.md
```

El usuario decide y ejecuta commit/push manualmente.

---

## 19. Prompt operativo recomendado para una nueva conversación

Usar este documento como handoff, pero la sesión nueva debe igualmente:

```text
Repositorio: Gtestino92/chamba-hunter
Base: main

Primero:
- verificar HEAD y últimos commits reales en GitHub;
- leer docs/PROJECT_CONTEXT.md completo;
- confirmar si migration 006 y occupation repository/service/command ya están publicados;
- distinguir GitHub code vs DB local observed state;
- no asumir que los conteos históricos siguen vigentes;
- inspeccionar el código real de occupation antes de diseñar el próximo slice;
- no modificar código todavía;
- preparar discovery del siguiente vertical: skills;
- trabajar inicialmente sobre el corpus geográficamente ELIGIBLE/UNKNOWN
  ya clasificado por OCCUPATION_V1;
- no usar backend_relevance UNKNOWN como filtro excluyente;
- no mezclar todavía seniority ni matching/ranking.
```
