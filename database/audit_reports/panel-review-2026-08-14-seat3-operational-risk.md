# Panel Review — Asiento 3: Riesgo operativo, blast radius y gobernanza del cambio

**Documento revisado:** `docs/superpowers/specs/2026-08-14-db-consolidation-design.md`
**Fecha:** 2026-08-14 | **Lente:** riesgo operativo / blast radius / gobernanza (no correctitud de código ni integridad de filas)
**Método:** verificación en vivo (`systemctl`, `crontab -l`, `ps aux`, `sqlite3` sobre las DBs de producción, `git`). Ningún hallazgo de este informe es inferido de la lectura del spec sin comando de respaldo.

## Resumen

El spec es, en calidad analítica, muy superior a la media: dry-run obligatorio, orden copia-antes-de-borrado, `INSERT OR IGNORE` para idempotencia, sección de rollback y exclusiones de alcance explícitas. Pero su modelo de "cero escritores concurrentes" (§5.3 paso 3) es **falso sobre el estado real de la máquina**: hay un timer systemd (`hpt-poller.timer`) escribiendo en `dqiii8.db` cada 2 minutos que `systemctl stop cron` no detiene, y los hooks de Claude Code del propio agente que ejecuta la migración escriben en `agent_actions` en cada llamada a herramienta. Además el paso 5 (`INSERT ... INTO session_memory` sobre `dqiii8.db`) **no puede ejecutarse**: esa tabla no existe en `dqiii8.db` ni en `schema_v2.sql`, de modo que el paso que el spec declara "sin cambio de esquema" es en realidad un cambio de esquema del SSOT operativo — exactamente la clase de operación que `CLAUDE.md` obliga a flaggear y no ejecutar. Y el guard-rail de aborto de §5.1 está mal calibrado (`sqlite_sequence`), por lo que el script se detendría solo en el peor momento. Faltan además dos consumidores vivos de `dqiii8_history.db` en la lista de §5.2, y no hay ninguna puerta de aprobación explícita del usuario antes del `DROP` de 29 tablas.

---

## Hallazgos

### 1. [P0] `hpt-poller.timer` escribe en `dqiii8.db` cada 2 minutos y `systemctl stop cron` no lo para

El §5.3 paso 3 dice: *"`systemctl stop dqiii8-bot dq-dashboard` Y `systemctl stop cron`"* (spec:452-461). El spec enumera cron y los 2 servicios como el conjunto completo de escritores, y ni una sola vez menciona timers systemd. La máquina tiene dos unidades DQIII8 basadas en timer que sobreviven a `stop cron`:

**Evidencia:**
```
$ systemctl list-timers --all --no-pager
Fri 2026-08-14 12:31:35 UTC   1min 3s  hpt-poller.timer      hpt-poller.service
Sat 2026-08-15 07:30:00 UTC       18h  dqiii8-health.timer   dqiii8-health.service

$ systemctl cat hpt-poller.timer
[Timer]
OnBootSec=2min
OnUnitActiveSec=2min
Persistent=true

$ systemctl cat hpt-poller.service
ExecStart=/usr/bin/python3 /root/dqiii8/services/hpt_poller.py

$ grep -nE "get_db|UPDATE" services/hpt_poller.py
39:from bin.core.db import get_db
90:  "UPDATE human_pending_tasks SET status='notified', ..."
135: "UPDATE human_pending_tasks SET notify_count=notify_count+1, ..."
161: "UPDATE human_pending_tasks SET status='notified', ..."
179: "UPDATE human_pending_tasks SET last_error=:err, ..."
```

`hpt_poller.py` abre `dqiii8.db` vía `bin.core.db.get_db` y ejecuta UPDATEs. Se dispara cada 2 minutos, con `Persistent=true`.

