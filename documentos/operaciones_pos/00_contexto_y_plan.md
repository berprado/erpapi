# Operaciones del POS desde la PWA: contexto y plan

Estado: **en análisis** (2026-10-09). Nada implementado todavía.

## Objetivo

Hacer desde la PWA, con una sola pantalla y sin la fricción del POS, las
operaciones de inventario más comunes. Las usará **solo el administrador**.

| Operación | Riesgo | Notas |
|---|---|---|
| Ingreso de proveedor → traspaso a barra → recepción en barra, en un paso | Medio | El de más valor. Hoy son ~14 pasos en el POS (registrar ingreso, procesarlo, registrar salida, procesarla, aceptarla en barra) |
| Aceptar o rechazar un traspaso | Bajo | Cambio de estado + stock de barra (aceptar) o de almacén (rechazar) |
| Marcar cortesía | Bajo | No mueve stock |
| Devolución barra → almacén | Medio | Crea un ingreso en el almacén ligado a la barra y modifica `alm_producto` (sin identificar qué columnas) |
| Anular comanda | Medio | Devolver el stock según la copia de receta guardada en la venta, nunca la receta actual |

Debe dejar **los mismos registros y estados que si el POS hubiera hecho cada
paso** (para que los reportes del POS no noten la diferencia), en **una sola
transacción** (mejor que el POS: no quedan traspasos a medio camino).

Precedente que ya funciona: aplicar ajustes del paloteo crea `bar_ajuste` /
`bar_salida_inventario`, iguala `bar_inventario` y marca los documentos en 20
desde la API (`main.py`, `aplicar_ajustes_inventario`); el POS los toma como
propios.

## Comportamiento del POS verificado en vivo

`test_pos`, operativa 163, 2026-10-01: se leyó la BD antes y después de cada
acción hecha en el POS (scripts en `AnalisisPos/herramientas_sesion_20261009/`).
Resumen también en la memoria del proyecto ("Como mueve stock el POS").

- **Comandas** (`bar_comanda`): 25 PENDIENTE al crear, no mueve stock.
  Imprimir = procesar: 26 y descuenta `bar_inventario` **solo en la barra de la
  comanda**. Sin stock suficiente el POS bloquea la impresión, la comanda queda
  en 25 y escribe en `ope_novedades`. Anular: 27 y **devuelve** el stock.
  `estado_impresion` llega tarde (null → 31 segundos después) y vuelve a null al
  anular. `bar_comanda_impresion` guarda una fila por comanda impresa y la
  conserva aunque se anule. Cortesía: se marca después de procesar
  (`tipo_salida` 50 → 51, `sub_total` 0, `cor_subtotal_anterior`, `cor_motivo`,
  `cor_registrado_por`, línea en `ope_novedades`); no mueve stock.
- **Copia de receta por venta**: cada venta de combo guarda la receta vigente en
  `bar_salida_combo_coctel` (cabecera) y `bar_detalle_sal_combo_coctel`
  (cantidad por ingrediente, `id_comanda`, `si_es_opcional`). Las recetas
  (`bar_detalle_combo_bar`) se editan en el lugar, sin historial. Ver TODO de
  `comandas_v9_detallada`.
- **Ingreso a almacén** (`alm_ingreso`): registrado = estado 0, no suma.
  Procesado = estado 1, suma a `alm_inventario` y toma la operativa abierta. El
  costo promedio lo calcula el trigger `trg_wac_after_insert_detalle` sobre
  `alm_detalle_ingreso` (corre igual si inserta la API).
- **Traspaso almacén → barra** (`alm_salida_inventario`, mov 83 / tipo 34): 16
  registrado (nada se mueve) → 20 procesado (sale del almacén, toma la
  operativa; la barra todavía no suma: unidades en tránsito) → 21 EN BARRA
  (recepción aceptada, la barra suma, `fecha_recepcion`) o 35 RECHAZADO (vuelve
  al almacén, la barra no se toca). `ope_novedades` registra la salida.
