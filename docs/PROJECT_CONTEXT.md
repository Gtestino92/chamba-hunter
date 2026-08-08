# Chamba Hunter — Project Context / Handoff operativo

**Fecha de actualización:** 2026-08-08  
**Repositorio:** `Gtestino92/chamba-hunter`  
**Rama operativa:** `main`

## Estado actual de GitHub y worktree

Último `main` confirmado en GitHub durante esta sesión:

```text
2e431c0413dd8825e0497001ecc4981b099b6edb
shortlist
```

Ese `main` ya contiene:

- Hiring Room;
- cross-source canonicalization v1;
- Argentina eligibility v1;
- occupation / IT / backend classification v1;
- skills classification v1;
- seniority classification v1;
- professional matching v1;
- content freshness v1;
- operational/application priority v1;
- shortlist/report v1;
- migraciones `004` a `011`;
- `BACKEND_SOFTWARE_V1`;
- `MATCHING_V1`;
- `JOB_CONTENT_V1`;
- `OPERATIONAL_PRIORITY_V1`;
- `SHORTLIST_REPORT_V1`.

El trabajo de **manual application tracking + end-to-end refresh v1** fue implementado y validado localmente después de ese commit y todavía está pendiente de publicación en GitHub.

Estado local esperado antes de publicar este slice, después de limpiar scripts temporales:

```text
M  docs/PROJECT_CONTEXT.md
M  src/chamba_hunter/repositories/job_shortlist_report_repository.py
?? migrations/012_application_opportunity_identity.sql
?? src/chamba_hunter/commands/refresh_search.py
?? src/chamba_hunter/commands/track_application.py
?? src/chamba_hunter/repositories/application_repository.py
?? src/chamba_hunter/services/application_tracking_service.py
```

Output local generado y deliberadamente ignorado por Git:

```text
output/chamba-shortlist.xlsx
```

Estado SQLite local confirmado después del primer refresh end-to-end real:

```text
Run 99
OPERATIONAL_PRIORITY_V1
SUCCESS

applications rows = 0
migration 012 applied = yes
```

La generación del reporte no crea runs. `track_application` sólo modifica `applications` cuando el usuario registra manualmente una acción real.

GitHub/código actual es siempre fuente de verdad frente a este documento. Los conteos de runs son evidencia observada de la DB local y pueden cambiar después de futuros refreshes.

---

## 1. Reglas operativas

Antes de recomendar, diseñar o escribir código:

1. Verificar HEAD real de `main`, últimos commits y worktree.
2. Leer este `docs/PROJECT_CONTEXT.md`.
3. Inspeccionar directamente los archivos reales del vertical a tocar.
4. Distinguir siempre:
   - confirmado por código;
   - confirmado por corrida manual;
   - inferido;
   - pendiente.
5. No asumir que conteos históricos siguen vigentes sin consultar la DB local.
6. No crear branches, commits, pushes, PRs ni writes a GitHub salvo pedido explícito.
7. El usuario hace commit/push manualmente.
8. Trabajar en vertical slices pequeños.
9. Código/comentarios en inglés; explicación en español.
10. Windows + PowerShell es el entorno operativo habitual.
11. Para scripts inline en PowerShell, preferir:

```powershell
@'
...
'@ | python -
```

12. Cuando se entregue un script o archivo para reemplazar, entregarlo completo; no fragmentos/parches.
13. No agregar tests salvo pedido explícito.
14. Validaciones baratas estándar:

```powershell
python -m compileall -q src
git diff --check
```

más una corrida funcional/manual focalizada.
15. Para cambios multiarchivo, preferir ZIP con rutas repo-relative.
16. No hacer bypass anti-bot, fake browser ni scraping agresivo.
17. 401/403/429 son señales operativas, no una invitación a evadir protección.
18. Evitar dependencias nuevas salvo necesidad clara.

---

## 2. Stack y arquitectura

- Python 3.12.x.
- venv `.venv`.
- package `chamba_hunter`.
- SQLite local.
- repositories explícitos con `sqlite3`.
- sin SQLAlchemy.
- Pydantic v2 en boundaries externos.
- dataclasses en domain/tracing.
- `httpx` como HTTP client.
- `openpyxl` para export XLSX local.
- migraciones SQL inmutables.
- services para reglas de negocio.
- commands para workflows manuales.
- tracing con `runs`, `run_steps`, `ats_syncs`.
- sin UI/web API por ahora.
- sin automated applications.

---

## 3. Objetivo del producto

Chamba Hunter es una herramienta local de inteligencia para búsqueda laboral.

No aplica automáticamente. Construye y mantiene un corpus amplio para reducirlo de manera auditable hasta obtener oportunidades accionables.

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
skills
    ↓
seniority
    ↓
professional matching
    ↓
operational / application priority
    ↓
shortlist / Excel report
    ↓
manual application tracking / refresh workflow
```

El end game debe soportar además un refresh manual orientado a **early application**:

```text
refresh acquisition / ATS
→ canonicalization
→ geography
→ occupation
→ skills
→ seniority
→ matching
→ operational priority
→ shortlist de oportunidades nuevas/relevantes
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

### Future architecture consideration — reusable search profiles

La prioridad sigue siendo la búsqueda de **Backend Software Engineer**.

No generalizar anticipadamente todo el proyecto ni construir un framework abstracto para múltiples profesiones. Tampoco refactorizar código estable sólo por una posibilidad futura.

Sin embargo, preservar esta separación:

```text
job acquisition / normalization / understanding
```

de:

```text
preferences of one specific professional search
```

Arquitectura conceptual:

```text
SHARED JOB SEARCH ENGINE

acquisition
ATS discovery
ATS ingestion
normalization
canonicalization
freshness
application channels
tracing
        ↓
SEARCH-SPECIFIC EVALUATION

geographic eligibility
occupation
skills / domains
credentials when applicable
seniority
matching
ranking
```

La primera parte debe ser ampliamente reutilizable sobre un mismo corpus.

La segunda puede depender de un:

```text
search_profile
```

El perfil implementado actualmente es:

```text
BACKEND_SOFTWARE_V1
```

y expresa preferencias de búsqueda sobre:

```text
occupation/backend relevance
skills y transferibilidad
seniority
leadership
```

El principio fundamental es:

```text
job understanding
!=
search-profile matching
```

Por ejemplo:

```text
job skills:
- Java
- Spring Boot
- PostgreSQL
```

significa que esas skills fueron observadas en el posting.

No significa por sí mismo:

```text
this is a good match for the current search profile
```

La comparación contra preferencias, experiencia y transferibilidad pertenece a `MATCHING_V1`.

La implementación actual ya prueba el modelo:

```text
one shared job corpus
        ↓
search_profiles
        ↓
job_professional_matches
```

sin modificar geography, occupation, skills ni seniority para adaptarlos al usuario.

Un futuro segundo search profile puede reutilizar acquisition, ATS ingestion, normalization, canonicalization, freshness y application channels, pero no debe motivar una abstracción preventiva ahora.

---

## 4. Search profile backend actual


Este perfil se usa en `MATCHING_V1`, no para adquisición ni para decidir si una skill existe en una vacante:

- Backend Software Engineer.
- Java.
- Kotlin.
- Spring Boot.
- REST APIs.
- Distributed Systems.
- batch / schedulers.
- retries.
- idempotency.
- distributed locks.
- resilience.
- PostgreSQL.
- Oracle.
- MongoDB.
- Flyway / JPA.
- AWS EC2 / RDS / S3 / SSM.
- Docker.
- Kubernetes.
- OpenShift.
- GitHub Actions.
- GitLab CI/CD.
- TypeScript / Node.js / NestJS como stack secundario.
- Android / Compose secundario.
- English C1.
- seniority objetivo aproximado: semisenior / mid-level.

Orden correcto:

```text
geography
→ occupation/backend
→ skills
→ seniority
→ professional matching
→ operational priority
```

No mezclar estas capas.

---

## 5. Schema y migraciones

Migraciones confirmadas en GitHub `main`:

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
```

Migration local implementada, aplicada y validada, pendiente de publicación:

```text
012_application_opportunity_identity.sql
```

Agrega identidad genérica de oportunidad a `applications` para soportar tanto `ATS` como `LEAD` sin inventar un `jobs.id`.

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
job_skill_classifications
job_seniority_classifications
job_professional_matches
job_operational_priorities
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

No filtrar por Argentina ni por IT/backend en adapters.

Principios:

- preservar provenance;
- `UNIQUE(source_type, external_id)` para leads;
- broad pagination puede ser parcial;
- ausencia en una corrida broad no implica cierre;
- broad leads no usan snapshot-deactivation de ATS;
- `first_seen_at` se preserva;
- `last_seen_at` se actualiza.

Última adquisición broad confirmada localmente:

```text
Run 85

HIMALAYAS
  received   500
  created    500
  updated      0

GETONBOARD
  received   339
  created    139
  updated    200

