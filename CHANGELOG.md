# Changelog

Resumen breve de los cambios por version. Cada entrada corresponde al bump de
`CACHE_NAME` / `?v=` definido en `.github/instructions/cache-busting-obligatorio.instructions.md`.
Las versiones anteriores a 10.13 no se reconstruyeron retroactivamente; ver `git log` para historial completo.

## 10.75
- Agrega a `documentos/redondeo_y_tolerancia.md` una seccion de 4 casos
  completos con productos reales de la BD de test (BRIGHTON PINK 494 y
  GEORGE FORSTER 495): ruido absorbido por captura, delta exacto 0.5 y zona
  de divergencia, redondeo de la suma vs por botella, y caso mixto paq/det.
- Corrige dos errores de ese doc: afirmaba que HALF_UP se replica con
  `Math.round` (falso: `Math.round(-0.5)` da `-0` y rompe faltantes en el
  punto medio) y que cada pesaje se redondea antes de sumarse (falso: se
  redondea el total una sola vez). Refresca referencias de linea de la
  seccion 1.

## 10.74
- Agrega pendiente en TODO.md para evaluar si se reconstruye el hueco del
  propio CHANGELOG (10.52 a 10.70, 19 versiones sin entrada) a partir del
  `git log`, con los argumentos a favor y en contra y el comando para listar
  los commits involucrados.

## 10.73
- Marca `documentos/decision_avance_delta_tolerancia_ajustes_pwa.md` como
  documento historico con propuesta descartada: seguia recomendando la grilla
  0.25 que v10.39 rechazo, sin ningun aviso. Se conserva el cuerpo como
  registro del analisis.
- Corrige `CLAUDE.md`: afirmaba que no existe suite de tests ni pytest, pero
  hay 24 tests unitarios en `tests/` con `pytest.ini` y `requirements-dev.txt`.
  Aclara que cubren solo logica pura (sin BD ni endpoints) y agrega el comando.

## 10.72
- Corrige la redaccion sobre la igualacion de `bar_inventario` en
  `documentos/redondeo_y_tolerancia.md` y `CLAUDE.md`: la doc afirmaba que se
  iguala "siempre" al fisico, pero el loop itera la lista ya filtrada por
  tolerancia, asi que un producto tolerado nunca se escribe (hoy no-op).
  Refresca ademas las referencias de linea, desactualizadas. Sin cambios de
  codigo. Nuevo pendiente en TODO.md para hacer la igualacion incondicional.

## 10.71
- Actualiza `CLAUDE.md`: la descripcion de la tolerancia operativa seguia
  diciendo "dead-band per product category" (esquema previo a 10.39). Ahora
  documenta la banda plana de 0.5 oz, donde se aplica, y que la columna
  `app_producto_pesaje_config_api.tolerancia_oz` es vestigial.

## 10.51
- Reordena el encabezado de la tarjeta de producto (PALOTEO 1 y 2): categoria,
  ID y codigo pasan a mostrarse en una fila arriba del nombre del producto
  (antes iban debajo). De paso, "Cod:" pasa a "COD:" para alinear con el
  encabezado de la tabla de REPORTE.

## 10.50
- Boton "+ Botella" (PALOTEO 1 y 2): quita el icono `add_circle` duplicado
  que mostraba un segundo signo "+" junto al de texto; ahora solo queda un
  simbolo "+" junto a la palabra Botella.
- Contador de navegacion de PALOTEO 2 (entre PREV y SIGT): quita la palabra
  "Prod" y agrega el porcentaje de avance junto a la posicion actual,
  pasando de "PROD X/Y" a "X/Y (Z%)".

