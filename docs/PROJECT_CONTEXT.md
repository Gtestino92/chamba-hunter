# Chamba Hunter — Project Context / Handoff operativo

**Fecha de actualización:** 2026-08-08  
**Repositorio:** `Gtestino92/chamba-hunter`  
**Rama operativa:** `main`

## Estado actual de GitHub y worktree

Último `main` confirmado en GitHub durante esta sesión:

```text
d7b6552f9a4ad0b431eec3246889af29f040a4fe
update context
```

Ese `main` ya contiene:

- Hiring Room;
- cross-source canonicalization v1;
- Argentina eligibility v1;
- occupation / IT / backend classification v1;
- skills classification v1;
- migraciones `004`, `005`, `006` y `007`;
- la consideración futura de reusable `search_profiles`;
- limpieza de artefactos locales históricos `.zip` / `.txt`.

El trabajo de **seniority classification v1** fue implementado, validado y aplicado sobre la DB local después de ese commit y todavía está pendiente de publicación en GitHub.

Estado local esperado antes de publicar seniority:

```text
M  docs/PROJECT_CONTEXT.md
?? migrations/008_job_seniority_classifications.sql
?? src/chamba_hunter/commands/classify_job_seniority.py
?? src/chamba_hunter/repositories/job_seniority_repository.py
?? src/chamba_hunter/services/job_seniority_classification_service.py
```

La DB SQLite local contiene los resultados persistidos de:

```text
Run 81
SKILLS_V1

Run 82
SENIORITY_V1
```

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
professional matching                      ← PRÓXIMO VERTICAL
    ↓
operational / application priority
    ↓
shortlist / Excel report / manual action
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

---

## 4. Perfil profesional objetivo futuro

Este perfil se usa más adelante para matching, no para adquisición ni para decidir si una skill existe en una vacante:

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
```

Migración local implementada y aplicada, pendiente de publicación:

```text
008_job_seniority_classifications.sql
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
job_skill_classifications
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

Estos números son DB local observada y pueden cambiar.

### Semántica importante de freshness

`JobRepository.sync_board_jobs()` actualmente:

- crea nuevos jobs con `first_seen_at = last_seen_at = seen_at`;
- para un `external_id` existente actualiza contenido y `last_seen_at`;
- vuelve a marcar `is_active = 1`;
- cuenta ese registro como `updated` aunque el contenido no haya cambiado;
- desactiva IDs activos ausentes de un snapshot ATS completo.

Por lo tanto:

```text
updated
```

no significa necesariamente “contenido modificado”, y:

```text
last_seen_at
```

significa “observado nuevamente”, no “cambió”.

Broad `JobLeadRepository.upsert_source_jobs()` también actualiza `last_seen_at` para existentes, pero ausencia broad no implica cierre.

Actualmente no existe:

```text
last_changed_at
content_hash
per-job change history
```

No resolver esto dentro de skills ni seniority.

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
Run 76
Tenants:       28
Succeeded:     28
Failed:         0
Jobs received: 485
Created:       213
Updated:       272
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

Professional match podrá considerar:

```text
occupation/backend
skills
skill transferability
seniority
otras señales profesionales
```

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

### Archivos locales implementados y aplicados

Pendientes de publicación al momento de este handoff:

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

## 18. Próximo vertical: professional matching

### Estado

NO implementado todavía.

Pipeline inmediato:

```text
geography
    ↓
occupation/backend
    ↓
skills
    ↓
seniority
    ↓
professional matching      ← NEXT
    ↓
operational/application priority
```

### Objetivo

Evaluar qué tan bien cada job representa una oportunidad profesional para el search profile backend actual, sin destruir ni reinterpretar las clasificaciones objetivas anteriores.

Matching es la primera capa que debe comparar explícitamente:

```text
job understanding
```

contra:

```text
search profile
```

Para el perfil backend actual podrá considerar, entre otras señales:

```text
occupation/backend relevance
skills
skill transferability
seniority
experience-year evidence
possibly role/domain evidence
```

### Principios de diseño

Antes de fijar score/schema:

1. inspeccionar la distribución real combinada de occupation + backend + skills + seniority;
2. medir cuántos candidatos sobreviven bajo distintas políticas, sin hard cuts prematuros;
3. diseñar explícitamente la representación del `BACKEND_SOFTWARE_PROFILE`;
4. distinguir señales positivas, negativas e inciertas;
5. preservar `UNKNOWN`;
6. diseñar skill relations curadas;
7. separar score profesional de prioridad operacional.

No usar una skill requerida ausente como rechazo automático.

Ejemplo:

```text
job requires Azure
profile has strong AWS

NO:
→ automatic rejection

SÍ:
→ exact match absent
→ cloud peer/transfer signal present
→ combine with other evidence
```

Skill relations futuras deberán distinguir al menos:

```text
EXACT
PEER / PARTIALLY SUBSTITUTABLE
RELATED ECOSYSTEM
```

Ejemplos conceptuales:

```text
AWS ↔ Azure ↔ GCP
Java ↔ Kotlin
PostgreSQL ↔ MySQL / SQL Server
Kafka ↔ RabbitMQ
Spring Boot ↔ Quarkus / Micronaut
Docker → Kubernetes
Java → Spring ecosystem
```

