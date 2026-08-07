# Chamba Hunter — Handoff operativo

**Fecha:** 2026-08-07  
**Repositorio:** `Gtestino92/chamba-hunter`  
**Rama operativa:** `main`  
**HEAD de referencia al cerrar este handoff:** `ed9db20034f57aa7edb75ae4f4b91837ab33f4a1`  
**Commit de referencia:** `ats detection`

> El SHA anterior es sólo una referencia temporal. **GitHub `main` y el código actual son siempre la fuente de verdad.**
> Antes de recomendar, diseñar o escribir código en una sesión nueva, volver a inspeccionar GitHub y reconciliar este handoff contra el estado real del repo.

---

## 1. Orden obligatoria para una sesión nueva

Antes de proponer cambios:

1. Conectarse al repositorio GitHub `Gtestino92/chamba-hunter`.
2. Verificar rama/default branch actual, HEAD actual de `main`, últimos commits relevantes y árbol real del repo.
3. Leer primero este handoff si está en el repo.
4. Después inspeccionar directamente en GitHub, como mínimo:
   - `pyproject.toml`
   - `migrations/`
   - `src/chamba_hunter/domain/enums.py`
   - `src/chamba_hunter/domain/models.py`
   - `src/chamba_hunter/domain/tracing.py`
   - `src/chamba_hunter/db/`
   - `src/chamba_hunter/repositories/`
   - `src/chamba_hunter/services/`
   - `src/chamba_hunter/sources/`
   - `src/chamba_hunter/commands/`
   - `examples/`
5. Verificar especialmente los archivos involucrados en la tarea siguiente antes de diseñar interfaces o repositorios nuevos.
6. Tratar cualquier diferencia entre este documento y GitHub como señal de que **GitHub ganó**.
7. No asumir que la DB local coincide exactamente con datos históricos escritos aquí; los resultados de corridas son evidencia operativa, no schema contractual.

### Forma recomendada de iniciar el contexto

```text
Repositorio: Gtestino92/chamba-hunter
Base: main

Primero:
- inspeccionar HEAD/tree reales en GitHub;
- leer este handoff;
- inspeccionar los archivos reales afectados por el próximo vertical;
- distinguir confirmado por código vs confirmado por corrida manual;
- recién entonces proponer cambios.
```

---

## 2. Preferencias operativas del usuario

- Conversación y explicaciones: **español**.
- Código: **inglés**.
- El usuario actualmente trabaja con ChatGPT directamente, no con Codex.
- Desarrollo incremental, vertical slices pequeños.
- Evitar sobrearquitectura.
- SQLite es la fuente de verdad local.
- No UI/web API por ahora.
- No automatizar postulaciones.
- El usuario hace los `push` manualmente.
- No crear branches/PRs ni escribir en GitHub salvo pedido explícito.
- **No agregar tests por ahora.** El usuario quiere incorporarlos más adelante con Codex.
- Sí usar validaciones baratas:
  - `python -m compileall -q src`
  - corridas funcionales manuales y diagnósticos puntuales.
- Antes de sugerir push, preferir una validación funcional.
- Cuando se modifique un archivo, entregar **el contenido completo del archivo**, nunca snippets parciales.
- Snippets parciales están bien sólo para diagnósticos one-off de shell/Python/SQL.
- No hacer bypass anti-bot, fake browser ni scraping agresivo.
- Si una página devuelve 403/429, tratarlo como señal operativa (`BLOCKED`/warning), no intentar evadir la protección.
- Evitar nuevas dependencias salvo necesidad real.
- `httpx` es la librería HTTP actual.
- No reintroducir BeautifulSoup sólo para sortear páginas que bloquean scraping.

### Entorno local observado

```text
~/Documents/Git/chamba-hunter
Windows + Git Bash (MINGW64)
Python 3.12.5
venv: .venv
package: chamba_hunter
```

Activación:

```bash
source .venv/Scripts/activate
```

---

## 3. Objetivo del producto

Chamba Hunter es una herramienta local de inteligencia para búsqueda laboral.

No aplica automáticamente. Su objetivo es construir y mantener una base útil de:

- empresas;
- careers pages;
- ATS;
- vacantes;
- compatibilidad geográfica;
- matching contra el perfil profesional;
- contactos/canales públicos para outreach manual;
- output final accionable.

Flujo global:

