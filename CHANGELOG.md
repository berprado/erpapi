# Changelog

Resumen breve de los cambios por version. Cada entrada corresponde al bump de
`CACHE_NAME` / `?v=` definido en `.github/instructions/cache-busting-obligatorio.instructions.md`.
Las versiones anteriores a 10.13 no se reconstruyeron retroactivamente; ver `git log` para historial completo.

## 10.26
- Cambio funcional: en CONVERSOR, la captura de botellas se mueve de una
  tarjeta inline al final del listado a una ventana modal (mismo estilo y
  mecanismo de cierre — overlay, boton X, Esc — que "Guia Operativa" y
  "Boletin"). Se quita el boton "Limpiar": cerrar la modal ya reinicia el
  estado, ya que el modulo no persiste nada.

## 10.25
- Feature: nuevo modulo CONVERSOR — calculadora de peso a onzas para
  cualquier producto pesable, disponible siempre sin importar el estado de
  la operativa ni la barra activa. Permite elegir el modelo de botella (si
  el producto tiene varios) y agregar multiples botellas para sumar su
  equivalente en onzas (exacto y redondeado POS). No registra nada en BD:
  el catalogo se carga una vez desde `GET /api/conversor/productos` y el
  calculo se hace en cliente.

## 10.24
- Cambio funcional: cuando la operativa no esta en INICIO CIERRE (estado 24),
  los modulos PALOTEO 1/2/3 ya no se bloquean. Permanecen accesibles en modo
  solo lectura para consultar el ultimo paloteo registrado (inputs y botones
  de ajuste deshabilitados), con un banner indicandolo. El guardado/edicion
  sigue exigiendo estado 24, validado tanto en frontend como en backend.

## 10.23
- Feature: asistencia de foco/progreso en PALOTEO 1 y PALOTEO 3 — barra
  "Capturados: X / Y (Z%)" que cuenta productos con unidades/peso ya
  ingresados, sin revelar el inventario ideal. Se actualiza en vivo al
  capturar y se mantiene sincronizada entre ambos modulos.

## 10.22
- Cambio funcional: en PALOTEO 3, los botones +/- de ajuste rapido (unidades
  y peso) ahora solo son visibles para usuarios administradores; el boton
  "+ Botella" sigue disponible para todos. Evita que se "redondee" un
  conteo sin escribir el valor real contado/pesado.

## 10.21
- Feature: asistencia de foco en PALOTEO 3 (igual que PALOTEO 1 y 2) —
  auto-focus y seleccion del primer campo al entrar al tab, y navegacion
  por Enter entre campos de una fila que avanza a la fila siguiente al
  terminar.

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
