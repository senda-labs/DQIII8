# Panel review — asiento 1: integridad de datos y seguridad de la migración

Spec revisado: `docs/superpowers/specs/2026-08-14-db-consolidation-design.md`
Fecha de la revisión: 2026-08-14 (estado de las DBs a las 12:30 UTC)
Método: re-verificación independiente vía `sqlite3` en vivo sobre las 3 DBs reales,
simulación completa de los pasos 6–7 del §5.3 sobre una copia, y lectura del código
real de los 15 ficheros que el spec afirma tocar.

## Resumen

El núcleo analítico del spec es sólido: verifiqué de forma independiente el overlap 0
en las 10 tablas de §2.2, la exclusividad mutua de las listas 29/31, y las 4 rutas mal
apuntadas de `knowledge_enricher.py` — todo confirmado línea por línea. Pero la
**mecánica de ejecución del §5.3 no es ejecutable tal como está escrita**: encontré 3
bloqueantes duros (la tabla destino de `session_memory` no existe, el comando de
verificación del dump devuelve 0 siempre, y el guardián de "exactamente 31 tablas"
aborta siempre por `sqlite_sequence`), 1 afirmación factual falsa que introduce un
`DELETE` nocturno no revisado contra el SSOT (`cleanup_old_sessions` **sí** tiene
caller: `bin/nightly.sh:122`), y 2 ficheros de infraestructura ausentes de la lista de
§5.2. Ninguno destruye datos por sí solo, pero tres de ellos abortan la migración a
mitad y el del `DELETE` vacía en 24h lo que la migración acaba de mover.

---

## Hallazgos

### 1 — [P0] El paso 5 falla siempre: `session_memory` **no existe** en `dqiii8.db`

**Descripción.** §5.1 dice que `dqiii8.db` «gana la tabla `session_memory` (traspaso
completo desde `dqiii8_history.db`, **sin cambio de esquema**)» y el §5.3 paso 5
ejecuta directamente `ATTACH ...; INSERT OR IGNORE INTO session_memory SELECT * FROM
history.session_memory`. La tabla destino no existe hoy en `dqiii8.db` y **no está
declarada en `database/schema_v2.sql`**. El paso implícito no descrito es un
`CREATE TABLE`.

**Evidencia.**
```
$ sqlite3 database/dqiii8.db "SELECT sql FROM sqlite_master WHERE name='session_memory';"
Error: in prepare, no such table: session_memory
$ grep -c -i session_memory database/schema_v2.sql
0
```
La única definición viva está hardcodeada en `bin/agents/working_memory.py:30`
(`CREATE TABLE IF NOT EXISTS session_memory ...` dentro de `_get_conn()`), y en
`update_dqiii8.sh:75-76` (contra `dqiii8_metrics.db`).

**Escenario de fallo.** El script llega al paso 5 con cron y servicios ya parados
(paso 3) y aborta con `OperationalError: no such table: session_memory`. El sistema
queda con cron parado y sin migrar; recuperable, pero es un aborto a mitad en el
estado más frágil. Peor variante: si el implementador "arregla" el error añadiendo un
`CREATE TABLE` improvisado con distinto orden de columnas, el `SELECT *` posicional
del paso 5 mete `content` en `role` sin error visible (`OR IGNORE` se comería la
violación del `CHECK(role IN ('user','assistant'))` fila a fila).

**Corrección.** El paso 5 debe (a) crear la tabla copiando literalmente la sentencia
de `sqlite_master` de `dqiii8_history.db`, no reescribiéndola; (b) usar lista de
columnas explícita, nunca `SELECT *`; (c) verificar `count(*)` post-inserción contra
el congelado, y **abortar** si difiere (no solo "verificar").

Nota: el orden de columnas de las dos `session_memory` existentes (history y metrics)
sí coincide, y las 52 filas de history cumplen el `CHECK` y los `NOT NULL`
(`SELECT count(*) ... WHERE role NOT IN ('user','assistant') OR content IS NULL OR
session_id IS NULL` → `0`). El riesgo es del esquema improvisado, no de los datos.

---