TOTAL received   839
TOTAL created    639
TOTAL updated    200
```

Estado inmediatamente después de adquisición y antes de la nueva canonicalization:

```text
active unresolved leads   1016
raw active candidates     4678
stored ATS hints              0
```

La corrida amplió deliberadamente la ventana broad respecto del baseline anterior de 200 + 200.

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

Principios:

- no blind probing;
- provider probes sólo con evidencia pública previa;
- `company_ats` representa estado actual;
- `ats_detections` preserva evidencia histórica;
- 401/403/429 se registran y no se evaden;
- no promover un ATS sólo por una URL dudosa.

---

## 8. ATS ingestion

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

Último snapshot activo confirmado después de Runs 86–92:

```text
GREENHOUSE       1659
LEVER            1139
HIRINGROOM        485
SMARTRECRUITERS   197
ASHBY              90
WORKABLE           65
BAMBOOHR           24
----------------------
ATS ACTIVE       3659
```

En ese refresh Greenhouse creó 2 jobs y desactivó 5; los demás providers no crearon ni desactivaron jobs.

Estos números son estado local observado y pueden cambiar.

### Semántica importante de freshness

Antes de migration `010`, `JobRepository.sync_board_jobs()` y `JobLeadRepository.upsert_source_jobs()` sólo podían distinguir:

```text
first_seen_at
last_seen_at
is_active
```

El contador `updated` de los syncs históricos significa “registro existente re-observado/escrito”, no necesariamente “contenido cambió”.

Desde el slice local pendiente de publicación se agrega:

```text
content_hash
content_hash_version
last_changed_at
```

a:

```text
jobs
job_leads
```

Hash version:

```text
JOB_CONTENT_V1
```

Contenido material incluido:

```text
title
description
location_text
workplace_type
employment_type
job_url
apply_url
published_at
expires_at   # sólo job_leads
```

No se incluyen:

```text
last_seen_at
is_active
raw_payload_json
```

Semántica:

```text
first observation
→ content_hash current
→ last_changed_at = NULL

same content observed again
→ update last_seen_at
→ preserve last_changed_at

material content hash changes
→ last_changed_at = seen_at
```

La inicialización de migration `010` se hace desde Python porque SQLite no tiene SHA-256 built-in.

El baseline inicializó hashes para:

```text
jobs       3662
job_leads   400
```

sin fabricar cambios históricos:

```text
jobs last_changed_at != NULL        0
job_leads last_changed_at != NULL   0
```

`last_seen_at` sigue significando “observado nuevamente”, no “cambió”.

ATS snapshot absence puede desactivar `jobs`.

Broad source absence sigue sin implicar cierre automático.

Freshness es parte del shared job search engine y permanece separada de `MATCHING_V1`.

---

## 9. Hiring Room — terminado

Hiring Room se modela como:

```text
AtsProvider.HIRINGROOM
```

No como broad `SourceType`.

Archivos publicados:

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

No se fabrican timestamps exactos desde edades relativas.

Última corrida confirmada:

```text
Run 92
Tenants:       28
Succeeded:     28
Failed:         0
Jobs received: 485
Created:         0
Updated:       485
Deactivated:     0
```

Hiring Room discovery manual/indexado queda cerrado por diminishing returns.

---

## 10. Bumeran / ZonaJobs

HTML público directo de `bumeran.com.ar` y `zonajobs.com.ar` devolvió sólo shell SPA bajo las restricciones actuales.

No implementar bypass de Cloudflare/browser/proxies.

`Bumeran Selecta` y `Jobint` sí fueron incorporados vía Hiring Room.

---

## 11. Cross-source canonicalization v1 — TERMINADO

Objetivo:

```text
job_leads.canonical_job_id -> jobs.id
```

sin destruir provenance.

Archivos publicados:

```text
migrations/004_job_lead_canonicalization.sql
src/chamba_hunter/repositories/job_lead_canonicalization_repository.py
src/chamba_hunter/services/job_lead_canonicalization_service.py
src/chamba_hunter/commands/canonicalize_job_leads.py
```

Reglas v1:

1. misma `company_id`;
2. título normalizado;
3. si hay exactamente un candidato → `TITLE`;
4. si hay varios → desempatar por location;
5. si aún hay varios → desempatar por workplace;
6. nada de fuzzy title;
7. nada de cross-company matching;
8. nada de borrado del lead.

Métodos:

```text
TITLE
TITLE_LOCATION
TITLE_LOCATION_WORKPLACE
```

Run 77:

```text
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

Casos ambiguos deliberadamente no resueltos incluyeron:

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

Clasificación separada y recomputable. No modifica `jobs` ni `job_leads`.

Archivos publicados:

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

Rule version:

```text
ARGENTINA_V1
```

Fuentes de evidencia:

- `location_text` tiene precedencia;
- `workplace_type` es señal complementaria;
- `title` sólo es fallback para señales geográficas fuertes;
- `description` no se usa para geography;
- `Remote` sin scope queda `UNKNOWN`;
- no intentar forzar `UNKNOWN = 0`.

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

DB invariants:

```text
classifications total: 4039
stale:                    0
missing:                  0
rule versions:            1
```

Toda la tabla está en `ARGENTINA_V1`.

---

## 13. Corpus efectivo después de geography

Universo procesado por occupation y skills:

```text
ELIGIBLE   831
UNKNOWN    162
----------------
TOTAL      993
```

Los 3046 `INELIGIBLE` se conservan en DB.

---

## 14. Occupation / IT / backend classification v1 — TERMINADO

Archivos publicados en GitHub:

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

Campos:

```text
occupation_class
backend_relevance
reason
method
rule_version
evidence_json
classified_at
```

Rule version:

```text
OCCUPATION_V1
```

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

Sólo `SOFTWARE_ENGINEERING` puede tener backend relevance distinta de `NOT_APPLICABLE`.

Principios:

- provider/source no es evidencia ocupacional;
- title específico tiene precedencia;
- description sólo decide occupation para familias realmente ambiguas;
- evitar bolsa global de keywords de description;
- preservar `UNKNOWN`;
- no mezclar skills, seniority ni matching;
- `backend_relevance=UNKNOWN` no es un rechazo;
- `Engineering Manager`, `Staff`, `Principal`, etc. no se descartan por seniority aquí.

Run 80:

```text
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

Backend dentro de software:

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
```

DB invariants:

```text
classifications total: 993
scoped candidates:      993
missing:                  0
stale:                    0
invalid backend:          0
rule versions:            1
```

`OCCUPATION_V1` ya fue persistida. Cambios materiales futuros deben usar `OCCUPATION_V2` o posterior.

---

## 15. Skills classification v1 — TERMINADO

### Objetivo

Extraer de forma provider-independent, determinista, auditable y recomputable las tecnologías explícitamente mencionadas en cada job geográficamente viable.

Scope:

```text
Argentina eligibility:
ELIGIBLE + UNKNOWN
```

Actualmente:

```text
993 candidates
```

Skills no depende de `occupation_class` como condición de entrada.

Esto es deliberado porque occupation `UNKNOWN` puede contener evidencia técnica útil y porque el extractor debe describir el posting sin decidir todavía si es buen match.

### Archivos publicados en GitHub

```text
migrations/007_job_skill_classifications.sql
src/chamba_hunter/repositories/job_skill_repository.py
src/chamba_hunter/services/job_skill_classification_service.py
src/chamba_hunter/commands/classify_job_skills.py
```

Tabla:

```text
job_skill_classifications
```

Identidad:

```text
UNIQUE(
    record_kind,
    record_id,
    skill_key
)
```

Campos:

```text
record_kind
record_id
skill_key
skill_category
title_match
description_match
evidence_json
rule_version
classified_at
```

Rule version:

```text
SKILLS_V1
```

### Semántica

Una fila significa solamente:

```text
esta skill reconocida aparece explícitamente
en title y/o description
```

No significa:

```text
REQUIRED
PREFERRED
candidate must know it
exact user match
reject if missing
```

No se persisten aquí:

```text
requirement strength
preference strength
skill equivalence
skill substitutability
seniority
matching score
freshness
application priority
```

### Catálogo

`SKILLS_V1` contiene 187 canonical skills con aliases deterministas.

Ejemplos:

```text
postgres / postgresql
→ POSTGRESQL

k8s / kubernetes
→ KUBERNETES

node.js / nodejs
→ NODEJS
```

No inferir:

```text
JAVA         → SPRING
AWS          → EC2
AWS          → S3
JAVASCRIPT   → NODEJS
KUBERNETES   → OPENSHIFT
```

Guardas explícitas:

```text
React Native
→ REACT_NATIVE
→ no implica REACT

Azure DevOps
→ AZURE_DEVOPS
→ no implica AZURE

SAP BTP
→ SAP_BTP
→ no implica SAP genérico
```

### Categorías observadas

```text
LANGUAGE
INFRASTRUCTURE
CLOUD
ARCHITECTURE
DATABASE
FRAMEWORK
FRONTEND
OBSERVABILITY
DATA_PLATFORM
BUSINESS_PLATFORM
CI_CD
MOBILE
MESSAGING
ANALYTICS
CLOUD_SERVICE
SECURITY
TESTING
ENGINEERING_PRACTICE
REALTIME
BUILD_TOOL
```

