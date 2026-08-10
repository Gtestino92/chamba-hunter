# Chamba Hunter — Project Context / Handoff operativo

**Fecha de actualización:** 2026-08-10
**Repositorio:** `Gtestino92/chamba-hunter`
**Rama operativa:** `main`
**Entorno habitual:** Windows + PowerShell + `.venv`

---

## 0. Fuente de verdad y estado actual

Código/GitHub actual y la DB local observada son siempre fuente de verdad frente a este documento.

Antes de recomendar, diseñar o implementar:

1. verificar HEAD real de `main`;
2. verificar `git status --short`;
3. leer este archivo completo;
4. inspeccionar directamente los archivos reales del vertical a tocar;
5. reconciliar este handoff contra GitHub;
6. cuando el estado de DB sea relevante, usar una consulta read-only focalizada en vez de asumir conteos históricos;
7. distinguir explícitamente:
   - confirmado por código/GitHub;
   - confirmado por corrida manual/DB;
   - inferido;
   - pendiente de verificar.

### GitHub publicado antes del slice C1 local

HEAD verificado antes de implementar C1:

```text
807a0eb7b90c329a204eb17550c22cf881268502
context
```

Parent funcional relevante:

```text
c7d82ef37193d3d3367f2e9b072751ddad08e6d5
add Jooble Argentina acquisition
```

El commit `807a0...` es documental respecto de Jooble; el último cambio funcional publicado antes de C1 sigue siendo `c7d82...`.

Si `main` avanzó después de este documento, verificar HEAD real y usar código/GitHub actual.

### Worktree local esperado al cerrar C1

Antes de agregar esta actualización documental, el estado local confirmado era:

```text
 M src/chamba_hunter/commands/discover_broad_ats.py
?? src/chamba_hunter/services/provider_hint_ats_detection_service.py
```

Después de aplicar este documento, el set intencional para commit debería ser:

```text
 M docs/PROJECT_CONTEXT.md
 M src/chamba_hunter/commands/discover_broad_ats.py
?? src/chamba_hunter/services/provider_hint_ats_detection_service.py
```

No hubo migration para C1.

### Último estado operativo observado

Último matching persistido:

```text
Run 141
MATCHING_V1
Candidates: 1605

VERY_HIGH   18
HIGH       182
MEDIUM     231
LOW       1174
```

Último operational priority:

```text
Run 142
OPERATIONAL_PRIORITY_V2
Candidates: 1682
```

Estados observados:

```text
NEW             194
UPDATED           1
KNOWN          1410
INACTIVE         23
SUPERSEDED       13
OUT_OF_SCOPE     41
```

Último XLSX exportado:

```text
SHORTLIST_REPORT_V2
OPENOFFICE_ACTIONS_V1
Priority run: 142

Focus:        7
High Value: 200
All Current: 1605
History:     77
```

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
- Windows + PowerShell es el entorno operativo habitual.

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
→ el usuario sube el .txt
```

### Implementaciones / archivos

Cuando se entregue una implementación:

- entregar un único ZIP;
- rutas directamente repo-relative;
- sin wrapper directory;
- sin carpeta auxiliar `files/`;
- sin `apply_*.py`;
- no pedir copiar fragmentos manualmente.

Junto con el ZIP, entregar un único bloque PowerShell que:

1. use `$ErrorActionPreference = "Stop"`;
2. verifique branch/HEAD y precondiciones relevantes;
3. descomprima sobre raíz del repo;
4. ejecute sólo validaciones focalizadas;
5. controle `$LASTEXITCODE`;
6. borre el ZIP sólo después de éxito;
7. muestre `git diff --stat`;
8. muestre `git status --short`.

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

No hubo migration para:

```text
geo/recency V2
batch application tracking
OpenOffice actions
A1 Jobicy/WWR
A2 Jooble
B Recruitee value test
C0 audit
C1 Jooble supported ATS discovery
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

### ATS ingestion

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

### Providers observados pero no soportados

Evidencia Jooble de C0 mostró, entre otros:

