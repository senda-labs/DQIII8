# /test-team — Agent Team Coordination Test

Prueba de coordinación directa entre agentes usando Agent Teams.
Demuestra que el output de un agente alimenta directamente al siguiente.

## Team

**Tarea**: Implementar Kelly Criterion en Python con base en investigación previa.

### Agente 1 — research-analyst (primero)

Investiga el Kelly Criterion y produce un resumen estructurado con:
- Fórmula matemática exacta: `f* = (bp - q) / b`
  donde `b` = odds netos, `p` = probabilidad de ganar, `q` = 1 - p
- Parámetros de entrada y sus rangos válidos
- Variante Half-Kelly (f* / 2) y cuándo preferirla
- Casos de uso en trading sistemático (position sizing)
- Limitaciones conocidas (sensibilidad a estimación de p)

Escribe el resultado a: `tasks/results/research-kelly-[timestamp].md`

### Agente 2 — python-specialist (después de Agente 1)

Lee el resultado de research-analyst en `tasks/results/research-kelly-*.md`
y basándose en él implementa:

```python
def kelly_criterion(win_prob: float, win_loss_ratio: float, half_kelly: bool = True) -> float:
    """
    Calcula el tamaño óptimo de posición según Kelly Criterion.
    ...
    """
```

Requisitos de implementación:
- Type hints completos
- Validación de inputs (0 < win_prob < 1, win_loss_ratio > 0)
- Soporte para Half-Kelly (por defecto True — más conservador)
- Ejemplo de uso en docstring con valores reales de trading

Escribe el resultado a: `tasks/results/python-kelly-[timestamp].md`

## Protocolo de coordinación

```
research-analyst → tasks/results/research-kelly-*.md
                              ↓
python-specialist lee ese archivo → implementa función
```

El python-specialist NO empieza hasta que research-analyst haya escrito su resultado.
Esto valida la coordinación secuencial de Agent Teams.

## Ejecución

Lanza ambos agentes como team coordinado. El orchestrator espera el resultado
del research-analyst antes de pasar el contexto al python-specialist.

Al terminar, muestra:
1. Resumen de investigación (fórmula + parámetros)
2. Código Python implementado
3. Confirmación: `[TEAM] ✅ Kelly Criterion — research + impl completos`
