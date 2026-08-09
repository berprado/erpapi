# Módulo POUR COST — Diseño y Alcance (v1)

Guía de referencia del módulo POUR COST: cálculo y simulación del costo de venta (pour cost) de combos/cócteles y productos sueltos comandados desde el POS. Estado: **implementado** (rama `feature/pour-cost`, cache v11.5). Este documento se mantiene como fuente de verdad de las decisiones de diseño y debe actualizarse cuando cambie el comportamiento del módulo.

## 0. Qué resuelve

El pour cost es el costo de los insumos de un ítem del menú expresado como porcentaje de su precio de venta: `costo / precio_venta x 100`. El módulo permite ver ese porcentaje "real" con el WAC actual, y simularlo en caliente (cambiar receta, precio o costo de un insumo) sin escribir nada en `adminerp`.

La arquitectura aprovecha que MySQL ya resuelve el trabajo pesado (joins, conversión de unidades, costeo WAC) en vistas — el mismo patrón que este repo ya usa para AJUSTES/PESAJE: la API es un canal delgado de lectura, la simulación vive en memoria del frontend.

## 1. Alcance de v1 (decidido)

| Decisión | Resultado |
|---|---|
| Cobertura | **Combos/cócteles + productos sueltos comandables**, ambos desde v1 (dos caminos de costeo distintos, ver sección 3) |
| Fase "Aplicar Precio" (`INSERT` en `ope_precio_venta`) | **Fuera de v1.** Muta un precio que el POS lee en producción; se diseña como fase separada, con su propio flujo de confirmación/auditoría (ver sección 8) |
| v1 es | 100% lectura (`GET`) + simulación en memoria en el frontend. Ningún endpoint transaccional |
| Rol de acceso | **Admin-only** (confirmado 2026-08-05), igual que PESAJE (`_es_usuario_administrador`), por ser información de costo/margen |
| `id_dia` | **1 por defecto** (confirmado 2026-08-05); el usuario puede seleccionar explícitamente `id_dia=2` en la UI para simular el horario de baja afluencia (ver sección 5 y sección 8, punto 2) |

## 2. Vistas de base de datos (dependencia externa al ORM, no versionada — hasta ahora)

Igual que los triggers de `alm_producto` (ver CLAUDE.md, sección "Pesaje config es sincronizado... por triggers"), estas 6 vistas viven en MySQL y no las gestiona ninguna migración de este repo. La fuente versionada ya no es el JSON/dump que trajo el usuario sino **`querys/create_views_pourcost.sql`** (recién creado, formato `CREATE OR REPLACE VIEW`, mismo molde que `querys/fix_trigger_alm_producto_after_*.sql`) — reaplicar manualmente si un entorno se reconstruye.

| Vista | Para qué la usa el módulo |
|---|---|
| `v9_menubackstage` | Menú activo (combos + productos sueltos) con `precio_venta` vigente |
| `vw_pourcost_receta` | Vista maestra: una fila por línea de receta de combo, con `cogs_ingrediente` ya calculado |
| `vw_alm_producto_con_nombres` | Catálogo de insumos para la simulación "agregar ingrediente" |
| `v9_cache_wac_producto` / `vw_cache_wac_producto_detalle` | WAC actual por producto — directo para productos sueltos, vía join para líneas de receta |
| `vw_combo_detalle_reload` | Detalle crudo de receta que arma `vw_pourcost_receta` (no se consulta directo desde la API salvo debug) |

**Entorno objetivo: `test_pos`, no `test` (decidido 2026-08-05).** El prefijo fijo `` `adminerp`.`tabla` `` de las vistas dejó de ser un riesgo porque `test_pos` usa exactamente ese nombre de esquema (`TEST_POS_DB_NAME=adminerp`) — y las 6 vistas **ya existen ahí, no hace falta aplicar `create_views_pourcost.sql`** (verificado por conexión directa: `v9_cache_wac_producto`, `v9_menubackstage`, `vw_alm_producto_con_nombres`, `vw_cache_wac_producto_detalle`, `vw_combo_detalle_reload`, `vw_pourcost_receta` presentes). `test_pos` es una réplica de producción con el POS real instalado (ver `documentos/despliegue_seenode.md`), y el deploy de seenode ya apunta ahí, así que el módulo se puede validar en vivo en la PWA real sin configuración adicional. El script queda como fuente versionada por si `test`/`adminerp_copy` la necesita en el futuro, o para reconstruir el entorno.

Datos reales en test_pos (2026-08-05): 430 combos, 3545 líneas de receta, 396 combos con al menos una línea costeada, 245 productos con WAC cacheado, 504 productos totales, 1706 filas en `ope_precio_venta`.

