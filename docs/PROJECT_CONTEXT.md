# Chamba Hunter — Project Context / Handoff operativo

**Fecha de actualización:** 2026-08-08  
**Repositorio:** `Gtestino92/chamba-hunter`  
**Rama operativa:** `main`

## Estado actual de GitHub y worktree

Último `main` confirmado en GitHub durante esta sesión:

```text
ad9f92222630893cd97e7a75abb48ec197670f79
seniority
```

Ese `main` ya contiene:

- Hiring Room;
- cross-source canonicalization v1;
- Argentina eligibility v1;
- occupation / IT / backend classification v1;
- skills classification v1;
- seniority classification v1;
- migraciones `004`, `005`, `006`, `007` y `008`;
- limpieza de artefactos locales históricos `.zip` / `.txt`.

El trabajo de **professional matching v1** fue implementado, calibrado, aplicado y validado sobre la DB local después de ese commit y todavía está pendiente de publicación en GitHub.

Estado local esperado antes de publicar matching:

```text
M  docs/PROJECT_CONTEXT.md
?? migrations/009_job_professional_matches.sql
?? src/chamba_hunter/commands/match_jobs.py
?? src/chamba_hunter/repositories/job_matching_repository.py
?? src/chamba_hunter/services/job_matching_service.py
```

La DB SQLite local contiene los últimos resultados persistidos de evaluación:

```text
Run 81
SKILLS_V1

Run 82
SENIORITY_V1

Run 83
MATCHING_V1
BACKEND_SOFTWARE_V1
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
professional matching
    ↓
operational / application priority          ← PRÓXIMO VERTICAL
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
```

Migración local implementada y aplicada, pendiente de publicación:

```text
009_job_professional_matches.sql
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
job_seniority_classifications
job_professional_matches
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

## 19. Próximo vertical: operational / application priority

### Estado

NO implementado todavía.

Este es el **último vertical lógico** antes de generar el shortlist/reporte accionable.

Pipeline inmediato:

```text
professional matching
    ↓
operational / application priority      ← NEXT
    ↓
shortlist / Excel report
    ↓
manual application / outreach
```

### Objetivo

Ordenar las oportunidades ya evaluadas profesionalmente según **qué conviene revisar/aplicar primero**, sin modificar el professional match.

Debe responder preguntas como:

```text
¿es nueva?
¿cuándo la vimos por primera vez?
¿sigue activa?
¿tiene apply URL directo?
¿qué tan confiable es published_at?
¿es HIGH/VERY_HIGH profesionalmente?
¿ya era conocida?
¿cambió realmente?
```

### Señales ya disponibles

Por candidate:

```text
first_seen_at
last_seen_at
published_at
is_active
job_url
apply_url
```

En el scope observado:

```text
first_seen_at   993 / 993  100.0%
last_seen_at    993 / 993  100.0%
job_url         993 / 993  100.0%
apply_url       606 / 993   61.0%
published_at     46 / 993    4.6%
```

Por lo tanto:

```text
first_seen_at
```

es la señal más sólida para NEW.

`published_at` es complementaria y sólo debe pesar cuando exista y sea confiable.

### Estados operativos mínimos

Diseñar al menos:

```text
NEW
KNOWN
UPDATED
CLOSED / INACTIVE
```

pero no inventar `UPDATED` desde `last_seen_at`.

El sync actual cuenta muchos records como `updated` aunque sólo hayan sido vistos nuevamente.

Por eso:

```text
last_seen_at
!=
last_changed_at
```

### NEW

La definición de NEW debe basarse en estado del sistema, no sólo en antigüedad publicada.

Punto de partida:

```text
first_seen_at
```

El diseño debe resolver explícitamente la ventana/semántica de:

```text
NEW
```

para refreshes manuales sucesivos.

No fijar una ventana arbitraria sin inspeccionar el flujo real de refresh.

### UPDATED

Actualmente no existe evidencia suficiente para afirmar cambios reales de contenido.

Antes de etiquetar `UPDATED` de forma fuerte, evaluar si hace falta introducir:

```text
content_hash
last_changed_at
change history / event
```

Esto es un problema de freshness, no de matching.

### Application channel quality

Orden conceptual actual:

```text
1. apply_url directo
2. job_url / careers page
3. general_application_url
4. public recruiting/careers email
```

Para los 993 candidatos actuales:

```text
job_url    993
apply_url  606
```

La prioridad puede usar calidad del canal, pero no debe convertir ausencia de `apply_url` en descarte.

### Professional score como input

Operational priority puede usar:

```text
professional score
match_level
```

como una señal importante, pero no debe recalcular el professional fit.

Ejemplo:

```text
match 88 + NEW + direct apply
```

puede ordenarse antes que:

```text
match 92 + KNOWN + older discovery
```

sin cambiar ninguno de los dos match scores.

### Salida deseada

El end game debe poder mostrar rápidamente:

```text
NEW + VERY_HIGH
NEW + HIGH
KNOWN + VERY_HIGH
KNOWN + HIGH
```

con:

```text
company
title
match score
match reasons
first_seen_at
published_at when available
application channel
job/apply URL
```

y después producir el shortlist/reporte.

### Discovery antes de implementar

Antes de fijar score/schema de operational priority:

1. inspeccionar distribución real de `first_seen_at` en los 993;
2. distinguir qué timestamps vienen de ATS vs broad leads;
3. inspeccionar `published_at` por provider;
4. medir direct `apply_url` por match level;
5. revisar cómo se ejecutaría un refresh manual completo hoy;
6. decidir si `NEW` necesita estado persistido entre refreshes o puede derivarse de una referencia de run;
7. estudiar si `UPDATED` requiere `content_hash` / `last_changed_at`;
8. decidir si operational priority necesita tabla persistida o puede ser una proyección/reporting layer;
9. preservar CLOSED/INACTIVE sin mezclarlos con match score.

No implementar todavía antes de ese discovery.

---

## 20. Restricciones para operational priority

- No modificar materialmente `ARGENTINA_V1`; usar versión nueva si hiciera falta.
- No modificar materialmente `OCCUPATION_V1`.
- No modificar materialmente `SKILLS_V1`.
- No modificar materialmente `SENIORITY_V1`.
- No modificar materialmente `MATCHING_V1`; usar `MATCHING_V2`.
- No introducir freshness dentro de `job_professional_matches`.
- No usar `last_seen_at` como prueba de cambio.
- No llamar `UPDATED` a todo registro que el ATS sync reporte como updated.
- No depender de `published_at` porque su cobertura actual es baja.
- No convertir ausencia de direct `apply_url` en rechazo.
- No borrar CLOSED/INACTIVE del corpus histórico.
- No mezclar operational priority con professional score semantics.
- No agregar auto-apply.
- No agregar UI/web API todavía.
- No hacer scraping evasivo para obtener mejores timestamps o apply URLs.
- No ampliar acquisition como parte de este vertical salvo defecto concreto que bloquee el objetivo.
- No sobrearquitecturar múltiples search profiles durante este vertical.

---

## 21. Runs y estados actuales

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
83 professional matching apply
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

MATCHING_V1 / BACKEND_SOFTWARE_V1
  scope               993
  ATS                 892
  LEAD                101
  very high            12
  high                 36
  medium              120
  low                 825
  missing               0
  stale                 0
  duplicate keys        0
  wrong rule version    0
  invalid scores        0
```