**Escenario de fallo concreto:** el operador ejecuta el paso 3, ve bot/dashboard/cron parados, y el paso 0(f) ("confirmación de que no queda ningún proceso Python del repo vivo") pasa limpio porque `hpt_poller` es `Type=oneshot` y dura milisegundos — entre disparo y disparo no hay proceso que ver. Noventa segundos después, en mitad del paso 5 (`ATTACH` + `INSERT` sobre `dqiii8.db`) o del paso 9 (`VACUUM` sobre `dqiii8.db`), systemd lanza el poller: `VACUUM` aborta con `SQLITE_BUSY` (VACUUM exige lock exclusivo), o el poller falla y marca `last_error` sobre una tarea humana pendiente. El chequeo del paso 0(f) es estructuralmente incapaz de detectarlo: es una foto de un escritor que no existe entre disparos.

**Fix requerido:** el paso 3 debe ser `systemctl stop hpt-poller.timer dqiii8-health.timer` además de cron y los 2 servicios, y el paso 11 debe rearrancar las 5 unidades, no 3. Alternativamente `systemctl stop timers.target`, pero eso también para `logrotate`/`fstrim`.

---

### 2. [P0] El paso 5 no puede ejecutarse: `session_memory` no existe en `dqiii8.db` — y crearla es un cambio de esquema del SSOT que el spec niega ser

§5.1 (spec:295-296): *"`dqiii8.db` — SSOT operativo. Gana la tabla `session_memory` (traspaso completo desde `dqiii8_history.db`, **sin cambio de esquema**)."*
§5.3 paso 5 (spec:471-473): `INSERT OR IGNORE INTO session_memory SELECT * FROM history.session_memory`.

**Evidencia:**
```
$ sqlite3 database/dqiii8.db "SELECT name FROM sqlite_master WHERE type='table' AND name='session_memory';"
(vacío — la tabla NO existe)

$ grep -c "session_memory" database/schema_v2.sql
0
```

La tabla no está en `dqiii8.db` ni declarada en el SSOT de esquema. El `INSERT` del paso 5 lanzará `OperationalError: no such table: session_memory` sobre la DB de producción con cron y servicios ya parados.

**Doble problema de gobernanza:** la corrección obvia (añadir un `CREATE TABLE session_memory` en `dqiii8.db`) es un cambio de esquema del SSOT operativo. `.claude/rules/01_database_mutations.md:12,14` obliga a que todo cambio de esquema pase por `schema_v2.sql` y prohíbe alterar el esquema vivo de `dqiii8.db` vía `sqlite3` crudo. `00_core_behavior.md` ("Destructive / irreversible actions (… schema change) → STOP, notify user, wait"). El spec dedica dos secciones enteras (§5.2 último punto, §7) a excluir cuidadosamente la *eliminación* de definiciones de `schema_v2.sql` por ser destructiva — y a la vez introduce una *adición* al esquema del SSOT operativo describiéndola literalmente como "sin cambio de esquema". La disciplina de gobernanza se aplica en una dirección y no en la otra.

**Escenario de fallo concreto:** el script muere en el paso 5 con servicios y cron parados y el paso 4 (dump de 29 tablas) ya escrito. El operador está en el estado que §5.5 no cubre: "antes del paso 8", sí, restaurable — pero con cron parado y sin trap que lo rearranque (ver hallazgo 4).

---

### 3. [P1] Los hooks de Claude Code hacen imposible el "cero escritores": el agente que ejecuta la migración es él mismo un escritor de `dqiii8.db`

El spec reconoce el riesgo de hooks a medias (spec:459-461: *"más los hooks de Claude Code (`user_prompt_submit.py`, que escribe en `spc_metrics` en cuanto el usuario teclea algo)"*) pero lo trata como algo que se resuelve con "verificación explícita de que no queda ningún proceso `python3` del repo en ejecución". Eso no aborda el mecanismo real.

**Evidencia:**
```
$ python3 -c "import json;print(json.load(open('.claude/settings.json'))['hooks'].keys())"
PreToolUse, PostToolUse, Stop, SubagentStop, UserPromptSubmit, PostToolUseFailure, SessionStart, PreCompact, PostCompact, SubagentStart, PermissionRequest

$ grep -n "INSERT INTO" .claude/hooks/pre_tool_use.py
150:  "INSERT INTO agent_actions "
$ grep -n "dqiii8.db" .claude/hooks/pre_tool_use.py
135:  _DB = os.path.join(DQIII8_ROOT, "database", "dqiii8.db")

$ grep -n "INSERT INTO" .claude/hooks/post_tool_use.py
221:  "INSERT INTO error_log ..."
295:  "INSERT INTO vault_memory ..."
```