```text
company discovery
    ↓
dedup + enrichment
    ↓
company classification
    ↓
geography / priority
    ↓
careers discovery
    ↓
ATS detection
    ↓
ATS adapters / job ingestion        ← PRÓXIMO FOCO
    ↓
job normalization
    ↓
matching / ranking
    ↓
Excel report / manual action
```

Outreach paralelo futuro:

```text
company
    ↓
no matching job
    ↓
public recruiting/careers email or general application URL
    ↓
manual outreach candidate
```

Nunca descubrir o adivinar emails personales de recruiters. Sólo contactos explícitamente públicos de la empresa.

---

## 4. Perfil profesional a usar más adelante para matching

Perfil resumido:

- Backend Software Engineer
- Java
- Kotlin
- Spring Boot
- REST APIs
- Distributed Systems
- batch/schedulers
- retries
- idempotency
- distributed locks
- resilience
- PostgreSQL
- Oracle
- MongoDB
- Flyway / JPA
- AWS EC2/RDS/S3/SSM
- Docker
- Kubernetes
- OpenShift
- GitHub Actions / GitLab CI/CD
- TypeScript / Node.js / NestJS como stack secundario
- Android/Compose secundario
- English C1

Matching conceptual futuro:

### Core
- Java
- Kotlin
- Spring Boot
- Backend
- REST
- Distributed Systems

### Strong support
- microservices
- batch
- schedulers
- retries
- idempotency
- PostgreSQL / Oracle / MongoDB
- AWS
- Docker
- Kubernetes
- OpenShift

### Secondary
- TypeScript
- Node.js
- NestJS
- Android

No exigir todos los keywords simultáneamente.

---

## 5. Foundation ya construida

Arquitectura vigente:

- Python package bajo `src/chamba_hunter`.
- Pydantic v2 sólo en boundaries externos.
- Domain/tracing con `@dataclass(slots=True)`.
- Repositories explícitos sobre `sqlite3`.
- Sin SQLAlchemy.
- SQLite local.
- Migraciones SQL.
- `httpx` para HTTP.
- editable install previsto con `pip install -e .`.

Dependencias conocidas principales:

```text
pydantic >= 2.13,<3
httpx >= 0.28,<1
pytest en dev, pero NO agregar tests ahora
```

Tablas principales ya diseñadas:

- `companies`
- `company_sources`
- `company_scans`
- `ats_detections`
- `company_ats`
- `public_contacts`
- `jobs`
- `search_profiles`
- `job_matches`
- `applications`
- `runs`
- `run_steps`
- `ats_syncs`

Migración adicional existente:

- `002_company_classifications.sql`

Las migraciones ya aplicadas son inmutables. Si hace falta cambiar schema, crear `003_...sql`, etc.

---

## 6. Company discovery e import — terminado para MVP

### Himalayas

Fuente pública:

```text
https://himalayas.app/jobs/api/search
```

No se scrapean perfiles de empresa de Himalayas porque devolvían 403.

Resultados observados:

```text
Queries:     17
Raw hits:    429
Discovered:  148
Created:     95
Existing:    53
```

Segunda corrida:

```text
Created:  0
Existing: 148
```

### Get on Board

Feed público:

```text
https://www.getonbrd.com/api/v0/categories/programming/jobs
```

Corrida observada:

```text
Jobs seen:             200
Companies discovered:   79
```

Idempotencia confirmada.

---

## 7. Dedup/import — decisiones importantes

Orden conceptual:

1. misma identidad de source;
2. mismo dominio oficial;
3. fallback por `normalized_name` sólo si es único y compatible;
4. empresa existente sin dominio puede enriquecerse con una source posterior que sí trae dominio;
5. no fusionar dominios diferentes sólo por nombre.

Esto evitó duplicados como:

```text
Himalayas: Checkr sin domain
Get on Board: Checkr con checkr.com
```

`careers_url` ya forma parte del import manual y puede rellenarse sin pisar un valor conocido.

---

## 8. Company classification — terminado para MVP

Classifier V3 para Get on Board.

Tipos:

```text
PRODUCT
CONSULTANCY
RECRUITER
OTHER
UNKNOWN
```

Principios:

- `PRODUCT`: producto/plataforma/SaaS/marketplace/tecnología propia.
- `CONSULTANCY`: consulting/services/staff augmentation/outsourcing/custom software/client work.
- `RECRUITER`: recruiting/staffing/headhunting/placement.
- `UNKNOWN`: evidencia débil.
- No clasificar sólo por nombre.
- No intentar llevar `UNKNOWN` a cero.
- `OTHER` existe pero no se forzó todavía para compañías no-software.

