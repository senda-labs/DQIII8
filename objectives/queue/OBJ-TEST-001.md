---
objective_id: OBJ-TEST-001
title: Verificar instalacion JAL-v3
type: technical
priority: 1
max_attempts: 2
---

# Objetivo: Verificar JAL-v3

## Descripcion
Comprobar que el sistema JAL-v3 funciona correctamente.

## Criterios de exito
- [ ] Archivo /tmp/jal_v3_ok.txt existe con contenido "JAL-v3 functional"
- [ ] BD contiene tabla jal_scoring_snapshots
- [ ] Test unitario jal_scoring.py supera los 4 tests

## Criterios de completion %
- 100%: los 3 criterios cumplidos
- 66%: 2 de 3 criterios
- 33%: 1 de 3 criterios
- 0%: ninguno cumplido