`PreToolUse` inserta en `agent_actions` de `dqiii8.db` en **cada** llamada a herramienta. `PostToolUse` inserta en `error_log` y `vault_memory`. Si el operador ejecuta `db_consolidate.py` desde una sesión de Claude Code (que es el modo de trabajo normal de este repo — hay una sesión viva ahora mismo: `PID 821705 claude --model sonnet`), cada `Bash` que lance durante o después de la migración dispara un INSERT en `dqiii8.db`.

**Escenario de fallo concreto:** el paso 9 (`VACUUM` en `dqiii8.db`) falla con `database is locked` porque el hook `PreToolUse` del propio comando que lanzó el VACUUM aún tiene la conexión abierta. Peor: `error_log` y `vault_memory` son 2 de las 10 tablas de §2.2 cuyo overlap-cero contra metrics el paso 0(c) verifica y **aborta si deja de ser 0** — el propio agente sigue escribiendo en la copia de `dqiii8.db` entre el dry-run y el DROP.

**Fix requerido:** o bien ejecutar el script desde una sesión ajena a Claude Code (tmux/ssh directo, hooks fuera de juego), y decirlo explícitamente en el spec como precondición; o bien exigir `DQIII8_HOOKS_DISABLED=1` (si existe tal palanca) durante la ventana. La verificación de "ningún proceso python3 vivo" no cubre este caso porque el escritor nace y muere dentro de cada llamada a herramienta.

---

### 4. [P1] No hay `trap`/`finally`: si el script muere entre el paso 3 y el 11, cron queda parado indefinidamente — y el watchdog que lo detectaría también

El paso 3 para cron; el paso 11 lo rearranca. Entre medias hay 8 pasos, incluidos un dump de 29 tablas, un `VACUUM INTO` sobre 33 MB y 29 `DROP TABLE`. El spec no especifica ningún manejador que garantice el rearranque de servicios ante excepción o `SIGINT`.

**Evidencia — qué se pierde con cron parado (13 jobs, no 10 como dice spec:455-458):**
```
$ crontab -l | grep -cE '^[0-9*]'
13
```
Entre ellos: `db_backup.sh` (02:50 — la red de seguridad de la que depende todo el §5.5), `nightly.sh` (03:05), `triage_error_log.py --apply` (03:50), `purge_transient_errors.py` (04:00), `memory_decay.py` (04:10), `sandbox_tester.py` (cada 6 h), `auto_researcher.py` (lunes 06:05), `daily_capture.py` de football-value (06:30), `monitor_januskeys_com.sh` (día 1 del mes) y — crítico — `health_watchdog.py --quiet` (06:00), **el único vigilante que detectaría que los crons no han corrido, y que corre desde el propio cron parado**.

**Escenario de fallo concreto:** la migración se ejecuta un viernes por la tarde, el paso 7 falla, el operador se ocupa del rollback de datos (que §5.5 sí describe) y se olvida de `systemctl start cron`. El sábado y el domingo no hay backup diario, no hay nightly, no hay decay, no hay purge, no hay captura de football-value — y el watchdog está mudo porque también es un cron. `dqiii8-health.timer` (07:30, systemd) sigue corriendo y escribiendo su JSON, dando una falsa señal de vida. La detección real llega el lunes, con 3 días de backups perdidos justo después del cambio más arriesgado del trimestre.

**Fix requerido:** el rearranque de las 5 unidades (ver hallazgo 1) debe estar en un `try/finally` a nivel del script, no como paso 11 de una lista secuencial; y el spec debe corregir "10 jobs de cron" a 13.

---

### 5. [P1] `DROP TABLE` de 29 tablas sobre producción sin ninguna puerta de aprobación explícita del usuario en el plan