```text
teamtailor.com   23 postings observados
breezy.hr         6 postings observados
```

Esto es evidencia para un value test futuro, no autorización para implementar providers por inercia.

---

## 7. A1 — Jobicy + We Work Remotely

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

Configuración:

```text
industry = engineering
geo = latam
max jobs default = 100
```

Primera adquisición observada:

```text
66 created
```

### We Work Remotely

RSS público:

```text
Programming
DevOps / Sysadmin
```

No detail-page scraping.

Primera adquisición observada:

```text
76 created
```

A1 combinado inicial:

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

No modificar A1 salvo evidencia nueva.

---

## 8. A2 — Jooble Argentina

Estado:

```text
COMPLETE / PUBLISHED
```

Commit:

```text
c7d82ef37193d3d3367f2e9b072751ddad08e6d5
add Jooble Argentina acquisition
```

Usa API oficial de Jooble Argentina.

Secreto:

```text
JOOBLE_API_KEY
```

Nunca pedir pegar la key en chat ni imprimir endpoints que la contengan.

Query set:

```text
backend
java developer
spring boot
```

Default:

```text
50 results/page
2 pages/query
3 queries
6 requests
```

Normalización relevante:

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

`updated` se preserva sólo en `raw_payload_json`.

No mapear `updated` a publication date.

El payload persistido conserva además `job.source`, que C1 explota sólo como provider hint.

Primera adquisición real:

```text
Run 123
Requests made:       6
Received unique:   251
Normalized:        247
Skipped:             4
```

No usar el redirect Jooble para recuperar first-party URL: el test C0 produjo `403` en los 12 casos inspeccionados y no se hace bypass.

---

## 9. Canonicalization

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

Canonicalization debe seguir ejecutándose después de broad acquisition y ATS sync.

---

## 10. Argentina / occupation / skills / seniority / matching

### ARGENTINA_V1

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

Remote sin scope:

```text
UNKNOWN / REMOTE_SCOPE_UNKNOWN
```

No cambiar `ARGENTINA_V1` por peculiaridades aisladas de una fuente sin evidencia suficiente.

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

### SKILLS_V1

Una skill row significa una mención explícita en title/description.

No significa required/preferred/hard requirement.

### SENIORITY_V1

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

Leadership es una dimensión separada.

### MATCHING_V1

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

No cambiar thresholds por una fuente nueva sin evidencia suficiente.

### Estado observado después de C1

Runs:

```text
137 ARGENTINA_V1
138 OCCUPATION_V1
139 SKILLS_V1
140 SENIORITY_V1
141 MATCHING_V1
```

Matching run 141:

```text
Candidates: 1605

ATS   1063
LEAD   542

VERY_HIGH    18
HIGH        182
MEDIUM      231
LOW        1174
```

---

## 11. JOB_CONTENT_V1 / operational priority

Mantener separado:

```text
professional fit
vs
freshness / source state
vs
application channel
```

`OPERATIONAL_PRIORITY_V2` usa el estado actual de las fuentes, canonicalization, freshness y canales de aplicación.

Último run observado:

```text
Run 142
Candidates: 1682

NEW             194
UPDATED           1
KNOWN          1410
INACTIVE         23
SUPERSEDED       13
OUT_OF_SCOPE     41
```

Application channels observados:

```text
DIRECT_APPLY_URL           767
JOB_URL                    915
GENERAL_APPLICATION_URL      0
PUBLIC_CONTACT               0
NONE                         0
```

Los 13 `SUPERSEDED` de run 142 corresponden exactamente a los broad leads canonicalizados por C1.

---

## 12. Shortlist / OpenOffice / application tracking

Export:

```powershell
python -m chamba_hunter.commands.export_shortlist
```

Default:

```text
output/chamba-shortlist.xlsx
```

Último export observado:

```text
SHORTLIST_REPORT_V2
OPENOFFICE_ACTIONS_V1
Priority run: 142
APPLY links: 1796

Focus:        7
High Value: 200
All Current: 1605
History:     77
```

Manual application tracking usa identidad polimórfica:

```text
record_kind = ATS | LEAD
record_id
```

Una job application es `APPLIED`.

Outreach/general application futuro, si existe, debe permanecer semánticamente separado.

Auditoría C1:

```text
13 canonical pairs
Tracked LEADs: 0
Tracked ATS:   0
Transfer risks: 0
```

No hubo que migrar application tracking durante C1.

---

## 13. Routine refresh actual

Plan manual:

```powershell
python -m chamba_hunter.commands.refresh_search
```

Real:

```powershell
python -m chamba_hunter.commands.refresh_search --apply
```

Pipeline:

```text
acquire Himalayas / Get on Board
acquire Jobicy / We Work Remotely
acquire Jooble
optional broad ATS discovery
sync all supported ATS providers
canonicalize --apply
geo --apply
occupation --apply
skills --apply
seniority --apply
matching --apply
priority --apply
XLSX export
```

Broad ATS discovery permanece deshabilitado por default:

```text
--discover-broad-ats-limit 0
```

Jooble puede deshabilitarse específicamente con:

```text
--jooble-max-pages-per-query 0
```

`--skip-broad` salta las cinco broad sources.

Antes de un refresh real:

1. confirmar que se quiere adquisición/repriorización real;
2. cerrar `output/chamba-shortlist.xlsx`;
3. cargar `JOOBLE_API_KEY`;
4. usar plan-only si hace falta;
5. recién entonces `--apply`.

No usar full refresh como validación de código.

---

## 14. Parte B — Recruitee

Estado:

```text
CLOSED / NO IMPLEMENTATION
```

Recruitee fue tratado como posible ATS nuevo y value-tested antes de construir adapter.

Conclusión:

```text
insufficient marginal value to justify implementation now
```

No se agregaron:

```text
AtsProvider.RECRUITEE
client
sync service
sync command
refresh integration
migration
```

Reabrir sólo con evidencia nueva de cobertura marginal suficiente.

---

## 15. Parte C — objetivo general

Objetivo original:

```text
explotar mejor empresas conocidas sin un ATS soportado
```

Canales considerados:

```text
custom first-party careers pages
explicit public recruiting/careers emails
explicit general application forms
supported ATS evidence hidden behind broad aggregators
```

Reglas:

```text
only explicit public evidence
never infer recruiter emails
no auto-email
no auto-submit
no anti-bot bypass
```

C0 mostró que el subproblema de mayor valor inmediato no era outreach genérico sino recuperar ATS first-party a partir de evidencia ya persistida en Jooble.

---

## 16. C0 — audit / value test

Estado:

```text
COMPLETE / POSITIVE
```

### C0a — application channels

Sobre el target High Value auditado:

```text
169 opportunities
89 companies
15 companies with known entry point
74 without known entry point
```

Todos tenían un job-specific `JOB_URL`.

Resultado:

```text
no strict NONE gap
generic application/contact discovery deferred
```

No priorizar email/general application mientras la oportunidad concreta ya tenga job URL.

### C0b — identity gap

Entre las 74 companies sin entry point:

```text
domain evidence: 0
source URL evidence: 8
```

La mayor parte provenía de Jooble.

No se justificó enrichment genérico por nombre.

### C0c — Jooble upstream provider evidence

`raw_payload_json.job.source` mostró evidencia de ATS/public job systems.

Supported provider evidence en la muestra C0:

```text
HIRINGROOM        5
GREENHOUSE        2
WORKABLE          2
SMARTRECRUITERS   2
LEVER             1
```

12 postings / 11 unique companies.

También se observó evidencia futura:

```text
TEAMTAILOR 23
BREEZY      6
```

No se implementaron esos providers.

### C0d — Jooble redirect resolution

12/12 requests a links Jooble soportados devolvieron `403`.

Decisión:

```text
do not resolve/bypass Jooble redirects
```

### C0e — marginality

Los 11 boards soportados auditados no estaban presentes en `company_ats`.

Esto confirmó valor marginal real para un discovery específico.

`job_ats_hints` no se usó para persistir source-only guesses porque requiere identidad concreta; C1 valida públicamente antes de escribir `company_ats`.

