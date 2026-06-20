# Changelog

Resumen breve de los cambios por version. Cada entrada corresponde al bump de
`CACHE_NAME` / `?v=` definido en `.github/instructions/cache-busting-obligatorio.instructions.md`.
Las versiones anteriores a 10.13 no se reconstruyeron retroactivamente; ver `git log` para historial completo.

## 10.20
- Feature: asistencia de foco en PALOTEO 1 (igual que PALOTEO 2) — auto-focus
  y seleccion del valor en el primer campo al cargar la lista, y navegacion
  por Enter entre campos (`cerradas -> pesos -> ...`) que avanza a la
  siguiente tarjeta de producto al terminar.

## 10.19
- Fix: en PALOTEO 2 (modo captura), en desktop el Enter saltaba siempre al
  siguiente producto en vez de respetar la navegacion campo-a-campo
  (cerradas -> peso -> ... -> siguiente). Se elimino el listener duplicado
  que causaba el conflicto.

## 10.18
- Fix: consistencia funcional de PALOTEO 3 (multi-botella, multi-perfil y
  step de ajuste).

## 10.17
- Modulo Pesaje: gramos/oz visible, indicador de perfiles incompletos,
  exclusion de categorias no pesables y FAB de scroll-top.

## 10.15
- Mejoras en la adicion de modelos de botella (modulo Pesaje).

## 10.13
- Incluir productos no pesables en el reporte de paloteo.