Son descriptivas, no weights ni familias de equivalencia.

### Evidence

Cada skill conserva:

```text
title_match
description_match
evidence_json
```

`evidence_json` conserva aliases/matches y snippets acotados.

Esto permite reinterpretar en el futuro señales como:

```text
required-like
preferred-like
alternative
```

sin convertir esas heurísticas en semántica rígida de V1.

### Requirement / preferred

Los discoveries mostraron que heurísticas simples por proximidad generan muchas colisiones entre `required-like` y `preferred-like`.

Por eso `SKILLS_V1` no persiste esas etiquetas.

En matching futuro pueden ser señales, nunca hard cuts automáticos.

Principio de producto:

```text
job: Azure required
profile: strong AWS experience

NO:
→ reject

SÍ:
→ exact Azure evidence absent
→ transferable cloud evidence present
→ considerar el resto del match
```

### Tecnologías transferibles

El corpus mostró relaciones explícitas como:

```text
AWS / Azure / GCP
Java / Kotlin
Spring Boot / Quarkus / Micronaut
Flask / FastAPI / Django
PostgreSQL / MySQL
Kafka / RabbitMQ / SQS
GitHub Actions / GitLab CI / Jenkins
```

No modelar estas relaciones dentro de `SKILLS_V1`.

Matching deberá distinguir después:

```text
EXACT MATCH
PEER / PARTIALLY SUBSTITUTABLE
RELATED ECOSYSTEM
```

mediante taxonomía curada, no inferida automáticamente desde co-mentions.

### Discovery y QA

Se realizaron tres rondas read-only sobre los 993 candidatos.

Hallazgos:

- software tuvo 95.9% de cobertura con catálogo inicial;
- catálogo expandido llegó a 97.6%;
- occupation `UNKNOWN` contiene señales técnicas importantes;
- non-tech puede mencionar tecnologías legítimamente;
- skill mention no equivale a requirement;
- alternativas tecnológicas aparecen explícitamente;
- no intentar 100% de coverage fabricando skills genéricas.

QA focalizada:

```text
SOFTWARE_ENGINEERING
240 / 246
97.6%
```

Los 6 software jobs sin skill reconocida eran postings con stacks no explícitos o información demasiado genérica.

No se detectaron regex peligrosamente amplios en el muestreo de tokens ambiguos.

### Run 81 — apply confirmado

```text
Rule version: SKILLS_V1
Scope:        Argentina ELIGIBLE + UNKNOWN
Mode:         APPLY

Candidates:   993
With skills:  512
No skills:    481
Skill rows:   2664

Created:      2664
Updated:         0
Deleted:         0

Run id:          81
```

Coverage:

```text
IT_TECHNICAL            114 / 137   83.2%
NON_TECHNICAL            51 / 180   28.3%
SOFTWARE_ENGINEERING    240 / 246   97.6%
TECH_ADJACENT            30 / 55    54.5%
UNKNOWN                  77 / 375   20.5%
```

Sources:

```text
DESCRIPTION          2430
TITLE                  68
TITLE_DESCRIPTION     166
-------------------------
TOTAL                 2664
```

Top skills:

```text
PYTHON               178
LINUX                147
AWS                  129
KUBERNETES           128
REACT                  94
SQL                    94
DOCKER                 70
POSTGRESQL             64
REST                   59
GO                     59
AZURE                  58
TYPESCRIPT             58
GCP                    54
JAVA                   45
DISTRIBUTED_SYSTEMS    45
CPP                    43
MYSQL                  41
OPENSTACK              40
JAVASCRIPT             39
SAP                    37
```

Target-stack observation:

```text
JAVA                     45
KOTLIN                    3
SPRING_BOOT               8
SPRING                    7
REST                     59
MICROSERVICES            33
DISTRIBUTED_SYSTEMS      45
POSTGRESQL               64
ORACLE_DB                 1
MONGODB                  11
AWS                     129
EC2                       3
RDS                      16
S3                       13
DOCKER                   70
KUBERNETES              128
OPENSHIFT                 2
GITHUB_ACTIONS           14
GITLAB_CI                14
NODEJS                   33
NESTJS                   12
TYPESCRIPT               58
```

DB invariants:

```text
Duplicate candidate/skill keys:          0
Rows without title/description evidence: 0
Rows outside current scope:              0
Non-SKILLS_V1 rows:                      0
```

Toda la tabla está en `SKILLS_V1`.

### Refresh semantics

En cada `--apply`:

```text
current geographic scope
    ↓
extract complete current skill set
    ↓
upsert current rows
    ↓
delete stale skill rows
```

Skills no modifica ni duplica:

```text
first_seen_at
last_seen_at
published_at
is_active
job_url
apply_url
```

`SKILLS_V1` ya fue persistida. Cambios materiales futuros deben usar `SKILLS_V2` o posterior.

---

## 16. Requisito de producto: freshness / early application

El sistema final debe permitir un refresh manual y devolver rápidamente oportunidades nuevas y relevantes.

Debe distinguir conceptualmente:

```text
NEW
KNOWN
UPDATED
CLOSED / INACTIVE
```

y especialmente:

```text
NEW + HIGH MATCH
```

### Datos ya disponibles

En los 993 candidatos observados:

```text
first_seen_at   993 / 993  100.0%
last_seen_at    993 / 993  100.0%
job_url         993 / 993  100.0%
apply_url       606 / 993   61.0%
published_at     46 / 993    4.6%
```

Por lo tanto `first_seen_at` será la base más fuerte para NEW.

`published_at` es señal adicional sólo cuando exista y sea confiable.

### Limitación de UPDATED

El `updated` actual de sync no prueba cambio de contenido.

`last_seen_at` tampoco representa cambio.

Más adelante diseñar explícitamente:

```text
content_hash
last_changed_at
change event / history
```

sin mezclarlo con skills ni seniority.

### Professional match vs operational priority

Separar:

```text
professional_match
```

de:

```text
operational_application_priority
```

`MATCHING_V1` ya considera:

```text
occupation/backend
skills
skill transferability
seniority
leadership
role/title mismatch signals
```

y lo persiste separado de freshness y application priority.

Operational priority podrá considerar:

```text
professional_match
NEW / first_seen_at
published_at cuando sea confiable
application channel quality
future company priority
change/freshness signals
```

Ejemplo:

```text
match 90 + discovered minutes ago
```

puede ser operacionalmente más prioritario que:

```text
match 94 + known for 10 days
```

sin alterar el professional match.

### Application end game

Orden conceptual:

```text
1. apply_url directo
2. job_url / careers page
3. general_application_url
4. public recruiting/careers email
```

No habrá auto-apply.

El sistema descubre, clasifica, prioriza y prepara. El usuario revisa y aplica/envía manualmente.

---

## 17. Seniority classification v1 — TERMINADO

### Objetivo

Clasificar de manera provider-independent, recomputable y auditable el nivel explícito del puesto, sin convertirlo todavía en una decisión de match.

Scope:

```text
Argentina eligibility:
ELIGIBLE + UNKNOWN
```

Total aplicado:

```text
993 candidates
```

Seniority no usa el target profesional del usuario para decidir la clase del job.

### Archivos publicados en GitHub

```text
migrations/008_job_seniority_classifications.sql
src/chamba_hunter/repositories/job_seniority_repository.py
src/chamba_hunter/services/job_seniority_classification_service.py
src/chamba_hunter/commands/classify_job_seniority.py
```

Tabla:

```text
job_seniority_classifications
```

Identidad:

```text
UNIQUE(record_kind, record_id)
```

Rule version:

```text
SENIORITY_V1
```

### Dos dimensiones separadas

`SENIORITY_V1` distingue deliberadamente nivel profesional de liderazgo/management.

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

Leadership title class:

```text
NONE
UNKNOWN
MANAGER
DIRECTOR
HEAD
VP
C_LEVEL
```

No asumir una equivalencia total entre estas dos dimensiones.

Ejemplos:

```text
Senior Engineering Manager
→ SENIOR + MANAGER

Engineering Manager
→ UNKNOWN + MANAGER

Software Engineering Director
→ UNKNOWN + DIRECTOR

Chief Revenue Officer
→ UNKNOWN + C_LEVEL

Lead Linux Kernel Engineer
→ LEAD + NONE
```

`Product Manager` no se interpreta automáticamente como people-management sólo por contener `Manager`; puede quedar leadership `UNKNOWN`.

### Principios

- title explícito tiene prioridad;
- description se usa sólo como fallback conservador;
- no inferir seniority automáticamente desde años de experiencia;
- no mapear `Software Engineer II` a una clase universal;
- no forzar `UNKNOWN = 0`;
- títulos con múltiples niveles explícitos quedan `UNKNOWN`;
- management/leadership sin nivel explícito no hereda artificialmente `SENIOR`, `STAFF` o `LEAD` desde la description;
- `LEAD` no se infiere desde description porque verbos como “lead a team” generan ambigüedad;
- el perfil actual semisenior/mid-level no modifica la clasificación objetiva.

