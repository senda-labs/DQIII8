---
name: intl-reports
description: Genera y entrega informes de internacionalización (Diagnóstico + Plan) para pymes españolas. Orquesta el pipeline empresa a empresa: content_brief → Haiku writer → QA → DOCX → Telegram → espera confirmación.
command: /intl-reports
allowed-tools: [Bash, Agent, Read, Write, Edit, Glob, Grep]
user-invocable: true
---

# /intl-reports — Orquestador de Informes de Internacionalización

Proyecto en `/root/dqiii8/my-projects/intl-reports/`.
CSV fuente: `Respuestas__P&L_Metal_31_03_2026.csv` (100 empresas).

## Arquitectura

**Claude Code Sonnet** = orquestador (esta sesión).
**Haiku via Agent tool** = escritor de contenido (una llamada por doc_type).
**Sin SDK externo, sin subprocess LLM. Sin revisión final con Sonnet.**

## Pipeline empresa a empresa

```
Para CADA empresa (una a la vez, esperar Telegram entre ellas):

1. [Bash] python3 tools/content_brief.py --slug {slug} --type both
          → Si ya existe content_brief.json y no hay DOCX, se puede reusar.

2. [Python] from tools.agent_writer import build_prompt
            diag_prompt = build_prompt(slug, "diagnostic")

3. [Agent haiku] Prompt = diag_prompt +
   "\n\nGenera el JSON completo del diagnóstico siguiendo el schema exacto.
   Cuando lo tengas, guárdalo ejecutando en Bash:
   cd /root/dqiii8/my-projects/intl-reports && python3 -c \"
   import sys,json; sys.path.insert(0,'.')
   from tools.agent_writer import write_content
   content = <TU_DICT_JSON>
   write_content('{slug}','diagnostic',content)
   \""

4. [Python] errors = check_qa(slug, "diagnostic")
            → Si errors: 1 retry Haiku con errores + prompt original.
            → Si retry falla: renderizar igual + loguear.

5. [Bash] python3 tools/rich_docx_builder.py --slug {slug} --type diagnostic
          → Verificar que drafts/{slug}_*diagnostic*.docx existe.

6. [Python] plan_prompt = build_prompt(slug, "plan")

7. [Agent haiku] Igual que paso 3 pero para "plan".
   ALTERNATIVA (si QA falla word count): usar build_plan_section_prompts(slug)
   → 6 secciones en paralelo → assemble_plan_sections(slug, sections)

8. [Python] errors = check_qa(slug, "plan")
            → 1 retry si errors.

9. [Bash] python3 tools/rich_docx_builder.py --slug {slug} --type plan
          → Verificar que drafts/{slug}_*plan*.docx existe.

10. [Bash] python3 tools/send_telegram.py --slug {slug}

11. ESPERAR confirmación del usuario vía Telegram antes de la siguiente empresa.
```

## Funciones clave (tools/agent_writer.py)

```python
from tools.agent_writer import (
    build_prompt,              # str con SYSTEM_PROMPT + datos empresa
    write_content,             # valida schema + escribe JSON
    check_qa,                  # [] = OK, lista = re-despachar
    build_plan_section_prompts,# dict[section_name → prompt] para planes largos
    assemble_plan_sections,    # ensambla 6 secciones → write_content
)
```

## Orden de ejecución (CSV)

Las 100 empresas del CSV, en orden de aparición, saltando las que ya tengan
ambos DOCX (diagnostic + plan) en `companies/{slug}/drafts/`.

```bash
# Ver estado completo
python3 -c "
import csv, re, pathlib
ROOT = pathlib.Path('/root/dqiii8/my-projects/intl-reports')
def slugify(n):
    import re
    for a,b in [('á','a'),('é','e'),('í','i'),('ó','o'),('ú','u'),('ñ','n'),
                ('à','a'),('è','e'),('ì','i'),('ò','o'),('ù','u'),
                ('ä','a'),('ë','e'),('ï','i'),('ö','o'),('ü','u')]:
        n = n.replace(a,b)
    n = re.sub(r'[^\w\s-]','',n.lower()); return re.sub(r'[\s_]+','-',n).strip('-')
with open(ROOT / 'Respuestas__P&L_Metal_31_03_2026.csv', encoding='utf-8-sig') as f:
    rows = list(csv.DictReader(f, delimiter=';'))
for i,row in enumerate(rows,1):
    name = row.get('Nombre de la empresa','').strip()
    if not name: continue
    slug = slugify(name)
    sd = ROOT/'companies'/slug
    hd = any((sd/'drafts').glob('*diagnostic*.docx')) if (sd/'drafts').exists() else False
    hp = any((sd/'drafts').glob('*plan*.docx')) if (sd/'drafts').exists() else False
    st = 'DONE' if (hd and hp) else ('PARTIAL' if (hd or hp) else 'PENDING')
    if st != 'DONE':
        print(f'[{i:3}] {st:8} {\"✓\" if (sd/\"meta.json\").exists() else \"✗ NO META\"} {slug}')
"
```

## Reglas absolutas

1. **NUNCA** usar `anthropic` SDK ni subprocess LLM. Solo Agent tool model=haiku.
2. **NUNCA** hacer revisión final con Sonnet 4.6 — 0 tokens de orquestación en revisión.
3. **SIEMPRE** llamar `check_qa()` tras `write_content()` antes de renderizar DOCX.
4. Si `check_qa()` falla en 2do intento → renderizar igual + loguear warnings en DOCX cover.
5. **NUNCA** enviar por Telegram un DOCX sin verificar que existe en `drafts/`.
6. Una empresa a la vez. Esperar confirmación Telegram antes de la siguiente.
7. No regenerar content_brief si ya existe Y no hay cambios en meta.json desde entonces.
8. **PROTOCOLO CERO COMPLACENCIA**: verifica que el DOCX existe en `drafts/` antes del envío.

## Directorio de trabajo

```
/root/dqiii8/my-projects/intl-reports/
├── Respuestas__P&L_Metal_31_03_2026.csv   ← fuente de 100 empresas
├── companies/{slug}/
│   ├── meta.json                           ← fuente de verdad datos empresa
│   ├── info-origin/raw_survey_data.json    ← cuestionario ANOVA
│   └── data/
│       ├── content_brief.json
│       ├── report_content_diagnostic.json
│       ├── report_content_plan.json
│       └── report_content.json            ← último generado
├── tools/
│   ├── content_brief.py
│   ├── agent_writer.py
│   ├── rich_docx_builder.py
│   ├── send_telegram.py
│   └── qa_pre_render.py
└── data/templates/                        ← plantillas DOCX
```