### 2 — [P0] El comando de verificación del dump (§5.3 paso 4) devuelve **0 para todas las tablas**

**Descripción.** §5.3 paso 4 prescribe literalmente
`zcat dump | grep -c '^INSERT INTO "tabla"'`. `sqlite3` 3.45.1 emite el nombre de
tabla **sin comillas** cuando no las necesita. El patrón no matchea nunca.

**Evidencia.**
```
$ sqlite3 -version
3.45.1 2024-01-30 ...
$ sqlite3 database/dqiii8_metrics.db ".dump error_log" | gzip > /tmp/error_log.sql.gz
$ sqlite3 database/dqiii8_metrics.db "SELECT count(*) FROM error_log;"
856
$ zcat /tmp/error_log.sql.gz | grep -c '^INSERT INTO "error_log"'
0
$ zcat /tmp/error_log.sql.gz | grep -c '^INSERT INTO error_log VALUES'
856
$ zcat /tmp/error_log.sql.gz | head -c 120
INSERT INTO error_log VALUES(1,'2026-03-16 17:29:23','cd902868-...
```
Reproducido idéntico en `vault_memory` (850 real / 0 con comillas / 850 sin) y
`amplification_log` (1849 / 0 / 1849).

**Escenario de fallo.** El guardián que existe precisamente para detectar un `gzip`
truncado por disco lleno compara `0 != 856` en **todas** las 29 tablas. Dos desenlaces,
ambos malos: (a) el script aborta siempre y nunca se llega a probar el mecanismo
real; (b) el implementador, viendo que "falla siempre", relaja o desactiva la
comprobación — y entonces el paso 7 (`DROP`) se ejecuta sin ninguna verificación
efectiva del backup. Este es el único guardián entre el `DROP` y la pérdida
irrecuperable de las 6.700 filas que solo viven en `metrics.db`.

**Corrección.** Además de quitar las comillas, el chequeo por conteo de líneas es
más débil de lo que el spec supone: `grep -c` cuenta líneas, y los dumps contienen
valores con saltos de línea embebidos (`error_log`: 873 líneas totales vs 856
`INSERT`; `amplification_log`: 1865 vs 1849). Un valor de texto que contuviera una
línea que empiece por `INSERT INTO <tabla> VALUES` inflaría el conteo sin que nadie
lo notara. La verificación robusta es restaurar el `.gz` a una DB `:memory:` /
temporal y comparar `count(*)` real tabla por tabla, más `gzip -t` sobre el fichero.

---

### 3 — [P1] El guardián de «exactamente 31 tablas» aborta siempre: falta `sqlite_sequence`

**Descripción.** §5.1 impone como «regla de implementación no negociable» que el
script genere la lista de supervivientes por complemento
(`SELECT name FROM sqlite_master WHERE type='table'` menos los 29 `DROP`) y **aborte**
si no coincide exactamente con las 31 enumeradas. `dqiii8_metrics.db` tiene **61**
tablas, no 60. La 61.ª es `sqlite_sequence`, que no aparece en ninguna de las dos
listas del spec.

**Evidencia.**
```
$ sqlite3 database/dqiii8_metrics.db "SELECT count(*) FROM sqlite_master WHERE type='table';"
61
$ comm -23 <lista_real_ordenada> <(sort -u drop29 keep31)
sqlite_sequence
$ comm -13 ...   # nada en las listas que no esté en la DB
$ comm -12 drop29 keep31   # intersección vacía → mutuamente excluyentes ✓
```
Simulación completa de los pasos 6–7 sobre una copia (`VACUUM INTO` + los 29 `DROP`):
```
$ sqlite3 /tmp/knowledge.db "SELECT count(*) FROM sqlite_master WHERE type='table';"
32          # no 31
```
Y si en lugar de comparar contra la lista literal el script derivara el `DROP` por
complemento de las 31 de conservar:
```
$ sqlite3 /tmp/t2.db "DROP TABLE sqlite_sequence;"
Error: in prepare, table sqlite_sequence may not be dropped
```

