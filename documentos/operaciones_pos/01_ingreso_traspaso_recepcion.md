# Ingreso de proveedor → traspaso a barra → recepción en barra

Estado: **confirmado en vivo** en `test_pos` (2026-10-10, operativa 169) e
implementado en la API en v12.50 (`POST /api/operaciones/ingreso-barra`).
Contexto general y método: `00_contexto_y_plan.md`.

Fuentes leídas (descompiladas, `AnalisisPos/`, no versionado):

| Paso | Bean de pantalla (`multi-web`) | EJB (`multi-ejb`) |
|---|---|---|
| Ingreso | `almacen/RecepcionProdBean` | `proceso/RecepcionProdEjbBean` (`guardarRecepcionDetalle`, `guardarProcesoIngresoAlm`) |
| Traspaso | `almacen/SalidaProdInventarioBean` | `almacen/AdmSalidaProductosEJBBean` (`guardarSalidaDetalle`, `verificarExistenciasProducto`, `procesarSalidaInventario`) |
| Recepción | `barra/AdmListIngresoBean` (no `SolicitudProdBarraEjbBean`, como se suponía) | `AdmSalidaProductosEJBBean.procesarEntradaABarra` / `procesarRechazoEnvio` + `admin/OperativaEjbBean.copyBarInventToInevetOperacion` |

**Alcance:** casa matriz, Beer Garden, `test_pos` y el entorno local corren
exactamente el mismo `.ear` del POS (confirmado 2026-10-12), así que lo
confirmado en `test_pos` (réplica de Beer Garden) vale también para casa
matriz. Comparación de datos de las dos réplicas (últimos 90 días, 2026-10-12):
sin filas duplicadas en `alm_inventario`, `bar_inventario` ni
`bar_inventario_operacion`; ninguna compra con un producto repetido; ningún
producto comprado sin fila en `alm_inventario`; un solo producto sin medidas en
casa matriz, sin compras recientes. Casa matriz traspasa solo a BARRA 1 y usa
FACTURA y OTRO; su almacén principal es el 1 (ALMACEN BACK, TRASPASOS es el 4).

Confirmación: 4 escenarios, 18 pasos con `diff_bd.py` (foto de la BD antes y
después de cada acción en el POS; bitácora en
`AnalisisPos/herramientas_sesion_20261009/diff_bd_bitacora.md`):
insumos en unidades con traspaso parcial (ingreso 837 / salida 738),
comandables con producto sin fila en barra (838 / 739), salida abierta desde el
listado y rechazada (740), producto abierto con costo 0 (839 / 741).

## 1. Qué escribe el POS, paso a paso

Los tres pasos exigen **operativa en 22 (EN PROCESO)**, no la 24 que usa el
paloteo (`ParameterTableType.ESTADO_OPERACION_EN_PROCESO`). El rechazo no
revisa la operativa.

### 1.1 Registrar el ingreso (cada vez que se guarda una línea)

- `alm_ingreso` (se crea con la primera línea): `fecha` = hoy, `ind_tipo_ingreso`
  = 80 (proveedor), `ind_estado_ingreso` = `'0'`, `ind_tipo_documento` 38
  FACTURA / 39 RECIBO / 40 OTRO, `numero_documento` (en la práctica a menudo
  `'0'`), `id_proveedor`, `id_almacen`, `observaciones`, `recepcionado_por` =
  nombre completo ("PATERNO MATERNO, NOMBRES"), `usuario_reg` = login,
  `fecha_reg` = hoy, `estado` = HAB. `id_operacion`, `id_barra` e
  `ind_tipo_pago` quedan NULL. **`fecha_mod` = hoy solo si hay más de una
  línea** (guardar la segunda línea vuelve a guardar la cabecera).
- `alm_detalle_ingreso`: `cantidad`, `precio_costo` = precio **unitario** tal
  como se carga, `precio_costo_real` = `p − p·13/100` con factura, `p / 0.92`
  con recibo u otro (`Constantes.IVA`, `IVA_ASUMIDO`), `ind_paq_detalle`
  `'1'` unidad / `'0'` detalle (onzas), `usuario_reg`, `fecha_reg`, HAB.
- `alm_producto`: `merge` del producto → en la práctica solo `usuario_reg` y
  `fecha_mod` (el formulario no deja editar un producto existente). Dispara
  `trg_alm_producto_after_update`. **La API no lo replica** (decisión
  2026-10-10: es solo auditoría).
