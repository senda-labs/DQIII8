# Panel Review — Asiento 2: corrección de código y completitud del arreglo de rutas de DB

Spec revisado: `docs/superpowers/specs/2026-08-14-db-consolidation-design.md`
Revisor: Opus 5, ciego respecto a los asientos 1 y 3. Fecha: 2026-08-14.

## Resumen

La lista de **11 ficheros de código está completa y correcta** — verificado por grep
cerrado sobre todas las tablas de conocimiento: no existe ningún consumidor adicional
en `bin/`, `my-projects/`, `.claude/`, `scripts/`, `tests/`, crontab ni systemd. La lista
de **4 ficheros de infraestructura está incompleta**: faltan al menos dos
(`bin/core/openrouter_wrapper.py:1111`, `bin/tools/health_check.py:131`), ambos con
efecto real post-migración. Además, la **regla "no negociable" de §5.1 (abortar si el
complemento no da exactamente 31 tablas) aborta siempre** sobre el sistema sano, porque
`sqlite_master` incluye `sqlite_sequence` (61−29 = **32**, no 31). Y el **test de regresión
de §5.4 tiene un falso-verde garantizado** en 3 de los 11 módulos, que se auto-crean la
tabla que el test comprueba. Dos afirmaciones factuales del spec son falsas (§5.2 sobre
`schema_v2.sql`; el conteo de crons de §5.3 paso 3).

---

## Hallazgos

### 1 — [P1] La regla de aborto de §5.1 aborta siempre: `sqlite_sequence` rompe la aritmética 31/29

**Descripción.** §5.1 impone como "regla de implementación no negociable" que el script
genere la lista de supervivientes por complemento (`SELECT name FROM sqlite_master WHERE
type='table'` menos los 29 `DROP`) y **aborte si el resultado no coincide exactamente con
las 31 enumeradas**. `dqiii8_metrics.db` tiene 61 tablas en `sqlite_master`, no 60: la
sexagésimo primera es `sqlite_sequence` (tabla interna de SQLite, creada por
`AUTOINCREMENT`). El complemento da 32.

**Evidencia (ejecutado):**
```
$ python3 -c "...select name from sqlite_master where type='table' ..."
total tables: 61 drop: 29 complement: 32
complement extras vs spec 31: ['sqlite_sequence']
```

**Escenario de fallo concreto.** El paso 0 (dry-run obligatorio) aborta en la primera
ejecución sobre un sistema perfectamente sano. El riesgo real no es el aborto en sí — es
la reacción: el operador, viendo un aborto espurio en un paso etiquetado "no negociable",
relaja o desactiva la comprobación, que es exactamente la salvaguarda que impide un `DROP`
sobre una tabla de conocimiento. `sqlite_sequence` además **sobrevive al `DROP`** de las 29
(SQLite no la elimina), así que el desajuste persiste en `dqiii8_knowledge.db`.

**Arreglo.** Excluir explícitamente `sqlite_sequence` y `sqlite_%` del complemento, o
declarar 32 y nombrarla en la lista de §5.1.

---

### 2 — [P1] El test de regresión de §5.4 tiene un falso-verde garantizado en 3 de 11 módulos

