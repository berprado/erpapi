# Documento maestro del motor financiero V9: WAC, COGS, márgenes y snapshots

**Sistema:** POS BackStage / AdminERP
**Base de datos:** MySQL 5.6.12
**Estado documental:** Consolidación técnica basada en código y objetos reales revisados
**Fecha de consolidación:** 2026-07-13

---

## 1. Propósito

Este documento describe cómo funciona actualmente el motor financiero V9 de BackStage y separa explícitamente:

1. el método de costos oficialmente adoptado;
2. la implementación comprobada en base de datos;
3. el cálculo dinámico realizado por las vistas V9;
4. el mecanismo externo de snapshots históricos;
5. los componentes heredados de métodos descartados;
6. las inconsistencias y vacíos que todavía deben resolverse.

La separación es necesaria porque la base de datos conserva vistas y scripts creados durante distintas etapas del desarrollo. El nombre de un objeto no garantiza que represente el método vigente.

---

## 2. Decisión financiera vigente

BackStage adoptó el siguiente método:

> **WAC Perpetuo Móvil con corte estratégico por inflación y mantenimiento mediante caché de costo.**

El sistema no debe recalcular el costo operativo recorriendo todo el historial de compras. Mantiene un costo vigente por producto y almacén en:

```sql
cache_wac_producto
```

El objetivo gerencial es aproximarse mejor al costo vigente de reposición y evitar márgenes ficticios producidos por compras antiguas demasiado baratas.

### 2.1 Fórmula vigente

Cuando ingresa una compra con costo mayor a cero:

```text
Nuevo WAC =
((WAC vigente × stock previo de almacén)
 + (cantidad ingresada × costo unitario nuevo))
/
(stock previo de almacén + cantidad ingresada)
```

### 2.2 Reglas aprobadas

- Si `precio_costo = 0`, el ingreso se considera una bonificación y no modifica el WAC.
- Si el stock previo de almacén es cero o negativo, el WAC toma el costo del nuevo ingreso.
- Si existe stock previo, se aplica el promedio ponderado incremental.
- Los traspasos internos de almacén a barra no modifican el WAC.
- El costo vigente se calcula por `id_almacen` e `id_producto`.
- Los cortes estratégicos permiten redefinir el costo base sin volver al promedio histórico completo.
- Las bonificaciones no diluyen el WAC, por decisión gerencial orientada al costo de reposición.

Esta última regla difiere de un promedio contable estricto que repartiría el costo total entre las unidades compradas y gratuitas. Por ello, el WAC de BackStage debe entenderse principalmente como **costo operativo de reposición**.

---

## 3. Ciclo de vida del WAC

La implementación atravesó tres etapas.

### 3.1 Población inicial

La caché se pobló inicialmente mediante un promedio histórico acumulado:

```sql
SUM(cantidad * precio_costo) / SUM(cantidad)
```

Ese procedimiento sirvió como punto de partida, pero fue descartado como método operativo permanente porque arrastraba costos antiguos y generaba “ganancias fantasma”.

### 3.2 Corte estratégico por inflación

Posteriormente se reinicializó `cache_wac_producto` usando el último costo válido de compra de cada producto. Este corte eliminó el peso de costos históricos considerados poco representativos del costo de reposición.

### 3.3 Mantenimiento incremental

Desde el corte, el trigger:

```sql
trg_wac_after_insert_detalle
```

actualiza incrementalmente el WAC después de cada inserción en:

```sql
alm_detalle_ingreso
```

---

## 4. Caché de costo vigente

La tabla física es:

```sql
cache_wac_producto
```

Su clave primaria es:

```sql
PRIMARY KEY (id_almacen, id_producto)
```

Esto garantiza una sola fila vigente por producto y almacén y permite que el trigger use:

```sql
ON DUPLICATE KEY UPDATE
    wac_actual = VALUES(wac_actual)
```

La columna:

```sql
fecha_actualizacion TIMESTAMP
    DEFAULT CURRENT_TIMESTAMP
    ON UPDATE CURRENT_TIMESTAMP
```

registra automáticamente cuándo se modificó el WAC.

La vista semántica documentada para exponer el costo es:

```sql
v9_cache_wac_producto
```

Esta vista enriquece el caché con información del producto y categoría y excluye productos deshabilitados y comodines.

### 4.1 Diferencia entre fuente física y semántica