Distribución final observada sobre 79 empresas Get on Board:

```text
PRODUCT      11
CONSULTANCY  16
RECRUITER     1
OTHER         0
UNKNOWN      51
```

Precisión > cobertura.

---

## 9. Geography + target priority — terminado para MVP

Se detectan señales separadas:

- company Argentina
- company Buenos Aires
- job Argentina
- job Buenos Aires
- remote global
- remote LATAM/South America
- remote Argentina-compatible
- remote + Buenos Aires

No inferir remote Argentina sólo porque la empresa esté basada en Argentina.

Prioridades:

```text
VERY_HIGH
HIGH
MEDIUM
LOW
UNKNOWN
```

Corrida observada:

```text
Processed:   79
Failed:       0

VERY_HIGH:    0
HIGH:        11
MEDIUM:      25
LOW:         11
UNKNOWN:     32

remote Argentina-compatible: 31
remote LATAM-compatible:     29
```

Nota: `remote_latam=True` persiste compatibilidad LATAM y puede incluir global remote; no equivale necesariamente a mención textual explícita de “LATAM”.

Empresas `HIGH` observadas:

```text
Coderslab.io
Devsu
Kreitech
LemonTech
Magnar
nCube
Niuro
PlainTech Solutions
Rapidseedbox LLC
Travefy
Whitestack
```

No seguir calibrando prioridad ahora salvo problema real posterior.

---

## 10. Seed manual curado de careers — terminado

Lista curada:

```text
Canonical
Konfio
dLocal
Remote
GitLab
Platzi
Lumenalta
Toptal
Globant
Stori
Bitso
Deel
Belvo
```

Archivo previsto:

```text
examples/linkedin_careers_seed.csv
```

Primera corrida:

```text
Processed: 13
Created:   12
Existing:   1
Invalid:    0
```

Segunda corrida:

```text
Processed: 13
Created:    0
Existing:  13
Invalid:    0
```

Idempotencia confirmada.

---

## 11. Careers / ATS detection — terminado para el vertical actual

Objetivo: a partir de careers URL conocida —o homepage → careers— detectar un ATS con evidencia trazable.

Pipeline:

```text
careers URL
    ↓
HTTP fetch + redirects
    ↓
links / iframe / scripts / URL params
    ↓
ATS candidates
    ↓
public API / board probes cuando corresponde
    ↓
ats_detections
    ↓
best candidate
    ↓
company_ats
```

Providers reconocidos:

```text
GREENHOUSE
ASHBY
LEVER
SMARTRECRUITERS
WORKABLE
BAMBOOHR
CUSTOM
```

`WORKABLE` y `BAMBOOHR` son detectables; eso NO implica adapters de ingestion existentes.

Métodos:

```text
HOMEPAGE_LINK
CAREERS_LINK
HTML_LINK
EMBED_URL
SCRIPT_REFERENCE
URL_PARAMETER
REDIRECT
PUBLIC_API_PROBE
BOARD_PROBE
OTHER
```

Status:

```text
DETECTED
NOT_DETECTED
BLOCKED
ERROR
```

403/429 no se evaden.

---

## 12. Tracing ATS

Ahora se usan:

- `runs`
- `run_steps`
- `company_scans`
- `ats_detections`
- `company_ats`

Repositorios incorporados:

```text
src/chamba_hunter/repositories/tracing_repository.py
src/chamba_hunter/repositories/company_ats_repository.py
```

El historial de scans/detections se conserva.

`company_ats` representa estado actual.

Regla actual:

- cuando un ATS se selecciona/upsertea como primario/activo;
- los otros `company_ats` de esa empresa se desactivan (`is_primary=0`, `is_active=0`);
- no se borra el historial de `ats_detections`.

---

## 13. Calibración ATS — lecciones

### SmartRecruiters

Se descubrió un falso positivo sistemático:

```text
SMARTRECRUITERS platzi
200
totalFound: 0

SMARTRECRUITERS fake
200
totalFound: 0
```

Conclusión:

> En SmartRecruiters, HTTP 200 + colección vacía NO valida un company identifier.

Regla actual:

```text
SmartRecruiters PUBLIC_API_PROBE sólo es evidencia positiva
si devuelve al menos un posting activo.
```

Cinco estados actuales SmartRecruiters generados por el probe defectuoso fueron desactivados:

```text
SmartRecruiters rows deactivated: 5
```

No se eliminó tracing.

### Lever