**Escenario de fallo.** Dos ramas. Si el script implementa la regla al pie de la
letra, el dry-run (§5.3 paso 0b) aborta en cada ejecución y nunca se migra. Si el
implementador deriva el `DROP` por complemento (lectura igualmente válida del texto
de §5.1.1: «generada y verificada por complemento contra las 31 de conservar»),
`DROP TABLE sqlite_sequence` lanza excepción **después** de haber borrado ya un
subconjunto de las otras 29 — aborto a mitad del `DROP`, en el punto exacto que el
paso 7 se reordenó para evitar. Sobrevive porque `dqiii8_knowledge.db` ya existe,
pero el estado resultante es el «rollback parcial» que §5.5 declara «el estado más
peligroso posible».

**Corrección.** Excluir explícitamente `sqlite_sequence` (y en general
`name LIKE 'sqlite_%'`) del complemento, y fijar el guardián en 32 tablas totales
post-`DROP` / 31 + `sqlite_sequence`. Verificado además que los `DROP` limpian
correctamente las filas de `sqlite_sequence` de las tablas borradas (quedan 14
entradas, todas de tablas conservadas).

---

### 4 — [P1] `cleanup_old_sessions()` **sí tiene caller** (nightly, 03:05): el traspaso de `session_memory` se autodestruye en 24h

**Descripción.** §4 («Hallazgo adyacente») y §7 afirman dos veces que
`cleanup_old_sessions()` «no tiene ningún caller — ni cron ni código» y que «la tabla
oficial de 52 filas crece sin límite». Ambas son falsas.

**Evidencia.**
```
$ grep -n "working_memory" bin/nightly.sh
122:python3 "$DQIII8_ROOT/bin/agents/working_memory.py" --cleanup 2>&1 || echo "  Working memory cleanup failed"
$ crontab -l | grep nightly
5 3 * * * cd /root/dqiii8 && bash bin/nightly.sh > tasks/nightly-report.md 2>&1
```
`bin/agents/working_memory.py:135-137` → `if "--cleanup" in sys.argv: n = cleanup_old_sessions(24)`.
La forma de los datos lo corrobora: la tabla «que crece sin límite» contiene 52 filas
en una ventana de **30 horas** (`min=2026-08-13 06:01:03`, `max=2026-08-14 11:29:18`),
de las cuales solo 2 tienen más de 24h — el residuo exacto de una purga diaria que
funciona.

**Escenario de fallo.** El paso 8 repunta `working_memory.py` a `dqiii8.db`. A las
03:05 de la noche siguiente, `nightly.sh:122` ejecuta
`DELETE FROM session_memory WHERE timestamp < datetime('now','-24 hours')`
**contra el SSOT operativo**. Las 52 filas recién migradas desaparecen en dos noches.
Consecuencias: (a) el traspaso no aporta nada duradero — es una copia con vida útil de
24h; (b) se introduce un `DELETE` nocturno nuevo contra `dqiii8.db` que el spec no
identifica, no revisa y no menciona en §5.4; (c) si alguien ejecuta la verificación
post-migración al día siguiente y ve 2 filas donde había 52, el diagnóstico natural
—"la migración perdió datos"— es incorrecto y puede disparar un rollback innecesario
sobre el SSOT (el escenario >48h de §5.5, el que el propio spec declara sin
restauración limpia posible).

**Corrección.** Reescribir §4/§7 con el caller real. Decidir explícitamente si el
`--cleanup` nocturno debe seguir apuntando a la misma tabla tras la fusión, y añadir a
§5.4 una nota de que un `count(*)` de `session_memory` medido >24h después de la
migración **no** es evidencia de pérdida.

---

### 5 — [P2] `bin/tools/health_check.py` y `bin/core/openrouter_wrapper.py` faltan en la lista de infraestructura de §5.2

**Descripción.** §5.2 enumera 4 ficheros de infraestructura (`update_dqiii8.sh`,
`install.sh`, `db_backup.sh`, `health_watchdog.py`) y afirma que el barrido fuera de
`bin/` está completo. Un `grep` exhaustivo por nombre de fichero de DB devuelve dos
consumidores vivos más, ninguno listado.

