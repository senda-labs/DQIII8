---
title: JARVIS Loop Benchmark
tags: [benchmark, testing, autonomous]
status: active
agents: [orchestrator]
model: varies (tier1/tier2/tier3/haiku)
---

# jarvis-loop-benchmark — Proyecto de Testing

## Objetivo
Comparar el rendimiento de los 4 tiers de modelos ejecutando
el mismo conjunto de objetivos de forma autónoma.

## Metodología
- 5 objetivos idénticos por tier
- Cada objetivo tiene criterio de éxito verificable
- Duración: 2-4h por tier
- Auditor Sonnet analiza los resultados al final

## Objetivos de benchmark (mismos para todos los tiers)
1. Crear un script Python que lea un CSV y genere estadísticas básicas
2. Añadir un test unitario para una función existente en el proyecto
3. Refactorizar una función de más de 50 líneas en funciones más pequeñas
4. Escribir documentación de una clase sin docstring
5. Corregir un error de linting reportado por ruff

## Próximo paso
Ejecutar: `j --loop jarvis-loop-benchmark 5 --tier tier1`

## Resultados
```bash
sqlite3 database/jarvis_metrics.db "SELECT * FROM benchmark_results;"
```

## Comandos de referencia
```bash
# Ejecutar benchmark para cada tier
j --loop jarvis-loop-benchmark 5 --tier tier1   # Ollama local
j --loop jarvis-loop-benchmark 5 --tier tier2   # OpenRouter free
j --loop jarvis-loop-benchmark 5 --tier tier3   # Claude Sonnet
j --loop jarvis-loop-benchmark 5 --tier haiku   # Claude Haiku 4.5

# Ver resultados comparativos
j --benchmark-report

# Ver resultados directos en BD
sqlite3 database/jarvis_metrics.db "SELECT * FROM benchmark_results;"
```
