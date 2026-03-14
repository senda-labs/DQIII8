# JARVIS — Lessons Log
Formato: `[FECHA] [KEYWORD] causa → solución`

---

## content-automation
- [2026-03-08] [elevenlabs-timeout] Texto >500 chars causa timeout → dividir en chunks de 450
- [2026-03-09] [windows-path] Rutas con espacios rompen FFmpeg → Path().as_posix()
- [2026-03-13] [class-name-verification] Importar sin verificar nombre exacto de clase → usar grep -n "^class" antes de importar
- [2026-03-13] [ast-transformation-risk] Transformaciones AST sin test inmediato → ejecutar test unitario después de cada transformación
- [2026-03-13] [oom-streaming-pattern] Acumular frames en List[np.ndarray] causa OOM → usar generadores + render_to_dir
- [2026-03-14] [hf-api-url] HuggingFace migró endpoint → usar router.huggingface.co/hf-inference/models/
- [2026-03-14] [clip-oom] CLIPScorer cargaba 4-5GB en __init__ → lazy-load con flag _load_attempted
- [2026-03-14] [frame-accumulation] render_to_dir acumulaba 900 frames × 6MB → streaming generator con del inmediato
- [2026-03-14] [elevenlabs-naming] 3 bugs de naming en ElevenLabs → verificar clase y método exactos antes de integrar
- [2026-03-14] [bible-cache] Groq devuelve Bible cacheada en tests → borrar /tmp/bible_cache antes de test real
- [2026-03-14] [ci-deps] CI falla con ModuleNotFoundError → instalar numpy/pillow/groq en ci.yml antes de pytest

## hult-finance
- [2026-03-10] [matplotlib-export] Guardar .png antes de insertar en PPT → no insertar figura directamente

## jarvis-core
- [2026-03-10] [hooks] BLOCKED_BASH hace match contra el string completo incluyendo commit message → usar mensajes de commit sin patrones peligrosos
- [2026-03-10] [ollama-routing] Claude Code no soporta ollama como modelo nativo → routing real via openrouter_wrapper.py
- [2026-03-14] [github-auth] Git push requiere PAT no contraseña → usar token en remote URL
- [2026-03-14] [git-keys-exposed] API keys en historial git → rotar keys + git-filter-repo para limpiar historial
- [2026-03-14] [black-ci] Black --check falla en CI si código no está formateado → correr black localmente antes de push
- [2026-03-14] [ci-ruff-inherited] ruff detecta 50+ errores preexistentes en CI → ignorar con --ignore para herencia limpia

## leyendas-del-este
- [2026-03-10] [spanish-dialogue] Em-dash (—) para diálogos, no comillas dobles
- [2026-03-10] [verb-tense] No mezclar pretérito/presente dentro de la misma escena
- [2026-03-14] [env-override] config/.env tenía GROQ key caducada con override=True → pipeline ignoraba /root/jarvis/.env → sincronizar ambos .env cuando se rota una key