- **Devolución barra → almacén**: `bar_salida_inventario` **tipo 76
  MOVIMIENTO** (la misma tabla que las bajas por ajuste de esta API, tipo 77):
  16 registrada (no mueve) → 20 procesada (baja la barra, sube el almacén, crea
  un `alm_ingreso` con `id_barra`, la operativa y "Devoucion de Barra", y
  modifica `alm_producto`). `alm_devolucion` no se usa. Una devolución en 16 no
  siempre se pudo procesar (la 228 quedó trabada; la 229 sí).

## Fuentes del POS

`AnalisisPos/` (ignorada por git: código propietario descompilado, uso interno).
`estructura_pos_20260724_190906/` tiene el `.ear`, `03_multi-ejb` (EJB +
56 entidades JPA + `persistence.xml`) y `02_multi-web` (beans JSF + `.xhtml`).
Hoy solo `.class`; hace falta exportar los `.java` (ver abajo).

Clases a leer primero (implementaciones, no las interfaces `*Local`):

| Flujo | EJB (`03_multi-ejb/org/erp/...`) | Bean de pantalla (`02_multi-web`) |
|---|---|---|
| Ingreso de proveedor | `proceso/RecepcionProdEjbBean` | `almacen/RecepcionProdBean`, `almacen/AdmRecepProdBean` |
| Salida / traspaso a barra | `almacen/AdmSalidaProductosEJBBean` | `almacen/SalidaProdInventarioBean`, `almacen/AdmSalidaInventarioBean` |
| Recepción en barra | `barra/SolicitudProdBarraEjbBean` (a confirmar) | `barra/AdmSolicitudProdBean`, `barra/SolicitudProdBarraBean` |
| Devolución barra → almacén | `barra/SalidaInvetarioBarraEjbBean` | `barra/SalidaInventarioBarraBean`, `barra/SalidaProdInvBarraBean` |
| Comandas (procesar, anular, cortesía) | `mobile/ComandaEjbBean` | `barra/AdminComandaBean`, `mobile/ComandasBean` |
| Operativa / cierre | `admin/OperativaEjbBean`, `proceso/InventarioEjbBean` | `barra/OperativaBarraBean` |
| Entidades | `entities/*` + `META-INF/persistence.xml` | |

## Método de trabajo

1. **Leer el código** del flujo: qué tablas escribe, en qué orden, validaciones,
   estados, correlativos, textos de `ope_novedades`.
2. **Confirmar en `test_pos`** (réplica de Beer Garden con el POS instalado):
   foto de la BD antes, el usuario hace la acción en el POS paso a paso, diff
   después de cada paso. El código dice qué debería pasar; el diff, qué pasa
   (triggers, valores por defecto).
3. **Implementar** en la API dentro de una transacción, con los mismos estados.
4. **Prueba diferencial**: misma operación por el POS y por la API en
   `test_pos`; las filas resultantes deben coincidir salvo ids y horas.
5. **Tests de integración** contra la BD `test` local.

Reglas:

- **Nunca pruebas en producción**: un ingreso con costo cambia el costo promedio
  (WAC) para siempre, aunque después se ajuste el stock. Las comandas de prueba
  quedan en ventas, reportes y `ope_novedades`.
- **Permisos**: aplicar antes el usuario `api_paloteo`
  (`querys/seguridad_usuario_api_tuneles.sql`) y ampliarlo tabla por tabla con
  cada operación nueva, en lugar de escribir como `root`.
- Mejorar antes la herramienta de diff (ver sus límites en la cabecera de
  `diff_tablas.py`): checksum de todas las filas, detalle por columna de cada
  UPDATE, incluir `alm_producto`, `alm_valoracion*`, `bar_valoracion`,
  `*_inventario_operacion`. Pasarla al repo cuando esté estable.

## Próximo paso

Exportar los `.java` de `multi-ejb.jar` y `multi-web.war` con JD-GUI
(*File → Save All Sources*) a `AnalisisPos/fuentes/`, y empezar por el flujo
**ingreso de proveedor → traspaso → recepción en barra**.