### Conflictos preservados

Ejemplos observados que quedan deliberadamente `UNKNOWN`:

```text
Senior/Staff/Principal Engineer
Junior / Semi Senior Developers
Semi Senior / Senior
JR/SSR
SSR/SR
```

Esto evita escoger arbitrariamente una de varias vacantes/niveles representados por el mismo posting.

### Description fallback auditado

Después de refinamientos R1-R3 quedaron solamente:

```text
DESCRIPTION_SENIOR   13
DESCRIPTION_MID       2
```

Los 15 casos fueron auditados manualmente.

Todos describían explícitamente el nivel del puesto, por ejemplo:

```text
senior individual contributor role
Senior Software Development Consultant
perfil ... semi senior
Senior Frontend Engineer
Senior Shopify Developer
Software Engineer Senior
Senior Python Engineer
Desarrollador/a Full Stack Senior
semi-senior backend software developer
Senior Backend Engineer
Senior AI Engineer
perfil SR
senior-level builder
```

No quedó `DESCRIPTION_LEAD`.

### Años de experiencia

La clasificación extrae también evidencia explícita de años cuando existe, pero no convierte esa evidencia en una tabla rígida de seniority.

Run 82 observó:

```text
Candidates with experience evidence: 273
Evidence snippets:                   354
```

Lower-bound mentions:

```text
 1 years   12
 2 years   68
 3 years   75
 4 years   32
 5 years   80
 6 years   18
 7 years   20
 8 years   20
10 years   14
12 years   13
15 years    1
16 years    1
```

Ejemplo de principio:

```text
5+ years
!= automatically SENIOR
```

Los años podrán ser una señal posterior de matching.

### Run 82 — apply confirmado

```text
Rule version: SENIORITY_V1
Scope:        Argentina ELIGIBLE + UNKNOWN
Mode:         APPLY

Candidates:   993
Created:      993
Updated:        0
Deleted:        0

Run id:        82
```

Seniority:

```text
UNKNOWN       724   72.9%
SENIOR        158   15.9%
MID            33    3.3%
LEAD           30    3.0%
JUNIOR         19    1.9%
STAFF           9    0.9%
ENTRY           8    0.8%
PRINCIPAL       8    0.8%
INTERN          4    0.4%
```

Leadership:

```text
NONE         854
UNKNOWN       70
MANAGER       39
DIRECTOR      18
HEAD           5
C_LEVEL        4
VP             3
```

Methods:

```text
DESCRIPTION     15
TITLE          383
UNRESOLVED     595
```

Seniority dentro de `SOFTWARE_ENGINEERING`:

```text
total       246

ENTRY         2
JUNIOR        6
MID          15
SENIOR       72
STAFF         7
PRINCIPAL     5
LEAD          6
UNKNOWN     133
```

### DB invariants después de apply

```text
Rows:              993
Current scope:     993
Missing:             0
Stale:               0
Duplicate keys:      0
Missing evidence:    0
Wrong version:       0
```

Rule versions:

```text
SENIORITY_V1   993
```

Tracing:

```text
Run id:       82
Command:      classify_job_seniority
Status:       SUCCESS
Step:         job_seniority_classification
Step status:  SUCCESS
Items:        993 / 993 / 0 failed / 0 skipped
```

La validación de invariantes terminó:

```text
PASS
```

### Refresh semantics

Futuros `--apply` deben mantener la tabla como current-state recomputable para el scope geográfico actual:

```text
current geographic scope
    ↓
recompute seniority
    ↓
upsert current candidates
    ↓
delete stale candidates
```

No copiar freshness, URLs ni matching score a esta tabla.

### Regla de versionado

`SENIORITY_V1` ya fue persistida.

No modificar materialmente su semántica manteniendo el mismo `rule_version`.

Cambios materiales futuros deben usar:

```text
SENIORITY_V2
```

o posterior, con decisión explícita de recalcular.

---

## 18. Professional matching v1 — TERMINADO

### Objetivo

Evaluar qué tan bien cada job representa una oportunidad profesional para el search profile backend actual sin destruir ni reinterpretar las clasificaciones objetivas anteriores.

Matching es la primera capa que compara explícitamente:

```text
job understanding
```

contra:

```text
search profile
```

Scope:

```text
active job_candidates
Argentina eligibility = ELIGIBLE + UNKNOWN
```

Total aplicado:

```text
993 candidates
892 ATS
101 LEAD
```

### Search profile

Se reutiliza la tabla ya existente:

```text
search_profiles
```

Profile:

```text
BACKEND_SOFTWARE_V1
```

Profile id observado:

```text
1
```

Rule version:

```text
MATCHING_V1
```

El profile se persiste con `rules_json` auditable.

### Persistencia de matches

No se reutiliza la tabla legacy:

```text
job_matches
```

porque está keyed sólo por:

```text
jobs.id
```

y no puede representar los `LEAD` no canonicalizados que siguen formando parte de `job_candidates`.

La tabla nueva es:

```text
job_professional_matches
```

Identidad:

```text
UNIQUE(
    record_kind,
    record_id,
    search_profile_id
)
```

Soporta:

```text
ATS
LEAD
```

La tabla legacy `job_matches` quedó intacta y observada con:

```text
0 rows
```

### Archivos locales implementados y aplicados

Pendientes de publicación al momento de este handoff:

```text
migrations/009_job_professional_matches.sql
src/chamba_hunter/repositories/job_matching_repository.py
src/chamba_hunter/services/job_matching_service.py
src/chamba_hunter/commands/match_jobs.py
```

### Score

Score profesional máximo:

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

Freshness, `first_seen_at`, `published_at`, URLs y application channel **no participan** del professional match score.

### Match levels

```text
VERY_HIGH   >= 80
HIGH        >= 65
MEDIUM      >= 45
LOW          < 45
```

No son hard eligibility states.

Un `MEDIUM` o incluso `LOW` permanece en DB y puede revisarse.

### Role / backend fit

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

Para:

```text
SOFTWARE_ENGINEERING
backend_relevance = UNKNOWN
```

existe un boost acotado:

```text
25 → 35
```

sólo cuando el posting tiene evidencia backend fuerte y específica del profile.

Strong JVM:

```text
Java/Kotlin
+
Spring Boot/Spring/JPA/Hibernate/Quarkus/Micronaut/Ktor
```

Strong Node:

```text
Node.js/TypeScript
+
NestJS
```

En la corrida final este boost se activó para **1 solo candidato**.

Ejemplo observado:

```text
Desarrollador Java Ssr /Sr
Java + Spring
backend_relevance UNKNOWN
→ role score 35
→ final score 65 HIGH
```

Esto pertenece al matcher profile-specific y no modifica `OCCUPATION_V1`.

### Skills y transferibilidad

Missing skill evidence no es rechazo ni penalización automática.

Las señales están agrupadas para evitar que muchas menciones del mismo ecosistema inflen el score.

Relaciones:

```text
EXACT
PEER
RELATED
SECONDARY
```

Ejemplos:

```text
AWS
→ EXACT

Azure / GCP
→ PEER de cloud

Spring Boot
→ EXACT

Quarkus / Micronaut
→ PEER de JVM backend framework

PostgreSQL
→ EXACT

MySQL / SQL Server / MariaDB / Percona
→ PEER de RDBMS

Terraform / Helm / CloudFormation / Pulumi
→ RELATED de platform/container ecosystem

Node.js / NestJS / TypeScript
→ SECONDARY para el profile actual
```

No asumir equivalencia exacta por pertenecer a la misma familia.

### Stacks backend alternativos

Familias detectadas:

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

Una tecnología alternativa no causa hard rejection.

Cuando un stack alternativo está explícito en el título y no hay core compatible explícito en ese mismo título:

```text
technology penalty = -5
score ceiling = 64
```

Por lo tanto permanece visible, pero no llega a `HIGH`.

Ejemplos calibrados:

```text
Backend Developer .NET SSR
→ MEDIUM

Senior Go Developer
→ MEDIUM

Senior Backend Engineer (Python)
→ MEDIUM

Developer PHP SSR
→ MEDIUM
```

Un título mixto compatible conserva posibilidad de match fuerte:

```text
Desarrollador Back-end Golang+Java
→ VERY_HIGH
```

### Seniority fit

Target:

```text
semisenior / mid-level
```

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

`UNKNOWN` sigue siendo viable.

Score ceilings:

```text
JUNIOR      64
STAFF       64
LEAD        64
PRINCIPAL   60
ENTRY       55
INTERN      45
```

De esa manera siguen visibles, pero no compiten como `HIGH` con el target mid-level.

### Architect guard

`SENIORITY_V1` no inventa una clase universal para `Architect`.

En matching, los títulos:

```text
Architect
Arquitecto / Arquitecta
```

tienen:

```text
score ceiling = 64
```

porque suelen implicar una distancia material respecto del target actual aunque no exista una clase IC universal segura.

Ejemplos observados después de calibración:

```text
BackEnd Architect
→ MEDIUM 64

Software Architect
→ MEDIUM <= 64
```

### Leadership fit