`CLAUDE.md` §Inviolable Rules: *"Destructive / irreversible actions (rm -rf, **DROP**, force-push) → STOP, notify, wait."* `.claude/rules/00_core_behavior.md:` idéntico.

El spec aplica esta disciplina con rigor a **un** punto: la eliminación de definiciones en `schema_v2.sql` (spec:423-430 y §7, spec:600-604), que excluye del alcance y remite a "aviso explícito y decisión del usuario". Pero el `DROP TABLE` de las 29 tablas (§5.3 paso 7, spec:488-496) **no tiene ningún gate equivalente**: está descrito como un paso más de un script automatizado, sin punto de parada, sin confirmación interactiva, sin "STOP, notify, wait". El dry-run del paso 0 es una precondición técnica de aborto, no una aprobación humana — pasa o falla por sí solo y continúa al paso 1 sin intervención.

Esto es tanto más llamativo cuanto que **el propio spec admite que el `DROP` es innecesario** (spec:497-499): *"Alternativa más simple, igualmente válida: no ejecutar este `DROP` en absoluto y dejar `dqiii8_metrics.db` intacto como `.old` — el `DROP` sobre el original no aporta nada, el fichero se retira igual."*

**Escenario de fallo concreto:** se ejecuta un `DROP` de 29 tablas sobre una DB de producción de 33 MB, cruzando explícitamente una regla inviolable del repo, para obtener cero beneficio declarado. Cualquier fallo en el paso 4 (dump) que el chequeo `grep -c '^INSERT INTO'` no atrape — p. ej. un dump correcto en filas pero con un `CREATE TABLE` truncado — se vuelve irrecuperable desde ese fichero en el instante del `DROP`.

**Recomendación:** eliminar el paso 7 del plan y quedarse con la alternativa que el propio spec identifica como equivalente. Si se conserva, debe llevar un gate explícito de parada y confirmación del usuario, no un dry-run automático.

---

### 6. [P1] Dos consumidores vivos de `dqiii8_history.db` faltan en la lista de §5.2, y el spec afirma haber barrido exhaustivamente

§5.1 (spec:324-326) elimina `dqiii8_history.db` del disco. §5.2 lista 11 ficheros de código + `working_memory.py` + 4 de infraestructura, y afirma (spec:417-421): *"Confirmado sin dependencias reales fuera de `bin/`: barrido de … ningún proyecto externo abre estas DBs"*. El barrido es correcto **fuera** de `bin/` pero incompleto **dentro**:

**Evidencia:**
```
$ grep -rn "dqiii8_history" --include=*.py --include=*.sh . | grep -v node_modules
bin/core/openrouter_wrapper.py:1111:  for rel in (".env", "database/dqiii8.db", "database/dqiii8_history.db",
bin/tools/health_check.py:131:        hist = ROOT / "database" / "dqiii8_history.db"
bin/monitoring/health_watchdog.py:241: BACKUP_DBS = [...]        # ← sí está en §5.2
bin/tools/db_backup.sh:30                                        # ← sí está en §5.2
bin/agents/working_memory.py:22                                  # ← sí está en §5.2
```

Los dos primeros **no aparecen en ninguna de las listas del spec**:

- **`bin/core/openrouter_wrapper.py:1102-1113`** — `_enforce_sensitive_permissions()`, que `CLAUDE.md` designa como el *entry point* del sistema. Itera sobre una lista literal `(".env", "dqiii8.db", "dqiii8_history.db", "dqiii8_metrics.db")` forzando `0600`. Tras la migración, `dqiii8_knowledge.db` **queda fuera del bucle de enforcement permanente**. El paso 10 del §5.3 hace un `chmod 600` de una sola vez, correcto pero no duradero: cualquier operación futura que reponga permisos (un `.backup`, una restauración) deja la nueva DB sin el guardián que sí protege a las otras.
- **`bin/tools/health_check.py:126-134`** — puntúa `+10` sobre el score de salud si `dqiii8_history.db` existe con permisos `600`. Tras borrar el fichero, `hist.exists()` es `False` → `secure=False` → **el score de salud del sistema baja 10 puntos de forma permanente y silenciosa**, y este script corre por partida doble: cron `50 5 * * *` **y** `dqiii8-health.timer` (07:30). Es exactamente el patrón de "alerta en falso para siempre" que el spec identifica correctamente para `health_watchdog.py BACKUP_DBS` (spec:405-407) — pero se le escapó el gemelo.