## 10.49
- Unifica el boton de registro de PALOTEO 1/2/3: mismo texto ("Registrar
  Paloteo"), mismo icono (`done_all`) y mismo estilo. PALOTEO 1 tenia texto
  ("Enviar Paloteo 1") e icono (`send`) distintos, y ademas un set de clases
  propio en JS (`_habilitarBtnEnvio`/`_deshabilitarBtnEnvio`) que le
  cambiaba el color de texto al habilitarse/deshabilitarse — los otros dos
  botones solo alternan `disabled` y dependen de las clases base
  (`disabled:opacity-50`/`disabled:cursor-not-allowed`), por eso se veian
  distintos. Se quito ese tratamiento especial de PALOTEO 1 para que los
  tres se comporten igual.
- Corrige tambien un `cursor-not-allowed` incondicional en el boton de
  PALOTEO 1 (mostraba cursor de "no permitido" incluso habilitado).
- Mueve el boton de PALOTEO 2 (captura 1x1) de arriba de la tarjeta a abajo,
  para que quede consistente con PALOTEO 1 y 3 (boton siempre al final del
  contenido, no antes).

## 10.48
- Migra `config.py` del estilo `class Config` (Pydantic v1, deprecado) a
  `model_config = SettingsConfigDict(...)` (Pydantic v2). Sin cambio de
  comportamiento; verificado con el test suite y una carga real de `.env`.

## 10.47
- Rediseña PESAJE: grid responsivo de tarjetas resumen (categoria, nombre,
  ID/codigo, medida+unidad, cantidad_detalle+unidad_detalle, badge de
  comanda y cantidad de modelos si tiene mas de uno) en vez de una lista de
  una sola columna con edicion inline. Al hacer click se abre un modal
  (mismo patron que CONVERSOR) con el contenido que antes vivia en la
  tarjeta: peso bruto/tara/g-oz/barcode por perfil, Guardar/Eliminar y
  Agregar modelo.
- Nueva pestaña INCOMPLETOS junto a PESABLES/NO PESABLES: pide el mismo
  `GET /api/pesaje/config?pesable=1` que PESABLES y separa en cliente los
  productos con algun perfil sin `peso_bruto`/`tara`. Al completarse el
  ultimo perfil incompleto, el producto pasa solo a PESABLES en el
  siguiente refresco (si el modal esta abierto, se refresca en el lugar en
  vez de cerrarse).
- Backend: `GET /api/pesaje/config` suma, via `LEFT JOIN` a
  `vw_alm_producto_con_nombres`, los campos `medida`, `nombre_unidad_medida`,
  `nombre_unidad_medida_detalle` y `nombre_ind_permite_comandar` (no
  `nombre_barra`: el peso/tara/codigo de barras no depende de la barra donde
  este el producto).
- Corrige 2 bugs de z-index expuestos por el modal nuevo: `#resultado-dialog`
  y `#modelo-botella-dialog` quedaban detras de `#pesaje-modal` (mismo
  `z-50` o menor), bloqueando sus botones cuando se abrian desde adentro.

## 10.46
- Los productos agregados sin movimiento (individual o via "Agregar todos")
  ahora se distinguen visualmente en PALOTEO 1, 2 y 3: borde/glow
  (`card-agregado-manual`) + badge "Sin movimiento" junto a ID/Codigo. Antes
  la marca se aplicaba una sola vez al agregar el producto y se perdia en
  cualquier re-render (PALOTEO 3 se reconstruye en cada tecla escrita en
  PALOTEO 1 via `refrescarPaloteo3DesdeInventario()`; PALOTEO 2 reconstruye
  la tarjeta en cada navegacion via `renderTarjetaCaptura()`). Ahora se
  decide en runtime dentro de `crearTarjetaProductoElement`/
  `crearFilaPaloteo3` a partir de `producto._agregadoManual`, asi sobrevive
  a cualquier re-render.
- El boton "x" para quitar un producto agregado sin movimiento, que ya
  existia en PALOTEO 1 y 3, ahora tambien esta disponible en PALOTEO 2
  (variante inline, para no chocar con el header Prev/Sigt de la captura).

## 10.45
- Paloteo completo: agrega la posibilidad de recontar todo el catalogo de la
  barra (no solo lo que tuvo movimiento) sin cargar producto por producto.
  Boton "Ver catalogo completo" trae de una vez el catalogo entero, y
  "Agregar todos (N)" vuelca en bloque el listado (completo o de una
  busqueda puntual, ej. una categoria) al conteo activo, con confirmacion
  previa por el volumen que puede implicar.
- Backend: `GET /api/inventario/catalogo/buscar` admite busqueda vacia
  (antes exigia minimo 2 caracteres) y un parametro `limite` (1-500, antes
  fijo en 15), para poder traer el catalogo completo en una sola llamada.

## 10.44
- Rediseña el PDF de AJUSTES (Paloteo 3) para consistencia visual y mas
  contexto por producto:
  - Tipografia: se embebe Space Grotesk (Regular/Bold, `static/fonts/`,
    misma fuente que `--font-family` en `cellar-sync-tokens.css`) en vez de
    la Helvetica por defecto de fpdf2, que rompia la identidad visual de la
    PWA (notorio en las columnas `ID`/`COD`).
  - Columnas nuevas `PAQ POS` / `PAQ BAR` / `DET POS` / `DET BAR` (cantidad
    de paquetes y onzas segun el POS vs. lo contado en barra), tomadas de la
    misma fuente que las franjas SISTEMA (IDEAL) / BARRA (REAL) de las
    tarjetas de Paloteo 1/2 (`card.dataset.paqsist/detsist` + el real
    capturado). Se agregan a los 3 tipos de reporte (general/ingreso/salida).
  - El PDF pasa de A4 vertical a A4 horizontal: con 10 columnas, el ancho
    util vertical (170mm) dejaba el nombre del producto ilegible; horizontal
    da 257mm utiles.

## 10.43
- Corrige PDF de AJUSTES (Paloteo 3): el reporte de la pestaña `SALIDA (-)`
  podia mostrar columnas `DIF REAL`/`DIF OP` en onzas que en realidad
  pertenecian al sentido contrario (ingreso), porque `aplicarEstadoReporte`
  anulaba `difUnidades`/`difOnzas` segun el signo al filtrar por pestaña pero
  no anulaba `difOnzasExactas`, y `exportarReportePaloteo3Pdf` preferia ese
  valor sin anular al armar el PDF. Ahora `difOnzasExactas` se anula en el
  mismo filtro, asi cada PDF (`INGRESO (+)` / `SALIDA (-)`) muestra unicamente
  los valores de onzas que corresponden a su propio sentido, igual que ya
  ocurria con `DIF. PAQ.`.

## 10.42
- Corrige AJUSTES (Paloteo 3): la banda de tolerancia se aplicaba sobre el
  peso crudo sin redondear en vez del total ya redondeado a grilla POS
  (`bar_detalle_fisico.cantidad_detalle`), lo que podia mostrar `DIF OP: 0`
  en pantalla/PDF para un producto que el backend si iba a ajustar al
  aplicar (detectado en prueba end-to-end: CAMPARI 750ML con delta crudo
  +0.39 oz vs delta operativo real +0.5 oz). Afectaba el chip `DIF DET` de
  Paloteo 1/2, el grid de AJUSTES y la columna `DIF OP` del PDF; el boton
  "Aplicar Ajustes" (que ya usaba el preview del backend) no estaba afectado.

## 10.41
- Grid on-screen de AJUSTES: alinea las columnas `DIF. PAQ.` y `DIF. DET.`
  (cabecera y valores) a la derecha, para que se lean como numeros en vez de
  texto. El grid on-screen sigue mostrando solo los datos que van al POS (sin
  la diferencia real sin redondear, que quedo reservada al PDF en v10.40).

## 10.40
- PDF de "Reporte de Diferencias" (AJUSTES): repone la columna con la
  diferencia real sin redondear (`DIF REAL`), retirada en v10.29, entre
  `DIF. PAQ.` y la columna renombrada `DIF DET` -> `DIF OP` (delta operativo,
  redondeado a 0.5 oz). Cabecera `CODIGO` -> `COD` y columnas `ID`/`COD`
  angostadas (max. 4 digitos / 5 caracteres) para dar espacio a la nueva
  columna sin agrandar el ancho total de la tabla.

## 10.39
- Unifica tolerancia operativa a 0.5 oz para todos los productos pesables
  (antes: 0.5 oz para VINOS/MEZCLADORES, 0.25 oz para el resto). Elimina la
  distincion por categoria en `_obtener_tolerancia_operativa_oz`. Decision
  respaldada por verificacion en BD: todos los ideales pesables en
  `bar_inventario` son multiplos de 0.5, por lo que el delta nunca introduce
  distorsion al cuantizarse a la misma grilla.

## 10.38
- Permite deshacer un producto agregado por error (sin movimiento esta
  operativa): boton "x" en su tarjeta/fila, con dialogo de confirmacion. Si
  el paloteo ya se habia guardado, da de baja la fila correspondiente en
  `bar_detalle_fisico` via el nuevo endpoint
  `DELETE /api/inventario/paloteo/{id}/producto/{id}` (no toca el log de
  auditoria `app_paloteo_registro_crudo`). Oculto en modo solo-lectura.

## 10.37
- Nueva funcionalidad: permite agregar al conteo activo un producto que no tuvo
  movimiento esta operativa (ej. una botella mal contada como faltante en un
  cierre previo). Se busca en la misma barra de busqueda unica de PALOTEO 1/2/3;
  si no hay coincidencias entre los productos cargados, se ofrece un resultado
  del catalogo completo (`GET /api/inventario/catalogo/buscar`) para agregarlo
  con un toque. El producto agregado se persiste en el autosave local y se
  distingue visualmente con un borde/realce propio en su tarjeta.

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