```text
dlocal → 200 + job
toptal → 200 + job
fake   → 404
```

Probe aceptado.

### Ashby

```text
belvo → 200 + jobs
deel  → 200 + jobs=[]
fake  → 404
```

Un board válido puede tener cero jobs.

### Greenhouse

```text
bitso      → 200, board name Bitso
canonical  → 200, board name Canonical
gitlab     → 200, board name GitLab
remotecom  → 200, board name Remote
fake       → 404
```

Se compara nombre del board contra empresa.

### Workable

Boards reales observados:

```text
Globant /globant/ → 200, title "Globant - Current Openings"
Konfio  /konfio/  → 200, title "konfio - Current Openings"
Platzi  /platzi/  → 200, title "Platzi - Current Openings"
Stori   /stori/   → 200, title "Stori - Current Openings"
```

Fake:

```text
/apply.workable.com/definitely-not-a-real-company-xyz/
→ redirect a /oops
title: Workable
company name absent
```

El `BOARD_PROBE` exige URL final compatible + nombre de empresa, por lo que el fake no pasa.

Limitación conocida:

> Que exista un board Workable válido no prueba necesariamente que sea el único o actual ATS primario enlazado desde la careers page; podría ser histórico.

Para el MVP se acepta con tracing/confidence. No seguir calibrando por inercia.

---

## 14. Última corrida ATS aceptada

```text
Processed:     13
Detected:      12
Not detected:   1
Blocked:        0
Failed:         0
Skipped:        0
```

Mappings:

```text
Belvo       → ASHBY [belvo]
Bitso       → GREENHOUSE [bitso]
Canonical   → GREENHOUSE [canonical]
Deel        → ASHBY [deel]
dLocal      → LEVER [dlocal]
GitLab      → GREENHOUSE [gitlab]
Globant     → WORKABLE [globant]
Konfio      → WORKABLE [konfio]
Lumenalta   → NOT_DETECTED
Platzi      → WORKABLE [platzi]
Remote      → GREENHOUSE [remotecom]
Stori       → WORKABLE [stori]
Toptal      → LEVER [toptal]
```

Warnings de fetch bloqueado pero detección independiente válida:

```text
Belvo  → HTTP 403 warning
Konfio → HTTP 403 warning
Toptal → HTTP 403 warning
```

No hubo bypass.

---

## 15. Archivos ATS clave actuales

Confirmar siempre contra GitHub, pero al cierre:

```text
src/chamba_hunter/commands/detect_careers_ats.py
src/chamba_hunter/domain/enums.py
src/chamba_hunter/domain/models.py
src/chamba_hunter/domain/tracing.py
src/chamba_hunter/repositories/company_ats_repository.py
src/chamba_hunter/repositories/tracing_repository.py
src/chamba_hunter/services/careers_ats_detection_service.py
```

HEAD de referencia:

```text
ed9db20034f57aa7edb75ae4f4b91837ab33f4a1
ats detection
```

---

# 16. PRÓXIMO FOCO: job ingestion

**No seguir refinando ATS detection ahora.**

El próximo vertical debe convertir detecciones ATS en **vacantes reales persistidas**.

Empezar por **Greenhouse solamente**.

Corpus controlado:

```text
Bitso      → GREENHOUSE [bitso]
Canonical  → GREENHOUSE [canonical]
GitLab     → GREENHOUSE [gitlab]
Remote     → GREENHOUSE [remotecom]
```

---

## 17. Orden recomendada para Greenhouse ingestion

Antes de editar:

1. Ingerir estado real de GitHub `main`.
2. Inspeccionar:
   - `Job` en `domain/models.py`;
   - schema de `jobs`;
   - `AtsSync`;
   - `company_ats`;
   - `company_ats_repository.py`;
   - `tracing_repository.py`;
   - converters;
   - commands/services existentes.
3. Verificar la API pública actual de Greenhouse antes de fijar endpoint/payload.
4. Diseñar el cambio mínimo.

Vertical:

```text
active primary company_ats
provider = GREENHOUSE
external_identifier = token
        ↓
Greenhouse public Job Board API
        ↓
normalize external jobs
        ↓
upsert jobs
        ↓
mark missing previous jobs inactive
        ↓
ats_sync tracing
        ↓
CLI summary
```

Evitar todavía:

- framework genérico enorme de adapters;
- plugins;
- colas;
- cron;
- UI;
- matching;
- Excel;
- LLM ranking;
- notificaciones;
- outreach;
- varios ATS a la vez.

