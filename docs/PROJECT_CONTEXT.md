# Chamba Hunter — Handoff operativo

**Fecha:** 2026-08-07  
**Repositorio:** `Gtestino92/chamba-hunter`  
**Rama operativa:** `main`  
**HEAD de referencia al cerrar este handoff:** `a06fc5ef5462f1a134850c59214fad92fa1b612a`  
**Commit de referencia:** `harden broad ATS discovery and Himalayas enrichment`

> Este SHA es sólo una referencia temporal. **GitHub `main` y el código actual son siempre la fuente de verdad.**
> Antes de recomendar, diseñar o escribir código en una sesión nueva, volver a inspeccionar GitHub y reconciliar este handoff contra el estado real del repo.
>
> La base SQLite local contiene resultados de corridas manuales que no están versionados en GitHub. Los conteos operativos de este documento deben tratarse como evidencia del estado local observado, no como contrato de schema ni como datos reproducibles desde el repo.

---

## 1. Orden obligatoria para una sesión nueva

Antes de proponer cambios:

1. Conectarse al repositorio GitHub `Gtestino92/chamba-hunter`.
2. Verificar:
   - default branch;
   - HEAD actual de `main`;
   - últimos commits relevantes;
   - árbol real del repo.
3. Leer `docs/PROJECT_CONTEXT.md`.
4. Inspeccionar directamente en GitHub los archivos reales involucrados en la tarea siguiente.
5. Como mínimo, cuando sean relevantes:
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
6. Distinguir siempre:
   - confirmado por código actual;
   - confirmado por corrida manual del usuario;
   - inferido;
   - pendiente de verificar.
7. Si este documento contradice GitHub, **GitHub gana**.
8. No asumir que la DB local coincide exactamente con conteos históricos escritos aquí.

Forma recomendada de iniciar una nueva sesión:

```text
Repositorio: Gtestino92/chamba-hunter
Base: main

Primero:
- verificar HEAD/tree reales en GitHub;
- leer docs/PROJECT_CONTEXT.md;
- inspeccionar los archivos reales afectados por el próximo vertical;
- distinguir código vs evidencia de corridas manuales;
- recién entonces proponer cambios.
```

---

## 2. Preferencias operativas del usuario

- Conversación y explicaciones: **español**.
- Código, nombres técnicos y comentarios de código: **inglés**.
- Desarrollo incremental en vertical slices pequeños.
- Evitar sobrearquitectura.
- SQLite es la fuente de verdad local.
- Sin UI/web API por ahora.
- No automatizar postulaciones.
- El usuario hace `commit`/`push` manualmente.
- No crear branches/PRs ni escribir en GitHub salvo pedido explícito.
- **No agregar tests por ahora.**
- Sí usar validaciones baratas:
  - `python -m compileall -q src`
  - `git diff --check`
  - corridas funcionales manuales;
  - diagnósticos puntuales de shell/Python/SQL.
- Antes de sugerir push, preferir al menos una validación funcional.
- Para cambios de archivos, preferir entregar archivos completos o ZIPs preservando rutas repo-relative.
- Snippets parciales están bien para diagnósticos one-off.
- No hacer bypass anti-bot, fake browser ni scraping agresivo.
- 401/403/429 de páginas externas deben tratarse como señal operacional (`BLOCKED`/warning), no como invitación a evadir protección.
- Evitar dependencias nuevas salvo necesidad real.
- `httpx` es la librería HTTP actual.
- No introducir BeautifulSoup sólo para sortear bloqueos.

Entorno local observado:

```text
~/Documents/Git/chamba-hunter
Windows + Git Bash (MINGW64)
Python 3.12.x
venv: .venv
package: chamba_hunter
```

Activación habitual:

```bash
source .venv/Scripts/activate
```

---

## 3. Objetivo del producto

Chamba Hunter es una herramienta local de inteligencia para búsqueda laboral.

No aplica automáticamente. Debe construir y mantener una base útil de:

- empresas;
- fuentes que las descubrieron;
- careers pages;
- ATS;
- vacantes;
- leads de aggregators;
- compatibilidad geográfica;
- matching contra el perfil profesional;
- contactos/canales públicos para outreach manual;
- output final accionable.

Arquitectura conceptual vigente:

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
full ATS board sync when supported
    ↓
larger normalized candidate corpus
    ↓
cross-source canonicalization
    ↓
Argentina eligibility
    ↓
occupation / backend classification
    ↓
skills + seniority + matching / ranking
    ↓
Excel report / manual action
```

Outreach paralelo futuro:

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

Nunca descubrir, inferir ni adivinar emails personales de recruiters. Sólo contactos explícitamente públicos de la empresa.

---

## 4. Perfil profesional futuro para matching

Perfil resumido:

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
- GitHub Actions / GitLab CI/CD
- TypeScript / Node.js / NestJS como stack secundario
- Android / Compose secundario
- English C1
- seniority objetivo aproximado: semisenior / mid-level

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

## 5. Foundation actual

Arquitectura:

- Python package bajo `src/chamba_hunter`.
- Pydantic v2 en boundaries externos.
- Domain/tracing con dataclasses.
- Repositories explícitos sobre `sqlite3`.
- Sin SQLAlchemy.
- SQLite local.
- Migraciones SQL.
- `httpx` para HTTP.
- editable install previsto con `pip install -e .`.

Migraciones actuales:

```text
001_initial_schema.sql
002_company_classifications.sql
003_broad_job_acquisition.sql
```

Las migraciones aplicadas son inmutables. Si hace falta cambiar schema, crear una migración nueva.

Tablas/vistas relevantes actuales incluyen:

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
- `company_classifications`
- `job_leads`
- `job_ats_hints`
- view `job_candidates`

---

## 6. Company discovery / import — MVP terminado

Fuentes históricas de company discovery:

### Himalayas

Feed público:

```text
https://himalayas.app/jobs/api/search
```

### Get on Board

Feed público de Programming:

```text
https://www.getonbrd.com/api/v0/categories/programming/jobs
```

El import/dedup de empresas sigue estos principios:

1. misma identidad de source;
2. mismo dominio oficial;
3. fallback por `normalized_name` sólo si es único y compatible;
4. una empresa existente sin dominio puede enriquecerse si otra fuente trae dominio;
5. no fusionar dominios diferentes sólo por nombre.

Precisión de identidad > cobertura.

---

## 7. Company classification y geography — MVP existente

Tipos:

```text
PRODUCT
CONSULTANCY
RECRUITER
OTHER
UNKNOWN
```

No clasificar sólo por nombre y no forzar `UNKNOWN` a cero.

Señales geográficas existentes:

- company Argentina
- company Buenos Aires
- job Argentina
- job Buenos Aires
- remote global
- remote LATAM / South America
- remote Argentina-compatible
- remote + Buenos Aires

No inferir remote Argentina sólo porque la empresa esté basada en Argentina.

Prioridades existentes:

```text
VERY_HIGH
HIGH
MEDIUM
LOW
UNKNOWN
```

No recalibrar esta capa ahora salvo defecto concreto.

---

## 8. Careers / ATS detection

Servicio principal:

```text
src/chamba_hunter/services/careers_ats_detection_service.py
```

Comandos relevantes:

```text
src/chamba_hunter/commands/detect_careers_ats.py
src/chamba_hunter/commands/refresh_careers_ats.py
src/chamba_hunter/commands/discover_broad_ats.py
```

Pipeline conceptual:

```text
known careers URL
or company homepage
    ↓
HTTP fetch + redirects
    ↓
careers link discovery
    ↓
links / iframe / scripts / raw URLs / URL params
    ↓
ATS candidates
    ↓
public API / board probes only when there is public provider evidence
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

Métodos relevantes:

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

Reglas:

- no blind-probing de ATS identifiers;
- los provider probes se usan sólo cuando la página pública ya dio evidencia del provider;
- 401/403/429 se registran; no se evaden;
- URLs malformadas encontradas dentro del HTML se ignoran en vez de tumbar el scan completo;
- `company_ats` representa estado actual;
- `ats_detections` conserva tracing histórico.

