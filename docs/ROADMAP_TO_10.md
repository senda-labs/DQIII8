# DQIII8 — Roadmap to 10/10
**Fecha:** 2026-03-25 | Sistema actual: **8/10**

Los 10 gaps que separan el sistema actual de un 10/10 de producción.
Ordenados por impacto descendente dentro de cada categoría.

---

## ALTO IMPACTO

### F1. ML Router (Random Forest)
**Estado:** `bin/monitoring/ml_selector.py` existe (119 LOC) — NO entrenado, NO conectado.
**Problema:** el routing actual es por keywords + embeddings estáticos. Predice tier pero no aprende de errores reales.
**Datos disponibles:** 9,972 filas en `routing_feedback` + 14,376 en `agent_actions` = suficiente para entrenar.
**Implementación:**
```python
# Entrenar RF con scikit-learn
features = ['domain', 'subdomain', 'intent', 'query_length', 'hour_of_day']
target = 'tier_optimal'  # C/B/A
# serializar con joblib, integrar en openrouter_wrapper.py
```
**Referencia:** "Config-driven routing (benchmark→lookup table) es más estable y auditable.
Dynamic routing añade una capa estocástica que necesita su propia evaluación."
**Esfuerzo:** ~4h | **Impacto:** alto — routing más preciso reduce coste API.

---

### F4. Tests (cobertura actual ~5%)
**Estado:** solo `tests/test_smoke.py` + `test_temporal_memory.py` — 12 tests para 74 scripts.
**Problema:** sistema de producción sin cobertura = cambios rompen sin detección.
**Mínimo para 10/10:**
- `test_enricher.py` — TOON/simple_json/full_json outputs
- `test_router.py` — clasificación por dominio, tier assignment
- `test_classifier.py` — domain_classifier, subdomain_classifier
- `test_benchmark.py` — formato de resultados, schema validation
- `test_security_hooks.py` — que los hooks bloquean lo que deben bloquear
**Target:** 200+ tests, >60% coverage.
**Esfuerzo:** ~8h | **Impacto:** alto — prerequisito para refactors seguros.

---

### F6. Feedback Loop Cerrado
**Estado:** no existe. El sistema genera respuestas pero nunca recibe calidad real del usuario.
**Problema:** el routing no puede aprender de errores reales sin feedback explícito.
**Implementación:**
1. Tras cada respuesta via Telegram → enviar mensaje "¿Útil? (1-5)" con botones inline.
2. Guardar rating en `routing_feedback` con los campos de la llamada.
3. Usar ratings para entrenar el ML router (F1).
**Esfuerzo:** ~3h | **Impacto:** alto — cierra el loop de aprendizaje continuo.

---

## MEDIO IMPACTO

### F2. Misroute Rate Tracking
**Estado:** no existe métrica de misroutes.
**Problema:** sin esta métrica no puedes saber si el routing mejora o empeora con cada cambio.
**Implementación:**
```sql
-- Nueva columna en routing_feedback
ALTER TABLE routing_feedback ADD COLUMN tier_optimal TEXT;
-- Comparar tier_used vs tier_optimal del benchmark
-- Misroute = tier_used != tier_optimal
```
**Esfuerzo:** ~2h | **Impacto:** medio — métrica clave para F1 y F6.

---

### F3. Cost Tracking Real
**Estado:** `bin/monitoring/cost_tracker.py` existe pero sin datos de producción.
**Problema:** DQIII8 no sabe cuánto cuesta al mes. Con 4 providers (3 gratuitos + Anthropic paid),
el coste real estimado es ~$0-5/mes + suscripción Claude Max.
**Implementación:** instrumentar cada llamada LLM con:
```python
log_cost(provider, model, tokens_in, tokens_out, cost_usd)
```
**Esfuerzo:** ~2h | **Impacto:** medio — visibilidad financiera del sistema.

---

