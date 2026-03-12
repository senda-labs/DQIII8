# /weekly-review — Weekly Dashboard Update

## Trigger
Usuario escribe `/weekly-review` (normalmente los lunes o viernes).

## Comportamiento

### 1. Leer sessions de los últimos 7 días
```bash
find $JARVIS_ROOT/sessions/ -name "*.md" -newer <(date -d '7 days ago' +%Y-%m-%d) | sort
```
Para cada sesión: extraer frontmatter (project, date) y sección "Qué hicimos" (primer bullet).

### 2. Leer estado de todos los proyectos
Leer `projects/*.md` — extraer: título, status del frontmatter YAML, sección "Próximo paso".

### 3. Consultar métricas de la semana
```sql
-- Sesiones esta semana
SELECT COUNT(*), SUM(total_actions), SUM(total_errors), MAX(end_time)
FROM sessions
WHERE start_time >= datetime('now', '-7 days');

-- Agente más usado
SELECT agent_name, COUNT(*) as n
FROM agent_actions
WHERE timestamp >= datetime('now', '-7 days')
GROUP BY agent_name ORDER BY n DESC LIMIT 3;

-- Tasa de éxito global
SELECT ROUND(AVG(success)*100,1) FROM agent_actions
WHERE timestamp >= datetime('now', '-7 days');
```

### 4. Regenerar `00_DASHBOARD.md`

```markdown
---
title: JARVIS Dashboard
date_updated: YYYY-MM-DD HH:MM
week_number: W[N] YYYY
tags: [dashboard, weekly]
---

# JARVIS Dashboard
**Actualizado:** YYYY-MM-DD · Semana W[N]

## Estado de Proyectos

| Proyecto | Status | Último avance | Próximo paso |
|----------|--------|---------------|--------------|
| [[content-automation]] | 🟢 Activo | [1-liner] | [próximo paso] |
| [[hult-finance]] | 🟡 Activo | [1-liner] | [próximo paso] |
| [[leyendas-del-este]] | 🔵 Pausado | [1-liner] | [próximo paso] |
| [[jarvis-core]] | 🟢 Activo | [1-liner] | [próximo paso] |

## Sesiones esta semana

- **YYYY-MM-DD** · [proyecto] — [1-liner de lo que se hizo]
- ...

## Métricas

| Métrica | Valor |
|---------|-------|
| Sesiones totales | N |
| Acciones totales | N |
| Tasa de éxito | N% |
| Agente más usado | [nombre] (N acciones) |
| Último audit score | N/100 |

## Tareas pendientes

> [!todo] content-automation
> - [ ] Fix subtítulos visibles en video final
> - [ ] ...

> [!todo] hult-finance
> - [ ] Scenario analysis capital structure
> - [ ] ...

## Alertas

> [!warning] [Solo si score audit < 80 o errores sin resolver]
> [Descripción del problema]
```

### 5. Git push
```bash
git -C $JARVIS_ROOT add 00_DASHBOARD.md sessions/
git -C $JARVIS_ROOT commit -m "📊 weekly review semana W[N]"
git -C $JARVIS_ROOT push origin main
```

### 6. Feedback
```
[WEEKLY] ✅ Dashboard actualizado en 00_DASHBOARD.md · Semana W[N] · [N] sesiones procesadas
```

## Notas
- Usar `date +%V` para el número de semana ISO
- Si no hay sesiones esa semana, indicarlo explícitamente en el dashboard
- El dashboard es el único archivo que el weekly-review regenera completamente