- `cache_wac_producto`: fuente física del costo vigente.
- `v9_cache_wac_producto`: interfaz semántica recomendada para consultas y reportes.

Actualmente `comandas_v9_detallada` consulta directamente la tabla física. El cálculo es funcionalmente válido, pero no sigue la capa semántica recomendada.

---

## 5. Funcionamiento comprobado del trigger

El trigger vigente realiza lo siguiente:

1. obtiene `id_almacen` desde la cabecera `alm_ingreso`;
2. obtiene `wac_actual` desde `cache_wac_producto`;
3. lee `alm_inventario.cantidad_paq` como stock previo;
4. aplica la regla de bonificación, reinicio o promedio ponderado;
5. inserta o actualiza el caché.

Se documentó y validó empíricamente que el POS actualiza `alm_inventario` después de insertar el detalle. Por tanto, durante el trigger, `cantidad_paq` representa el stock previo al ingreso actual.

### 5.1 Condiciones operativas necesarias

Para que el cálculo sea correcto deben cumplirse estas condiciones:

- `NEW.cantidad` y `alm_inventario.cantidad_paq` deben representar la misma unidad base;
- todo producto con stock positivo debe tener un WAC cacheado mayor a cero;
- los detalles deben insertarse como parte de un ingreso válido y definitivo;
- no deben ingresarse cantidades negativas ni costos negativos;
- las anulaciones y correcciones posteriores necesitan un procedimiento específico porque el trigger solo responde a `INSERT`;
- dos procesos concurrentes sobre el mismo producto podrían requerir control adicional para evitar actualizaciones perdidas.

### 5.2 Caso crítico: stock positivo sin caché

Si existe stock previo pero no existe WAC cacheado, el trigger usa cero como WAC anterior. Esto subvalora el inventario previo y produce un WAC incorrecto. Este escenario debe tratarse como una anomalía de datos.

### 5.3 Bonificaciones

Cuando `precio_costo = 0`, el trigger conserva el WAC vigente. Si el producto nunca tuvo un costo válido, no crea una fila con WAC cero. Esos productos deben monitorearse mediante `vw_productos_sin_costo_cache` o una consulta equivalente.

---

## 6. Motor analítico V9 en tiempo real

El pipeline principal comprobado es:

```text
Datos RAW del POS
    → comandas_v7
    → comandas_v8
    → comandas_v9_detallada
    → v9_item_base
    → vistas KPI V9
```

### 6.1 Modelo dual

El motor separa dos dimensiones que no deben mezclarse.

#### Dimensión de venta

- Nivel: artículo vendido.
- Fuente recomendada: `v9_item_base`.
- Categoría: `categoria_item_venta`.
- Responde qué se vendió, cuánto se cobró y cuál fue el margen del artículo.

#### Dimensión de consumo

- Nivel: ingrediente o producto real descontado.
- Fuente recomendada: `comandas_v9_detallada`.
- Categoría: `categoria_receta`.
- Responde qué productos físicos fueron consumidos y cuánto costaron.

Regla fundamental:

> **Venta no es lo mismo que consumo.**

Un combo puede representar una venta, pero consumir varios ingredientes.

### 6.2 `comandas_v9_detallada`

Esta vista trabaja a nivel de ingrediente. Toma el consumo preparado por `comandas_v8`, incorpora el WAC vigente y calcula:

```text
costo_total_linea =
cantidad_consumida_unidad_base × wac_actual
```

La unión comprobada es:

```sql
LEFT JOIN cache_wac_producto c
       ON c.id_producto = v8.id_producto_receta
      AND c.id_almacen = 1
```

Consecuencias:

- utiliza el WAC operativo vigente del almacén 1;
- no usa un WAC histórico por operativa;
- si falta el caché, `COALESCE(c.wac_actual, 0)` produce COGS cero;
- el almacén está fijado en `id_almacen = 1`;
- una consulta posterior puede revalorizar comandas antiguas con el WAC que esté vigente en ese momento.

Esto último no es un error para análisis operativo con costo de reposición actual, pero significa que estas vistas no son históricamente inmutables.

### 6.3 `v9_item_base`

Agrupa las líneas de ingredientes por:

```text
id_operacion + id_detalle_comanda
```

Su propósito es regresar al nivel del artículo vendido sin duplicar ventas. Calcula:

- venta real;
- venta teórica;
- COGS por artículo;
- margen real y teórico;
- pour cost real y teórico.

### 6.4 `v9_kpi_operativa`

Consolida `v9_item_base` por operativa y calcula:

- venta real total;
- venta teórica total;
- COGS total;
- margen real y teórico;
- pour cost real y teórico.

Como hereda el COGS desde `comandas_v9_detallada`, también utiliza indirectamente el WAC vigente al momento de la consulta.

---

## 7. Cortesías y venta teórica

Las cortesías consumen inventario y generan COGS, aunque su venta real sea cero.

En `comandas_v9_detallada`:

- `venta_real` usa el subtotal realmente cobrado;
- `venta_teorica` recupera `cor_subtotal_anterior` cuando el subtotal quedó en cero por cortesía;
- el COGS se mantiene porque el producto sí fue consumido;
- el margen real disminuye por el costo de la cortesía;
- el margen teórico permite analizar el valor comercial antes de la cortesía.

---

## 8. Sistema de snapshots históricos

La tabla:

```sql
analytics_cogs_historico
```

está diseñada para guardar:

- operativa;
- comanda cerrada;
- producto consumido;
- cantidad consumida;
- costo unitario congelado;
- COGS congelado;
- fecha del snapshot.

El proceso externo documentado es:

```text
scripts/snapshot_job.php
```

El script busca hasta 100 comandas con:

```sql
estado = 'HAB'
AND estado_comanda = 26
```

que todavía no tengan ninguna fila en `analytics_cogs_historico`. Después inserta por separado consumos de combos y productos directos.

### 8.1 Funcionamiento real del snapshot actual

El código revisado no utiliza `cache_wac_producto`. Utiliza:

```sql
vw_wac_producto_almacen
```

Esta vista calcula:

```sql
SUM(cantidad * precio_costo) / SUM(cantidad)
```

sobre el historial completo de ingresos válidos con costo mayor a cero.

Por tanto, el snapshot actual congela:

> **el WAC histórico acumulado disponible cuando se ejecuta el job**, no el WAC Perpetuo Móvil vigente en `cache_wac_producto`.

Esto contradice el método financiero vigente y las notas documentales que afirman que el pipeline histórico ya fue migrado a la caché.

### 8.2 Momento real de congelamiento

El snapshot no se genera al cerrar físicamente la comanda. Se genera cuando se ejecuta `snapshot_job.php` después del cierre.

Por eso, incluso si se migrara el script al caché, el costo congelado sería el WAC vigente al ejecutar el job, no necesariamente el WAC exacto existente cuando se cerró la comanda.

Para que ambos momentos sean equivalentes se necesitaría:

- ejecutar el job inmediatamente después del cierre; o
- guardar el WAC en el evento de cierre; o
- mantener una bitácora temporal de cambios WAC que permita recuperar el valor vigente a la fecha de cierre.

### 8.3 Riesgos técnicos del job actual

#### Procesamiento parcial no recuperable

La candidatura se decide a nivel de comanda:

```sql
id_comanda NOT IN (
    SELECT id_comanda FROM analytics_cogs_historico
)
```

Si el bloque de combos inserta al menos una fila y después falla el bloque de directos, la comanda deja de aparecer como pendiente y los directos no se reintentan.

#### Falta de transacción

Los dos `INSERT` no están protegidos por una transacción común. Una comanda puede quedar parcialmente congelada.

#### Dependencia mediante `INNER JOIN`

Los dos bloques usan `INNER JOIN` con la fuente WAC. Un producto sin costo en esa fuente desaparece del snapshot en lugar de quedar visible con costo cero o como error auditable.

#### Duplicados por ejecución concurrente

La tabla solo tiene una clave primaria autoincremental. Dos ejecuciones simultáneas pueden seleccionar las mismas comandas e insertar filas duplicadas.

#### Granularidad no protegida

No existe una restricción única que declare si debe haber:

- una fila por comanda y producto; o
- una fila por línea real de consumo.

El script puede insertar varias filas del mismo producto dentro de una comanda. Esto puede ser correcto a nivel de línea, pero la tabla no conserva un identificador de línea que permita distinguirlas de duplicados accidentales.

#### Almacén fijo

El snapshot usa siempre `id_almacen = 1`.

### 8.4 `check_last_snapshot.php`

