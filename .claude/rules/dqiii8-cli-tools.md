# DQIII8 — CLI Tools (invocación directa)

| Script | Uso | Trigger |
|--------|-----|---------|
| `bin/tools/gemini_export.py` | Exporta módulo para review Gemini | `/gemini_export [module]` |
| `bin/tools/gemini_review.py` | Registra feedback Gemini en DB | Post-review |
| `bin/tools/github_researcher.py` | Busca repos GitHub relevantes | `/github_research [topic]` |
| `bin/tools/orphan_finder.py` | Detecta scripts sin referencias | `python3 bin/tools/orphan_finder.py` |
| `bin/core/validate_env.py` | Verifica .env keys al startup | Llamado por `bin/j.sh` |
