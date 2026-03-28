# ANOVA-REPORTS — Plan Maestro del Proyecto (v2)

> Sistema autónomo de generación de Informes de Diagnóstico e Informes de Plan de Internacionalización para PYMEs españolas, con calidad de consultor senior.
> 
> **v2 — Correcciones críticas aplicadas:** sub-agentes para redacción larga, docxtpl reemplaza Node.js, radar generado desde JSON (no extraído de PNG), API REST en producción.

---

## 0. Auditoría previa: Lo que sé

### Inputs por empresa (3 escenarios)
| Caso | Frecuencia | Datos disponibles |
|------|-----------|-------------------|
| Mínimo | Poco frecuente | CIF + Puntuaciones radar (JSON) |
| Estándar | **Más frecuente** | CIF + Web + Puntuaciones radar (JSON) |
| Completo | Poco frecuente | CIF + Web + Puntuaciones radar (JSON) + Informe económico |
| +Cuestionario | Opcional en cualquier caso | Cuestionario de inscripción (preguntas con puntuación 0/0.5/1 en 6 áreas) |

> **CAMBIO v2:** El input primario de puntuaciones es SIEMPRE el JSON numérico (enteros 0-4). La gráfica radar PNG se GENERA desde el JSON con matplotlib, nunca se extrae de una imagen. Si el cliente entrega una imagen radar, se usa como referencia visual para cargar los enteros manualmente en el JSON, pero el sistema nunca depende de OCR/Vision.

### Outputs por empresa (2 documentos DOCX)
1. **Informe de Diagnóstico** (~15 páginas)
2. **Plan de Internacionalización** (~35-50 páginas)

### Estructura verificada del Diagnóstico (extraída de ejemplos)
```
1. Información de la empresa
   - Datos identificativos
   - Actividad y modelo de negocio
2. Potencial de internacionalización
   - Empresa / modelo de negocio (X/4)
   - Producción y operaciones (X/4)
   - Organización y RRHH (X/4)
   - Finanzas (X/4)
   - Comercial y Marketing (X/4)
   - Digitalización (X/4)
   [INSERTAR GRÁFICA RADAR — generada por radar_generator.py]
3. Conclusiones
   - Tabla áreas de mejora vs palancas
   - Análisis por área (frenos)
   - Análisis por área (palancas)
   - Conclusiones adicionales / análisis global
   - Recomendaciones finales
```

### Estructura verificada del Plan de Internacionalización (extraída de ejemplos)
```
Índice de contenido (auto-generado)

1. Análisis estratégico de las conclusiones del diagnóstico
   - Narrativa analítica extensa (3-5 págs)
   1.1 DAFO
   1.2 CAME
   1.3 PESTEL

2. Mercado objetivo
   - Análisis del mercado destino (Portugal típicamente)
   - Datos macro, sectorial, competencia, oportunidades (~10 págs)

3. Plan de internacionalización
   3.1. Organización y gestión del Proyecto
   3.2. Estrategia de Entrada
   3.3. Marketing Mix Internacional (4P)
   3.4. Plan de Marketing
   3.5. Plan Económico-financiero
   3.6. Planificación y gobernanza
   3.7. Recomendaciones y recursos

4. Anexo: Fuentes de financiación
```

### Cuestionario de inscripción (estructura extraída)
```
6 áreas × 4 preguntas = ~24 preguntas
Puntuación: 0 / 0.5 / 1 por pregunta → Total área = suma (max 4)
Formato: ZIP disfrazado de .pdf (7 JPEG + 7 TXT + manifest.json)
```

### Formato obligatorio
- Fuente: **APTOS**
- Tamaño: 12pt párrafos, 10-12pt tablas
- Rupturas de página: por cada nuevo apartado (no subapartados)
- Rupturas de página: por cada ficha de financiación en anexo
- Figura descriptiva centrada bajo gráfica radar
- Puntuaciones = números enteros, coinciden con gráfica
- Márgenes iguales en todo el documento
- Formato: DOCX (Word)
- Índice actualizado al final

---

## 1. Arquitectura del Proyecto

### 1.1. Estructura de carpetas