**Escenario de fallo concreto:** post-migración el score de salud diario cae de 100 a 90 sin causa visible; alguien investiga, no encuentra nada roto, y el sistema aprende a ignorar una degradación de 10 puntos en su propia métrica de salud.

---

### 7. [P2] El guard-rail de aborto de §5.1 está mal calibrado: `sqlite_sequence` haría abortar el script a sí mismo

§5.1, "Regla de implementación no negociable" (spec:314-318): *"El script … la debe generar por complemento (`SELECT name FROM sqlite_master WHERE type='table'` menos la lista fija de `DROP`) y **abortar** si el conjunto resultante no coincide exactamente con estas 31."*

**Evidencia:**
```
$ sqlite3 database/dqiii8_metrics.db "SELECT count(*) FROM sqlite_master WHERE type='table';"
61

$ comm -23 <(sqlite3 ...metrics.db "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name") <(sort keep31 drop29)
sqlite_sequence
```
Verificado por diff completo: las 31 supervivientes y las 29 del `DROP` del spec son **exactamente correctas y complementarias** (0 tablas del spec ausentes en la DB, 0 tablas de la DB sin clasificar) — salvo `sqlite_sequence`, la tabla interna de SQLite. El complemento real es 61 − 29 = **32**, no 31.

**Escenario de fallo concreto:** el paso 0(b) aborta con "esperaba 31, encontré 32". El operador, con el dry-run ya lanzado y el trabajo mental hecho, diagnostica en treinta segundos que es solo `sqlite_sequence` y **relaja el guard-rail bajo presión** — que es precisamente el momento y el estado mental en que un guard-rail deja de proteger. Efecto secundario relacionado: `DROP TABLE` sobre tablas con `AUTOINCREMENT` muta `sqlite_sequence`, un efecto que el spec no menciona en ningún sitio.

**Fix:** excluir explícitamente `name NOT LIKE 'sqlite_%'` en la consulta de complemento y documentar el número esperado como 31 tras esa exclusión.

---

### 8. [P2] `chunk_health` y `domain_enrichment` viven en `schema_v2.sql`: el primer `update_dqiii8.sh` posterior recrea el split-brain que el spec arregla

El spec identifica correctamente (spec:394-401) que `update_dqiii8.sh`/`install.sh` recrean `dqiii8_metrics.db` desde `schema_v2.sql` y lo marca CRÍTICO. Pero el análisis se detiene en `dqiii8_metrics.db` y no cubre el efecto sobre `dqiii8.db`:

**Evidencia:**
```
$ grep -n "chunk_health\|domain_enrichment" database/schema_v2.sql
778:  CREATE TABLE IF NOT EXISTS domain_enrichment (
1250: CREATE TABLE IF NOT EXISTS chunk_health (

$ sed -n '73p' update_dqiii8.sh
sqlite3 "$DQIII8_ROOT/database/dqiii8.db" < "$DQIII8_ROOT/database/schema_v2.sql" 2>/dev/null || true
```
`chunk_health` es la tabla que §2.1 (spec:114-132) se esfuerza en rescatar del `DROP` para que viva en `dqiii8_knowledge.db`. Su definición sigue en `schema_v2.sql`, que `update_dqiii8.sh` aplica a `dqiii8.db` en cada actualización.

**Escenario de fallo concreto:** semanas después de la consolidación, alguien corre `update_dqiii8.sh`. Se recrea un `chunk_health` vacío en `dqiii8.db`. `knowledge_enricher._load_health_verdicts` (repuntado a knowledge.db por §5.2) sigue bien — pero cualquier código nuevo o cualquier re-derivación de rutas desde `paths.py` vuelve a encontrar una tabla vacía con el nombre correcto en el sitio equivocado. Es la reaparición exacta del bug de 4,5 meses que este spec existe para cerrar.