---

## 9. Calibraciones ATS importantes

### Greenhouse

Probe por Job Board API aceptado cuando:

- board responde válidamente;
- el nombre es compatible con la empresa.

### Ashby

La API puede conservar boards históricos.

Regla actual para identifiers derivados:

- HTTP 200 no alcanza;
- debe existir evidencia suficiente de postings activos para validar el board derivado.

### Lever

El endpoint público de postings se usa para validar identifiers con evidencia previa.

### SmartRecruiters

Importante:

```text
HTTP 200 + totalFound = 0
```

NO valida un identifier.

Sólo se considera probe positivo cuando devuelve postings activos.

### Workable

Un board histórico o una página genérica no alcanza.

El probe verifica:

- URL final compatible;
- nombre compatible;
- evidencia de postings activos.

### BambooHR

Es detectable, pero no existe todavía ingestion adapter.

---

## 10. ATS ingestion implementado

Adapters / sync implementados:

```text
GREENHOUSE
ASHBY
LEVER
```

Comandos:

```text
python -m chamba_hunter.commands.sync_greenhouse_jobs
python -m chamba_hunter.commands.sync_ashby_jobs
python -m chamba_hunter.commands.sync_lever_jobs
```

Cada sync mantiene snapshot actual:

- upsert de postings observados;
- `first_seen_at` preservado;
- `last_seen_at` actualizado;
- postings ausentes del snapshot del board se desactivan;
- tracing mediante `runs` / `run_steps` / `ats_syncs`.

Adapters NO implementados todavía:

```text
WORKABLE
SMARTRECRUITERS
BAMBOOHR
```

---

## 11. Snapshot ATS observado antes del broad discovery reciente

Últimos conteos manuales confirmados antes de sincronizar cualquier board nuevo descubierto en broad discovery:

### Greenhouse

```text
Canonical 303
GitLab    188
Remote    204
Bitso       8
TOTAL     703
```

### Ashby

```text
Belvo       6
TOTAL       6
```

### Lever

```text
dLocal     58
Toptal     26
TOTAL      84
```

Total ATS jobs observado:

```text
793
```

Estos números son datos locales históricos; verificar de nuevo antes de usarlos como estado actual.

---

## 12. Broad job acquisition

Migración:

```text
003_broad_job_acquisition.sql
```

Nuevas entidades:

### `job_leads`

Staging/provenance para postings provenientes de aggregators.

Identidad:

```text
UNIQUE(source_type, external_id)
```

Puede enlazarse más adelante con:

```text
canonical_job_id -> jobs.id
```

### `job_ats_hints`

Evidencia ATS concreta extraída de URLs de leads.

No promueve automáticamente un ATS a `company_ats`.

### view `job_candidates`

Une:

```text
active ATS jobs
UNION ALL
active unresolved broad leads
```

El resultado es un corpus crudo previo a deduplicación cross-source.

Fuentes broad implementadas:

```text
HIMALAYAS
GETONBOARD
```

Comando:

```bash
python -m chamba_hunter.commands.acquire_broad_jobs \
  --himalayas-max-jobs 200 \
  --getonboard-max-pages 2
```

Semántica importante:

- broad aggregator pagination es parcial;
- ausencia de un lead en una corrida NO implica que la vacante cerró;
- por eso broad leads no usan la misma snapshot-deactivation que los ATS boards;
- `first_seen_at` se preserva;
- `last_seen_at` se actualiza.

Última corrida broad estabilizada observada:

```text
HIMALAYAS
received:   200
normalized: 200
updated:    200

GETONBOARD
received:   200
normalized: 200
updated:    200

Active unresolved leads: 400
Stored ATS hints:         0
Raw active candidates:    1193
```

El `1193` era:

```text
793 ATS jobs + 400 unresolved broad leads
```

antes de sincronizar boards descubiertos posteriormente.

---

## 13. Lecciones de normalización broad

### Himalayas pagination

Páginas adyacentes pueden solaparse por GUID.

Regla:

- ignorar GUID duplicado;
- avanzar offset por cantidad de filas devueltas por provider, no por cantidad de filas nuevas.

### Himalayas timestamps

En datos observados, `pubDate` / `expiryDate` numéricos pueden venir en segundos aunque documentación externa sugiera milisegundos.

Heurística estabilizada:

```text
>= 100_000_000_000 -> milliseconds
otherwise          -> seconds
```

### Himalayas `applicationLink`

Dato empírico importante:

- `applicationLink` apunta a la página del job dentro de Himalayas;
- NO es el external ATS apply URL.

Semántica actual:

```text
applicationLink -> job_url
apply_url       -> None
```

Un backfill one-shot corrigió localmente los 200 leads históricos que tenían esa URL en `apply_url`.

La utilidad de backfill no quedó en el repo; el código productivo actual ya escribe correctamente hacia adelante.

---

## 14. Protección de identidad Himalayas

Se observó un incidente upstream transitorio:

```text
companyName = "name"
```

26 leads de 17 `companySlug` distintos habían quedado fusionados en una única empresa local.

Se hizo una reparación local one-shot:

- 17 slugs reconciliados vía Himalayas MCP;
- 17 empresas reales creadas/reutilizadas;
- 26 leads movidos;
- 17 `company_sources` movidos;
- scan inválido histórico eliminado;
- empresa basura eliminada;
- `PRAGMA foreign_key_check`: OK.

Después de la reparación:

```text
bad company/name rows: 0
```

Único caso multi-slug restante observado:

```text
XKTalent Inc. - Rimutee
slugs: rekluti, xktalent-inc-rimutee
```

Se decidió NO separarlo automáticamente porque la evidencia observada es compatible con alias/rebrand de la misma entidad.

Protección productiva actual:

- si Himalayas vuelve a entregar exactamente `companyName="name"`,
- no se usa ese placeholder como identidad compartida;
- se deriva un nombre seed estable desde `companySlug`;
- el nombre canónico puede enriquecerse después vía MCP.

---

## 15. Himalayas company enrichment vía MCP

Scrapear HTML de perfiles Himalayas con `httpx` devolvió 403 de forma consistente.

Esa estrategia fue abandonada y no debe reintroducirse como workaround.

Solución productiva:

```text
src/chamba_hunter/sources/himalayas_mcp.py
src/chamba_hunter/commands/enrich_himalayas_websites.py
```

MCP público:

```text
https://mcp.himalayas.app/mcp
```

El cliente usa el tool público:

```text
get_company_details(company_slug)
```

y extrae:

- nombre canónico;
- website oficial.

El enrichment apunta a empresas:

- activas;
- con leads HIMALAYAS activos y unresolved;
- sin ATS activo;
- sin website;
- con slug HIMALAYAS disponible.

Resultados manuales observados:

Primer lote histórico:

```text
Processed: 10
Found:     10
Conflicts: 0
Failed:    0
```

Después de reparar la identidad, quedaron 145 elegibles.

Corridas:

```text
25 / 25 FOUND
120 / 120 FOUND
```

Total de esas 145 pendientes:

```text
Found:     145
Not found: 0
Conflicts: 0
Failed:    0
```

No hacer scraping alternativo de los perfiles si MCP resuelve el dato.

---

## 16. Broad careers / ATS discovery

Comando:

```bash
python -m chamba_hunter.commands.discover_broad_ats
```

Filtros relevantes:

```text
--limit N
--source ALL|HIMALAYAS|GETONBOARD
--dry-run
--include-scanned
```

Entrada permitida actual:

```text
KNOWN_CAREERS
HOMEPAGE
```

El comando ya NO usa:

```text
LEAD_APPLY_URL
LEAD_JOB_URL
```

como careers entry points.

Razón:

- aggregator URLs no son evidencia suficiente del ATS/careers oficial;
- en Himalayas `applicationLink` es una URL interna del aggregator.

Por defecto se excluyen empresas ya escaneadas contra su website actual.

`--include-scanned` permite volver a incluirlas explícitamente.

Scans históricos contra entry points obsoletos no cuentan como scan del website actual.