Base:

```text
NONE       10
UNKNOWN     8
MANAGER     2
DIRECTOR    1
HEAD        0
VP          0
C_LEVEL     0
```

Ceilings:

```text
MANAGER    60
DIRECTOR   55
HEAD       50
VP         45
C_LEVEL    45
```

Leadership no es lo mismo que IC seniority.

### Title-role mismatch guard

Un posting puede haber sido clasificado upstream como software/backend pero tener un título claramente incompatible con la búsqueda de ingeniería.

`MATCHING_V1` agrega un guard conservador para títulos educativos explícitos:

```text
Tutor
Instructor
Teacher
Professor
Docente
Trainer
```

Ceiling:

```text
40
```

Esto corrigió el caso observado:

```text
Tutor de trayecto educativo:
Desarrollo Backend Empresarial con Java y Spring Boot
```

que antes de calibración podía obtener un score artificialmente alto por stack.

No se modifica `OCCUPATION_V1`; el matcher contiene el falso positivo para este search profile.

### Calibración R1-R3

R1 detectó:

- stacks alternativos demasiado altos;
- Junior capaz de llegar a HIGH;
- rol educativo con Java/Spring capaz de llegar a VERY_HIGH.

R2 corrigió:

- stack alternativo explícito en title;
- Junior ceiling;
- title-role mismatch educativo.

R3 agregó:

- Architect ceiling;
- boost muy acotado para backend `UNKNOWN` con strong backend-core evidence.

No hubo R4.

R3 se congeló como:

```text
MATCHING_V1
```

### Run 83 — apply confirmado

```text
Rule version:  MATCHING_V1
Search profile: BACKEND_SOFTWARE_V1
Mode:          APPLY

Candidates:    993
Created:       993
Updated:         0
Deleted:         0

Run id:         83
Profile id:      1
```

Record kinds:

```text
ATS    892
LEAD   101
```

Match levels:

```text
VERY_HIGH    12    1.2%
HIGH         36    3.6%
MEDIUM      120   12.1%
LOW         825   83.1%
```

Por occupation/backend:

```text
IT_TECHNICAL/NOT_APPLICABLE
  LOW 137

NON_TECHNICAL/NOT_APPLICABLE
  LOW 180

SOFTWARE_ENGINEERING/BACKEND
  VERY_HIGH 12
  HIGH      16
  MEDIUM    46
  LOW        1

SOFTWARE_ENGINEERING/FULL_STACK
  HIGH      19
  MEDIUM    38
  LOW        1

SOFTWARE_ENGINEERING/NON_BACKEND
  LOW 49

SOFTWARE_ENGINEERING/UNKNOWN
  HIGH    1
  MEDIUM 36
  LOW    27

TECH_ADJACENT/NOT_APPLICABLE
  LOW 55

UNKNOWN/NOT_APPLICABLE
  LOW 375
```

Diagnostics finales:

```text
Technology penalties      94
Score ceilings           878
HIGH with 0 skill points   3
Title role mismatches       6
Title alt-stack caps       48
Title seniority risks       4
Strong backend boosts       1
```

Los 3 `HIGH` con cero skill points son deliberadamente válidos:

```text
Software Engineer Backend - (Semi Senior)   70
DESARROLLADOR BackEnd                       67
Software Engineer Backend - (Senior)        65
```

Son roles backend explícitos. La ausencia de una lista tecnológica detallada no se interpreta como falta de capacidad del candidato.

### Ejemplos del top final

```text
88.9  VERY_HIGH
Improving
Semi Senior Back-end Engineer: Java

85.0  VERY_HIGH
Bitso
Software Engineer - Latam or Europe

83.8  VERY_HIGH
Credencial Payments
Senior Backend Developer

83.5  VERY_HIGH
ITSM Consulting
Desarrollador Backend - SSR

83.5  VERY_HIGH
PlainTech Solutions
Back-end Developer Kotlin/Java
```

El top final está dominado por backend/JVM y evidencia tecnológica relevante, no por conteos indiscriminados.

### DB invariants después de apply

```text
Profile active:      1
Rows:              993
Current scope:     993
Missing:             0
Stale:               0
Duplicate keys:      0
Wrong version:       0
Invalid scores:      0
Legacy job_matches:  0
```

Rule versions:

```text
MATCHING_V1   993
```

Tracing:

```text
Run id:       83
Command:      match_jobs
Status:       SUCCESS
Step:         professional_matching
Step status:  SUCCESS
Items:        993 / 993 / 0 failed / 0 skipped
```

Validación final:

```text
PASS
```

### Refresh semantics

Futuros `--apply` deben mantener current state por profile:

```text
current geographic scope
    ↓
occupation + skills + seniority
    ↓
search profile evaluation
    ↓
upsert current matches
    ↓
delete stale matches for that profile
```

No copiar freshness ni application priority a `job_professional_matches`.

### Regla de versionado

`MATCHING_V1` ya fue persistida.

No modificar materialmente score semantics, transfer rules, ceilings o match-level thresholds manteniendo el mismo `rule_version`.

Cambios materiales futuros deben usar:

```text
MATCHING_V2
```

o posterior, con decisión explícita de recalcular.

---

## 19. Content freshness + operational/application priority v1 — TERMINADO

### Objetivo

Separar explícitamente:

```text
professional fit
```

de:

```text
what should be reviewed/applied first
```

sin degradar `MATCHING_V1` ni usar timestamps débiles como sustitutos de cambios reales.

Dos responsabilidades separadas:

```text
010_job_content_freshness.sql
→ shared job corpus freshness

011_job_operational_priorities.sql
→ search-profile-specific operational state
```

### Freshness compartido

Migration:

```text
010_job_content_freshness.sql
```

Agrega a `jobs` y `job_leads`:

```text
content_hash
content_hash_version
last_changed_at
```

Hash version:

```text
JOB_CONTENT_V1
```

Helper:

```text
src/chamba_hunter/domain/job_content.py
```

Los dos puntos comunes de escritura fueron actualizados:

```text
src/chamba_hunter/repositories/job_repository.py
src/chamba_hunter/repositories/job_lead_repository.py
```

No fue necesario modificar cada adapter ATS individual.

Regla:

```text
new record
→ write current hash
→ last_changed_at NULL

existing + same hash
→ preserve last_changed_at

existing + different hash
→ last_changed_at = seen_at
```

No usar:

```text
last_seen_at
```

como prueba de modificación.

### Baseline de hash

Repository:

```text
src/chamba_hunter/repositories/job_freshness_repository.py
```

La primera ejecución real inicializó:

```text
3662 jobs
400 job_leads
```

Todos quedaron con:

```text
content_hash_version = JOB_CONTENT_V1
```

y:

```text
last_changed_at = NULL
```

No se inventó historial previo a la existencia de esta feature.

### Operational priority

Migration:

```text
011_job_operational_priorities.sql
```

Tabla:

```text
job_operational_priorities
```

Identidad:

```text
UNIQUE(
    record_kind,
    record_id,
    search_profile_id
)
```

Soporta:

```text
ATS
LEAD
```

A diferencia de `job_professional_matches`, operational priority **retiene** filas históricas cuando una oportunidad deja de formar parte del current professional scope.

Eso permite representar:

```text
INACTIVE
SUPERSEDED
OUT_OF_SCOPE
```

sin perder el último snapshot profesional conocido.

### Archivos locales pendientes de publicación

```text
migrations/010_job_content_freshness.sql
migrations/011_job_operational_priorities.sql
src/chamba_hunter/domain/job_content.py
src/chamba_hunter/repositories/job_repository.py
src/chamba_hunter/repositories/job_lead_repository.py
src/chamba_hunter/repositories/job_freshness_repository.py
src/chamba_hunter/repositories/job_operational_priority_repository.py
src/chamba_hunter/services/job_operational_priority_service.py
src/chamba_hunter/commands/prioritize_jobs.py
```

Rule version:

```text
OPERATIONAL_PRIORITY_V1
```

Search profile:

```text
BACKEND_SOFTWARE_V1
```

### Estados operativos

```text
NEW
UPDATED
KNOWN
INACTIVE
SUPERSEDED
OUT_OF_SCOPE
```

Semántica:

#### `NEW`

No usa “últimas N horas”.

Usa como watermark:

```text
finished_at
```

del último:

```text
prioritize_jobs
status = SUCCESS
```

Entonces:

```text
first_seen_at > previous successful watermark
→ NEW
```

La primera corrida no tiene watermark anterior:

```text
initial baseline
→ KNOWN
```

Esto evita marcar artificialmente como nuevos todos los jobs existentes cuando se instala la feature.

#### `UPDATED`

```text
last_changed_at > previous successful watermark
→ UPDATED
```

No deriva `UPDATED` desde:

```text
last_seen_at
ATS jobs_updated counters
```

Si una fila previamente no accionable vuelve al current professional scope:

```text
INACTIVE / SUPERSEDED / OUT_OF_SCOPE
→ current scope again
→ UPDATED
```

#### `KNOWN`

```text
first_seen_at <= watermark
and no recorded content change after watermark
→ KNOWN
```

