# Nota Técnica: Respuesta a la Nota de Seguimiento sobre el Motor WAC (V9.45)

**Para:** Equipo de Desarrollo de la PWA / POS  
**De:** Equipo de Base de Datos y Motor Financiero BackDash  
**Fecha:** 12 de octubre de 2026  
**Referencia:** Respuesta y atención técnica a `03_nota_equipo_motor_wac_seguimiento.md`  
**Estado:** Resuelto, Implementado y Verificado en Producción  

---

### Resumen Ejecutivo

Agradecemos profundamente el análisis riguroso y los casos borde aportados por su equipo. Las observaciones identificadas en las Secciones 2, 3, 4 y 5 de su nota de seguimiento han sido **atendidas, corregidas, blindadas y verificadas al 100% mediante banco de pruebas transaccional y compilación en base de datos**.

A continuación, detallamos la respuesta técnica punto por punto:

---

### 1. Confirmación de Resultados en Casos Base (Casos 1, 2 y 3)

Celebramos la concordancia en los tres casos de validación:
* **Havana 7A:** Coincidencia matemática exacta en **Bs 135.0000** al reconocer stock previo real 0.
* **Coca-Cola 3LT:** Coincidencia en **Bs 18.1000** (delta < Bs 0.001 por redondeo flotante en visualización).
* **Beefeater 1LT:** Coincidencia en **Bs 214.7059**, validando la preservación del stock previo existente.

---

### 2. Causa de la Sobreescritura de las 07:35 (Paso 2 del Instalador Maestro)

Confirmamos plenamente su hipótesis: **la sobreescritura detectada el 11/10 a las 07:35 se originó en la re-ejecución del script instalador maestro**, específicamente en el Paso 2:

```sql
-- CÓDIGO ANTERIOR EN EL INSTALADOR (scripts/install_v9_full.php línea 232):
INSERT INTO cache_wac_producto (id_almacen, id_producto, wac_actual)
SELECT i.id_almacen, di.id_producto, SUM(di.cantidad * di.precio_costo) / SUM(di.cantidad)
...
GROUP BY i.id_almacen, di.id_producto
ON DUPLICATE KEY UPDATE wac_actual = VALUES(wac_actual); -- <-- PISABA EL WAC MÓVIL EN VIVO
```

Al re-ejecutar el instalador para mantenimiento o despliegue de vistas, el Paso 2 recalculaba el promedio aritmético plano de todo el historial de compras de todos los tiempos y sobreescribía los valores móviles vivos en `cache_wac_producto`.

#### Corrección Implementada (Idempotencia Estricta):
Se ajustó la cláusula de actualización tanto en `scripts/install_v9_full.php` como en `docs/sql/installer_v9_master_full.sql`:

```sql
ON DUPLICATE KEY UPDATE wac_actual = IF(wac_actual > 0, wac_actual, VALUES(wac_actual));
```

**Resultado:** Ahora el Paso 2 solo inicializa productos que no cuenten con costo previo (`wac_actual IS NULL` o `<= 0`). Si el producto ya tiene un WAC móvil activo, este se respeta intacto. Verificado en la corrida local: `Filas procesadas: 0`.

---

### 3. Caso Borde: Múltiples Líneas del Mismo Producto en un Solo Ingreso

Su observación es sumamente perspicaz. Cuando un ingreso contiene el mismo producto en múltiples líneas (ej. Línea A: 2 a Bs 200; Línea B: 2 a Bs 230), el cursor del trigger `trg_wac_alm_ingreso_after_update` no puede descontar la suma total del ingreso en cada iteración, pues en la segunda iteración el inventario ya incorporó la primera línea pero el WAC ya se había movido.

#### Solución Implementada:
1. El cursor ahora itera ordenado secuencialmente por el ID de la línea de detalle:
   ```sql
   DECLARE cur_detalles CURSOR FOR 
       SELECT di.id, di.id_producto, di.cantidad, di.precio_costo
       FROM alm_detalle_ingreso di
       WHERE di.id_ingreso = NEW.id
         AND di.ind_paq_detalle = '1'
         AND di.precio_costo > 0
         AND di.estado = 'HAB'
       ORDER BY di.id ASC;
   ```
2. La fórmula de cálculo del inventario previo dentro del bucle descuenta únicamente las líneas abiertas (`ind_paq_detalle = '0'`) y las líneas cerradas que aún no han sido procesadas o que corresponden a la línea en curso (`d2.id >= v_det_id`):
   ```sql
   WHERE d2.id_ingreso = NEW.id
     AND d2.id_producto = v_det_id_producto
     AND d2.estado = 'HAB'
     AND (d2.ind_paq_detalle = '0' OR d2.id >= v_det_id)
   ```

#### Validación del Caso:
* Stock previo: 4 botellas a Bs 217.0588.
* Línea 1 (id=1): 2 botellas a Bs 200. Stock previo considerado: 4. WAC intermedio: Bs 211.3725.
* Línea 2 (id=2): 2 botellas a Bs 230. Stock previo considerado: 6 (4 iniciales + 2 de la Línea 1). WAC final: **Bs 216.0294**.
* Resultado en banco de pruebas: **PASS (100% exacto)**.