---

## 17. Resultados recientes de broad ATS discovery

Dry-run limpio después del enrichment:

```text
Companies without ATS: 246
Usable scan targets:   246
No usable entry point:   0
KNOWN_CAREERS:            0
HOMEPAGE:               246
```

### Primer lote real: 10

Detecciones:

```text
2BRAINS -> LEVER
Devsu   -> WORKABLE
```

Resultado:

```text
Processed:    10
Detected:      2
Not detected:  8
Blocked:       0
Failed:        0
Active ATS companies: 11 -> 13
```

Después se corrigió el selector para no reescanear por defecto esos 8 `NOT_DETECTED`.

Dry-run posterior:

```text
Companies without ATS: 244
Usable scan targets:   236
Scanned current site:    8
```

### Segundo lote real: 50

Detecciones:

```text
ELVTR                 -> WORKABLE
Fundraise Up          -> GREENHOUSE
mercor                -> ASHBY
Bluelight Consulting  -> LEVER
Sezzle                -> GREENHOUSE
Blend360              -> SMARTRECRUITERS
```

Resultado:

```text
Processed:    50
Detected:      6
Not detected: 32
Blocked:       9
Failed:        3
Skipped:       0
Active ATS companies: 13 -> 19
```

Provider distribution de ese lote:

```text
GREENHOUSE       2
ASHBY            1
LEVER            1
SMARTRECRUITERS  1
WORKABLE         1
```

Cumulativo de los dos lotes broad observados:

```text
GREENHOUSE       2
ASHBY            1
LEVER            2
SMARTRECRUITERS  1
WORKABLE         2
TOTAL            8
```

---

## 18. Blocked / failed recientes

`BLOCKED` es señal operacional y no requiere bypass.

En el lote de 50 hubo 9 bloqueos HTTP 403.

Tres `FAILED`:

### Lisit

```text
https://lisit.cl
ReadTimeout
```

Tratar como fallo transitorio de red.

### Ascensus

```text
https://ascensus.com
SSLV3_ALERT_HANDSHAKE_FAILURE
```

Tratar como fallo TLS externo/operacional salvo evidencia posterior de bug local.

### 3IT

```text
https://3it.cl
ValueError:
'a-zA-Z0-9-' does not appear to be an IPv4 or IPv6 address
```

Root cause:

- HTML externo contenía una referencia URL malformada;
- `urllib.parse.urlsplit()` podía lanzar `ValueError`;
- eso hacía fallar el scan completo.

Fix productivo actual:

- `_resolve_http_url()` ignora referencias malformadas;
- `_detect_from_url()` devuelve `None` para URLs inválidas.

Validación manual focalizada:

```text
resolve: None
detect:  None
```

El scan histórico de 3IT sigue registrado como FAILED; no se reescribió tracing.

---

## 19. Estado local inferido después de la última corrida

Confirmado directamente por la última corrida:

```text
Active ATS companies: 19
```

A partir de los outputs observados se espera, aproximadamente:

```text
238 companies without active ATS
52 already scanned against current site
~186 not-yet-scanned broad companies
```

Este último bloque es una inferencia aritmética, NO un snapshot consultado después del commit.

En una sesión nueva, verificar primero con:

```bash
python -m chamba_hunter.commands.discover_broad_ats --dry-run
```

antes de asumir esos valores.

---

## 20. Próximo foco inmediato

No empezar todavía por matching/ranking.

El próximo vertical debe cerrar la expansión del corpus de manera controlada.

Orden recomendado:

### Paso A — verificar estado real

1. GitHub `main` / HEAD / `PROJECT_CONTEXT.md`.
2. DB local mediante outputs del usuario.
3. `discover_broad_ats --dry-run`.

### Paso B — continuar broad ATS discovery sobre empresas nunca escaneadas

Objetivo:

- ampliar la muestra;
- medir cobertura real por provider;
- no reescanear sistemáticamente `NOT_DETECTED`/`BLOCKED`/`ERROR`;
- no hacer bypass.

Puede escalarse por lotes controlados.

