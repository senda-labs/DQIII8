# JARVIS — Lessons Log
Formato: `[FECHA] [KEYWORD] causa → solución`

---

## content-automation
- [2026-03-09] [windows-path] Rutas con espacios rompen FFmpeg → Path().as_posix()
- [2026-03-08] [elevenlabs-timeout] Texto >500 chars causa timeout → dividir en chunks de 450

## hult-finance
- [2026-03-10] [matplotlib-export] Guardar .png antes de insertar en PPT — no insertar figura directamente

## jarvis-core
- [2026-03-10] [hooks] BLOCKED_BASH hace match contra el string completo del comando, incluyendo el mensaje de commit → usar mensajes de commit sin patrones peligrosos en el texto, o añadir contexto de exclusión para comandos git
- [2026-03-10] [ollama-routing] Claude Code no soporta ollama como modelo nativo. Routing real via http://localhost:11434/api/generate confirmado con curl. Implementar bin/ollama_wrapper.py en Fase 2.

## leyendas-del-este
- [2026-03-10] [spanish-dialogue] Em-dash (—) para diálogos, no comillas dobles
- [2026-03-10] [verb-tense] No mezclar pretérito/presente dentro de la misma escena

[2026-03-13] [class-name-verification] Antes de ejecutar un pipeline, verificar 
el nombre exacto de clase con grep -n "^class" antes de importar → evita 4-5 
intentos fallidos de import.

[2026-03-13] [ast-transformation-risk] Las transformaciones AST automatizadas 
(list → yield) pueden introducir bugs de referencias (frames.append sin frames 
definido). Fix: siempre ejecutar test unitario inmediatamente después de cada 
transformación, no al final de todas.

[2026-03-13] [oom-streaming-pattern] Acumulación de frames en List[np.ndarray] 
es un OOM garantizado para vídeos largos. Patrón correcto: generadores Python + 
render_to_dir + ImageSequenceClip por rutas de archivo → pico 54.9MB vs 7.4GB.
