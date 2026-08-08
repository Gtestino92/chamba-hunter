# Chamba Hunter — Project Context / Handoff operativo

**Fecha de actualización:** 2026-08-08  
**Repositorio:** `Gtestino92/chamba-hunter`  
**Rama operativa:** `main`

## Estado de GitHub al generar este documento

Último `main` confirmado en GitHub al momento de escribir este handoff:

```text
d9ed0d4812e9618f91452768c2cfeb87f2fa700e
hr
```

Ese commit ya contiene la integración de **Hiring Room**.

Sin embargo, el trabajo de **cross-source canonicalization** y **Argentina eligibility** descrito en este documento fue implementado y validado en el worktree local después de ese commit y todavía no estaba publicado en GitHub al momento de generar este archivo.

Por lo tanto:

1. antes de iniciar una sesión nueva, verificar siempre el HEAD real de `main`;
2. si `main` ya contiene las migraciones `004` y `005` y los comandos descritos abajo, tratar ese código como fuente de verdad;
3. si todavía no están en `main`, revisar el worktree local antes de asumir que el trabajo se perdió;
4. GitHub/código actual gana siempre frente a este documento.

La base SQLite local contiene estado operativo y resultados de corridas manuales que no están versionados. Los conteos de este documento son evidencia observada de esa DB local, no datos reproducibles sólo desde GitHub.

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
9. El usuario hace el push manualmente.
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
occupation / IT / backend classification   ← PRÓXIMO VERTICAL
    ↓
skills + seniority
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

No usar todavía este perfil para filtrar adquisición.

Orden correcto:

```text
geography
→ occupation/backend
→ skills
→ seniority
→ matching/ranking
```

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

Migraciones esperadas después de publicar el worktree actual:

```text
001_initial_schema.sql
002_company_classifications.sql
003_broad_job_acquisition.sql
004_job_lead_canonicalization.sql
005_job_eligibility_classifications.sql
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

Hiring Room ya está confirmado en GitHub `main` desde commit `d9ed0d...`.

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

Archivos relevantes ya publicados en GitHub:

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

Archivos locales que deben existir/publicarse:

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

Archivos locales que deben existir/publicarse:

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

## 13. Corpus efectivo para el próximo vertical

No trabajar sobre los 4039 indiscriminadamente.

Para clasificación ocupacional inicial, el universo relevante es:

```text
ELIGIBLE   831
UNKNOWN    162
----------------
TOTAL      993
```

Los 3046 `INELIGIBLE` geográficos deben conservarse en DB pero no necesitan consumir el siguiente pipeline de clasificación/matching salvo que se quiera recalcular geography.

---

## 14. Próximo vertical: occupation / IT / backend classification

### Estado

NO implementado todavía.

No empezar directamente con matching/ranking.

Primero construir una clasificación ocupacional provider-independent y recomputable.

Objetivo conceptual:

```text
993 geographically viable/unknown candidates
    ↓
occupation / technology relevance
    ↓
backend/software classification
    ↓
skills
    ↓
seniority
    ↓
matching
```

### Principios recomendados

- preservar raw corpus;
- clasificación separada, auditable y recomputable;
- no borrar vacantes;
- no mezclar geography con occupation;
- no usar el perfil completo del usuario como filtro en la primera clasificación;
- distinguir claramente:
  - software/backend;
  - software no-backend;
  - IT/technical adjacent;
  - non-technical;
  - unknown;
- no forzar unknown a cero;
- usar title como señal de alta precisión;
- usar description sólo cuando haga falta y de forma explícita;
- evitar un keyword matcher monolítico imposible de auditar;
- medir primero la distribución real de titles/descriptions antes de fijar taxonomía definitiva.

### Primera tarea sugerida en la próxima sesión

Sólo inspección/diseño, sin escribir código todavía:

1. verificar `main` y que `004`/`005` estén publicados;
2. leer este documento;
3. inspeccionar schema/repos/services de canonicalization y eligibility;
4. consultar la DB local para obtener:
   - distribución de titles entre `ELIGIBLE` + `UNKNOWN`;
   - top titles repetidos;
   - ejemplos por provider/source;
   - volumen obviamente software/backend vs obviamente non-tech;
5. diseñar la taxonomía v1 con evidencia real;
6. recién después implementar.

---

## 15. Qué NO hacer en el próximo vertical

- No volver a ampliar acquisition antes de necesidad concreta.
- No hacer más Hiring Room discovery manual por ahora.
- No implementar Bumeran/ZonaJobs con evasión anti-bot.
- No eliminar los 3046 ineligible.
- No asumir `UNKNOWN geography` como eligible.
- No arrancar matching por Java/Kotlin todavía.
- No meter skills y seniority en la misma primera regla ocupacional.
- No hacer fuzzy canonicalization adicional salvo evidencia de que aporta valor.
- No cambiar semantics de ATS snapshot.
- No tocar outreach todavía.
- No agregar UI.

---

## 16. Validaciones operativas acumuladas

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
```

Run 79 es el último estado de geography confirmado.

---

## 17. Checklist antes de push de este handoff

El worktree debería contener, como mínimo, además del código ya publicado de Hiring Room:

```text
migrations/004_job_lead_canonicalization.sql
migrations/005_job_eligibility_classifications.sql

src/chamba_hunter/repositories/job_lead_canonicalization_repository.py
src/chamba_hunter/services/job_lead_canonicalization_service.py
src/chamba_hunter/commands/canonicalize_job_leads.py

src/chamba_hunter/repositories/job_eligibility_repository.py
src/chamba_hunter/services/argentina_eligibility_service.py
src/chamba_hunter/commands/classify_argentina_eligibility.py

docs/PROJECT_CONTEXT.md
```

Antes de push:

```powershell
python -m compileall -q src
git diff --check
git status --short
git diff --stat
```

El usuario decide y ejecuta commit/push manualmente.

---

## 18. Prompt operativo recomendado para una nueva conversación

Usar el handoff externo provisto junto a este documento, pero la sesión nueva debe igualmente:

```text
Repositorio: Gtestino92/chamba-hunter
Base: main

Primero:
- verificar HEAD y últimos commits reales en GitHub;
- leer docs/PROJECT_CONTEXT.md;
- confirmar que migrations 004/005 y sus services/commands están publicados;
- distinguir GitHub code vs DB local observed state;
- no modificar código todavía;
- preparar diagnóstico del siguiente vertical: occupation / IT / backend classification
  sobre candidates con Argentina eligibility ELIGIBLE o UNKNOWN.
```