**Implicación para pruebas automatizadas:** `tests/conftest.py` falla duro si `APP_ENV != test`, a propósito, para que nada automatizado toque `test_pos`/producción — no se toca ese guard. Los `GET` de POUR COST no tendrán integración automatizada en v1 (mismo nivel que `POST /pesaje/perfiles` hoy); se validan a mano contra `test_pos` vía `/docs` o la PWA en seenode. Las fórmulas (agregación de costo, pour cost, precio sugerido) sí se cubren con unitarias puras, sin DB.

## 3. Dos caminos de costeo (por la decisión de la sección 1)

### 3.1 Combos/cócteles — vía `vw_pourcost_receta`

1. Agrupar todas las filas de `vw_pourcost_receta` por `id_combo_coctel`.
2. Sumar `cogs_ingrediente` de cada línea → **Costo Total de Receta**.
3. `pour_cost = (costo_total_receta / precio_venta) x 100`.

Cada fila ya trae `sin_wac = 1` cuando el ingrediente no tiene costo cacheado (`cache_wac_producto` vacío) — el agregado debe marcar el combo como "costo incompleto" en ese caso, no mostrar un pour cost falsamente bajo.

### 3.2 Productos sueltos comandables — vía `v9_menubackstage` (`tipo='producto'`) + WAC directo

No pasan por `vw_pourcost_receta` (esa vista solo cubre `bar_detalle_combo_bar`, es decir combos). Para un producto suelto (ej. una cerveza vendida tal cual):

1. Tomar la fila de `v9_menubackstage` con `tipo='producto'` → `id_origen` = `id_producto`, `precio_venta`.
2. Buscar su costo en `v9_cache_wac_producto` por `id_producto` → `wac_unitario` es el costo directo (no hay receta que sumar).
3. `pour_cost = (wac_unitario / precio_venta) x 100`.

Este camino es un endpoint/función separada — más simple, sin agregación de líneas. **No reutilizar el código de agregación de 3.1** para este caso; es un formato de datos distinto (una vista por línea de receta vs. una vista por producto).

## 4. Fórmulas

```
Pour Cost                = (Costo Total Receta / Precio Venta) x 100
Precio Sugerido (inverso) = Costo Total Receta / (Target Pour Cost / 100)
```

### Convención de redondeo (decidido 2026-08-05)