**Nota relacionada:** `update_dqiii8.sh:70-72` ejecuta tres `sed -i` **sobre `database/schema_v2.sql`**, es decir, reescribe automáticamente el SSOT de esquema en cada actualización. Esto contradice frontalmente `01_database_mutations.md:11-12` ("`schema_v2.sql` es el single source of truth; schema changes: edit `schema_v2.sql` ONLY"). Es deuda preexistente, no introducida por este spec, pero es el motivo por el que la exclusión de §7 ("no tocar `schema_v2.sql` sin aviso") ofrece menos protección de la que aparenta: un script de infraestructura ya lo toca sin aviso.

---

### 9. [P2] Blast radius y ventana de caída: cuantificados aquí porque el spec no los cuantifica en ningún punto

El spec describe qué se para (paso 3) y cómo se vuelve atrás (§5.5), pero **nunca estima cuánto dura la ventana ni quién la nota**. Datos reales:

```
$ ls -la database/*.db
dqiii8.db          12 083 200 B   (60 tablas)
dqiii8_metrics.db  33 603 584 B   (61 tablas)
dqiii8_history.db     110 592 B
$ df -h /root  →  31 G disponibles   (holgura suficiente, paso 0(e) OK)
$ systemctl status dqiii8-bot   → active (running) since 2026-08-12, 2 days
$ systemctl status dq-dashboard → active (running) since 2026-08-11, 2 days
```

- **Ventana técnica:** dump de 29 tablas + `VACUUM INTO` de 33 MB + `VACUUM` de 12 MB ≈ minutos, no horas. Espacio de sobra. Esta parte no es el riesgo.
- **Ventana real:** el bot de Telegram (`@YourBotName`, única UI móvil del sistema según `CLAUDE.md`) y el dashboard quedan caídos durante toda la ejecución **más** todo el tiempo de diagnóstico si algo falla. Como la migración se ejecuta de forma interactiva y supervisada, la ventana la fija el humano, no el script: un fallo en el paso 5 (hallazgo 2, que **ocurrirá**) convierte una ventana de minutos en una de horas mientras se decide si crear la tabla es o no un cambio de esquema que requiere aprobación.
- **Rollback §5.5:** los backups existen y son recientes y verificados (`database/backups/`, rotación de 7, último `20260814T025001Z` de hoy). El `db_backup.sh` usa `.backup` + `integrity_check` + size-gate, es sólido. Y el `pre-consolidation-<ts>/` del paso 1 es un subdirectorio, a salvo de la rotación (`find -maxdepth 1` + glob de timestamp estricto, `db_backup.sh:74-77`). **§5.5 está bien resuelto en la parte de datos.** Su hueco es operativo, no de datos: no menciona rearrancar los timers systemd (hallazgo 1) ni garantiza el rearranque de cron ante excepción (hallazgo 4).
- **Riesgo de entrelazado en el rollback de código:** el árbol de trabajo **no está limpio** ahora mismo:
```
$ git status --short
 M README.md
 M bin/core/dispatch.py
 M bin/core/openrouter_wrapper.py     ← fichero implicado (hallazgo 6)
 M requirements.txt
$ git log --oneline origin/main..HEAD | wc -l  →  21 commits sin pushear
```
§5.5 dice "revertir el commit de código … primero". Con 4 ficheros modificados sin commitear, uno de ellos (`openrouter_wrapper.py`) tocando precisamente las rutas de DB, un `git revert` bajo presión arrastra o pisa trabajo no relacionado. **El árbol debe estar limpio antes del paso 8.**

---

### 10. [P2] El spec que gobierna un cambio destructivo de 15 ficheros está gitignorado

```
$ git check-ignore -v docs/superpowers/specs/2026-08-14-db-consolidation-design.md
.gitignore:272:docs/superpowers/    docs/superpowers/specs/2026-08-14-db-consolidation-design.md
```