#### `INACTIVE`

Se usa cuando la oportunidad previamente retenida:

```text
source missing/inactive
```

o cuando:

```text
expires_at <= now
```

para una fuente que expone expiry.

#### `SUPERSEDED`

Para un `LEAD` previamente retenido cuando existe:

```text
canonical_job_id
```

y el canonical ATS job está activo.

#### `OUT_OF_SCOPE`

El source sigue activo pero ya no existe current professional match para ese search profile.

### Orden de prioridad

No se creó otro score 0–100.

El orden es lexicográfico y auditable:

```text
1. actionable before non-actionable

2. professional match level
   VERY_HIGH
   HIGH
   MEDIUM
   LOW

3. operational state
   NEW
   UPDATED
   KNOWN

4. professional score DESC

5. application channel
   DIRECT_APPLY_URL
   JOB_URL
   GENERAL_APPLICATION_URL
   PUBLIC_CONTACT
   NONE

6. first_seen_at DESC
```

Consecuencia intencional:

```text
NEW VERY_HIGH 88
> KNOWN VERY_HIGH 92
```

pero:

```text
KNOWN VERY_HIGH 92
> NEW HIGH 77
```

Freshness puede ordenar dentro del nivel profesional, pero no destruir la jerarquía profesional.

### Application channel

Orden:

```text
DIRECT_APPLY_URL
JOB_URL
GENERAL_APPLICATION_URL
PUBLIC_CONTACT
NONE
```

`apply_url` es conveniencia operacional, no professional quality.

El discovery mostró fuerte dependencia del provider, por lo que no debe dominar el ranking.

Para `GENERAL_APPLICATION_URL` y recruiting/careers email vía `public_contacts`, sólo se consideran contactos:

```text
is_active = 1
review_status = VALID
```

Tipos públicos soportados:

```text
GENERAL_APPLICATION_URL
CAREERS_EMAIL
RECRUITING_EMAIL
```

No inferir emails personales.

### `published_at`

No participa de `OPERATIONAL_PRIORITY_V1`.

Coverage observada:

```text
46 / 993
4.6%
```

y entre `HIGH`:

```text
0 / 36
```

Se preserva para reporting cuando existe.

### Dry-run aislada

La validación usó una copia temporal de la DB real.

Baseline esperado observado:

```text
Candidates: 993

NEW          0
UPDATED      0
KNOWN      993
INACTIVE     0
SUPERSEDED   0
OUT_OF_SCOPE 0
```

Application channels:

```text
DIRECT_APPLY_URL   606
JOB_URL            387
```

Hash baseline:

```text
jobs       3662
job_leads   400
```

Luego se ejercitaron cambios sintéticos sobre la copia:

```text
1 NEW
1 UPDATED
991 KNOWN
```

Además:

```text
ATS unchanged → no last_changed_at
LEAD unchanged → no last_changed_at

ATS changed → last_changed_at set
LEAD changed → last_changed_at set
```

Resultado:

```text
PASS
```

La DB real no fue modificada durante esa validación.

### Run 84 — baseline real

Primera ejecución real:

```text
Rule version:   OPERATIONAL_PRIORITY_V1
Search profile: BACKEND_SOFTWARE_V1
Mode:           APPLY
Candidates:     993
Watermark:      INITIAL BASELINE

Created:        993
Updated:          0

Run id:          84
Profile id:       1
```

Operational states:

```text
NEW               0
UPDATED           0
KNOWN           993
INACTIVE          0
SUPERSEDED        0
OUT_OF_SCOPE      0
```

States por professional match:

```text
VERY_HIGH    KNOWN 12
HIGH         KNOWN 36
MEDIUM       KNOWN 120
LOW          KNOWN 825
```

Application channels:

```text
DIRECT_APPLY_URL   606
JOB_URL            387
GENERAL_APPLICATION_URL 0
PUBLIC_CONTACT      0
NONE                0
```

Freshness invariants:

```text
jobs total                       3662
job_leads total                   400
jobs missing JOB_CONTENT_V1         0
leads missing JOB_CONTENT_V1        0
jobs last_changed_at baseline        0
leads last_changed_at baseline       0
```

Operational invariants:

```text
priority rows                    993
duplicate keys                     0
wrong priority rule version        0
wrong professional rule version    0
```

Professional snapshot preservado:

```text
VERY_HIGH   12
HIGH        36
MEDIUM     120
LOW        825
```

Tracing:

```text
Run id:       84
Command:      prioritize_jobs
Status:       SUCCESS

Step:         operational_priority
Step status:  SUCCESS
Items:        993 / 993 / 0 failed / 0 skipped
```

Validación final:

```text
PASS
```

### Refresh semantics a partir de Run 84

Run 84 constituye el primer watermark real.

Un refresh futuro debe ejecutar la cadena correspondiente:

```text
acquisition / ATS refresh
→ canonicalization
→ geography
→ occupation
→ skills
→ seniority
→ professional matching
→ operational priority
```

Entonces:

```text
new source record after Run 84
→ NEW

same record, same content hash
→ KNOWN

same record, content hash changed after Run 84
→ UPDATED

previous opportunity no longer active/current
→ retained as INACTIVE / SUPERSEDED / OUT_OF_SCOPE
```

No volver a correr `prioritize_jobs --apply` sin un refresh previo sólo para “actualizar” el watermark.

### Regla de versionado

No modificar materialmente las reglas anteriores manteniendo:

```text
JOB_CONTENT_V1
OPERATIONAL_PRIORITY_V1
```

Cambios materiales futuros deben usar nuevas versiones explícitas.

---

## 20. Shortlist / report v1 — TERMINADO

### Objetivo

Convertir el estado persistido de:

```text
job_operational_priorities
+
job_professional_matches
```

en una salida local cómoda para:

```text
review
prioritization
manual application
```

sin recalcular matching, freshness ni operational priority.

### Discovery real

Estado usado:

```text
Run 84
OPERATIONAL_PRIORITY_V1
```

Rows:

```text
993
```

Estados:

```text
NEW            0
UPDATED        0
KNOWN        993
INACTIVE       0
SUPERSEDED     0
OUT_OF_SCOPE   0
```

Professional levels:

```text
VERY_HIGH   12
HIGH        36
MEDIUM     120
LOW        825
```

Application channels:

```text
DIRECT_APPLY_URL   606
JOB_URL            387
GENERAL_APPLICATION_URL 0
PUBLIC_CONTACT      0
NONE                0
```

High value:

```text
VERY_HIGH + HIGH = 48
```

Current applications:

```text
0
```

No se deduplica automáticamente.

Discovery observó:

```text
31 exact company+title duplicate groups
32 normalized company+title duplicate groups
```

Los IDs/URLs pueden representar postings distintos, regiones distintas o variantes reales.

Por eso el reporte sólo expone:

```text
Same-title Count
```

como señal informativa.

### Decisión de formato

Formato V1:

```text
XLSX
```

Razones:

- múltiples vistas lógicas;
- URLs clickeables;
- filters/sorting;
- evidencia profesional ancha;
- mejor workflow manual que CSV;
- sólo 993 rows actuales, por lo que XLSX es suficientemente pequeño.

Dependencia nueva:

```text
openpyxl>=3.1,<4
```

en:

```text
pyproject.toml
```

### Archivos del slice

```text
pyproject.toml
src/chamba_hunter/commands/export_shortlist.py
src/chamba_hunter/repositories/job_shortlist_report_repository.py
src/chamba_hunter/services/job_shortlist_report_service.py
```

Report version:

```text
SHORTLIST_REPORT_V1
```

Default search profile:

```text
BACKEND_SOFTWARE_V1
```

Default output:

```text
output/chamba-shortlist.xlsx
```

`output/` ya está ignorado por Git.

### Repository de reporting

```text
JobShortlistReportRepository
```

Es read-only.

Lee:

```text
search_profiles
job_operational_priorities
job_professional_matches
applications
runs
```

No crea:

```text
runs
run_steps
DB writes
```

El source run del workbook se deriva del:

```text
evaluated_run_id
```

persistido en `job_operational_priorities` del profile.

No usa simplemente “latest global prioritize run” como sustituto del snapshot realmente exportado.

### Application tracking en reporte

El reporte originalmente soportaba tracking sólo por `applications.job_id`.

El slice posterior de application tracking generalizó la identidad a:

```text
record_kind
record_id
```

por lo que `SHORTLIST_REPORT_V1` ahora puede mostrar el tracking de:

```text
ATS
LEAD
```

sin cambiar la semántica del reporte.

Campos mostrados:

```text
application_type
status
applied_at
updated_at
```

Compatibilidad:

```text
ATS
→ record_kind = ATS
→ record_id = jobs.id
→ job_id = jobs.id

LEAD
→ record_kind = LEAD
→ record_id = job_leads.id
→ job_id = NULL
```

Actualmente:

```text
applications rows = 0
```

El workbook sigue siendo read-only y no crea ni modifica application tracking.

### Workbook

Hojas:

```text
Overview
Focus
High Value
All Current
History
```