---

## 17. C1 — JOOBLE_SUPPORTED_ATS_DISCOVERY_V1

Estado:

```text
COMPLETE / POSITIVE
FUNCTIONALLY VALIDATED
PENDING LOCAL COMMIT/PUSH
```

### Objetivo

Transformar:

```text
Jooble raw_payload.job.source
→ supported provider hint
→ tenant candidates derived from company identity
→ public provider probe
→ tracing / ats_detections / company_ats
→ existing ATS sync
→ existing canonicalization
```

### Implementación

Archivos:

```text
src/chamba_hunter/commands/discover_broad_ats.py
src/chamba_hunter/services/provider_hint_ats_detection_service.py
```

No migration.

No cambio necesario en `refresh_search.py`.

`discover_broad_ats` agrega:

```text
--source JOOBLE
strategy PROVIDER_HINT
```

Provider mappings V1:

```text
boards.greenhouse.io
job-boards.greenhouse.io
→ GREENHOUSE

jobs.lever.co
→ LEVER

workable.com
apply.workable.com
jobs.workable.com
→ WORKABLE

smartrecruiters.com
jobs.smartrecruiters.com
careers.smartrecruiters.com
→ SMARTRECRUITERS

hiringroom.com / subdomains
→ HIRINGROOM
```

Unknown providers se ignoran.

No se hace HTTP contra Jooble durante provider-hint detection.

El Jooble source es **hint only**.

`company_ats` se escribe únicamente si el probe público del provider valida un board/tenant concreto.

### Identidad / aliases

C1 reutiliza derivación existente de identificadores desde identidad de company.

No se agregaron aliases hardcoded.

En particular, no se hardcodeó:

```text
PedidosYa → DeliveryHero
MindIT HR Agency → mindithr
```

Mantener esta restricción salvo evidencia y diseño explícito.

### Discovery real

Dry-run previo:

```text
Companies without ATS: 106
Usable scan targets:    27
PROVIDER_HINT:          27
Provider hint conflicts: 0
```

Primera corrida real:

```text
Run 132
Selected:     25
Detected:     12
Not detected: 13
Blocked:       0
Failed:        0

Active ATS companies:
68 → 80
```

Detectados:

```text
Frávega              HIRINGROOM   fravega
Grupo Petersen       HIRINGROOM   grupopetersen
Alianza Estrategica  HIRINGROOM   alianzaestrategica
AppDirect            GREENHOUSE   appdirect
Megatlon             HIRINGROOM   megatlon
getsquire            LEVER        getsquire
ThinkBig HR          HIRINGROOM   thinkbighr
CL Select            HIRINGROOM   clselect
La Caja              HIRINGROOM   lacaja
Making Sense         HIRINGROOM   makingsense
Grupo Myth           HIRINGROOM   grupomyth
GoFundMe             GREENHOUSE   gofundme
```

Provider totals:

```text
HIRINGROOM  9
GREENHOUSE  2
LEVER       1
```

False positives observados:

```text
0
```

### ATS sync validation

Focused sync runs:

```text
Run 133 GREENHOUSE
Run 134 LEVER
Run 135 HIRINGROOM
```

Todos los boards nuevos sincronizaron con éxito.

Jobs creados por los 12 boards C1:

```text
AppDirect             64
GoFundMe              41
getsquire              6
Frávega                14
Megatlon               14
ThinkBig HR            16
CL Select               9
La Caja                19
Grupo Petersen         28
Alianza Estrategica    10
Making Sense            3
Grupo Myth             32
```

Total first-party jobs creados desde los 12 boards:

```text
256
```

### Canonicalization validation

Dry-run:

```text
Total:      1383
Resolved:     13
Ambiguous:     2
Unmatched:  1368
```

Las 2 ambigüedades eran preexistentes y ajenas a C1.

Apply:

```text
Run 136
Applied: 13
```

Verificación DB de esos 13 links:

```text
Rows found:      13
Linked:          13
Wrong provider:   0
Inactive jobs:    0
```

