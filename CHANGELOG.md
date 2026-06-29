# Changelog

Resumen breve de los cambios por version. Cada entrada corresponde al bump de
`CACHE_NAME` / `?v=` definido en `.github/instructions/cache-busting-obligatorio.instructions.md`.
Las versiones anteriores a 10.13 no se reconstruyeron retroactivamente; ver `git log` para historial completo.

## 10.36
- Backend: `/api/inventario/ajustes/aplicar` ahora verifica, dentro de la misma
  transaccion y antes del commit, que cada fila de `bar_inventario` actualizada
  quede exactamente igual al inventario fisico contado (relectura desde BD, no
  desde el objeto en memoria). Si no coincide, hace rollback y devuelve 500 en
  vez de comitear un ajuste inconsistente. La respuesta ahora incluye
  `igualacion_verificada`.

## 10.35
- Cambio funcional: la barra de busqueda unica (10.34) deja de ser una fila fija
  debajo del navbar y pasa a vivir dentro del navbar superior, colapsada por
  defecto detras de un icono de lupa (`btn-topbar-search-toggle`). Al expandirla,
  el logo horizontal se reemplaza por el isotipo compacto (`isotipo.png`) y se
  oculta el selector de barra, para dejar espacio al input en pantallas chicas.
  El icono solo aparece en los modulos con busqueda (oculto en AJUSTES). El
  contador de PALOTEO 2 se acorta a "X/Y" / "Sin match" para caber en el espacio
  reducido del navbar.

## 10.34
- Feature: barra de busqueda unica en la parte superior, compartida por
  PALOTEO 1, PALOTEO 2, PALOTEO 3, PESAJE y CONVERSOR (oculta en AJUSTES).
  Se reconfigura placeholder + logica de filtrado segun el tab activo
  (`actualizarBarraBusqueda()` en `app.js`). Reemplaza los 3 buscadores
  independientes que ya existian en PALOTEO 3/PESAJE/CONVERSOR.
  - PALOTEO 1: ahora se puede filtrar la lista de productos por ID, codigo
    o nombre (antes no existia busqueda; habia que scrollear).
  - PALOTEO 2 (captura 1x1): al escribir, salta directo a la primera
    coincidencia; mientras hay busqueda activa, PREV/SIGT recorren solo
    las coincidencias (no todo el catalogo), con contador "Coincidencia
    X de Y" junto al buscador.
  - PALOTEO 3, PESAJE, CONVERSOR: mismo comportamiento de filtrado que
    tenian antes, ahora alimentado por el input compartido.

## 10.33
- Fix: en PALOTEO 2 (modo captura 1x1), navegar a la siguiente tarjeta mientras
  la operativa esta en modo solo lectura disparaba la validacion de "campos
  vacios se registraran como 0" (dialogo de confirmacion), aunque los inputs
  estan deshabilitados y no hay nada que registrar. `navegarCaptura` ahora
  salta esa validacion cuando `!operativaPermitePaloteo`, permitiendo navegar
  libremente entre tarjetas en modo lectura.

## 10.32
- Ajustes de forma en AJUSTES (PDF y pantalla):
  - El PDF de "Reporte de Diferencias" ya no muestra "Paloteo 3" como subtitulo;
    ahora dice "Stock Barra vs. Stock POS".
  - Las columnas "DIF PAQ"/"DIF DET (POS)" se renombran a "DIF. PAQ."/"DIF. DET."
    tanto en el PDF como en la tabla en pantalla.
  - En el PDF, las columnas ID y CODIGO usan un gris mas oscuro (90,90,90 en vez
    de 150,150,150) para mejorar legibilidad sobre fondo blanco.
  - El banner sticky de "Modo solo lectura..." (visible mientras la operativa no
    esta en INICIO CIERRE) se acorta a "Modo Lectura"; la explicacion completa
    ahora se muestra una sola vez, en un dialogo, al entrar a ese modo
    (`mostrarDialogoResultado` con un nuevo tipo `warning`).

## 10.31
- Hardening (sugerencia de gemini-code-assist en el PR): `aplicar_ajustes_inventario`
  ahora usa `.with_for_update()` al leer la fila de `bar_inventario` que va a mutar,
  para evitar perder una escritura concurrente sobre la misma fila mientras dura la
  transaccion. No cambia el manejo de la carrera entre dos aplicaciones simultaneas
  del mismo ajuste (eso ya lo cubre el `UNIQUE KEY` de `app_paloteo_ajuste_control`).

## 10.30
- Fix (hallazgo de code review sobre el modulo AJUSTES): `_calcular_diferencias_paloteo`
  no validaba que cada producto con diferencia tuviera exactamente una fila `HAB` en
  `bar_inventario` para esa barra; esa validacion solo existia dentro del loop de
  `aplicar_ajustes_inventario`, por lo que el preview podia mostrar un diff "limpio"
  y el admin recien se enteraba del problema de datos al confirmar el ajuste (500).
  Ahora `_validar_cardinalidad_bar_inventario` (compartida por preview y aplicar) lo
  valida con una sola query batched antes de construir la respuesta, distinguiendo
  productos sin registro de los que tienen filas duplicadas.
- Refactor: se extrajo `_resolver_inventario_fisico` (validacion de barra + busqueda
  de `InventarioFisicoPOS`) y se elimino el predicado "tiene diferencia" duplicado
  entre `previsualizar_consolidacion_ajustes` y `aplicar_ajustes_inventario`, que
  hasta ahora estaban copiados en ambos endpoints en vez de compartidos.

## 10.29
- Feature: el modulo "Reporte" se renombra a "Ajustes". Administradores ven
  ademas un boton "Aplicar Ajustes" que, cuando la operativa esta CERRADA
  (estado 23) y hay diferencias entre el paloteo y el ideal POS, llama a
  `POST /api/inventario/ajustes/aplicar` (creado en rama
  claude/adjustments-module-guide-xp8pt8) para generar los movimientos de
  ingreso/salida y actualizar el inventario vivo. Si ya se aplico antes,
  se muestra un badge en vez del boton. `/api/operacion/activa` ahora expone
  `estado_operacion` y el preview de consolidacion expone `ya_aplicado` para
  soportar este gating.
- Fix: el reporte PDF de diferencias ya no muestra la columna "DIF DET"
  (valor exacto pre-redondeo); solo "DIF PAQ" y "DIF DET POS".
- Fix (backend, commit `556f8cd`, sin bump propio de version): el calculo de
  diferencias paloteo-vs-POS (`_calcular_diferencias_paloteo`) tenia un join
  roto contra `inventario_excluido` (columna inexistente resuelta como
  subconsulta correlacionada, excluyendo el 100% de los productos siempre) y
  comparaba `vista_inventario_barra_con_filtro.id_barra` (en realidad
  `bar_inventario.id`) en vez de `nro_barra`. El endpoint de aplicar ajustes
  era inoperante hasta este fix.

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
