# Nota para el equipo del motor WAC (V9.44)

Redactada 2026-10-11 a partir de las pruebas en vivo en `test_pos` (ver
`01_ingreso_traspaso_recepcion.md`, secciones 3 y 5). **Enviada.** Respuesta
del equipo (2026-10-12): aplicaron la resta de la compra en
`trg_wac_alm_ingreso_after_update` y el respaldo cronológico de la anulación,
corrigieron su documentación y publicaron el instalador en su `master`
(`install_v9_full.php` / `installer_v9_master_full.sql`); ya estaba instalado en
`test_pos`. Verificación y casos borde pendientes en
`03_nota_equipo_motor_wac_seguimiento.md`. Nota: la afirmación del punto 1
sobre "dos líneas del mismo producto" resultó incorrecta (ver nota 03, punto 2).

---

**Asunto: Motor WAC V9.44 — el trigger cuenta dos veces las unidades compradas (con corrección propuesta)**

Hola equipo:

Al integrar la PWA de BackStage con el flujo de compras del POS, probamos el motor WAC V9.44 en `test_pos` (réplica de Beer Garden, con el POS instalado). Encontramos un error en el cálculo y dos diferencias con la nota técnica del 10/10.

## 1. El trigger cuenta dos veces las unidades compradas

`trg_wac_alm_ingreso_after_update` toma como stock previo lo que hay en `alm_inventario` cuando el ingreso pasa de `'0'` a `'1'`. Pero el POS **ya sumó la compra a `alm_inventario` antes de cambiar el estado**: al procesar, primero actualiza el inventario y después la cabecera. Entonces el stock "previo" incluye las unidades que se están comprando, y esas unidades pesan dos veces en el promedio. Además, la regla "sin stock previo, el WAC toma el costo nuevo" nunca se aplica en compras hechas desde el POS.

Casos medidos en `test_pos` (compras procesadas desde el POS):

| Ingreso | Producto | WAC antes | Compra | Stock previo real | WAC correcto | WAC que quedó |
|---|---|---|---|---|---|---|
| 837 | COCA COLA 3LT | 16.4818 | 6 a Bs 19 | 3.335 | 18.1004 | 17.4671 |
| 837 | HAVANA 7A 700ML | 169.2853 | 2 a Bs 135 | 0 | 135.0000 | 152.1427 |
| 838 | RED BULL LATA | 17.2157 | 4 a Bs 16 | 0 | 16.0000 | 16.6079 |
| 840 | RED BULL LATA | 16.6079 | 2 a Bs 16 | 0 | 16.0000 | 16.3040 |

En los cuatro casos, el valor que quedó es exactamente el que da la fórmula usando el stock *después* de sumar la compra. Por ejemplo, en el 838: (17.2157·4 + 16·4) / 8 = 16.6079.

**Corrección propuesta.** En el CASO 1 (`'0'` → `'1'`), restar del stock lo que este mismo ingreso ya sumó para el producto, normalizado igual que el stock:

```sql
-- Stock previo equivalente. Al pasar el ingreso a 1, alm_inventario YA incluye
-- esta compra (el POS suma el stock antes de cambiar el estado): se descuenta.
SELECT
    COALESCE(inv.cantidad_paq, 0)
  + COALESCE(inv.cantidad_detalle / NULLIF(p.cantidad_detalle, 0), 0)
  - (SELECT COALESCE(SUM(CASE WHEN d2.ind_paq_detalle = '1' THEN d2.cantidad
                              ELSE d2.cantidad / NULLIF(p.cantidad_detalle, 0) END), 0)
       FROM alm_detalle_ingreso d2
      WHERE d2.id_ingreso = NEW.id
        AND d2.id_producto = v_det_id_producto
        AND d2.estado = 'HAB')
INTO v_stock_pre_ingreso
FROM alm_inventario inv
JOIN alm_producto p ON p.id = v_det_id_producto
WHERE inv.id_producto = v_det_id_producto
  AND inv.id_almacen = NEW.id_almacen
  AND inv.estado = 'HAB'
LIMIT 1;
```

El ajuste a 0 cuando sale negativo ya está y sigue haciendo falta. La resta también cubre el caso de dos líneas del mismo producto en un ingreso, que hoy se calculan con el mismo stock previo.

**Contrato del trigger.** Conviene dejar documentado que, cuando el ingreso pasa a `'1'`, `alm_inventario` ya incluye la compra. La PWA de BackStage escribe en ese mismo orden a propósito, así que con la corrección las dos quedan bien sin otro cambio. Lo verificamos con una prueba diferencial: la misma compra por el POS (ingreso 840) y por la PWA (ingreso 842) dejó el mismo WAC.

## 2. Anulación: el respaldo de la Opción A busca la compra más cara, no la última

En el CASO 2, cuando no hay historial, el respaldo hace `SELECT MAX(di.precio_costo) … AND ai.id < NEW.id`. El comentario dice "última compra cerrada válida anterior", pero `MAX(precio_costo)` devuelve **el precio más alto** de todas las compras anteriores, no el de la última. Sugerimos tomar el precio de la línea con mayor `ai.id` (`ORDER BY ai.id DESC, di.id DESC LIMIT 1`).

## 3. La nota técnica V9.44 no coincide con el trigger

- **Stock previo:** la nota dice que pondera "el inventario físico existente en almacén y barra". El trigger solo lee `alm_inventario` del almacén del ingreso.
- **Anulación:** la matriz de casos dice que anular una compra procesada "descuenta stock". Ni el trigger ni el POS (`cancelarRecepcion`) tocan `alm_inventario`: solo se restaura el WAC.

Si lo del punto 1 es intencional, avísennos y lo ajustamos de nuestro lado. Si les sirve, les pasamos los casos de prueba con los ids de `test_pos` para validar la corrección.

Saludos,
BackStage
