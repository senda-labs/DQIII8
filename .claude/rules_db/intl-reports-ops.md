# intl-reports — Reglas operativas

## Producción autónoma (desde terminal/tmux, NUNCA desde dentro de Claude Code)
```bash
python3 scripts/generate_company.py --slug {SLUG} --phase generate
python3 scripts/generate_company.py --slug {SLUG} --phase generate --force --concurrency 3
```

## Orquestación manual (desde Claude Code)
```
--phase prompts  → genera /tmp/intl_{slug}_*.txt
--phase status   → secciones faltantes
--phase assemble → QA + DOCX
```
Para cada sección: Read /tmp/intl_{slug}_{section}.txt → Agent(intl-writer, prompt=INLINE) → heredoc + parse_agent_response + save_section_json

## Guardado — OBLIGATORIO
NUNCA: `python3 -c "...json..."` (rompe con caracteres especiales)
NUNCA: `scripts/save_response.py` (patrón deprecado, sin script vigente en el árbol principal)
SIEMPRE:
```bash
cat > /tmp/intl_response.json << 'HEREDOC_EOF'
{respuesta raw del agent}
HEREDOC_EOF
python3 -c "
import sys
sys.path.insert(0, '.')
from tools.agent_writer import parse_agent_response, save_section_json
data = parse_agent_response(open('/tmp/intl_response.json').read())
save_section_json('{SLUG}', '{SECTION}', data)
print('Guardado OK')
"
```

## Restricciones absolutas
- NUNCA usar `--dangerously-skip-permissions` (falla con root)
- NUNCA `claude --print` desde dentro de Claude Code (conflicto recursivo)
- NUNCA `intl-writer` para implications_brief
- batch_run.py NO funciona (API key sin créditos)