### Paso C — sincronizar boards recién detectados de providers ya soportados

Nuevos boards observados que deberían revisarse/sincronizarse con adapters existentes:

```text
GREENHOUSE
- Fundraise Up
- Sezzle

ASHBY
- mercor

LEVER
- 2BRAINS
- Bluelight Consulting
```

Antes de ejecutar sync:

- inspeccionar `company_ats` real;
- verificar identifiers/board URLs actuales;
- usar los comandos provider existentes;
- observar jobs creados/actualizados/desactivados.

### Paso D — medir provider distribution antes de crear otro adapter

Candidates actuales sin ingestion adapter observados:

```text
WORKABLE
- Devsu
- ELVTR

SMARTRECRUITERS
- Blend360
```

No elegir adapter por intuición.

Primero terminar/expandir suficiente discovery y comparar frecuencia real de:

```text
WORKABLE
SMARTRECRUITERS
BAMBOOHR
otros
```

Luego implementar sólo el adapter con mayor valor marginal.

---

## 21. Después del broad ATS expansion

Una vez que se haya:

- escaneado suficiente universo broad;
- sincronizado Greenhouse/Ashby/Lever recién descubiertos;
- elegido e implementado el siguiente adapter si vale la pena;

pasar a:

### Cross-source canonicalization

Prioridad de matching:

1. match fuerte por ATS URL / provider / external id;
2. fallback conservador por company + title + location/date;
3. sólo entonces asignar `job_leads.canonical_job_id`.

No sobre-deduplicar.

Después medir:

```text
unique active candidate corpus
duplicates resolved
unresolved broad leads
ATS jobs
```

---

## 22. Roadmap posterior

Después de canonicalization:

1. Argentina eligibility;
2. occupation/software/backend classification;
3. skills extraction;
4. seniority;
5. matching/ranking contra perfil;
6. outreach candidates sólo con contactos públicos;
7. Excel final.

Tabs futuras sugeridas:

```text
Top Matches
Review
Outreach
Rejected / reasons   (opcional)
```

---

## 23. Cosas que NO hacer en el próximo chat

- No crear UI.
- No crear API web.
- No automatizar applications.
- No bypass de 403/429.
- No fake browser.
- No introducir Selenium/Playwright sólo para evadir bloqueos.
- No reintroducir scraping HTML de Himalayas profiles si MCP funciona.
- No blind-probar slugs/identifiers ATS sin evidencia pública.
- No implementar Workable/SmartRecruiters/BambooHR antes de medir cobertura suficiente.
- No empezar matching antes de ampliar/canonicalizar el corpus.
- No crear migraciones innecesarias.
- No agregar tests todavía salvo cambio explícito de decisión.
- No crear branch/commit/push/PR sin pedido explícito del usuario.
- No asumir que utilidades one-shot de reparación/backfill existen en el repo: fueron deliberadamente eliminadas antes del push.

---

## 24. Validaciones estándar

Para cambios Python:

```bash
python -m compileall -q src
git diff --check
```

Después, validación funcional focalizada del comando o provider afectado.

No correr exploraciones masivas de red sólo para “probar” un cambio pequeño.

---

## 25. Último push verificado al cerrar este handoff

`main`:

```text
a06fc5ef5462f1a134850c59214fad92fa1b612a
harden broad ATS discovery and Himalayas enrichment
```

Archivos incluidos en ese commit:

```text
src/chamba_hunter/commands/discover_broad_ats.py
src/chamba_hunter/commands/enrich_himalayas_websites.py
src/chamba_hunter/services/broad_job_acquisition_service.py
src/chamba_hunter/services/careers_ats_detection_service.py
src/chamba_hunter/sources/himalayas_mcp.py
```

Cambios esenciales:

- broad ATS discovery sólo por careers conocida / homepage oficial;
- exclusión por defecto de companies ya escaneadas en su website actual;
- `--include-scanned`;
- Himalayas MCP website enrichment;
- protección contra `companyName="name"`;
- `applicationLink` de Himalayas tratado como `job_url`;
- tolerancia a URLs HTML malformadas.

Fin del handoff.