#### Overview

Incluye:

```text
report version
search profile
source priority run
source run timestamp
generation timestamp
priority rule
professional rule
counts
links a las hojas
notas de semántica
```

#### Focus

Semántica:

```text
NEW or UPDATED
+
VERY_HIGH or HIGH
```

Es la cola primaria después de refreshes futuros.

En el baseline Run 84:

```text
0 rows
```

#### High Value

```text
all current VERY_HIGH / HIGH
```

Baseline:

```text
48 rows
```

#### All Current

```text
all actionable
NEW / UPDATED / KNOWN
```

Baseline:

```text
993 rows
```

#### History

```text
INACTIVE
SUPERSEDED
OUT_OF_SCOPE
```

Baseline:

```text
0 rows
```

### Orden

El reporte reutiliza el orden de operational priority.

No introduce un score nuevo.

Orden:

```text
actionable
→ professional match level
→ operational state
→ professional score DESC
→ application channel
→ first_seen_at DESC
```

### Columnas

Bloque visible principal:

```text
Priority Rank
Operational State
Match Level
Professional Score
Company
Title
Origin / Provider
Application Channel
Open
Tracked Status
First Seen
Last Changed
Published At
Same-title Count
```

Evidencia profesional:

```text
Occupation
Backend Relevance
Seniority
Leadership
Role Pts
Skills Pts
Seniority Pts
Leadership Pts
Tech Penalty
Score Ceiling
Exact Skills
Peer Skills
Related Skills
Secondary Skills
Alternate Stack
Ceiling Reasons
```

Tracking/identidad/URLs:

```text
Application Type
Applied At
Record Kind
Record ID
Application Target
Job URL
Apply URL
```

### Validación real

Workbook generado:

```text
output/chamba-shortlist.xlsx
```

Size observado:

```text
283966 bytes
```

Sheets observadas:

```text
Overview
Focus
High Value
All Current
History
```

Rows:

```text
Focus          0
High Value    48
All Current  993
History        0
```

Hyperlinks:

```text
High Value    48
All Current  993
```

Top row:

```text
Improving
Semi Senior Back-end Engineer: Java
88.9
```

Duplicate signal:

```text
max Same-title Count = 8
```

DB read-only invariant:

```text
runs before = 84
runs after  = 84
latest prioritize_jobs = 84
```

No formulas fueron necesarias.

No hubo errores de fórmula.

### Nota sobre el falso fallo del validator

El validator local terminó con:

```text
FAILED
- unexpected overview title
```

Ese resultado fue un falso negativo del runner.

El workbook real contiene exactamente:

```text
Chamba Hunter — Shortlist
```

en:

```text
Overview!A1
```

La causa fue Windows PowerShell 5.1 interpretando un `.ps1` UTF-8 sin BOM como ANSI y corrompiendo el em dash de la **cadena esperada del validator**.

No fue un defecto del workbook.

Todos los otros invariantes del validator pasaron y el workbook fue inspeccionado directamente después.

No es necesario volver a correr validation.

### Regla para futuros `.ps1`

Por preferencia operativa del usuario:

```text
cuando se entregue un único .ps1
→ entregarlo dentro de un ZIP
```

Esto evita que el navegador abra el script en panel lateral.

También preferir bloques:

```powershell
@'
...
'@ | python -
```

frente a `python -c` con SQL/quotes complejos.

---

## 21. Manual application tracking + refresh workflow v1 — TERMINADO

### Discovery

El discovery confirmó que el gap de tracking era material:

```text
ALL ACTIONABLE
  ATS    892
  LEAD   101

VERY_HIGH/HIGH
  ATS     28
  LEAD    20
```

Los 101 LEAD accionables tenían:

```text
canonical_job_id = NULL
```

incluidos los 20 LEAD `VERY_HIGH/HIGH`.

Por lo tanto, `applications.job_id` no podía identificar correctamente todas las oportunidades que ya aparecían en el shortlist.

La tabla estaba vacía:

```text
applications rows = 0
```

y no existía repository/command de application tracking.

### Migration 012

Archivo:

```text
migrations/012_application_opportunity_identity.sql
```

Agrega:

```text
record_kind
record_id
```

a:

```text
applications
```

Valores permitidos para job opportunities:

```text
ATS
LEAD
```

Compatibilidad:

```text
ATS
→ record_kind = ATS
→ record_id = jobs.id
→ job_id = jobs.id

LEAD
→ record_kind = LEAD
→ record_id = job_leads.id
→ job_id = NULL
```

Los campos legacy:

```text
job_id
public_contact_id
```

se conservan.

No se hizo una migración destructiva.

### Invariantes DB

Migration 012 agrega:

```text
idx_applications_record
uq_applications_job_opportunity
```

La unique parcial garantiza un único row actual de tracking por:

```text
application_type = JOB
+
record_kind
+
record_id
```

También agrega triggers que:

- exigen `record_kind + record_id` para `application_type = JOB`;
- verifican que el source ATS/LEAD exista;
- exigen `ATS job_id == record_id`;
- impiden `job_id` en LEAD.

Rows JOB existentes con `job_id` pueden backfillearse a:

```text
record_kind = ATS
record_id = job_id
```

### Enums

No fue necesario crear nuevos estados.

Se reutilizan:

```text
PENDING
APPLIED
SENT
INTERVIEW
REJECTED
WITHDRAWN
NO_RESPONSE
```

Application types existentes:

```text
JOB
SPONTANEOUS_EMAIL
GENERAL_APPLICATION
```

Este slice sólo agrega el workflow manual de `JOB`.

### Repository/service

Archivos:

```text
src/chamba_hunter/repositories/application_repository.py
src/chamba_hunter/services/application_tracking_service.py
```

Responsabilidad:

```text
resolve opportunity
→ read current tracking
→ create/update one JOB application row
```

No crea tracing runs.

No toca matching ni operational priority.

### CLI manual

Archivo:

```text
src/chamba_hunter/commands/track_application.py
```

Uso conceptual:

```powershell
python -m chamba_hunter.commands.track_application `
    --record-kind LEAD `
    --record-id 168 `
    --status APPLIED
```

o:

```powershell
python -m chamba_hunter.commands.track_application `
    --record-kind ATS `
    --record-id 8 `
    --status INTERVIEW
```

`--notes` es opcional.

Si se omite:

```text
existing notes are preserved
```

Si se pasa vacío:

```text
notes are cleared
```

Semántica de `applied_at`:

```text
first transition to APPLIED
→ set applied_at

later status changes
→ preserve applied_at
```

Semántica de `last_status_at`:

```text
status changes
→ now

same status re-written
→ preserve existing last_status_at
```

### Shortlist integration

Archivo modificado:

```text
src/chamba_hunter/repositories/job_shortlist_report_repository.py
```

El reporte ahora hace join de tracking por:

```text
(record_kind, record_id)
```

cuando migration 012 está disponible.

También conserva fallback legacy ATS-only si se abre una DB pre-012.

No se cambió:

```text
SHORTLIST_REPORT_V1
```

ni su ranking.

`Focus` tampoco excluye automáticamente oportunidades aplicadas.

Razón:

```text
freshness / professional priority
!=
manual application state
```

El estado manual queda visible y filtrable en:

```text
Tracked Status
Application Type
Applied At
```

### Dry-run aislado

Se validó sobre una copia SQLite real.

Caso ATS:

```text
ATS 8
PENDING
→ APPLIED

job_id = 8
record_kind = ATS
record_id = 8
```

Caso LEAD:

```text
LEAD 168
APPLIED

job_id = NULL
record_kind = LEAD
record_id = 168
```

Resultado:

```text
Migration 012             PASS
JOB application rows      2
duplicate opportunity     0
ATS tracking in XLSX      PASS
LEAD tracking in XLSX     PASS
All Current rows          993
```

La DB real quedó intacta durante ese dry-run.

### Apply real de migration 012

Migration aplicada sobre la DB real.

Validación:

```text
Migration 012                         1
record_kind/record_id columns         yes
unique opportunity index             yes
identity triggers                     4 / 4
runs before/after                     84 / 84
applications before/after              0 / 0
```

El XLSX baseline continuó:

```text
Focus          0
High Value    48
All Current  993
History        0
```

---

## 22. End-to-end refresh v1 — TERMINADO

### Objetivo

Componer los commands ya existentes sin duplicar reglas de negocio.

Archivo:

```text
src/chamba_hunter/commands/refresh_search.py
```

Sin `--apply`:

```text
PLAN ONLY
```

No ejecuta nada.

Con:

```text
--apply
```

ejecuta secuencialmente:

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

El wrapper usa subprocesses de los commands existentes.

No duplica repositories/services ni reglas de clasificación.

Si un step retorna non-zero:

```text
refresh stops
```

Los runs ya persistidos por steps anteriores quedan como evidencia real del intento.

### Opciones

```text
--skip-broad
--skip-ats
--skip-export
--discover-broad-ats-limit N
--himalayas-max-jobs N
--getonboard-max-pages N
--output PATH
```