```
anova-reports/
├── PROJECT.md
├── CONFIG.md
├── README.md
├── models.py                     # Pydantic v2 schemas (ÚNICO archivo)
│
├── config/
│   ├── settings.py               # Rutas, API keys, constantes
│   └── prompts/                  # Prompts centralizados
│       ├── diagnostic_section1.txt
│       ├── diagnostic_section2_area.txt
│       ├── diagnostic_section3.txt
│       ├── plan_strategic_analysis.txt
│       ├── plan_dafo.txt
│       ├── plan_came.txt
│       ├── plan_pestel.txt
│       ├── plan_market.txt
│       ├── plan_organization.txt
│       ├── plan_marketing.txt
│       ├── plan_financial.txt
│       ├── plan_governance.txt
│       └── plan_recommendations.txt
│
├── core/
│   ├── orchestrator.py           # Máquina de estados con checkpointing
│   ├── document_builder.py       # Ensamblaje DOCX con docxtpl
│   ├── radar_generator.py        # Matplotlib radar chart maker
│   └── state.py                  # CompanyReportState
│
├── agents/
│   ├── base_agent.py             # Clase base: Anthropic SDK + Groq fallback
│   ├── researcher.py             # Fusión: company + sector + market
│   ├── diagnostic_writer.py      # Diagnóstico completo (1 call, 15 págs)
│   ├── strategy_architect.py     # DAFO, CAME, PESTEL (3 calls)
│   ├── plan_director.py          # Orquesta sub-agentes del plan
│   ├── plan_section_writer.py    # Escribe 1 sección del plan
│   ├── financial_writer.py       # Especialista financiero
│   └── quality_reviewer.py       # Revisor de calidad
│
├── data/
│   ├── inputs/{slug}/meta.json
│   ├── templates/                # .docx REALES con tags Jinja2
│   │   ├── diagnostico_template.docx
│   │   └── plan_template.docx
│   └── outputs/{slug}/
│       ├── diagnostico.docx
│       ├── plan_internacionalizacion.docx
│       ├── radar.png
│       ├── state.json
│       └── quality_report.json
│
├── knowledge/
│   ├── markets/portugal/base.md
│   ├── financing/fichas_financiacion.md
│   ├── resources/general_resources.md
│   └── writing_style/style_guide.md
│
├── db/
│   ├── schema.sql
│   └── anova_reports.db
│
└── tests/
    └── golden/
```

### 1.2. Correcciones arquitectónicas (4 puntos críticos)

#### C1: Sub-agentes para el plan (anti-trampa de 50 páginas)

**Problema:** Un solo agente generando 35-50 páginas en 1 llamada LLM → repeticiones, pérdida de formato, alucinaciones.

**Solución: Patrón Director → Sub-agentes (map-reduce)**

```
plan_director.py
├── Call 1: Genera OUTLINE completo
├── Call 2: Análisis estratégico narrativo (3-5 págs)
├── Call 3: DAFO (strategy_architect)
├── Call 4: CAME (con DAFO como input)
├── Call 5: PESTEL (con web_search)
├── Call 6: Mercado objetivo (~10 págs)
├── Call 7: Organización + Estrategia entrada
├── Call 8: Marketing Mix + Plan Marketing
├── Call 9: Plan Financiero (financial_writer)
├── Call 10: Gobernanza
├── Call 11: Recomendaciones + Recursos
└── Ensamblaje final → InternationalizationPlan JSON
```

Cada sub-agente recibe: outline global + datos relevantes + secciones previas (coherencia forward). Fallo en sección N no pierde 1..N-1.

El diagnóstico (15 págs) SÍ cabe en 1 sola llamada — no necesita sub-agentes.

#### C2: Stack 100% Python — docxtpl reemplaza Node.js

**Problema:** Node.js (docx-js) rompe homogeneidad del stack DQIII8.

**Solución:** `docxtpl` — plantilla Word real con tags Jinja2:

```python
from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm

doc = DocxTemplate("data/templates/diagnostico_template.docx")
context = {
    "company_name": "CODIMA SL",
    "radar_image": InlineImage(doc, "outputs/codima/radar.png", width=Mm(130)),
    "areas": [{"name": "Finanzas", "score": 2, "text": "..."}],
}
doc.render(context)
doc.save("outputs/codima/diagnostico.docx")
```

Formato visual se diseña en Word (Aptos, márgenes, colores), Python solo inyecta datos.

#### C3: Radar generado desde JSON, nunca extraído de imagen

**Problema:** OCR/Vision para leer puntuaciones de imagen radar = impreciso y frágil.

**Solución:** Input = JSON numérico → matplotlib genera radar.png → docxtpl lo inyecta:

```
JSON {empresa_modelo: 1, finanzas: 2, ...}
    ↓
radar_generator.py (matplotlib) → radar.png
    ↓
docxtpl InlineImage → DOCX final
```

Coherencia garantizada: mismo JSON alimenta texto Y gráfica. Imposible discrepancia.

#### C4: API REST en producción, CLI solo para desarrollo

**Problema:** `claude -p` CLI no escala a 1100 calls/día (100 empresas × ~11 calls).

**Solución:** Arquitectura dual:

```
DESARROLLO: Claude Code CLI → construye el código
PRODUCCIÓN: anthropic SDK (pip) → API REST estándar
FALLBACK:   Groq (llama-3.3-70b) → calidad inferior, gratis
```

Escalabilidad: ~60 req/min API → 100 empresas en ~1 hora con paralelismo.
Coste: ~$0.50/empresa → $50/día para 100 informes.

### 1.3. Pipeline de 5 fases

```
FASE 1: INVESTIGACIÓN → researcher.py
  Tier B (Groq). 1-3 calls. Checkpoint: research_cache en DB.

FASE 2: DIAGNÓSTICO → diagnostic_writer.py
  Tier A (Anthropic API). 1 call. Checkpoint: diagnostic JSON en DB.

FASE 3: PLAN → plan_director.py + plan_section_writer.py
  Tier A (Anthropic API). ~11 calls. Checkpoint por sección.

FASE 4: ENSAMBLAJE → document_builder.py + radar_generator.py
  Local (0 LLM). docxtpl + matplotlib. Checkpoint: DOCX paths.

FASE 5: REVISIÓN → quality_reviewer.py
  Tier A (Anthropic API). 1 call. Output: quality_report.json.
```

Total calls LLM por empresa: ~15 (3 gratis + 12 Anthropic)

### 1.4. Orquestador con Checkpointing

```python
class CompanyReportState(BaseModel):
    company: CompanyInput
    status: PipelineStatus
    research: Optional[CompanyResearch] = None
    diagnostic: Optional[DiagnosticReport] = None
    plan_outline: Optional[str] = None
    plan_sections_completed: dict[str, str] = {}
    plan: Optional[InternationalizationPlan] = None
    radar_png_path: Optional[str] = None
    diagnostic_docx_path: Optional[str] = None
    plan_docx_path: Optional[str] = None
    quality_report: Optional[QualityReport] = None
    tokens_used: dict[str, int] = {}
    errors: list[str] = []
```

Recovery: si cae en sección 7 del plan, retoma desde sección 7. No repaga fases 1-2 ni secciones 1-6.

---

## 2. Tecnología

| Componente | Tecnología | Por qué |
|-----------|-----------|---------|
| Modelos de datos | Pydantic v2 | Validación estricta, serialización |
| LLM producción | anthropic SDK | API REST, batch, escalable |
| LLM gratis | Groq OpenAI-compatible | Investigación, fallback |
| LLM desarrollo | Claude Code CLI | Solo para construir el proyecto |
| DOCX | docxtpl | Plantilla Word real + Jinja2, Python puro |
| Radar chart | matplotlib | Generación desde JSON, 0 OCR |
| Base de datos | SQLite | Coherente con DQIII8 |
| Async | asyncio | Paralelismo batch |

---

## 3. Próximos pasos

### Paso 1 ✅ COMPLETADO
- [x] Documentación y análisis completo
- [x] Auditoría de puntos críticos (v2)

### Paso 2: Subir al VPS + Claude Code organiza
- [ ] scp al VPS, crear estructura, inicializar DB
- [ ] pip install docxtpl matplotlib anthropic

### Paso 3: Construir el final primero (Fase 4)
- [ ] Crear plantillas .docx en Word con tags Jinja2
- [ ] Mock JSON con datos falsos → renderizar DOCX → validar formato
- [ ] radar_generator.py funcional
- [ ] **Si DOCX sale bien con datos falsos, el resto es llenar el JSON**

### Paso 4: Agentes de redacción
- [ ] base_agent.py (Anthropic SDK + Groq fallback)
- [ ] diagnostic_writer.py
- [ ] plan_director.py + plan_section_writer.py
- [ ] strategy_architect.py, financial_writer.py, researcher.py

### Paso 5: Orquestador + integración
- [ ] orchestrator.py con checkpointing
- [ ] quality_reviewer.py
- [ ] Integración Telegram
- [ ] Test E2E con 3 empresas de ejemplo

---

## 4. Riesgos

| Riesgo | Impacto | Mitigación |
|--------|---------|-----------|
| Calidad textual vs consultor | ALTO | Sub-agentes focalizados, prompts con ejemplos, revisión F5 |
| Coherencia entre secciones plan | ALTO | Outline compartido, secciones previas como contexto |
| ANTHROPIC_API_KEY no disponible | MEDIO | Groq fallback, calidad inferior pero funcional |
| Plantilla docxtpl formato | BAJO | Plantilla diseñada en Word real |
| Costes API volumen alto | BAJO | ~$50/día para 100 informes |
| Investigación web caso mínimo | ALTO | Múltiples fuentes: registros, CNAE, LinkedIn |