- No mueve stock ni WAC.

### 1.2 Procesar el ingreso

- `alm_inventario` (por producto y almacén, HAB): suma `cantidad_paq`; para
  líneas en detalle suma onzas y convierte en botellas cerradas lo que pase del
  contenido (`cantidad_detalle` del producto). Actualiza `usuario_reg` y
  `fecha_mod`. Si no existe la fila, la crea.
- `alm_ingreso`: `ind_estado_ingreso` = `'1'`, `id_operacion` = operativa en 22.
- **El trigger del WAC corre aquí** (ver sección 3).
- No escribe en `ope_novedades`.

### 1.3 Registrar el traspaso

- `alm_salida_inventario`: `ind_tipo_movimiento` 83, `ind_tipo_salida` 34
  (barra), `ind_estado_salida` 16, `fecha_salida` = hoy, `responsable` =
  nombre completo, `observaciones_salida`, `id_almacen`, `id_barra`,
  `usuario_reg`, `fecha_reg`, HAB; `fecha_mod` = hoy solo con más de una línea.
  `correlativo`, `id_proveedor`, `id_area`, `id_operacion` quedan NULL
  (`correlativo` no se llena nunca: 0 de 741 filas).
- `alm_detalle_salida_inv`: `cantidad`, `ind_paq_detalle`, `usuario_reg`,
  `fecha_reg`, HAB.
- Validaciones de pantalla: cantidad con `intValue() > 0` (mínimo 1), el
  producto debe tener `medida` y `cantidad_detalle` > 0, y una línea en detalle
  no puede pasar del contenido de una botella.

### 1.4 Procesar el traspaso

- `alm_inventario`: resta (solo la cantidad; no toca `usuario_reg` ni
  `fecha_mod`). En detalle, si no alcanzan las onzas sueltas y hay botellas
  cerradas, **abre una**: `det + contenido − pedido`, `paq − 1`.
- `alm_salida_inventario`: `ind_estado_salida` 20, `id_operacion`.
- `ope_novedades` (`fecha`, `fecha_reg` = ahora; `usuario`, `usuario_reg`,
  `id_operacion`, HAB):
  `Se registró una salida del Almacen: {nombre}, con el correlativo NRO  {id salida} en fecha: {fecha de la OPERATIVA dd/MM/yyyy}`
  (doble espacio después de "NRO"; la fecha es la de la operativa, no la de
  hoy). El POS escribe `Almacen: null` cuando la salida se procesa desde la
  misma pantalla en que se registró (el almacén solo tiene cargado su id), y el
  nombre real cuando se abre desde el listado con el lápiz (639 vs 66 filas en
  `test_pos`). **La API escribe siempre el nombre real.**
- La barra todavía no suma (unidades en tránsito).

### 1.5 Aceptar en barra

- `alm_salida_inventario`: `ind_estado_salida` 21, `fecha_recepcion` = hoy,
  `responsable_recepcion` = nombre completo, `observaciones_recepcion` (el
  diálogo propone "OK"), y **pisa** `usuario_reg` e `id_operacion` con los de
  quien recibe.
- `bar_inventario` (producto, barra, HAB): suma y normaliza igual que el
  almacén; `usuario_reg`, `fecha_mod` (DATETIME). Si no existe la fila la crea:
  `cantidad_paq`, `cantidad_detalle` = 0, `fecha_reg` = hoy, sin `fecha_mod`.
- `bar_inventario_operacion` (barra, operativa, producto, HAB): suma en
  `cantidad_*` (no toca `inicial_*`), `usuario_reg` = quien recibe,
  `fecha_mod` = hoy. Si no existe la crea con solo `cantidad_paq` (o
  `cantidad_detalle`), `inicial_*` y `fecha_mod` NULL, `usuario_reg` y `estado`
  **de la operativa**. `main.py` no lee esta tabla.
- No escribe en `ope_novedades`. En el POS son dos transacciones separadas
  (`procesarEntradaABarra` y `copyBarInventToInevetOperacion`); si no hay
  operativa en 22, igual suma en la barra ("auxilio" en el log).

### 1.6 Rechazar en barra

`ind_estado_salida` 35 + los mismos campos de recepción; devuelve al almacén
(suma y normaliza, `usuario_reg`, `fecha_mod`); no toca la barra ni
`ope_novedades`.

## 2. Cálculos con onzas (confirmados con el producto abierto)