---

## 18. Semántica deseada de jobs

El modelo/schema ya contempla aproximadamente:

```text
company_id
company_ats_id
external_id
title
description
location_text
workplace_type
employment_type
job_url
apply_url
published_at
first_seen_at
last_seen_at
is_active
raw_payload
```

Verificar contra GitHub antes de implementar.

Reglas esperadas:

- identidad: `(company_ats_id, external_id)`;
- primera aparición → insert;
- existente → update mutable fields + `last_seen_at`;
- presente → `is_active=True`;
- antes activo pero ya no aparece → `is_active=False`;
- conservar `first_seen_at`;
- raw payload sólo si aporta trazabilidad;
- no inferir datos que Greenhouse no entregue claramente.

---

## 19. Tracing deseado para ingestion

Usar `ats_syncs`; no crear infraestructura paralela.

Guardar:

```text
run_step_id
company_ats_id
status
http_status
jobs_received
jobs_created
jobs_updated
jobs_deactivated
error_type
error_message
started_at
finished_at
```

---

## 20. Validación manual del próximo vertical

No agregar pytest.

Primero:

```bash
python -m compileall -q src
```

Después corrida controlada sobre Greenhouse, idealmente con `--limit 1` o equivalente seguro.

Validar:

1. jobs recibidos > 0 en algún board conocido;
2. filas creadas en SQLite;
3. segunda corrida no duplica;
4. `first_seen_at` no cambia;
5. `last_seen_at` se refresca;
6. `ats_syncs` tiene trazabilidad;
7. deactivation sólo si puede probarse de forma segura.

Luego ampliar a:

```text
Bitso
Canonical
GitLab
Remote
```

Sólo tras eso decidir push.

---

## 21. Próximos verticales tentativos

```text
1. Greenhouse ingestion
2. Ashby ingestion
3. Lever ingestion
4. SmartRecruiters ingestion si hay detecciones sólidas
5. Workable/BambooHR cuando valga la pena
6. job geography normalization
7. deterministic matching contra perfil
8. action candidates
9. Excel report
10. scheduling/cron
```

---

## 22. Output final futuro

Conceptualmente:

```text
GitLab
  Backend Engineer
  Remote LATAM
  HIGH MATCH
  → aplicar manualmente

Canonical
  Senior Software Engineer
  Remote
  MEDIUM/HIGH MATCH
  → aplicar manualmente

Company X
  no matching jobs
  public careers/recruiting contact available
  → outreach manual candidate
```

XLSX futuro:

```text
Companies
Matching Jobs
Contacts / Outreach
ATS Tracing
Run Summary
```

No CSV como output final.

---

## 23. Definiciones de terminado

### Company discovery
MVP suficiente.

### Dedup
MVP suficiente.

### Get on Board classification
MVP suficiente. No V4 salvo evidencia real.

### Company priority
MVP suficiente.

### Manual curated seeds
Funcionando e idempotente.

### Careers / ATS detection
Vertical cerrado para MVP.

Limitaciones aceptadas:
- 403;
- JS-heavy careers;
- Workable potencialmente histórico;
- SmartRecruiters vacío no valida identifier;
- `NOT_DETECTED` no significa `CUSTOM`.

### Job ingestion
**No implementado todavía. Es el próximo foco.**

---

## 24. Regla de fuente de verdad

```text
HANDOFF = orientación
GITHUB MAIN = verdad
MANUAL RUN OUTPUT = evidencia funcional
```

Si algo no coincide:

```text
GitHub main > handoff
```

---

## 25. Instrucción corta para pegar al iniciar otra sesión

```text
Continuamos con Chamba Hunter.

Repo: Gtestino92/chamba-hunter
Base: main.

Antes de recomendar o escribir código, conectate a GitHub e ingerí el estado real del repo: HEAD, tree y archivos relevantes. Leé el handoff del proyecto si existe, pero tratá GitHub main como fuente de verdad y reconciliá cualquier diferencia.

No agregues tests por ahora. Trabajo incremental, cambios pequeños. Código en inglés, explicación en español. Cuando modifiques un archivo, entregá el archivo completo. No branches/PR/push salvo pedido explícito.

El vertical de careers/ATS detection está cerrado para MVP. Próximo foco: job ingestion, empezando sólo por Greenhouse sobre los boards ya detectados/validados (Bitso, Canonical, GitLab, Remote), usando los modelos/tables existentes de jobs y ats_syncs y sin crear infraestructura paralela.
```