Este script solo consulta:

```sql
MAX(fecha_snapshot), COUNT(*)
```

Sirve como señal básica de actividad, pero no demuestra:

- que todas las comandas cerradas estén procesadas;
- que una comanda tenga todas sus líneas;
- que el WAC utilizado sea el correcto;
- que no existan duplicados;
- que el último job haya terminado sin errores.

Debe considerarse un indicador de “última escritura”, no un control de integridad.

---

## 9. Dos lecturas financieras actualmente disponibles

Con el código revisado, el sistema ofrece dos lecturas distintas:

| Lectura | Fuente de costo | Naturaleza |
|---|---|---|
| V9 dinámico | `cache_wac_producto.wac_actual` | Costo operativo vigente al consultar |
| Snapshot actual | `vw_wac_producto_almacen.wac_global` | Promedio histórico acumulado congelado al ejecutar el job |

Estas lecturas no son equivalentes y no deben combinarse como si provinieran del mismo método.

El diseño objetivo documentado debería ser:

| Lectura | Fuente de costo | Naturaleza |
|---|---|---|
| V9 dinámico | `v9_cache_wac_producto` o caché físico | Costo operativo vigente |
| Histórico congelado | WAC vigente del caché capturado según una regla temporal definida | COGS histórico inmutable |

---

## 10. Estado de las vistas relacionadas con WAC

### 10.1 Núcleo vigente confirmado

```text
cache_wac_producto
v9_cache_wac_producto
trg_wac_after_insert_detalle
comandas_v7
comandas_v8
comandas_v9_detallada
v9_item_base
v9_kpi_operativa
v9_kpi_venta_categoria
v9_kpi_consumo_categoria
v9_kpi_operativa_categoria
v9_kpi_operativa_tipo_parte
v9_rank_item_vendido_margen_teorico
v9_rank_producto_por_cogs
```

### 10.2 Obsoleta declarada documentalmente

```text
v9_item_reconstruido
```

Antes de eliminarla deben verificarse dependencias internas y consumidores externos.

### 10.3 Requiere revisión funcional

```text
v9_rank_producto_peor_pourcost
```

Fue señalada por mezclar dimensiones de venta y consumo.

### 10.4 Vistas asociadas a métodos anteriores

```text
vw_base_wac_operativa
vw_costo_heredado_producto
vw_wac_anterior
vw_wac_anterior_producto
vw_wac_global_producto
vw_wac_operativa
vw_wac_operativa_producto
vw_wac_operativa_producto_corregido
vw_wac_operativa_producto_unico
vw_wac_perpetuo_operativa
vw_wac_producto_almacen
vw_consumo_valorizado_operativa
```

Estas vistas son candidatas a retiro porque no representan el método operativo vigente. No obstante, `vw_wac_producto_almacen` todavía no puede eliminarse: el `snapshot_job.php` actual depende directamente de ella.

También deben revisarse las vistas COGS anteriores a V9 (`vw_cogs_*`, `vw_margen_*`, `vw_pourcost_receta`) para determinar si todavía son utilizadas por dashboards o scripts externos.

---

## 11. Inconsistencias documentales resueltas

### “WAC por operativa”

No es el método final. Las vistas con ese enfoque pertenecen a pruebas anteriores. El costo oficial es un WAC vigente por producto y almacén.

### “Snapshot al cerrar la comanda”

El código actual lo ejecuta posteriormente mediante un job. Debe describirse como snapshot de comandas ya cerradas, generado durante la ejecución del proceso programado.

### “El snapshot usa el WAC vigente”

No con el código revisado. Actualmente usa el promedio histórico acumulado de `vw_wac_producto_almacen`.

### “Todo el pipeline fue migrado al caché”

El pipeline V9 sí usa `cache_wac_producto`, pero `snapshot_job.php` no fue migrado.

### “Los KPI V9 son históricos e inmutables”

No. Los KPI V9 se recalculan con el WAC vigente. La inmutabilidad solo existe en las filas ya guardadas en `analytics_cogs_historico`.

---

## 12. Correcciones recomendadas, por prioridad

### Prioridad 1 — Definir la semántica temporal del snapshot

Debe elegirse y documentarse una regla:

1. WAC vigente al cerrar cada comanda;
2. WAC vigente al cerrar la operativa;
3. WAC vigente cuando corre el job;
4. costo operativo de reposición recalculado al consultar.