`alm_inventario`, `bar_inventario` y `bar_inventario_operacion` convierten en
botella cerrada lo que pasa del contenido (`cantidad_detalle` del producto):
30 oz de DON LUCHO ORO (25.5 oz) → 1 + 4.5; recibir 10 oz con 1 + 23.5 en barra
→ 2 + 8. El POS usa `float`: con múltiplos de 0.5 no deja restos, con otros
valores podría; si la API maneja onzas algún día, calcular con `Decimal` y
redondear a 2 decimales. **La v1 de la API no maneja onzas.**

## 3. WAC (motor V9.44, `trg_wac_alm_ingreso_after_update`)

- Corre cuando `alm_ingreso` pasa de `'0'` a `'1'`; solo líneas `'1'`, tipo 80,
  `precio_costo > 0`, HAB. El trigger de inserción (`trg_wac_after_insert_detalle`)
  solo actúa si la línea entra a un ingreso ya procesado.
- Stock previo = `cantidad_paq + cantidad_detalle / contenido` de
  `alm_inventario` **del almacén**, leído en el momento del UPDATE (la nota
  técnica V9.44 dice "almacén y barra": no es así).
- Escribe `cache_wac_producto` y `cache_wac_historial` (InnoDB: una vista previa
  con ROLLBACK no deja rastro).
- **Contrato (desde la corrección del 2026-10-12):** cuando el ingreso pasa a
  `'1'`, `alm_inventario` **ya incluye la compra** (el POS y la API suman el
  stock antes de cambiar el estado) y el trigger descuenta lo que el mismo
  ingreso sumó para el producto. Verificado en `test_pos` con la vista previa
  de la API: BEEFEATER 1LT, stock 4, WAC 217.0588, compra 2 a Bs 210 →
  **214.7059** (con el error anterior habría dado 215.2941).
- **Error original (detectado 2026-10-10, corregido por el equipo del motor el
  2026-10-12 en `test_pos`):** el POS actualiza `alm_inventario` antes que el
  estado del ingreso y el trigger contaba dos veces las unidades compradas:

  | Producto | WAC antes | Compra | Stock previo real | WAC correcto | WAC que quedó |
  |---|---|---|---|---|---|
  | COCA COLA 3LT | 16.4818 | 6 a 19 | 3.335 | 18.1004 | 17.4671 |
  | HAVANA 7A 700ML | 169.2853 | 2 a 135 | 0 | 135.0000 | 152.1427 |
  | RED BULL LATA | 17.2157 | 4 a 16 | 0 | 16.0000 | 16.6079 |

  **La API escribe en el mismo orden que el POS** (stock primero, estado
  después), así que deja siempre el mismo WAC que el POS; con el trigger
  corregido, el correcto. Notas al equipo del motor:
  `02_nota_equipo_motor_wac.md` y `03_nota_equipo_motor_wac_seguimiento.md`.
- **Motor v9.45 (2026-10-12), casos borde resueltos** (respuesta del equipo del
  motor en `04_respuesta_seguimiento_motor_wac.md`). Verificado en la BD local y
  en `test_pos` con productos propios, dentro de transacciones revertidas:
  1. Dos líneas del mismo producto en un ingreso: el cursor recorre las líneas
     por `di.id` y cada una descuenta solo las líneas pendientes
     (`d2.id >= v_det_id`): BEEFEATER 2 a 200 + 2 a 230 → **216.0294** (con
     v9.44 daba 217.5817). La API igual no admite productos repetidos.
  2. Producto sin fila en `alm_inventario`: la lectura del stock es una
     subconsulta escalar (`COALESCE((SELECT …), 0)`) en los dos triggers, así
     que el `NOT FOUND` ya no corta el cursor y las líneas siguientes se calculan.
  3. Anulación: el cursor usa `DISTINCT di.id_producto` y restaura
     `wac_anterior` una vez por producto; sin historial, el precio de la última
     compra anterior.
  4. COCA COLA 3LT (stock 3 + 34 oz, botella de 101.5 oz, WAC 16.4818, 6 a
     Bs 19): el trigger v9.45 da **18.1004**, el valor exacto. El 18.0995 de la
     tabla del equipo del motor viene de su banco de pruebas, no del trigger.
