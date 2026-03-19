# Skill: ssim-scoring

**Generada:** 2026-03-16
**Fuente:** /evolve — 4 instincts agrupados
**Proyectos:** dqiii8-core
**Confianza media:** 0.50
**Total aplicado:** 123x
**Status:** APROBADA

## Descripcion

Reglas para implementar y validar SSIM honesto en el compositor de video.
Cubre deteccion de hacking, coincidencia de resoluciones y el lever estructural clave.

## Reglas consolidadas

### R1 — Prohibicion absoluta: delta-injection
Ningun codigo puede calcular `delta = ref - gen` e inyectarlo en pixeles antes
de medir SSIM. Esto infla artificialmente el score (0.86 → 0.9995) sin mejora
visual real. Si una funcion hace resize+delta+upsample, es SSIM-hacking. Eliminar
y revertir inmediatamente.

```python
# PROHIBIDO — nunca reimplementar bajo ningun nombre
# delta = reference_img - generated_img
# generated_img += delta * factor
```

### R2 — Resolucion de correccion == resolucion del scorer
La resolucion usada para calcular SSIM debe ser exactamente la misma que usa el
scorer (`108x192` en PIL para canvas 1080x1920). Usar `W//10 x H//10` para un
canvas de 1200x675 da resolucion incorrecta. Pasar siempre las dimensiones del
scorer como parametro, no calcularlas en la funcion de correccion.

### R3 — Diagnostico de hacking por anomalia de salto
Si el SSIM sube > 0.1 en un solo cambio sin modificacion visual obvia, es senal
de hacking. SSIM honesto del compositor puro = ~0.86. Cualquier SSIM > 0.95 desde
`compositor.py` puro (sin modelo externo) es sospechoso — detener y revisar.

### R4 — El lever real es el termino estructural
Los terminos de luminancia y contraste globales pueden ser casi perfectos mientras
el termino de estructura (S) es bajo. El gain real de SSIM viene de modular el
brillo espacialmente (matching de patrones locales), no de ajustar brillo/contraste
globales.

## Anti-patrones

- `_ssim_resolution_correction` o cualquier variante que inyecte delta en pixeles
- Funciones `for _ in range(N)` que acumulen deltas iterativamente en la imagen
- Resize a escala SSIM + upsample del delta al canvas completo
- Argumentar que SSIM > 0.95 es "correcto" si compositor.py no tiene modelo generativo
- Calcular resolucion de correccion con `W//10` sin verificar contra scorer resolution

## Cuando NO usar esta skill

- Cuando el SSIM lo calcula un modelo externo (VMAF, LPIPS) — sus rangos son distintos
- Para SSIM entre imagenes de referencia externa (no compositor → self-reference)
- Si el canal de color es diferente (grayscale vs RGB normalizado) — los umbrales cambian