### Downstream impact

Runs:

```text
137 eligibility
138 occupation
139 skills
140 seniority
141 matching
```

Auditoría de los 13 pares broad → ATS:

```text
Missing current ATS: 0
High Value before:   6
High Value after:    6
Score improved:      7
Score unchanged:     6
Score decreased:     0
```

Mejoras destacadas:

```text
AppDirect
77.00 HIGH
→ 81.75 VERY_HIGH

ThinkBig HR
72.00 HIGH
→ 82.75 VERY_HIGH
```

C1 no sólo mejora provenance/URLs: el contenido first-party puede mejorar la calidad del matching.

### Priority impact

Run 142 marcó exactamente los 13 broad leads como:

```text
SUPERSEDED
```

y retuvo los ATS first-party como oportunidades actuales.

Entre las oportunidades `NEW` High/Very High del run aparecieron, entre otras:

```text
ThinkBig HR | Desarrollador Backend Java - Referente técnico
AppDirect | Senior Backend Developer (Java)
AppDirect | Senior Backend Engineer (Java)
Alianza Estrategica | Backend Developer
Frávega | Backend Developer SR
GoFundMe | Senior Software Engineer (Payments)
getsquire | Backend Engineer, Payments Team
Grupo Petersen | Full stack developers / Java / React
```

### Application tracking safety

Auditoría:

```text
Pairs:          13
Tracked LEADs:   0
Tracked ATS:     0
Transfer risks:  0
```

No hubo tracking manual que migrar.

### Shortlist final C1

```text
Priority run: 142
Focus:          7
High Value:   200
All Current: 1605
History:       77
```

C1 queda cerrado funcionalmente.

---

## 18. Qué NO hacer automáticamente

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
- no nuevas broad sources por inercia;
- no Recruitee implementation sin evidencia nueva;
- no Teamtailor/Breezy implementation sólo porque C0 mostró sources;
- no hardcoded tenant aliases sin diseño/evidencia explícitos;
- no usar Jooble redirects para evadir 403.

---

## 19. Próximo foco después de publicar C1

Primero:

```text
commit/push manual del usuario
```

con sólo:

```text
docs/PROJECT_CONTEXT.md
src/chamba_hunter/commands/discover_broad_ats.py
src/chamba_hunter/services/provider_hint_ats_detection_service.py
```

Después, antes de implementar más:

1. verificar HEAD publicado y worktree limpio;
2. leer este documento completo;
3. inspeccionar el C1 ya publicado;
4. decidir C2 por **valor marginal medido**, no por completitud técnica.

Candidatos razonables para value test C2:

```text
Teamtailor
Breezy
```

porque C0 observó evidencia Jooble real.

Pero primero medir:

```text
unique companies
current supported ATS overlap
high-value relevance
public interface stability
tenant identity derivability
expected first-party job gain
```

La salida válida puede seguir siendo:

```text
do not implement
```

También queda disponible el fallback original de Parte C:

```text
explicit first-party custom careers
explicit general application forms
explicit public recruiting/careers contacts
```

pero C0 mostró que no es prioritario mientras las oportunidades High Value ya tengan job-specific URLs.

No ejecutar otra discovery Jooble `--limit 25` sólo para intentar alcanzar los 2 targets que quedaron fuera de la primera corrida: primero inspeccionar semántica de re-scan/revisit para evitar reprobar innecesariamente los 13 `NOT_DETECTED`.

---

## 20. Método operativo para próximas conversaciones

Trabajar de a un paso importante por vez:

```text
inspección
→ propuesta
→ comando focalizado/read-only
→ usuario pasa output
→ revisión
→ siguiente paso
```

Para outputs largos:

```text
command *> diagnostic.txt
→ usuario sube diagnostic.txt
```

No saltar de discovery a implementación.

No correr full refresh salvo finalidad operacional real.

No alterar capas estables sólo para acomodar una fuente nueva.

Al retomar después de C1, la pregunta inicial es:

```text
¿Existe suficiente valor marginal para construir C2, y en qué provider/canal?
```
