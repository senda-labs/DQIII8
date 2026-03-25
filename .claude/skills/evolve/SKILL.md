---
name: evolve
description: Agrupa instincts consolidados en skills accionables y las registra en skills-registry/custom/evolved/. Las skills quedan PENDIENTE_REVISION hasta que el usuario las apruebe.
command: /evolve
allowed-tools: [Bash]
user-invocable: true
---

# /evolve — Convertir Instincts en Skills

Lee instincts con alta confianza o alta frecuencia de aplicacion de `dqiii8.db`,
los agrupa por keyword raiz, y genera skill drafts para clusters con 3+ instincts.

## Uso

```
/evolve
/evolve --min-confidence 0.5
/evolve --min-applied 10
/evolve --min-cluster 2
/evolve --dry-run
```

## Que hace

1. Lee instincts con `confidence >= 0.7 OR times_applied >= 5` (ajustable)
2. Agrupa por primer segmento del keyword (`ssim-hacking` → raiz `ssim`)
3. Para clusters con 3+ instincts: escribe `skills-registry/custom/evolved/[raiz].md`
4. Registra en `skills-registry/INDEX.md` con status `PENDIENTE_REVISION`

## Implementacion

```bash
python3 /root/dqiii8/bin/evolve.py "$@"
```

<!-- TODO: bin/evolve.py does not exist — needs creation -->

## Flujo de aprobacion

1. Revisar el draft en `skills-registry/custom/evolved/[raiz].md`
2. Editar las secciones "Reglas consolidadas" y "Anti-patrones"
3. Cambiar status en `INDEX.md` a `✅ APROBADA`
4. Mover de `custom/evolved/` a `custom/[nombre]/SKILL.md`

## Notas DQIII8

- Threshold por defecto: `confidence >= 0.7 OR times_applied >= 5`
- Las skills en `custom/evolved/` NO se cargan en sesion — requieren aprobacion manual
- El comando es idempotente: re-ejecutar no sobreescribe skills existentes en INDEX
- Las skills evolucionadas son mas precisas que las importadas de ECC/ruflo
  porque provienen de comportamiento real del sistema (5.687+ acciones acumuladas)
- Complementa P3c (Intelligence Loop): P3c ajusta confidence, /evolve la convierte en skill