**Evidencia.**
```
$ grep -rn "dqiii8_metrics\.db\|dqiii8_history\.db" --include=*.py --include=*.sh . | grep -v .venv
...
bin/core/openrouter_wrapper.py:1111-1112:  for rel in (".env", "database/dqiii8.db", "database/dqiii8_history.db",
                                                       "database/dqiii8_metrics.db"):
bin/tools/health_check.py:131:  hist = ROOT / "database" / "dqiii8_history.db"
```

**Escenario de fallo (a) — permisos.** `openrouter_wrapper._enforce_sensitive_permissions()`
(línea 1104) es lo que mantiene las DBs en `0600` de forma continua, sobre una lista
hardcodeada. `dqiii8_knowledge.db` no estará en ella. El §5.3 paso 10 hace un
`chmod 600` **una sola vez**; verificado que hace falta, porque tanto `VACUUM INTO`
como `.backup` crean el fichero en `0644`:
```
$ sqlite3 database/dqiii8_metrics.db "VACUUM INTO '/tmp/knowledge.db'"
$ ls -la /tmp/knowledge.db → -rw-r--r--
```
Cualquier recreación posterior (rollback, restauración de backup, nuevo `VACUUM INTO`)
deja la DB de conocimiento en `0644` **permanentemente**, porque el único mecanismo que
lo corregiría ya no la conoce. Es una regresión de seguridad silenciosa en un sistema
con dos incidentes de fuga documentados este mismo mes.

**Escenario de fallo (b) — score de salud.** `health_check.py:132-135` otorga
`+10` al score diario si `dqiii8_history.db` existe con permisos owner-only. Tras
borrar el fichero (§5.1), `hist.exists()` es `False`, `secure` es `False`, y el score
diario cae 10 puntos **para siempre**, sin error ni traza. Cron diario 05:50.

---

### 6 — [P2] Las 19 vistas de `dqiii8_metrics.db` no aparecen en ningún punto del spec; 10 de ellas quedan rotas por el `DROP`

**Descripción.** §5.1 razona exclusivamente sobre `type='table'`. `dqiii8_metrics.db`
contiene además 19 vistas y 56 índices. `VACUUM INTO` copia las vistas al fichero
nuevo, y los `DROP TABLE` no las eliminan: quedan como definiciones colgando del vacío.

**Evidencia.** Estado hoy vs. estado simulado tras los 29 `DROP`:

| Vista | Hoy | Tras el DROP |
|---|---|---|
| `knowledge_benchmark_summary` | 49 filas | `no such table: knowledge_benchmark_results` |
| `knowledge_benchmark_dq_uplift` | 24 filas | `no such table: knowledge_benchmark_results` |
| `v_dq_uplift` | 49 filas | `no such table: knowledge_benchmark_results` |
| `error_keywords_freq` | 49 filas | `no such table: error_log` |
| `benchmark_results` | 5 filas | `no such table: objectives` |
| `loop_effectiveness` | 3 filas | `no such table: objectives` |
| `tier_comparison` / `tier_ranking` / `autonomy_score` / `visual_convergence` | 5/1/1/2 | `no such table: code_metrics` |

(Las otras 9 ya están rotas hoy — apuntan a `agent_actions`, `video_metrics`,
`jal_scoring_snapshots`, `jal_error_patterns`, que nunca existieron en esta DB.)

**Escenario de fallo.** El más relevante no es la rotura en sí, sino lo que revela:
`knowledge_benchmark_results` (**421 filas**) está en la lista de `DROP` clasificada
como «tabla vacía en `dqiii8.db` sin código vivo» (§2.1), pero es la tabla base de las
**tres únicas vistas con nombre de conocimiento** que el spec conserva en
`dqiii8_knowledge.db`. Es la evidencia cuantitativa del uplift del clúster de
conocimiento — precisamente el activo que toda la consolidación existe para rescatar —
y se va a `.sql.gz` offline mientras sus vistas se quedan. Es una inconsistencia de
clasificación, no un descuido cosmético.

