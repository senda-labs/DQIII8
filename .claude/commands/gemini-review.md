# /gemini-review — Gemini Pro Code Reviewer

Lanza una auditoría de eficiencia sobre archivos Python no revisados usando Aider + Gemini 2.0 Flash.

## Uso

```
/gemini-review              # Revisar todos los .py modificados pendientes
/gemini-review <archivo>    # Revisar un archivo específico
/gemini-review --check-only # Ver cuántos archivos hay pendientes (sin revisar)
```

## Qué hace

1. Detecta archivos `.py` modificados en git que no han sido revisados aún (via BD).
2. Pasa cada archivo a Aider con el modelo `gemini/gemini-2.0-flash`.
3. Analiza: bugs, eficiencia, legibilidad, seguridad.
4. Guarda reporte Markdown en `database/audit_reports/gemini_review_<ts>.md`.
5. Registra el review en `jarvis_metrics.db` (tabla `audit_reports`).
6. Git push → reporte disponible en Obsidian en ~1 min.

## Requisitos

- `GEMINI_API_KEY` configurada en `/root/dqiii8/.env`
- `aider` instalado: `pip install aider-chat --break-system-packages`

## Integración automática

Se ejecuta automáticamente al final de cada sesión ≥15 min (via `stop.py`)
si hay archivos pendientes. El proceso corre en background y no bloquea el cierre.

## Implementación

```bash
python3 /root/dqiii8/bin/gemini_review.py $ARGUMENTS
```