Para un histórico verdaderamente auditable, las opciones 1 o 2 son las más sólidas. La opción 3 es más sencilla, pero debe reconocerse explícitamente.

### Prioridad 2 — Migrar el snapshot al método vigente

Después de definir el momento de valoración, `snapshot_job.php` debe dejar de usar `vw_wac_producto_almacen` y utilizar la fuente de costo aprobada.

### Prioridad 3 — Hacer el job atómico e idempotente

El proceso debería:

- usar una transacción;
- procesar cada comanda completa o no procesarla;
- prevenir ejecuciones simultáneas;
- detectar reintentos;
- registrar errores;
- validar productos sin WAC;
- establecer una granularidad única y verificable.

### Prioridad 4 — Mejorar monitoreo

`check_last_snapshot.php` debería reportar como mínimo:

- última ejecución correcta;
- comandas cerradas pendientes;
- comandas parcialmente procesadas;
- filas duplicadas;
- productos sin WAC;
- última operativa completamente cubierta.

### Prioridad 5 — Separar BI dinámico de BI histórico

Las aplicaciones deben indicar claramente si muestran:

- costo vigente de reposición; o
- costo histórico congelado.

Un mismo KPI no debería cambiar silenciosamente de semántica según la consulta.

### Prioridad 6 — Retirar vistas heredadas

Solo después de migrar el snapshot y comprobar dependencias internas y externas debe eliminarse `vw_wac_producto_almacen` y el resto de vistas experimentales sin consumidores.

---

## 13. Vacíos conceptuales pendientes

Para cerrar completamente la arquitectura se necesita confirmar:

1. ¿El costo histórico debe congelarse al cerrar la comanda o al cerrar la operativa?
2. ¿Los reportes oficiales de operaciones cerradas deben leer snapshots o deben mostrar siempre el costo vigente de reposición?
3. ¿Una fila de `analytics_cogs_historico` representa una línea de consumo o el total consolidado de un producto dentro de una comanda?
4. ¿Puede repetirse un producto en varias líneas de una misma comanda?
5. ¿Cómo se corrige un snapshot incompleto o calculado con un WAC erróneo?
6. ¿Cuándo se considera definitivo un ingreso de almacén y qué ocurre si después se anula?
7. ¿`cantidad_paq` y `alm_detalle_ingreso.cantidad` siempre usan exactamente la misma unidad?
8. ¿Existirá más de un almacén de costos o `id_almacen = 1` es una regla permanente?
9. ¿Qué aplicaciones externas siguen consultando las vistas COGS y WAC anteriores?

Estas preguntas no invalidan el método vigente. Definen los límites necesarios para que la implementación sea completamente consistente y auditable.

---

## 14. Definición oficial recomendada

> BackStage utiliza un WAC Perpetuo Móvil orientado al costo operativo de reposición. El WAC vigente se mantiene incrementalmente por producto y almacén en `cache_wac_producto` mediante `trg_wac_after_insert_detalle`. El motor V9 aplica ese costo vigente al consumo real reconstruido desde las comandas para calcular COGS, márgenes y pour cost. Las vistas V9 son dinámicas y pueden revalorizar operaciones anteriores cuando cambia el caché. Para preservar un costo histórico inmutable existe `analytics_cogs_historico`, alimentada por un proceso externo; sin embargo, el `snapshot_job.php` revisado todavía usa el promedio histórico descartado y debe migrarse después de definir el momento exacto de valoración y la granularidad del snapshot.

---

## 15. Veredicto técnico

El núcleo dinámico V9 y el trigger de WAC están alineados con la decisión financiera vigente. El componente que rompe la consistencia es el job histórico, que todavía utiliza el método anterior.

Por tanto:

- el WAC móvil cacheado está implementado;
- el COGS dinámico V9 usa el caché vigente;
- el snapshot existe y conserva valores inmutables una vez insertados;
- el snapshot actual no congela el mismo método de costo que usa V9;
- las vistas históricas no pueden eliminarse todas todavía porque al menos una sigue siendo dependencia del job;
- la limpieza debe comenzar después de corregir el snapshot y verificar consumidores externos.

Este documento debe actualizarse cuando se apruebe la semántica temporal del snapshot y se publique una versión corregida de `snapshot_job.php`.