### F5. Observability Dashboard (accesible desde Telegram)
**Estado:** `bin/ui/dashboard.py` activo en `127.0.0.1:8080` pero nadie lo mira en producción.
**Problema:** métricas solo visibles si estás en el VPS. Sin alertas proactivas.
**Implementación:** comando Telegram `/stats` que devuelva:
```
📊 DQIII8 Stats (últimas 24h)
Audit score: 84.5/100
Acciones: 1,234 | Success: 97.2%
Top error: openrouter_wrapper timeout (12x)
Benchmark: 74/600 (EN PROGRESO)
chunk_key_facts: 27/1309 poblados
```
**Esfuerzo:** ~2h | **Impacto:** medio — observabilidad desde móvil.

---

### F9. Agent Skill Contracts (inputs/outputs tipados)
**Estado:** los agentes tienen prompts en .md pero sin schema de input/output estructurado.
**Problema:** cuando un agente falla, no hay contrato formal sobre qué debería haber recibido/devuelto.
**Implementación:** añadir a cada `agent.md`:
```yaml
## Contract
input:
  required: [task_description]
  optional: [context, examples]
output:
  format: markdown
  required_fields: [result, confidence]
errors:
  - insufficient_context: "Responder con lista de preguntas clarificadoras"
```
**Esfuerzo:** ~3h | **Impacto:** medio — debugging más rápido, integración más robusta.

---

## BAJO IMPACTO

### F7. Rename jarvis→dqiii8 Completo
**Estado:** paths con `/root/jarvis/` siguen existiendo. `database/dqiii8.db` es symlink a `/root/jarvis/database/jarvis_metrics.db`.
**Problema:** deuda técnica que confunde pero no rompe funcionalidad.
**Implementación:** migración de datos, actualizar symlinks, renombrar directorios.
**Riesgo:** alto (rompe paths si no se hace bien) | **Esfuerzo:** ~4h | **Impacto:** bajo — solo claridad.
**Recomendación:** hacer al final, cuando todo lo demás esté 10/10.

---

### F8. ADR Documentation (Architecture Decision Records)
**Estado:** `decisions/` puede estar vacío o incompleto.
**Problema:** decisiones arquitectónicas no documentadas formalmente. "¿Por qué sqlite-vec en vez de pgvector?" no está escrito.
**Implementación:** crear `docs/decisions/ADR-NNN-titulo.md` para las 10 decisiones más importantes.
**Esfuerzo:** ~2h | **Impacto:** bajo — onboarding futuro más rápido.

---

### F10. Re-benchmark Trimestral Automatizado
**Estado:** benchmark se ejecuta manualmente. No hay cron.
**Problema:** sin re-benchmark periódico, no sabes si los modelos han mejorado/empeorado.
**Referencia:** "Re-benchmark trimestralmente como mínimo. Después de un release de modelo mayor,
re-ejecutar categorías afectadas en una semana."
**Implementación:**
```bash
# crontab — primer lunes de cada trimestre a las 03:00
0 3 1-7 1,4,7,10 1 cd /root/dqiii8 && python3 bin/tools/benchmark_multimodel.py --run --report
```
**Esfuerzo:** ~30min | **Impacto:** bajo — automatiza algo ya implementado.

---

## Resumen de priorización

| Gap | Impacto | Esfuerzo | Prioridad |
|-----|---------|---------|-----------|
| F6. Feedback loop cerrado | Alto | 3h | **1** |
| F4. Tests >200 | Alto | 8h | **2** |
| F2. Misroute rate tracking | Medio | 2h | **3** |
| F5. /stats Telegram | Medio | 2h | **4** |
| F1. ML Router RF | Alto | 4h | **5** |
| F3. Cost tracking real | Medio | 2h | **6** |
| F9. Agent contracts | Medio | 3h | **7** |
| F10. Re-benchmark cron | Bajo | 0.5h | **8** |
| F8. ADR docs | Bajo | 2h | **9** |
| F7. jarvis→dqiii8 rename | Bajo | 4h | **10 (último)** |

**Total estimado:** ~31h de trabajo para pasar de 8/10 a 10/10.
**Ruta rápida (8→9/10):** F6 + F2 + F5 = ~7h — cierra el loop de aprendizaje y da observabilidad.