**Corrección.** Decidir explícitamente: o `knowledge_benchmark_results` pasa a la lista
de conservar (mi recomendación: sus 3 vistas ya están en el fichero destino), o se
`DROP`ean también las 10 vistas dependientes. Y el guardián del paso 0b debe cubrir
`type IN ('table','view')`, no solo `table`.

---

### 7 — [P2] `VACUUM INTO` y `.backup` **no** son equivalentes: el `journal_mode` cambia

**Descripción.** §5.3 paso 6 los ofrece como intercambiables
(«`VACUUM INTO 'dqiii8_knowledge.db'` (o `sqlite3 origen ".backup destino"`)»).
No lo son.

**Evidencia.**
```
$ sqlite3 database/dqiii8_metrics.db "PRAGMA journal_mode;"          → wal
$ sqlite3 database/dqiii8_metrics.db "VACUUM INTO '/tmp/knowledge.db'"
$ sqlite3 /tmp/knowledge.db "PRAGMA journal_mode;"                    → delete
$ sqlite3 database/dqiii8_metrics.db ".backup '/tmp/bk.db'"
$ sqlite3 /tmp/bk.db "PRAGMA journal_mode;"                           → wal
```

**Escenario de fallo.** Con `VACUUM INTO`, `dqiii8_knowledge.db` nace en modo
rollback-journal. El único escritor vivo del clúster es
`knowledge_enricher._log_chunk_usage` (línea 512, ~10.900 escrituras solo en agosto
sobre `knowledge_usage`, 61.538 filas totales): en modo `delete`, cada escritura toma
un lock exclusivo que bloquea a todos los lectores concurrentes, donde antes no lo
hacía. Es un cambio de comportamiento de concurrencia introducido de forma
accidental, en la ruta de código más caliente de la DB. O se usa `.backup`, o se añade
`PRAGMA journal_mode=WAL` explícito tras el `VACUUM INTO` (y se verifica).

---

### 8 — [P2] La verificación del paso 6 no puede ejecutarse sobre `vec_knowledge` con `sqlite3` a secas

**Descripción.** §5.3 paso 6 exige verificar «que las 31 tablas esperadas están
presentes **con sus conteos**». Una de las 31 es una tabla virtual `vec0` que requiere
la extensión `sqlite-vec` cargada.

**Evidencia.**
```
$ sqlite3 /tmp/knowledge.db "SELECT count(*) FROM vec_knowledge;"
Error: in prepare, no such module: vec0
$ sqlite3 database/dqiii8_metrics.db "SELECT sql FROM sqlite_master WHERE name='vec_knowledge';"
CREATE VIRTUAL TABLE vec_knowledge USING vec0(chunk_id INTEGER PRIMARY KEY, embedding FLOAT[1024] distance_metric=cosine)
```

**Escenario de fallo.** El bucle de verificación del paso 6 lanza excepción en la
tabla 31 de 31, justo antes del `DROP`, y el aborto parece un fallo de la copia cuando
en realidad la copia es correcta. El sustituto correcto es contar la tabla sombra real
`vec_knowledge_rowids` (1.444 según `sqlite_sequence`), o cargar la extensión — pero
cargar `sqlite-vec` in-process sobre una DB de producción ya está registrado como P0
del stress test del 2026-08-12, así que la vía es la tabla sombra.

---

### 9 — [P3] Ventana de escritura no cerrada entre el congelado del conteo (paso 5) y el borrado de `dqiii8_history.db`

**Descripción.** §5.3 paso 3 para `dqiii8-bot`, `dq-dashboard` y `cron`, y comprueba
que no queda ningún proceso Python del repo. Es una comprobación puntual, no un lock.
El escritor de `session_memory` es `openrouter_wrapper.py:1469` (`_wm.save_exchange`),
que se dispara en **cualquier** invocación del pipeline — incluida una manual (`dq cc`)
o una hecha por la propia sesión de Claude Code desde la que se ejecuta la migración,
vía `bin/core/dispatch.py`.