**Descripción.** §5.4 exige "un test que, para cada uno de los 11 módulos de §5.2,
verifique que `DB_PATH` tal como se resuelve en runtime contiene realmente las tablas que
ese módulo consulta". Tres de esos módulos **crean ellos mismos, con `CREATE TABLE IF NOT
EXISTS`, la tabla cuya existencia el test comprueba**. Un test de existencia pasa aunque el
módulo apunte a la DB equivocada — que es literalmente el bug de hoy.

**Evidencia (grep real):**
- `bin/agents/chunk_freshness_reviewer.py:47` — `CREATE TABLE IF NOT EXISTS chunk_health (`
- `bin/tools/knowledge_harvester.py:103` — `CREATE TABLE IF NOT EXISTS harvest_log (`
- `bin/ui/dashboard.py:847,851` — `CREATE TABLE IF NOT EXISTS chat_sessions` / `chat_messages`

Confirmación de que el mecanismo ya ha ocurrido en producción: ambas tablas existen **vacías
en `dqiii8.db`**, creadas por estos mismos módulos apuntando mal:
```
chunk_health in main rows= 0
harvest_log  in main rows= 0
```
(`facts` y `vector_chunks` sí lanzan `no such table` en `dqiii8.db` — esas no se auto-crean.)

**Escenario de fallo concreto.** Se olvida repuntar `chunk_freshness_reviewer.py`. El test
de §5.4 arranca, el módulo crea `chunk_health` vacía en `dqiii8.db`, el test verifica
"la tabla existe" → verde. El cron de los domingos sigue roto (falla en `vector_chunks`,
que no se auto-crea) y nadie se entera. Idéntico para `dashboard.py`: el chat sigue
escribiendo en `dqiii8.db` con split-brain y el test pasa.

**Arreglo.** El criterio no puede ser existencia. Debe ser: (a) la tabla existe **y** tiene
`count(*) > 0` para las tablas con dato conocido (`vector_chunks` 927, `chunk_health` 271,
`chunk_key_facts` 936, `harvest_log` 58, `chat_messages` 10), y (b) el `DB_PATH` resuelto
apunta al fichero `dqiii8_knowledge.db` por nombre. Coherente con la propia corrección C2
del spec ("verificar `len(resultados) > 0`, no ausencia de excepción") — el spec aplica ese
criterio a la verificación manual pero no al test automatizado.

---

### 3 — [P1] El test de §5.4 es inimplementable tal como está escrito para 3 de los 11 módulos: no tienen `DB_PATH`

**Descripción.** §5.4 asume que los 11 módulos exponen un símbolo `DB_PATH` inspeccionable
en runtime. Tres no lo tienen:

| Fichero | Símbolo real |
|---|---|
| `bin/tools/benchmark_multimodel.py:33` | `DB = ROOT / "database" / "dqiii8.db"` (se llama `DB`, no `DB_PATH`) |
| `bin/ui/dashboard.py:840,878,951,981,998` | **cinco** literales `db = JARVIS / "database" / "dqiii8.db"` locales a función, sin símbolo de módulo |
| `bin/agents/knowledge_enricher.py:139,429,512,625,817` | **cinco** `db_path = ...` locales a función, sin símbolo de módulo |

**Evidencia (ejecutado):**
```
temporal_memory.DB_PATH = /root/dqiii8/database/dqiii8.db
hybrid_search.DB_PATH   = /root/dqiii8/database/dqiii8.db
vector_store.DB_PATH    = /root/dqiii8/database/dqiii8.db
knowledge_enricher DB_PATH attr? False
```

**Escenario de fallo concreto.** El test se escribe como un bucle `for mod in MODULES:
assert tables(mod.DB_PATH) >= mod.TABLES`. Para estos tres, `getattr(mod,'DB_PATH')` lanza
`AttributeError` y se resuelve "pragmáticamente" con un `hasattr` guard o un `skip` — con
lo que los tres módulos de mayor riesgo (el enricher con 4 rutas independientes, el
dashboard con 5) quedan **sin cobertura**, justo los que el spec identifica como la
degradación real. Este hallazgo y el nº2 se solapan en `dashboard.py`: sin `DB_PATH` **y**
auto-creando sus tablas.

**Arreglo.** Prerrequisito del test: extraer en los tres ficheros una constante de módulo
(o consumir `paths.KNOWLEDGE_DB_PATH`, ver hallazgo 6). Es trabajo de refactor, no de test.

---

### 4 — [P1] La lista de 4 ficheros de infraestructura está incompleta: faltan `openrouter_wrapper.py` y `health_check.py`

**Descripción.** El barrido de §5.2 ("confirmado sin dependencias reales fuera de `bin/`",
y las 4 infra listadas) omite dos ficheros que abren/gobiernan estas DBs por nombre literal.

**Evidencia (grep real):**
```
bin/core/openrouter_wrapper.py:1111:    for rel in (".env", "database/dqiii8.db", "database/dqiii8_history.db",
bin/core/openrouter_wrapper.py:1112:                "database/dqiii8_metrics.db"):
bin/tools/health_check.py:131:    hist = ROOT / "database" / "dqiii8_history.db"
```

**4a — `openrouter_wrapper.py:1102-1120` (`_enforce_sensitive_permissions`), P1.** Es el
mecanismo *continuo* que reimpone `0600` en cada arranque del wrapper (entry point del
sistema). Estado actual verificado: las 3 DBs son `-rw------- root root`. Tras la
consolidación, `dqiii8_knowledge.db` **no está en esa tupla** → queda fuera de la
reimposición permanente. §5.3 paso 10 hace un `chmod 600` de una sola vez en el script de
migración; eso no sustituye al enforcement continuo, y la propia nota del paso 10 reconoce
que `.backup` crea `0644`. Escenario concreto: cualquier `sqlite3 ... ".backup"`,
`VACUUM INTO` o restauración manual posterior recrea el fichero a `0644`, y a diferencia de
las otras tres DBs, nada lo vuelve a cerrar. Regresión de seguridad silenciosa, indefinida.

**4b — `health_check.py:126-134`, P2.** Otorga +10 sobre 100 si `dqiii8_history.db` existe
y es owner-only. §5.1 elimina ese fichero del disco → `hist.exists()` es `False` → `secure`
es `False` → **−10 puntos permanentes**. Umbral de alerta: `if score < 70` (línea 158).
Escenario concreto: el health_check diario pasa de techo 100 a techo 90 para siempre; el
margen antes de la alerta se reduce de 30 a 20 puntos, y el comentario de las líneas
126-130 (que documenta explícitamente por qué este check existe) queda describiendo un
fichero inexistente. Peor: el sistema no alerta, simplemente pierde margen — el mismo
patrón de degradación silenciosa que el spec denuncia en §G.

**4c — `update_dqiii8.sh:22`, P3.** `-e "database/dqiii8_metrics.db"` en los excludes de
`git clean -fd`. Redundante hoy (`database/*.db` en la línea 21 ya cubre), y seguirá
cubriendo `dqiii8_knowledge.db`. Sin impacto funcional; se lista para que la limpieza de
nombres sea completa.

---

### 5 — [P2] §5.2 afirma que ninguna tabla del clúster de conocimiento está en `schema_v2.sql`. Es falso: `chunk_health` sí lo está

**Descripción.** §5.2 dice textualmente: *"Verificado: las 29 tablas de `DROP` […] están
todas declaradas en `database/schema_v2.sql`, y ninguna tabla del clúster de conocimiento
lo está."* Ambas mitades son inexactas.

**Evidencia (ejecutado):**
```
KEEP-list tables ALSO declared in schema_v2.sql (spec says none): ['chunk_health']
DROP-list tables NOT in schema_v2.sql (spec says all are): ['session_memory']
```
(`session_memory` es la excepción ya conocida y manejada — `install.sh:145` la crea con un
`CREATE TABLE` inline aparte, no vía `schema_v2.sql`. Esa mitad no es un problema.)

**Escenario de fallo concreto.** `chunk_health` — que §2.1/C5 acaba de reclasificar, con
razón, como tabla **viva del clúster de conocimiento** — está declarada en el SSOT de
esquema. Consecuencia: cada `update_dqiii8.sh` (línea 74) e `install.sh` (línea 139)
posteriores a la consolidación **recrean `chunk_health` vacía dentro de `dqiii8.db`**. Eso
reabre indefinidamente la trampa del hallazgo nº2: existe una `chunk_health` vacía en la DB
equivocada, permanentemente, resembrada por el instalador. §7 excluye del alcance tocar
`schema_v2.sql` — decisión correcta como política, pero el spec debe **saber** que este caso
queda abierto y documentarlo, en vez de afirmar lo contrario.

---

### 6 — [P2] El refactor a `paths.py` está infravalorado: la constante que haría falta no existe

**Descripción.** §5.2 marca correctamente que `paths.METRICS_DB_PATH` no tiene consumidores
y que centralizarlo es un refactor real. Lo que no dice: (a) `paths.py` no define ninguna
`KNOWLEDGE_DB_PATH` — hay que **crearla** y decidir el destino de `METRICS_DB_PATH`
(¿renombrar? ¿alias? ¿borrar?); (b) el número de puntos a tocar no son 11 imports sino
**~20 sitios de conexión**, porque 2 de los 11 ficheros tienen múltiples literales locales.

**Evidencia (grep real):**
```
bin/core/paths.py:11:METRICS_DB_PATH = ROOT / "database" / "dqiii8_metrics.db"
$ grep -rn "METRICS_DB_PATH" bin/ tests/ .claude/   → 1 hit, su propia definición
```
Consumidores actuales de `paths.py` en todo el repo: `bin/core/cdp_client.py:30`,
`bin/tools/cdp_investigate.py:35`, `bin/tools/fix_orphaned_failures.py:16`,
`bin/tools/db_init.py:16`. Ninguno de los 11.

Puntos de conexión reales por fichero: `knowledge_enricher.py` 5 (139/429/512/625/817),
`dashboard.py` 5 (840/878/951/981/998), los otros 9 con 1 constante de módulo cada uno.

**Escenario de fallo concreto.** Se repunta la constante de módulo de los 9 ficheros
"fáciles" y se dan por hechos los 11. Los literales locales de `knowledge_enricher.py`
(429, 625, 817) y `dashboard.py` (878, 951, 981, 998) sobreviven — repuntar solo el primer
literal de cada fichero es el error natural. Es el mismo modo de fallo que causó el bug
original en 2026-03. **Sin riesgo de import circular**: `paths.py` no importa nada del repo
(solo `os`/`pathlib`), verificado leyendo el fichero completo.

---

### 7 — [P2] Nada crea el esquema de `dqiii8_knowledge.db` en una instalación limpia

**Descripción.** Tras la consolidación, los 11 ficheros repuntados dependen de un fichero
que **ningún instalador sabe crear**. `install.sh` solo aplica `schema_v2.sql` a `dqiii8.db`
(línea 139) y a `dqiii8_metrics.db` (línea 145); `update_dqiii8.sh` igual (líneas 74-75).
Ninguno menciona el esquema del clúster de conocimiento.

**Evidencia (grep real):** el único fichero que define esas tablas es
`database/legacy/schema_temporal.sql`, referenciado **solo desde los tests**:
```
tests/test_temporal_memory.py:60:_SCHEMA = .../database/legacy/schema_temporal.sql
tests/test_vector_hybrid_search.py:50:_SCHEMA = .../database/legacy/schema_temporal.sql
database/legacy/README.md:8:| schema_temporal.sql | Pre-v2 | ... never promoted to production |
```
El README de `legacy/` califica de "nunca promovido a producción" el esquema de una DB de
33 MB que está en producción.

**Escenario de fallo concreto.** Instalación limpia (o restauración desde repo tras pérdida
del VPS): `dqiii8_knowledge.db` no existe; los 11 módulos abren un fichero SQLite vacío que
`sqlite3.connect` crea al vuelo, y el sistema arranca con el clúster de conocimiento
apagado — **el estado exacto que este spec existe para arreglar**, reintroducido por la vía
del instalador. §5.2 corrige que `update_dqiii8.sh` no *recree* `metrics.db`, pero no cubre
el hueco simétrico: que nadie *cree* `knowledge.db`.

**Arreglo.** Promover `schema_temporal.sql` (+ las sentencias FTS5/vec0 que hoy se crean en
runtime) a `database/schema_knowledge.sql` y añadirlo a `install.sh`/`update_dqiii8.sh` en
el mismo commit; o documentar explícitamente que la instalación limpia parte de un backup.

---

### 8 — [P3] §5.3 paso 3 subestima el número de crons a parar (10 declarados, 13 reales)

**Evidencia (`crontab -l`, ejecutado):** 13 jobs activos. Además de los que el spec nombra,
están `auto_researcher.py --full` (lunes 06:05, escribe `research_items` — tabla de la lista
de `DROP`), `health_check.py` (05:50) y `health_watchdog.py --quiet` (06:00). El spec
menciona `nightly.sh 03:05` y `triage_error_log.py 03:50` con horas correctas, y
`purge_transient_errors.py` a las 04:00 (real: `0 4 * * *`, correcto).

**Escenario de fallo.** Bajo. `systemctl stop cron` los para todos, así que el arreglo
prescrito funciona; el error está en el conteo, no en la acción. Se anota porque el spec
usa ese conteo como justificación del paso y una lista incompleta invita a "parar solo
esos" si alguien decide no tumbar cron entero.

---

### 9 — [P3] Comentario obsoleto en `test_vector_hybrid_search.py` no está en la lista de doc a actualizar

**Evidencia:** `tests/test_vector_hybrid_search.py:5-7` afirma *"the facts/fact_access_log
tables live readonly in `dqiii8_history.db`"*. Verificado: viven en `dqiii8_metrics.db`
(`facts` 6 filas, `fact_access_log` 12 560); en `dqiii8.db` ni siquiera existe `facts`
(`no such table: facts`, ejecutado). La lista de documentación de §5.2 recoge `CLAUDE.md`,
`.claude/rules/`, `zones/` — pero no este docstring, ni
`.claude/rules_db/dqiii8-error-prevention.md:20` (solo cita la línea 19), ni los comentarios
de `openrouter_wrapper.py:1108-1110` y `health_check.py:126-130`, que quedarán describiendo
un fichero borrado tras §5.1.

---

## Verificado sin problemas

- **La lista de 11 ficheros de código es completa.** Grep cerrado por nombre de tabla
  (`vector_chunks|chunk_key_facts|knowledge_usage|harvest_log|subdomain_centroids|
  fact_access_log|chunk_health|vec_knowledge`) sobre `bin/ .claude/ my-projects/ scripts/
  tests/` devuelve exactamente 9 ficheros de producción + los 2 tests; los otros 2 de los 11
  (`dashboard.py` por `chat_*`, `benchmark_multimodel.py` por `benchmark_*`) salen del
  barrido por tabla correspondiente. **No hay ningún consumidor adicional.** Los hits en
  `bin/tools/_archived/` son código archivado, no ejecutado por cron ni importado.
- **La afirmación de §5.2 "los 11 declaran literalmente `DB_PATH = DQIII8_ROOT / "database"
  / "dqiii8.db"` y ninguno importa `paths.py`" es correcta en cuanto al destino**, y
  confirmada en runtime para los inspeccionables (`temporal_memory`/`hybrid_search`/
  `vector_store` → `/root/dqiii8/database/dqiii8.db`). Matiz de forma en el hallazgo 3.
- **Ningún import circular.** `bin/core/paths.py` importa solo `os` y `pathlib`.
- **La corrección C2 es exacta y la reproduje en vivo:** `query_facts()` →
  `OperationalError: no such table: facts`; `hybrid_search(...)` → `([], 'empty')` sin
  excepción; `vector_store.search_text('test',3)` → `[]` sin excepción. El criterio de
  éxito `len(resultados) > 0` de §5.4 es el correcto.
- **La afirmación sobre los tests es exacta.** `tests/test_temporal_memory.py:33-52` y
  `tests/test_vector_hybrid_search.py:36-47` crean un `NamedTemporaryFile` y sobrescriben
  `tm.DB_PATH`/`vs.DB_PATH`/`hs.DB_PATH` antes de cualquier aserción. Cero señal de
  producción, tal como dice el spec.
- **`domain_enrichment` en la lista de `DROP` es seguro.** Sus tres consumidores vivos
  (`hierarchical_router.py:257`, `domain_classifier.py:544-599`, `intent_amplifier.py:257`)
  resuelven vía `bin/core/db.py:9` → `dqiii8.db`, donde la tabla tiene las 5 filas (la
  versión rica, según C1). Borrar la copia de `metrics` no afecta a ningún lector.
- **Ningún fichero de los 11 necesita las dos DBs a la vez de forma no separable.**
  `dashboard.py` es el único que toca ambos conjuntos (`agent_actions`, `human_hours`,
  `error_log`, `sessions`, `amplification_log`, `audit_reports` en `dqiii8.db` vs
  `chat_sessions`/`chat_messages` en conocimiento), pero el bloque de chat está limpiamente
  aislado en las líneas 838-1010 con sus propias conexiones — **el acotado "líneas 840-998"
  de §5.2 punto 8 es correcto**. `knowledge_harvester.py` y `chunk_freshness_reviewer.py`
  aparecen tocando tablas presentes en ambas DBs (`chunk_health`, `harvest_log`) solo porque
  ellos mismos las crearon vacías en `dqiii8.db` (hallazgo 2); su repunteo total es correcto.
- **`memory_decay.py` y `auto_researcher.py` (ambos en cron) no tocan tablas de
  conocimiento** — `memory_decay` opera sobre `vault_memory`/`instincts` en `dqiii8.db`.
  No entran en el alcance.
- **Ninguna unidad systemd ni fichero en `/etc/cron.d/` referencia estas DBs**
  (`grep -rn "\.db" /etc/systemd/system/dq*.service` → sin resultados).
- **Permisos de partida confirmados:** las 3 DBs son `-rw------- root root`, coherente con
  la premisa del paso 10.
