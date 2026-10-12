# Nota de seguimiento para el equipo del motor WAC (V9.44)

Redactada 2026-10-12, en respuesta a "Re: Motor WAC V9.44 — correcciones
aplicadas y verificadas" (respuesta a `02_nota_equipo_motor_wac.md`).
Verificaciones hechas en `test_pos` el mismo día (ver
`01_ingreso_traspaso_recepcion.md`, sección 3). **Enviada y resuelta:** el
equipo del motor respondió el mismo día con la v9.45
(`04_respuesta_seguimiento_motor_wac.md`), que corrige los puntos 2 y 3, explica el 4 (el instalador, también
corregido) y responde el 5. Verificado en los cuatro entornos.

---

**Asunto: Re: Motor WAC V9.44 — corrección verificada en test_pos y dos casos borde pendientes**

Hola equipo:

Gracias por la respuesta rápida y por la corrección. La verificamos en `test_pos` y funciona: el doble conteo quedó resuelto. Les dejamos el resultado y dos casos borde que encontramos al revisar el trigger nuevo. El primero viene de una afirmación nuestra que no era del todo correcta.

## 1. Corrección del doble conteo: verificada

Usamos la vista previa de la PWA, que ejecuta el ingreso completo dentro de una transacción y la revierte (el WAC no queda modificado):

| Producto | Stock previo | WAC antes | Compra | Esperado | Trigger corregido | Con el error anterior |
|---|---|---|---|---|---|---|
| BEEFEATER 1LT | 4 | 217.0588 | 2 a Bs 210 | 214.7059 | **214.7059** | 215.2941 |

También revisamos la anulación: el respaldo ahora toma la última compra (`ORDER BY ai.id DESC, di.id DESC LIMIT 1`), como acordamos.

## 2. Dos líneas del mismo producto en un ingreso: todavía no queda bien

En la primera nota dijimos que la resta "también cubre el caso de dos líneas del mismo producto en un ingreso". **No es así, y la afirmación fue nuestra.** El cursor recorre las líneas de a una: la segunda línea toma el WAC ya actualizado por la primera, pero su stock previo descuenta las dos líneas, así que no incluye las unidades de la primera.

Caso medido en `test_pos` (en una transacción revertida, sin dejar rastro):

| Producto | Stock previo | WAC antes | Líneas | WAC correcto | Trigger |
|---|---|---|---|---|---|
| BEEFEATER 1LT | 4 | 217.0588 | 2 a Bs 200 + 2 a Bs 230 | 216.0294 | 217.5817 |

La PWA no permite repetir un producto en un ingreso, pero el POS sí, así que el caso puede aparecer en compras cargadas desde el POS.

**Corrección propuesta:** agregar `di.id` al cursor y descontar solo las líneas de ese producto que todavía no se procesaron (la actual y las siguientes):

```sql
DECLARE v_det_id INT;

DECLARE cur_detalles CURSOR FOR
    SELECT di.id, di.id_producto, di.cantidad, di.precio_costo
    FROM alm_detalle_ingreso di
    WHERE di.id_ingreso = NEW.id
      AND di.ind_paq_detalle = '1'
      AND di.precio_costo > 0
      AND di.estado = 'HAB'
    ORDER BY di.id;

-- ...
FETCH cur_detalles INTO v_det_id, v_det_id_producto, v_det_cantidad, v_det_precio;
-- ...

-- En el descuento del stock previo, solo la línea actual y las siguientes:
                    WHERE d2.id_ingreso = NEW.id
                      AND d2.id_producto = v_det_id_producto
                      AND d2.estado = 'HAB'
                      AND (d2.ind_paq_detalle = '0' OR d2.id >= v_det_id)
```

Las líneas en detalle (`'0'`) se siguen descontando completas, porque el cursor no las procesa. Con este cambio, el caso de arriba da 216.0294.

## 3. Producto sin fila en `alm_inventario`: el cursor termina antes de tiempo

La consulta del stock previo es un `SELECT … INTO` sobre `alm_inventario`. Si el producto no tiene fila, no devuelve filas y el `CONTINUE HANDLER FOR NOT FOUND` pone `done = TRUE`. El recorrido termina en esa línea y **las líneas siguientes del ingreso no recalculan el WAC**. Además, `v_stock_pre_ingreso` conserva el valor de la línea anterior, no queda en NULL.

Caso medido en `test_pos` (transacción revertida): un ingreso con un producto sin fila en `alm_inventario` como primera línea y RED BULL LATA como segunda. Solo se registró la primera en `cache_wac_historial`; el WAC de RED BULL no cambió.

Con el contrato actual no debería pasar, porque el POS y la PWA crean la fila de inventario antes de pasar el ingreso a `'1'`. Igual sugerimos blindarlo como hicieron en la anulación, con una subconsulta escalar:

```sql
SELECT COALESCE((
    SELECT COALESCE(inv.cantidad_paq, 0)
         + COALESCE(inv.cantidad_detalle / NULLIF(p.cantidad_detalle, 0), 0)
         - COALESCE((SELECT SUM(...) FROM alm_detalle_ingreso d2 WHERE ...), 0)
    FROM alm_inventario inv
    JOIN alm_producto p ON p.id = v_det_id_producto
    WHERE inv.id_producto = v_det_id_producto
      AND inv.id_almacen = NEW.id_almacen
      AND inv.estado = 'HAB'
    LIMIT 1
), 0) INTO v_stock_pre_ingreso;
```

## 4. Consulta: WAC reescrito en test_pos el 11/10 a las 07:35

En `test_pos`, el 2026-10-11 a las 07:35 se reescribió el WAC de los tres productos de nuestras pruebas, sin filas nuevas en `cache_wac_historial`:

| Producto | WAC antes de nuestras pruebas | WAC después de nuestras pruebas | WAC desde el 11/10 07:35 |
|---|---|---|---|
| COCA COLA 3LT | 16.4818 | 17.4671 | 16.4880 |
| HAVANA 7A 700ML | 169.2853 | 152.1427 | 169.1309 |
| RED BULL LATA | 17.2157 | 16.1520 | 17.2080 |

Suponemos que fue parte de sus pruebas de la corrección y no nos preocupa en `test_pos`. Pero si viene de un proceso del instalador, ¿nos confirman qué hace? Nos interesa saber si recalcula el WAC de productos existentes al instalarse en producción, porque los valores no coinciden exactamente con los anteriores.

## 5. Despliegue en producción

Del lado de la PWA, el módulo de ingresos exige el trigger `trg_wac_alm_ingreso_after_update`, pero solo verifica que exista: no distingue la versión original de la corregida. Antes de habilitarlo en casa matriz y en Beer Garden, ¿nos avisan cuando instalen la versión corregida en cada una?

Gracias de nuevo,
BackStage