El propio `SKILL.md` de `panel-review` es explícito sobre esta distinción: *"Report: written to `database/audit_reports/…` (tracked path, mirrors the `audit` skill). **Never `docs/superpowers/`**"*. La convención existe y el spec la incumple en la otra dirección: el documento de diseño vive en la ruta no versionada.

**Escenario de fallo concreto:** el rollback de §5.5 revierte el commit de código. El razonamiento que justifica cada una de las 29 tablas del `DROP`, la clasificación de `chunk_health` y las 4 rutas de `knowledge_enricher.py` no está en ningún commit — vive en un fichero suelto que un `git clean -xdf` (o una restauración desde otra máquina, o el `nightly.sh` que ya barre ficheros no ignorados en la raíz) borra sin dejar rastro. Un cambio destructivo de esta magnitud debe dejar su justificación en el historial junto al código que la implementa.

---

### 11. [P3] `spc_metrics` está simultáneamente en la lista de `DROP` y es escrita por un hook en caliente

`spc_metrics` figura entre las 17 tablas "vacías en `dqiii8.db`" (spec:95) y por tanto entra en el `DROP` de §5.1.1. El propio spec la cita como escrita por hooks: *"los hooks de Claude Code (`user_prompt_submit.py`, que escribe en `spc_metrics` en cuanto el usuario teclea algo)"* (spec:459-461).

```
$ grep -n "spc_metrics" .claude/hooks/user_prompt_submit.py
255:  "SELECT reason FROM spc_metrics WHERE triggered=1 ORDER BY id DESC LIMIT 1"
```

No es contradictorio en el fondo (el `DROP` es sobre la copia de `metrics.db`; el hook usa la de `dqiii8.db`, que es la correcta), y §2.1 ya explica ese matiz de forma general. Pero es exactamente el tipo de tabla donde una confusión de fichero durante la ejecución tiene consecuencias en la ruta caliente de cada interacción del usuario. Merece una mención nominal en el paso 7 del script, no quedar diluida en una lista de 29.

---

### 12. [P3] "10 jobs de cron" es una cifra desactualizada dentro de un spec que presume de no usar cifras sin verificar

§5.3 paso 3 (spec:455): *"quedaban vivos **10 jobs de cron**"*. El real es 13 (`crontab -l | grep -cE '^[0-9*]'` → 13). El spec omite de su enumeración: `auto_researcher.py` (lunes 06:05), `health_check.py` (05:50), `daily_capture.py` de football-value (06:30), `monitor_januskeys_com.sh` (mensual) y `health_watchdog.py` (06:00). Menor en sí mismo, pero el §0 del documento se apoya en la premisa de que toda cifra fue verificada en vivo — y esta es precisamente la lista que define el perímetro de escritores concurrentes, el punto donde el spec falla más gravemente (hallazgos 1 y 4).

---

## Verificado sin problemas

Estas partes del spec fueron comprobadas contra el estado real y **están bien resueltas**; no requieren cambios:

1. **Las listas de 29 `DROP` y 31 supervivientes son exactas.** Diff completo por `comm` contra `sqlite_master` de `dqiii8_metrics.db`: cero tablas del spec ausentes de la DB, cero tablas de la DB sin clasificar. La única discrepancia es `sqlite_sequence` (hallazgo 7), que no invalida ninguna de las dos listas — solo el guard-rail de conteo.
2. **La regla "generar por complemento, nunca a mano, nunca wildcard"** (§5.1, §5.1.1) es la disciplina correcta para una lista de `DROP` de este tamaño.
3. **El orden invertido copia→`DROP`** (§5.3 pasos 6→7) elimina una ventana real de pérdida. Análisis correcto.
4. **`VACUUM INTO` en lugar de `cp`.** Verificado: `PRAGMA journal_mode` = `wal` en `dqiii8_metrics.db` y en `dqiii8.db`. La preocupación por el `-wal` huérfano es real y la solución es la adecuada.
5. **`INSERT OR IGNORE` en el paso 5** para idempotencia real frente al `INSERT` simple del borrador: correcto (una vez exista la tabla — hallazgo 2).
6. **Verificación del dump releyéndolo** (`zcat | grep -c '^INSERT INTO'` contra el `count(*)` del dry-run, paso 4): es exactamente la precaución que un gzip truncado por disco lleno exige.
7. **Espacio en disco:** 31 G libres frente a ~46 MB de DBs. El chequeo del paso 0(e) pasará con enorme holgura.
8. **La red de backups de la que depende §5.5 es sólida y está viva.** `db_backup.sh` usa `.backup` (seguro sobre WAL), `flock` contra concurrencia, size-gate + `integrity_check` antes de confiar en el fichero, y rotación por timestamp del nombre (no mtime). Último backup verificado: `dqiii8.db.bak-20260814T025001Z`, de hoy. El directorio `pre-consolidation-<ts>/` del paso 1 es inmune a la rotación (`find -maxdepth 1` + glob de timestamp estricto).
9. **La ausencia de dependencias externas a `bin/`** (§6.4) es correcta: `grep -rn` sobre `my-projects/`, `.claude/`, `tests/`, `/etc/cron.d/` y unidades systemd no encuentra ningún consumidor de datos de estas DBs fuera de `bin/`. El fallo de §5.2 es de completitud *dentro* de `bin/` (hallazgo 6), no fuera.
10. **La disciplina de alcance de §7 es genuina y bien argumentada** en los dos puntos que enumera: `cleanup_old_sessions()` (§4, con las tres razones verificadas — búfer efímero, IDs inalcanzables, colisión real con `watchdog_test_001`) y la eliminación de definiciones de `schema_v2.sql`. Ambas son decisiones de producto correctamente separadas de la consolidación y correctamente remitidas al usuario. El problema no es lo que §7 excluye, sino lo que se cuela sin ese mismo filtro (hallazgo 2: la *adición* de esquema a `dqiii8.db`; y en menor medida el refactor de `paths.py`, que §5.2 sí marca honestamente como "refactor real, no una línea de config", spec:384-388).
11. **El criterio de éxito `len(resultados) > 0` en lugar de "no lanza excepción"** (§5.4) es la corrección más valiosa del documento: sin ella, la verificación post-migración habría pasado en verde con el sistema igual de roto, que es exactamente lo que lleva 4,5 meses ocurriendo.
12. **El test de regresión propuesto** (§5.4, verificar que `DB_PATH` resuelto en runtime contiene las tablas que cada módulo consulta) ataca la causa raíz — tests que construyen sus propias DBs temporales y dan cero señal de producción — en vez del síntoma. Es la clase de QA estructural que `00_core_behavior.md` exige.
13. **Permisos (paso 10):** el diagnóstico es correcto — `sqlite3 ".backup"` crea con `0644` frente al `0600 root:root` de las tres DBs actuales (verificado: `-rw------- root root` en las tres). El `chmod 600` explícito es necesario. Solo le falta la parte duradera (hallazgo 6).
14. **Dejar los originales como `.old` y no borrarlos al terminar** (paso 11) + la ventana de ~72 h de §5.5: proporcionado al riesgo.

---

## Bloqueantes antes de implementar

En orden:

1. Corregir el paso 5: `session_memory` no existe en `dqiii8.db` (hallazgo 2). Requiere decisión explícita del usuario porque es un cambio de esquema del SSOT.
2. Ampliar el paso 3 a `hpt-poller.timer` y `dqiii8-health.timer` (hallazgo 1).
3. Definir dónde se ejecuta el script respecto a los hooks de Claude Code (hallazgo 3).
4. Envolver los pasos 3–11 en `try/finally` que garantice el rearranque de las 5 unidades (hallazgo 4).
5. Eliminar el paso 7 (`DROP`) — el propio spec lo declara innecesario — o añadirle una parada explícita con confirmación del usuario (hallazgo 5).
6. Añadir `openrouter_wrapper.py` y `health_check.py` a la lista de §5.2 (hallazgo 6).
7. Limpiar el árbol de trabajo (4 ficheros modificados) antes del paso 8 (hallazgo 9).