- **Instalada en los cuatro entornos** (verificado 2026-10-12 por huella de los
  triggers): local (casa matriz), `test_pos`, producción Beer Garden y producción
  casa matriz. Huellas `MD5(REPLACE(action_statement, CHAR(13), ''))`:
  `trg_wac_after_insert_detalle` = `3426aabe81f95690264f021e409e10eb`,
  `trg_wac_alm_ingreso_after_update` = `90e67235efa3c4948f4f7a6450a8c28a`.
- Anular un ingreso (`'2'` o `DES`) restaura el WAC pero **no descuenta stock**
  (ni el trigger ni `cancelarRecepcion`).
- El 2026-10-11 07:35 el WAC de COCA COLA 3LT, HAVANA 7A 700ML y RED BULL LATA
  se reescribió en `test_pos`: lo causó el Paso 2 del instalador del motor
  (`ON DUPLICATE KEY UPDATE wac_actual = VALUES(wac_actual)`, promedio plano del
  historial). En la v9.45 solo inicializa productos sin WAC
  (`IF(wac_actual > 0, wac_actual, VALUES(wac_actual))`).

## 4. Implementación en la API (v12.50)

`POST /api/operaciones/ingreso-barra` (y `/preview`, que hace lo mismo y
ROLLBACK), solo administrador. Una sola transacción, en este orden:

1. `ope_operacion` única en 22 (`FOR UPDATE`); verificar que exista
   `trg_wac_alm_ingreso_after_update`.
2. `alm_ingreso` en `'0'` + `alm_detalle_ingreso` (unidades, `'1'`).
3. `alm_inventario` += cantidad (o crear la fila).
4. `alm_ingreso` → `'1'` + operativa (corre el trigger del WAC).
5. Si hay líneas a barra: `alm_salida_inventario` ya con los valores finales
   (21 y campos de recepción), `alm_detalle_salida_inv`, `alm_inventario` −=,
   `ope_novedades`, `bar_inventario` +=, `bar_inventario_operacion` += (o crear
   las filas como el POS).
6. `app_operacion_pos_control` (auditoría + clave contra doble envío).

Decisiones (2026-10-10): no tocar `alm_producto`; nombre real del almacén en
`ope_novedades`; traspaso parcial por línea (lo no traspasado queda en el
almacén); una barra por operación; sin onzas, sin alta de productos, sin
ingresos por ajuste (81).

## 5. Prueba diferencial POS vs PWA (`test_pos`, 2026-10-11)

La misma compra hecha primero en el POS (ingreso 840 / salida 742) y después en
la PWA (ingreso 842 / salida 744), con el usuario BERNARDO, comparada con
`diff_bd.py` (pasos "DIF-POS" y "DIF-PWA" de la bitácora): FACTURA `DIF-1`,
proveedor VARIOS, ALMACEN GARDEN → BARRA 1; RED BULL LATA 2 a Bs 16 (2 a la
barra), SENSS ACHACHAIRU 2 a Bs 10 (1 a la barra, traspaso parcial).

**Resultado: mismas filas salvo ids y horas.** Idénticos `alm_ingreso` (todas
las columnas, incluidos estado `'1'`, operativa, `recepcionado_por` y
`fecha_mod`), `alm_detalle_ingreso` (`precio_costo_real` 13.92 y 8.7),
`alm_salida_inventario` (21, recepción, `fecha_mod`, sin correlativo),
`alm_detalle_salida_inv`, los movimientos de `alm_inventario`, `bar_inventario` y
`bar_inventario_operacion`, y el WAC: RED BULL 16.304 → 16.152, el mismo valor
que había anunciado la vista previa (con el doble conteo del trigger de ese
momento, corregido después; sección 3).

Diferencias, todas esperadas:

1. `ope_novedades`: el POS escribió "Almacen: null", la PWA "Almacen: ALMACEN GARDEN".
2. `alm_producto`: el POS actualizó `fecha_mod` de los dos productos; la PWA no lo toca.
3. `app_operacion_pos_control`: fila de control de la PWA (lo enviado y el resultado).
4. Huecos de numeración: el "Revisar" (vista previa con ROLLBACK) consumió un id
   en cada tabla (ingreso 841, salida 743, novedad 8919...). En el POS esos ids
   son el número visible del documento.

Hallazgo aparte, previo a este módulo: la API escribe `seg_acceso.fecha` (login)
en UTC y el POS en hora local (04:47 vs 00:40). Lo mismo pasa con las fechas que
escriben la captura del paloteo y los ajustes. Ver TODO.