A diferencia de la oz (`redondeo_y_tolerancia.md`), acá **no hay una grilla física que backend y frontend deban calcular byte a byte** — nada de esto se escribe todavía (Fase 2 sigue fuera de alcance). Por eso la elección de regla de desempate (HALF_UP vs. banker's rounding) no es crítica en sí misma; lo que sí importa es no arrastrar error de `float` al sumar muchas líneas de `cogs_ingrediente`, y no mostrar un precio con centavos cuando el negocio nunca los usa.

- **Pour cost %:** acumular con `Decimal` (evita arrastre de error en la suma de `cogs_ingrediente`), redondear a 2 decimales con HALF_UP solo por consistencia con el resto del código — no es una decisión cargada de consecuencias como en oz, un empate exacto a esa escala es irrelevante en la práctica.
- **Precio sugerido:** mostrar **dos valores**, mismo patrón que crudo-vs-operativo ya usado en paloteo (`app_paloteo_registro_crudo` exacto vs. `bar_detalle_fisico` redondeado):
  - *Exacto:* `costo_total_receta / (target_pour_cost / 100)` sin redondear.
  - *Redondeado (el accionable):* HALF_UP a la unidad entera de moneda, con `Decimal`. Justificado con datos: **el 100% de los 1706 `precio_venta` HAB en test_pos son números enteros** (sin centavos, ni siquiera .50) — un precio sugerido con decimales no es una cifra que alguien vaya a teclear en el POS. Es una inferencia de los datos actuales, no una regla de negocio documentada; si el negocio empieza a usar precios fraccionarios habría que revisar esta regla.

## 5. Endpoints implementados (v1, todos `GET`, todos admin-only)

Los datos se devuelven **agrupados por el backend** con un `schemas.py` real — la suma de `cogs_ingrediente` y la detección de `sin_wac` ocurren en Python, no en JS.

Los tres primeros aceptan `id_dia` como query param (default `1`), ya que `vw_pourcost_receta` fija `id_dia=1` internamente; el precio se resuelve aparte contra `v9_menubackstage` y se cruza en Python por `id_combo_coctel`/`id_origen`.

| Endpoint | Fuente | Devuelve |
|---|---|---|
| `GET /api/pourcost/menu?id_dia=1` | `v9_menubackstage`, filtrando `id_dia` | Lista plana: combos + productos sueltos con `precio_venta` del horario elegido |
| `GET /api/pourcost/recetas?id_dia=1` | `vw_pourcost_receta` (costo/receta) + `v9_menubackstage` filtrado por `id_dia` (precio) | Un objeto por combo: costo total, `precio_venta`, pour cost %, lista de ingredientes con `cantidad_receta`, `tipo_cantidad_combo`, `tipo_parte_combo`, `unidad_base`, `medida_unidad_base`, `unidades_detalle_por_base`, `unidad_detalle`, `wac_actual`, `sin_wac`, `cantidad_unidad_base`, `cogs_ingrediente` |
| `GET /api/pourcost/productos?id_dia=1` | `v9_menubackstage` (`tipo='producto'`) + `v9_cache_wac_producto` | Un objeto por producto suelto: `wac_unitario`, `precio_venta`, pour cost directo |
| `GET /api/pourcost/insumos` | `vw_alm_producto_con_nombres` | Catálogo completo para la simulación "agregar ingrediente" |

**Nota sobre `ind_tipo_producto`:** `vw_pourcost_receta` no expone el ID numérico de `bar_detalle_combo_bar.ind_tipo_producto`; sí expone `tipo_parte_combo` (el nombre resuelto desde `parameter_table`, ej. `"PRINCIPAL"`, `"OPCIONAL"`). El schema `PourCostIngrediente` y el estado local de simulación usan `tipo_parte_combo` como campo semántico para distinguir ingredientes principales y opcionales — es equivalente y suficiente para la próxima tarea de opcionales.

## 6. Sandbox de simulación (implementado, 100% en memoria del cliente)

Toda la simulación corre en memoria del cliente, sin `POST`/`PUT` a `adminerp`:

- **Simulación inversa (bidireccional):** el usuario puede ingresar un **% objetivo** para obtener el precio sugerido (`costo / (% / 100)`), o bien ingresar un **precio en Bs** para obtener el pour cost % resultante (`costo / precio × 100`). Ambas direcciones reaccionan en tiempo real si el costo simulado cambia por edición de cantidades/WAC.
- **Alteración de WAC:** el usuario edita el WAC de un ingrediente → recalcula `cogs_ingrediente` de esa línea y el total.
- **Alteración de receta:** selector `[−] [cantidad] [+]` con paso 0,5 por ingrediente. El frontend edita `cantidad_receta` y deriva `cantidad_unidad_base` internamente (`pourCostCantidadUnidadBase`). Para `Detalle`: `cantidad_unidad_base = cantidad_receta / unidades_detalle_por_base`; para `Unidad`: `cantidad_unidad_base = cantidad_receta`.
- **Reiniciar simulación:** restaura exactamente los valores originales del backend (cantidades, WAC, costos y % original).

### 6.1 Consistencia del modal de ingredientes (implementada en v11.4)

El modal mantiene separación explícita entre:

- `cantidad_receta`: cantidad visible y editable (ej. `1 OZ`). Fuente de verdad para la edición.
- `cantidad_unidad_base`: fracción interna de costeo, derivada de `cantidad_receta`. No se expone como campo editable.

El estado local de simulación clona los campos `tipo_cantidad_combo`, `tipo_parte_combo`, `unidades_detalle_por_base`, `unidad_detalle`, `medida_unidad_base` y `unidad_base` para que `pourCostCantidadUnidadBase` pueda recalcular sin consultar al backend.

La normalización de entradas acepta coma o punto como separador decimal (`1`, `1.0`, `1,0`, `1,5`), rechaza vacíos, negativos y no numéricos, y evita errores de punto flotante con `Math.round(val * 100) / 100`.

Cada fila muestra `ENVASE: {medida_unidad_base} {unidad_base} · RENDIMIENTO: {unidades_detalle_por_base} {unidad_detalle}` para ingredientes tipo `Detalle`.

## 7. Cierre del flujo — Fase 2, fuera de alcance v1

Botón "Aplicar Precio" → `INSERT` en `ope_precio_venta`. Queda **explícitamente fuera de v1** (decisión de la sección 1). Cuando se diseñe: rol admin, confirmación explícita (no un solo clic), y algún registro de auditoría — mismo criterio que ya se aplicó a login (`app_login_auditoria_api`) para escrituras sensibles.

## 8. Riesgos y abiertos a resolver antes de implementar

1. ~~Prefijo de esquema `adminerp` hardcodeado en las vistas~~ — **resuelto** (2026-08-05): entorno objetivo es `test_pos`, cuyo esquema se llama exactamente `adminerp`. Ver sección 2.

2. ~~`id_dia`~~ — **resuelto** (2026-08-05). `id_dia` es un "horario de precio" que se elige al abrir la operativa (ej. jueves-sábado a Bs 40, domingo-lunes a Bs 30 con `id_dia=2`); `ope_operacion` tiene su propia columna `id_dia` que lo confirma, aunque las 1262 operativas históricas HAB en test_pos usan `id_dia=1` sin excepción (los 779 registros con `id_dia=2` en `ope_precio_venta` nunca fueron consumidos por una operativa real ahí). **Decisión: selector manual en la UI, no resolución automática desde la operativa activa.** El usuario del módulo elige `id_dia` explícitamente al abrir POUR COST — sirve para simular el horario de baja afluencia sin depender de que esté activo en ese momento. Consecuencia de arquitectura: `id_dia` es un **parámetro de query en los endpoints de la sección 5** (no algo que el backend infiera de `ope_operacion`); el módulo **no debe confiar en el `precio_venta` embebido en `vw_pourcost_receta`/`v9_menubackstage`** (fijo a `id_dia=1` en su definición SQL) — debe resolver el precio contra `v9_menubackstage` filtrando por el `id_dia` que llega en el query param.

3. ~~Frescura de `cache_wac_producto`~~ — **resuelto** (2026-08-05, ver `DOCUMENTO_MAESTRO_MOTOR_FINANCIERO_V9_WAC_COGS.md` aportado por el usuario): se actualiza incrementalmente vía `trg_wac_after_insert_detalle` (trigger `AFTER INSERT` sobre `alm_detalle_ingreso`, confirmado en test_pos), no por batch/cron — es WAC perpetuo móvil, razonablemente al día. **Matiz de diseño importante:** ese mismo documento aclara que `cache_wac_producto`/`v9_cache_wac_producto` son una lectura **dinámica** ("V9 dinámico"), no un snapshot histórico inmutable — el costo de un combo puede cambiar retroactivamente si se registra una compra nueva. Encaja bien con POUR COST, que es deliberadamente una herramienta de simulación en caliente con el costo *vigente*, no un reporte histórico — pero la UI nunca debe dar a entender que el pour cost mostrado hoy es el que tenía una venta pasada.

4. **Ingredientes sin WAC (`sin_wac = 1`):** no es hipotético — 472 de las líneas de receta en test_pos no tienen WAC cacheado (`vw_productos_sin_costo_cache` confirma 182 productos sin costo cacheado en total). Según el documento maestro, esto puede ser una **anomalía de datos real** (stock positivo sin WAC cacheado subvalora el costo, no solo "todavía no se compró"), no un caso a ocultar silenciosamente. Definir en la UI: pour cost con nota de "costo incompleto", y considerar exponer el catálogo de `vw_productos_sin_costo_cache` como lista de atención en el módulo (encaja con el endpoint `GET /api/pourcost/insumos` de la sección 5).

5. ~~Confirmar existencia de las vistas en `test`~~ — **resuelto**, ya existen en `test_pos` (ver sección 2). Cobertura de integración automatizada sigue sin ser posible ahí por el guard de `conftest.py` (intencional, no se toca); validación de los `GET` es manual contra `test_pos`.

### Nota sobre el alcance de la documentación externa aportada

El usuario aportó `DOCUMENTO_MAESTRO_MOTOR_FINANCIERO_V9_WAC_COGS.md` y `GUIA_DECISION_SNAPSHOT_WAC_CIERRE_OPERATIVA.md` — documentación de un proyecto más amplio (motor financiero V9: `analytics_cogs_historico`, `snapshot_job.php`, congelamiento de WAC al cierre de operativa, KPIs `v9_item_base`/`v9_kpi_operativa`). **No pertenece a este repo y la mayor parte queda fuera del alcance de POUR COST v1** — es contexto para entender de dónde salen `cache_wac_producto`/`v9_cache_wac_producto` (puntos 3 y 4 arriba), no una lista de trabajo pendiente para este módulo. POUR COST v1 lee directamente el WAC vigente (lectura "V9 dinámico"); no depende de `analytics_cogs_historico` ni del snapshot job, y no se ve afectado por sus inconsistencias documentadas (job no migrado, granularidad sin definir, etc.) porque no los toca.

## 9. Referencias visuales

Las imágenes aportadas sirven como referencia visual del estado actual del modal y deben consultarse junto con la receta y las vistas SQL al implementar la refactorización:

- [long_island.png](./long_island.png)
- [chuflay.png](./chuflay.png)

## 10. Pruebas

- **Unitarias, sin DB** (`tests/test_calculos_pourcost.py`, 21 tests): cubren `_calcular_pour_cost_pct`, `_calcular_precio_sugerido`, `_agregar_costo_receta` y los casos de aceptación de la refactorización de cantidades (Long Island 1 oz → Bs 2,35; 1,5 oz → Bs 3,53; Chuflay fracción interna; división por cero → 0). Corren con `python -m pytest`.
- **Sin integración automatizada en v1.** Los 4 `GET` se validan a mano contra `test_pos` vía `/docs` o la PWA en seenode — `tests/conftest.py` exige `APP_ENV=test` y no se toca ese guard.

---

Documentos fuente de este diseño: `documentos/pour_cost/vistas_modulo_pourcost.json` (dump original de las vistas) y `querys/create_views_pourcost.sql` (DDL versionado, ejecutable).