**Escenario de fallo.** Entre el paso 5 (conteo congelado + copia) y el momento en que
`dqiii8_history.db` se retira del disco median los pasos 6–11 (dumps, `VACUUM INTO`,
29 `DROP`, cambio de código, `VACUUM`, reinicio de servicios) — minutos, y con
intervención humana en medio. Cualquier exchange escrito en esa ventana entra en
`dqiii8_history.db` y se pierde al borrarlo.

**Corrección.** Barata y suficiente: `chmod 400 dqiii8_history.db` inmediatamente
antes de congelar el conteo, y re-verificar el `count(*)` (delta = 0) justo antes de
mover el fichero a `.old`. Mitiga, además, que el borrado real se difiere («queda como
`.old` unos días»), así que el daño práctico es bajo — de ahí P3, no P2.

---

### 10 — [P3] No hay paso explícito de renombrado, y el `.old` entra en conflicto con la «alternativa más simple» del paso 7

**Descripción.** El §5.3 crea `dqiii8_knowledge.db` (paso 6), `DROP`ea sobre el
original (paso 7) y al final dice que los originales «quedan como `.old`» (paso 11),
pero ningún paso ejecuta el `mv`. Además, la «alternativa más simple, igualmente
válida» del paso 7 (no `DROP`ear nada y dejar `dqiii8_metrics.db` intacto como `.old`)
deja dos ficheros de 33 MB con las mismas 61 tablas, uno de ellos aún con el nombre
que `update_dqiii8.sh` y `install.sh` conocen — recomiendo adoptar esa alternativa
(el `DROP` sobre el original no aporta nada, como el propio spec admite) **y** hacer
el `mv` explícito, porque si el fichero conserva su nombre, la corrección de
`update_dqiii8.sh` es la única barrera entre él y su recreación.

**Evidencia adicional.** Existe hoy un `dqiii8_history.db.pre-fix-20260813T125634Z` de
**31 MB** junto a los tres DBs activos. El spec dice que «`dqiii8_history.db` desaparece
del disco» sin aclarar si ese hermano entra en el alcance; `db_backup.sh:30` y
`health_watchdog.py:241` trabajan sobre nombres exactos y lo ignoran en cualquier caso.

---

### 11 — [P3] Dos afirmaciones factuales de §5.2 sobre `schema_v2.sql` son inexactas

**Descripción.** §5.2 afirma: «Verificado: **las 29 tablas de `DROP`, incluidas
`chunk_health` y `domain_enrichment`, están todas declaradas en
`database/schema_v2.sql`**, y ninguna tabla del clúster de conocimiento lo está».
Dos errores.

**Evidencia.**
```
# tablas de la lista DROP que NO están en schema_v2.sql:
session_memory          # → son 28 de 29, no 29
# tablas de la lista KEEP (conocimiento) que SÍ están en schema_v2.sql:
chunk_health            # → «ninguna» es falso
```
La frase además arrastra `chunk_health` como si siguiera en la lista de `DROP`, cuando
la corrección C5 la sacó (§2.1). Es un residuo de edición no propagado.

**Escenario de fallo.** Menor pero real: la conclusión operativa de §5.2 («el primer
`update_dqiii8.sh` posterior recrea las 29 tablas vacías + `session_memory`») sigue
siendo correcta —`update_dqiii8.sh:75-76` crea `session_memory` con un `CREATE TABLE`
propio, aparte del schema— pero por un mecanismo distinto al que el spec describe.
Quien implemente confiando en la frase puede corregir solo la línea 74 y dejar viva la
75-76.

---

## Verificado sin problemas

Lo siguiente lo comprobé de forma independiente y **es correcto tal como lo describe
el spec**:

- **Overlap 0 en las 10 tablas de §2.2.** Recalculado con `ATTACH` + `INTERSECT` sobre
  el conjunto completo de columnas comunes excluyendo `id`, las 10 tablas, sin
  muestreo. Overlap = 0 en las 10, y los conteos `main|metrics` coinciden exactamente
  con la tabla de §2 (`error_log` 1066/856, `amplification_log` 6356/1849,
  `sessions` 40/230, `learning_metrics` 170/619, `permission_decisions` 194/35,
  `audit_reports` 15/42, `research_items` 13/17, `agent_registry` 39/123,
  `instincts` 26/51, `vault_memory` 88/850). La conclusión de §2 —que un `DROP` sin
  exportar destruiría datos irrecuperables— está bien fundada.