Run 83 es el último estado persistido confirmado.

---

## 22. Checklist antes de publicar matching

El worktree debería contener exactamente:

```text
M  docs/PROJECT_CONTEXT.md
?? migrations/009_job_professional_matches.sql
?? src/chamba_hunter/commands/match_jobs.py
?? src/chamba_hunter/repositories/job_matching_repository.py
?? src/chamba_hunter/services/job_matching_service.py
```

No versionar diagnósticos temporales:

```text
matching-v1-discovery.*
matching-v1-dry-run.*
matching-v1-r2-dry-run.*
matching-v1-r3-dry-run.*
matching-v1-apply-validation.*
matching-v1-post-apply-validation.*
```

Antes de commit/push:

```powershell
python -m compileall -q src

git add -N -- `
    "migrations/009_job_professional_matches.sql" `
    "src/chamba_hunter/commands/match_jobs.py" `
    "src/chamba_hunter/repositories/job_matching_repository.py" `
    "src/chamba_hunter/services/job_matching_service.py"

git diff --check

git reset -- `
    "migrations/009_job_professional_matches.sql" `
    "src/chamba_hunter/commands/match_jobs.py" `
    "src/chamba_hunter/repositories/job_matching_repository.py" `
    "src/chamba_hunter/services/job_matching_service.py"

git diff --stat
git status --short
```

Los warnings LF→CRLF de Git en Windows son informativos. Evaluar el exit code de Git, no el hecho de que PowerShell represente stderr como `NativeCommandError`.

El usuario decide y ejecuta commit/push manualmente.

---

## 23. Prompt operativo para nueva conversación

```text
Repositorio: Gtestino92/chamba-hunter
Base: main

Primero:
- verificar HEAD y últimos commits reales en GitHub;
- leer docs/PROJECT_CONTEXT.md completo;
- confirmar si migration 009 y matching repository/service/command ya están publicados;
- distinguir GitHub code vs DB local observed state;
- no asumir que conteos históricos siguen vigentes;
- inspeccionar código real de ingestion/freshness, canonicalization, geography, occupation, skills, seniority y matching;
- no modificar código todavía;
- preparar discovery del último vertical: operational/application priority;
- preservar MATCHING_V1 como professional fit independiente;
- no incorporar first_seen_at, published_at, application channel ni freshness dentro de MATCHING_V1;
- inspeccionar distribución real de first_seen_at;
- inspeccionar published_at por provider;
- inspeccionar apply_url por match level;
- diseñar NEW/KNOWN/CLOSED de forma explícita;
- no usar last_seen_at como prueba de UPDATED;
- evaluar si UPDATED necesita content_hash / last_changed_at;
- decidir si priority se persiste o se deriva por run/report;
- mantener application order: direct apply_url, job_url/careers, general_application_url, public recruiting/careers email;
- no auto-apply;
- no UI;
- no evasión anti-bot;
- mantener reusable search_profiles como principio, sin sobrearquitectura preventiva.
```
