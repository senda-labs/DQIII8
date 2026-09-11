# Arquitectura — {{TITULO_PROYECTO}}

Por qué esta estructura de carpetas, no solo qué hay en cada una — así un modelo de IA (o una
persona nueva) entiende dónde escribir sin tener que preguntarlo cada vez.

## Carpetas

| Carpeta | Para qué sirve | Qué NO va aquí |
|---|---|---|
| `01-notas/` | Notas de trabajo, ideas sueltas, borradores. Un archivo `.md` por tema, nombre descriptivo. | Entregables finales |
| `02-investigacion/` | Fuentes, datos brutos, research de apoyo (enlaces, capturas, exports). | Conclusiones — esas van en notas o entregables |
| `03-entregables/` | Versión final de lo que se envía al cliente. Solo lo que ya está listo. | Borradores a medio hacer |
| `docs/` | Documentación del propio proyecto (esta carpeta). | Contenido de cliente |

## Convenciones

- Cada nota nueva enlaza hacia atrás a `[[PROJECT]]` o al documento del que nace — así Obsidian
  construye el grafo solo, sin mantenimiento manual.
- Nombres de archivo descriptivos y en minúsculas con guiones (`analisis-mercado-mexico.md`), no
  `notas1.md`/`nuevo.md`.
- Una decisión importante (cambio de alcance, cliente pide algo nuevo) se anota en
  `PROJECT.md` → Historial breve, con fecha. Así queda trazado sin depender de la memoria.

## Cuándo crear una carpeta nueva

Solo si vas a meter 3+ archivos del mismo tipo. Un archivo suelto va directo en `01-notas/`.