- **Exclusividad mutua de las listas 29/31.** `comm -12` sobre las dos listas
  ordenadas → vacío. Ninguna tabla está en ambas, y ninguna tabla de las listas falta
  en la DB. El único fallo de exhaustividad es `sqlite_sequence` (hallazgo 3).
- **Las 11 rutas de código de §5.2, verificadas una a una** — todos los números de
  línea del spec son correctos, incluidas las 4 rutas independientes de
  `knowledge_enricher.py` (139, 429, 625, 817 → `dqiii8.db`; 512 → `dqiii8_metrics.db`,
  la única correcta) y `benchmark_dq.py:30` (única que apunta bien hoy y se rompería
  *con* el renombrado). `paths.METRICS_DB_PATH` confirmado con **cero** consumidores
  (`bin/core/paths.py:11` es la única aparición en todo el repo).
- **`db_backup.sh:30` y `health_watchdog.py:241`** contienen efectivamente las listas
  fijas de 3 nombres que el spec identifica. Correctamente marcados como bloqueantes.
- **Invertir el orden copia-antes-que-`DROP`** (pasos 6→7) cierra la ventana que el
  spec dice cerrar. Lo simulé de principio a fin sobre una copia: `VACUUM INTO`
  produce una DB con `integrity_check = ok`, y tras los 29 `DROP` el fichero sigue
  íntegro (`integrity_check = ok`, `vector_chunks` 927 filas, `knowledge_usage` 61.538).
- **Integridad de los índices FTS5 tras el `DROP`.** Verifiqué explícitamente que las
  tablas base de contenido externo sobreviven y que los índices siguen consistentes:
  `INSERT INTO chunks_fts(chunks_fts) VALUES('integrity-check')` y el equivalente de
  `facts_fts` pasan ambos sin error sobre la DB post-`DROP`. La advertencia de §5.1
  sobre `content='vector_chunks'` / `content='facts'` está bien puesta y bien resuelta.
- **`VACUUM INTO` sobre una DB con una tabla virtual `vec0` sin la extensión cargada
  funciona** — copia correctamente las tablas sombra sin necesitar el módulo. Solo la
  *verificación* por `count(*)` requiere la extensión (hallazgo 8).
- **Idempotencia del `INSERT OR IGNORE` (paso 5), una vez creada la tabla.** Los
  rangos de `id` no colisionan (`history` 673–744, `metrics` 1473–2448) y las 52 filas
  de `history` cumplen el `CHECK(role IN ('user','assistant'))` y los `NOT NULL`
  (0 violaciones), así que `OR IGNORE` no descartará nada silenciosamente en una
  primera ejecución y será un no-op en la segunda. La corrección del spec respecto al
  `INSERT` simple es acertada.
- **No hay colisiones de comodín `LIKE` en `.dump <tabla>`.** Comprobé las 29: cada
  nombre matchea exactamente 1 tabla pese a que `_` es comodín en el `LIKE` que
  `.dump` usa internamente. El riesgo existe conceptualmente pero no se materializa
  con estos nombres.
- **Espacio en disco.** 31 GB libres en `/`; la copia pesa 26 MB y los dumps
  comprimidos son de orden de MB. El criterio (e) del dry-run pasará holgadamente.
- **Ausencia de triggers en `dqiii8_metrics.db`** (`sqlite_master` → 0 triggers), así
  que ningún `DROP` arrastra lógica oculta. `dqiii8.db` sí tiene 8, pero no se toca su
  esquema.
- **`dqiii8_history.db` está en `journal_mode = delete`**, no WAL, así que la
  advertencia de §5.3 paso 6 sobre no copiar con `cp` aplica a `dqiii8_metrics.db`
  (confirmado en WAL) y a `dqiii8.db`, no a history. El spec no se equivoca aquí, solo
  no lo distingue.
