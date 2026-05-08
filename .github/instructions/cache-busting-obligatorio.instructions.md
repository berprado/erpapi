---
description: "Usar cuando se realice cualquier modificacion, edicion, correccion u optimizacion en este proyecto. Obliga a actualizar cache busting de PWA y frontend."
name: "Cache Busting Obligatorio"
applyTo: "**"
---
# Regla Obligatoria: Versionado de Cache

Cada vez que se modifique cualquier archivo del proyecto, se debe aplicar tambien este ajuste de versionado.

## Requisitos

- Incrementar la version de `CACHE_NAME` en `static/sw.js`.
- Invalidar la query string `?v=X` en `static/index.html`.

## Formato de version

Usar version semantica simplificada: `MAJOR.MINOR` (ej: `1.0`, `1.1`, `1.2` ... `1.9`, `2.0`).

- El **MINOR** sube en 0.1 por cada cambio incremental (fix, texto, logica).
- El **MAJOR** sube en 1.0 en cambios grandes de arquitectura, breaking changes o refactors importantes.

## Como aplicar la invalidacion

- Si ya existe `?v=X.Y` en los assets versionados de `static/index.html`, incrementar segun el impacto.
- Si no existe `?v=X.Y`, agregarla comenzando en `?v=1.0`.
- Mantener el mismo numero de version entre `CACHE_NAME` y los assets de `static/index.html` para evitar mezclas de cache.

## Checklist de cierre

- Cambio funcional completado.
- `CACHE_NAME` incrementado en `static/sw.js`.
- Query string `?v=X` actualizada en `static/index.html`.