`discover_broad_ats` está deshabilitado por default en el refresh rutinario:

```text
--discover-broad-ats-limit 0
```

Esto separa:

```text
routine refresh
```

de:

```text
careers/ATS discovery for new broad companies
```

que tiene otra semántica y costo.

### Primer refresh real post-baseline

Baseline anterior:

```text
Run 84
finished_at 2026-08-08T22:41:13.367176Z
```

Primer refresh end-to-end real:

```text
Runs 85–99
```

Todos terminaron:

```text
SUCCESS
```

Secuencia:

```text
85 acquire_broad_jobs
86 sync_greenhouse_jobs
87 sync_lever_jobs
88 sync_ashby_jobs
89 sync_workable_jobs
90 sync_smartrecruiters_jobs
91 sync_bamboohr_jobs
92 sync_hiringroom_jobs
93 canonicalize_job_leads
94 classify_argentina_eligibility
95 classify_job_occupations
96 classify_job_skills
97 classify_job_seniority
98 match_jobs
99 prioritize_jobs
```

El export XLSX no crea run.

### Broad acquisition Run 85

```text
HIMALAYAS received 500
GETONBOARD received 339

received total   839
created          639
updated          200
```

Después de adquisición:

```text
active unresolved leads   1016
raw active candidates     4678
```

### ATS sync Runs 86–92

Todos los boards/sites/tenants procesados terminaron correctamente.

Snapshot activo:

```text
GREENHOUSE       1659
LEVER            1139
HIRINGROOM        485
SMARTRECRUITERS   197
ASHBY              90
WORKABLE           65
BAMBOOHR           24
----------------------
ATS ACTIVE       3659
```

Greenhouse:

```text
created       2
deactivated   5
```

Los demás providers:

```text
created       0
deactivated   0
```

### Canonicalization Run 93

```text
Total       1016
Resolved      11
Ambiguous      3
Unmatched   1002
Applied       11
```

### Argentina Run 94

```text
Total        4664
Eligible      849
Ineligible   3544
Unknown       271
```

Nuevo downstream scope:

```text
ELIGIBLE + UNKNOWN = 1120
```

### Occupation Run 95

```text
Total          1120
Software        311
IT technical    142
Tech adjacent    59
Non technical   189
Unknown         419
```

Software backend relevance:

```text
BACKEND       94
FULL_STACK    95
NON_BACKEND   54
UNKNOWN       68
```

### Skills Run 96

```text
Candidates      1120
With skills      604
No skills        516
Skill rows       3298
```

### Seniority Run 97

```text
Candidates      1120

UNKNOWN          804
SENIOR           191
MID               39
LEAD              32
JUNIOR            22
STAFF             10
ENTRY              9
PRINCIPAL          9
INTERN             4
```

### Matching Run 98

```text
Candidates     1120
ATS             892
LEAD            228

VERY_HIGH        14
HIGH             68
MEDIUM          145
LOW             893
```

### Operational priority Run 99

Watermark:

```text
2026-08-08T22:41:13.367176Z
```

Persisted rows:

```text
1120
```

Estados:

```text
NEW            127
UPDATED          0
KNOWN          993
INACTIVE         0
SUPERSEDED       0
OUT_OF_SCOPE     0
```

Por match:

```text
VERY_HIGH
  NEW      2
  KNOWN   12

HIGH
  NEW     32
  KNOWN   36

MEDIUM
  NEW     25
  KNOWN  120

LOW
  NEW     68
  KNOWN  825
```

Channels:

```text
DIRECT_APPLY_URL   606
JOB_URL            514
```

El hecho de que:

```text
UPDATED = 0
```

es válido: los sync counters `updated` significan re-observación/escritura de rows existentes; `UPDATED` operacional sólo se activa por `JOB_CONTENT_V1 last_changed_at` posterior al watermark.

### Shortlist post-refresh

Workbook:

```text
output/chamba-shortlist.xlsx
```

Source priority run:

```text
99
```

Views:

```text
Focus          34
High Value     82
All Current  1120
History         0
```

`Focus = 34` corresponde exactamente a:

```text
NEW/UPDATED
+
VERY_HIGH/HIGH
```

En esta corrida:

```text
2 NEW VERY_HIGH
32 NEW HIGH
0 UPDATED high-value
```

Applications:

```text
0
```

El refresh no modificó tracking manual.

### Acceptance

```text
refresh exit code      0
runs before/after      84 → 99
applications           0 → 0
latest priority        Run 99 SUCCESS
workbook source run    99
result                 PASS
```

---

## 23. Workflow operativo actual

### Refresh rutinario

Para ver plan:

```powershell
python -m chamba_hunter.commands.refresh_search
```

Para ejecutar:

```powershell
python -m chamba_hunter.commands.refresh_search --apply
```

El command finaliza regenerando:

```text
output/chamba-shortlist.xlsx
```

### Review

Abrir:

```text
output/chamba-shortlist.xlsx
```

Orden recomendado:

```text
Focus
→ High Value
→ All Current
```

`Focus` es la cola de oportunidades nuevas/actualizadas de alto valor.

### Registrar una aplicación real

Tomar desde XLSX:

```text
Record Kind
Record ID
```

y ejecutar:

```powershell
python -m chamba_hunter.commands.track_application `
    --record-kind <ATS|LEAD> `
    --record-id <ID> `
    --status APPLIED
```

Luego regenerar el XLSX:

```powershell
python -m chamba_hunter.commands.export_shortlist
```

El nuevo status aparece en:

```text
Tracked Status
Application Type
Applied At
```

### Cambiar estado

Ejemplo conceptual:

```text
APPLIED
→ INTERVIEW
→ REJECTED
```

Se actualiza el mismo row de oportunidad.

No se crea una fila histórica por cada transición en V1.

### Principios preservados

- no auto-apply;
- no auto-email;
- no inferir recruiter emails;
- no web UI;
- DB es source of truth;
- XLSX es read-only;
- application tracking no altera professional matching;
- application tracking no altera operational priority;
- refresh no modifica applications;
- rediscovery ATS no corre automáticamente salvo flag explícito.

---

## 24. Checklist antes de publicar application tracking + refresh

Después de limpiar scripts temporales, el worktree esperado es:

```text
M  docs/PROJECT_CONTEXT.md
M  src/chamba_hunter/repositories/job_shortlist_report_repository.py
?? migrations/012_application_opportunity_identity.sql
?? src/chamba_hunter/commands/refresh_search.py
?? src/chamba_hunter/commands/track_application.py
?? src/chamba_hunter/repositories/application_repository.py
?? src/chamba_hunter/services/application_tracking_service.py
```

No versionar:

```text
application-refresh-discovery.ps1
application-refresh-v1-dry-run.ps1
application-refresh-v1-dry-run-fixed.ps1
application-refresh-v1-apply-and-validate.ps1
application-refresh-v1-real-refresh.ps1
application-refresh-discovery.txt
application-refresh-v1-dry-run.txt
application-refresh-v1-apply-validation.txt
application-refresh-v1-real-refresh.txt
```

Los `.txt` root ya están ignorados.

`output/` ya está ignorado.

Conservar localmente:

```text
output/chamba-shortlist.xlsx
```

Validación mínima antes de commit:

```powershell
python -m compileall -q src
git diff --check
git diff --stat
git status --short
```

No volver a ejecutar `refresh_search --apply` sólo para validar: hacerlo movería nuevamente el watermark y dejaría de ser una validación neutra.

El usuario decide y ejecuta commit/push manualmente.

---

## 25. Prompt operativo para nueva conversación

```text
Repositorio: Gtestino92/chamba-hunter
Base: main

Primero:
- verificar HEAD real y últimos commits;
- leer docs/PROJECT_CONTEXT.md completo;
- confirmar si application tracking + refresh v1 ya fue publicado;
- código/GitHub es source of truth;
- DB local observada más reciente después del primer refresh end-to-end: Run 99 OPERATIONAL_PRIORITY_V1 SUCCESS;
- migration 012 está aplicada localmente;
- applications rows observadas: 0;
- current shortlist: Focus 34, High Value 82, All Current 1120, History 0;
- preservar ARGENTINA_V1, OCCUPATION_V1, SKILLS_V1, SENIORITY_V1, MATCHING_V1, JOB_CONTENT_V1, OPERATIONAL_PRIORITY_V1 y SHORTLIST_REPORT_V1;
- application tracking usa (record_kind, record_id) y soporta ATS + LEAD;
- ATS conserva job_id; LEAD usa job_id NULL;
- refresh_search compone los existing commands y es PLAN ONLY sin --apply;
- no ejecutar refresh real sólo para comprobar código porque movería el watermark;
- no auto-apply;
- no auto-email;
- no inferir emails personales;
- no web UI;
- próximo trabajo debe surgir del uso operativo real, no de una generalización preventiva;
- revisar Focus primero y registrar aplicaciones reales con track_application;
- si aparece una necesidad nueva, hacer discovery contra código/DB actual antes de cambiar schema;
- cuando se entregue un único .ps1, empaquetarlo en ZIP;
- no evasión anti-bot.
```