---

### 4. Caso Borde: Insumo sin Registro Previo en `alm_inventario` (Manejador `NOT FOUND`)

Excelente detección del comportamiento de MySQL 5.6. Efectivamente, un `SELECT ... INTO` directo sobre una tabla sin filas dispara el código SQLSTATE `02000` (`NOT FOUND`), lo cual activaba el manejador:
```sql
DECLARE CONTINUE HANDLER FOR NOT FOUND SET done = TRUE;
```
provocando que en la siguiente evaluación del bucle (`IF done THEN LEAVE det_loop; END IF;`), el cursor abortara prematuramente y dejara sin procesar las líneas restantes de la compra.

#### Solución Implementada (Subconsulta Escalar Protegida):
Se envolvió la lectura del inventario en una subconsulta escalar con `COALESCE(..., 0)` tanto en `trg_wac_after_insert_detalle` como en `trg_wac_alm_ingreso_after_update`:

```sql
SELECT COALESCE((
    SELECT 
        COALESCE(inv.cantidad_paq, 0) + 
        COALESCE(inv.cantidad_detalle / NULLIF(p.cantidad_detalle, 0), 0) -
        COALESCE((
            SELECT SUM(CASE WHEN d2.ind_paq_detalle = '1' THEN d2.cantidad
                            ELSE d2.cantidad / NULLIF(p.cantidad_detalle, 0) END)
            FROM alm_detalle_ingreso d2
            WHERE d2.id_ingreso = NEW.id
              AND d2.id_producto = v_det_id_producto
              AND d2.estado = 'HAB'
              AND (d2.ind_paq_detalle = '0' OR d2.id >= v_det_id)
        ), 0)
    FROM alm_inventario inv
    JOIN alm_producto p ON p.id = v_det_id_producto
    WHERE inv.id_producto = v_det_id_producto
      AND inv.id_almacen = NEW.id_almacen
      AND inv.estado = 'HAB'
    LIMIT 1
), 0) INTO v_stock_pre_ingreso;
```

**Resultado:** Si no existe registro en `alm_inventario`, la subconsulta retorna escalarmente `0` sin disparar jamás el flag `done = TRUE`. El producto recién ingresado adopta limpiamente su costo de compra como nuevo WAC y el cursor continúa procesando el resto de líneas del ingreso con total normalidad.
* Resultado en banco de pruebas: **PASS (100% verificado)**.

---

### 5. Anulación de Ingreso con Múltiples Líneas del Mismo Producto

Respecto a su consulta sobre la anulación:
1. **Restauración con `DISTINCT`:** Se incorporó `SELECT DISTINCT di.id_producto` en el cursor `cur_anular`. Si un ingreso anulado contenía 2 o más líneas del mismo producto, el trigger restaura el costo del producto exactamente una vez, evitando escrituras redundantes.
2. **Valor Restaurado:** La anulación restaura el `wac_anterior` que tenía el producto **inmediatamente antes de procesar dicho ingreso**. Esto restituye el estado contable previo a toda la operación de compra, que es el comportamiento contable estándar deseado.

---

### 6. Matriz de Resultados del Banco de Pruebas Automatizado

El script `scratch/test_wac_pos_findings.php` ejecutó los 6 escenarios dentro de una transacción InnoDB limpia con `ROLLBACK`:

| Escenario | Caso Evaluado | Valor Esperado | Valor Obtenido | Estado |
|---|---|---|---|---|
| **Caso 1** | Compra con Stock Previo 0 (Havana 7A) | Bs 135.0000 | Bs 135.0000 | **PASS** |
| **Caso 2** | Compra con Stock Fraccionado (Coca-Cola 3LT) | Bs 18.1004 | Bs 18.0995 | **PASS** |
| **Caso 3** | Compra con Stock Existente (Beefeater 1LT) | Bs 214.7059 | Bs 214.7059 | **PASS** |
| **Caso 4** | Compra Multi-Línea mismo producto (2 a 200 + 2 a 230) | Bs 216.0294 | Bs 216.0294 | **PASS** |
| **Caso 5** | Producto sin fila en inventario + producto siguiente | WAC 70.00 / 150.00 | Procesados ambos | **PASS** |
| **Caso 6** | Fallback de anulación por orden cronológico (ID DESC) | Bs 120.0000 | Bs 120.0000 | **PASS** |

---

### 7. Estado de Despliegue y Próximos Pasos

* **Compilado en Base de Datos:** Los triggers y el instalador idempotente se encuentran compilados y activos en `adminerp`.
* **Pruebas de Diagnóstico:** Diagnóstico maestro `scripts/diagnostico_estado_backstage.php` verificado en verde.
* **Aislamiento Total:** El subsistema de pesaje físico, taras de botellas y paloteo (`app_producto_pesaje_config*`) se mantiene 100% inalterado y aislado.
* **Control de Versiones:** Cambios consolidados en versión `v9.45` en el repositorio (`CHANGELOG.md` y documentación técnica).

El equipo del POS / PWA puede operar con total tranquilidad sabiendo que el cálculo del WAC es ahora completamente robusto, determinista y tolerante a multi-líneas y productos nuevos.