No asumir que pertenecer a una familia implica sustituibilidad completa.

### Seniority en matching

El target profesional actual es aproximadamente:

```text
semisenior / mid-level
```

pero:

- `MID` puede ser señal positiva fuerte;
- `UNKNOWN` no debe ser rechazo;
- `SENIOR` puede seguir siendo oportunidad viable según el resto de evidencia;
- `JUNIOR`, `STAFF`, `PRINCIPAL`, `LEAD` requieren tratamiento ponderado, no necesariamente hard cuts;
- leadership/management debe mantenerse separado de IC seniority;
- años explícitos pueden complementar, no reemplazar, la clase.

No decidir todavía pesos finales sin discovery real.

---

## 19. Restricciones para professional matching

- No ampliar acquisition sin necesidad concreta.
- No hacer más Hiring Room discovery manual por ahora.
- No implementar Bumeran/ZonaJobs con evasión anti-bot.
- No eliminar geographic `INELIGIBLE`.
- No asumir geography `UNKNOWN` como `ELIGIBLE`.
- No eliminar occupation `UNKNOWN`.
- No tratar `backend_relevance=UNKNOWN` como rechazo.
- No modificar materialmente `OCCUPATION_V1`; usar `OCCUPATION_V2`.
- No modificar materialmente `SKILLS_V1`; usar `SKILLS_V2`.
- No modificar materialmente `SENIORITY_V1`; usar `SENIORITY_V2`.
- No convertir una skill ausente en hard rejection.
- No convertir `REQUIRED` tecnológico en hard rejection automático.
- No asumir equivalencia exacta entre tecnologías reemplazables.
- No convertir seniority `UNKNOWN` en rechazo.
- No convertir años de experiencia en una escala rígida automática.
- No mezclar professional match con operational priority.
- No incorporar freshness en el professional match score salvo decisión explícita y justificada.
- No cambiar ATS snapshot semantics.
- No tocar auto-apply.
- No agregar UI.
- No sobrearquitecturar reusable search profiles antes de necesidad real.

---

## 20. Runs y estados actuales

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
81 skills classification apply
82 seniority classification apply
```

Estados actuales:

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

SKILLS_V1
  scope                  993
  candidates with skills 512
  candidates no skills   481
  skill rows            2664
  duplicate keys           0
  invalid evidence         0
  stale                    0
  wrong rule version       0

SENIORITY_V1
  scope             993
  unknown           724
  senior            158
  mid                33
  lead               30
  junior             19
  staff               9
  entry               8
  principal           8
  intern              4
  missing             0
  stale               0
  duplicate keys      0
  wrong rule version  0
```

Run 82 es el último estado persistido de clasificación confirmado.

---

## 21. Checklist antes de publicar seniority

El worktree debería contener:

```text
migrations/008_job_seniority_classifications.sql

src/chamba_hunter/repositories/job_seniority_repository.py
src/chamba_hunter/services/job_seniority_classification_service.py
src/chamba_hunter/commands/classify_job_seniority.py

docs/PROJECT_CONTEXT.md
```

No versionar diagnósticos temporales:

```text
seniority-v1-dry-run.txt
seniority-v1-r2-dry-run.txt
seniority-v1-r3-dry-run.txt
seniority-v1-description-audit.txt
seniority-v1-apply.txt
```

Root `.txt` ya está ignorado por `.gitignore`.

Antes de commit/push:

```powershell
python -m compileall -q src

git add -N -- `
    "migrations/008_job_seniority_classifications.sql" `
    "src/chamba_hunter/commands/classify_job_seniority.py" `
    "src/chamba_hunter/repositories/job_seniority_repository.py" `
    "src/chamba_hunter/services/job_seniority_classification_service.py"

git diff --check

git reset -- `
    "migrations/008_job_seniority_classifications.sql" `
    "src/chamba_hunter/commands/classify_job_seniority.py" `
    "src/chamba_hunter/repositories/job_seniority_repository.py" `
    "src/chamba_hunter/services/job_seniority_classification_service.py"

git diff --stat
git status --short
```

El usuario decide y ejecuta commit/push manualmente.

---

## 22. Prompt operativo para nueva conversación

```text
Repositorio: Gtestino92/chamba-hunter
Base: main

Primero:
- verificar HEAD y últimos commits reales en GitHub;
- leer docs/PROJECT_CONTEXT.md completo;
- confirmar si migration 008 y seniority repository/service/command ya están publicados;
- distinguir GitHub code vs DB local observed state;
- no asumir que conteos históricos siguen vigentes;
- inspeccionar código real de geography, occupation, skills y seniority;
- no modificar código todavía;
- preparar discovery del siguiente vertical: professional matching;
- preservar geography UNKNOWN, occupation UNKNOWN, backend_relevance UNKNOWN y seniority UNKNOWN;
- no usar skills faltantes ni tecnologías required como hard cuts;
- diseñar skill transferability de forma curada;
- tratar años de experiencia como evidencia, no escala universal;
- usar el perfil backend actual sólo en matching;
- no mezclar professional match con freshness/operational priority;
- preservar first_seen_at / last_seen_at / published_at / active state / URLs;
- mantener la consideración futura de reusable search_profiles sin sobrearquitectura preventiva.
```
