# 📋 Documentación: Proceso de Ingresos y Salidas por Ajuste desde PWA

**Versión:** 0.2  
**Fecha:** 12 de junio de 2026  
**Proyecto:** BackStage | PWA + FastAPI + POS MySQL  
**Tema:** Igualación del inventario ideal con el inventario físico real  
**Actualización v0.2:** incorpora el diccionario real de parámetros (`master_table` / `parameter_table`) y corrige la interpretación de estados.

---

## 1. Introducción

La PWA ya permite registrar el inventario físico desde fuera del POS, poblando:

- `bar_inventario_fisico` como cabecera del inventario físico.
- `bar_detalle_fisico` como detalle de productos contados/pesados.

Con esa información, la PWA puede comparar:

```text
Inventario real físico - Inventario ideal del sistema = Diferencia
```

La siguiente etapa consiste en convertir esas diferencias en movimientos compatibles con el POS:

- Si sobra producto, registrar un **ingreso por ajuste** en `bar_ajuste` y `bar_detalle_ajuste`.
- Si falta producto, registrar una **salida / baja por ajuste** en `bar_salida_inventario` y `bar_detalle_salida_inv`.
- Luego actualizar `bar_inventario` para que el inventario en tiempo real quede igual al inventario físico.

El objetivo es que la PWA replique la lógica del POS, pero agregando controles de idempotencia y auditoría para evitar doble aplicación de ajustes.

---

## 2. Diccionario de parámetros relevante

El archivo `parametros.md` muestra que los parámetros se organizan mediante:

- `master_table`: define el grupo o familia del parámetro.
- `parameter_table`: define los valores concretos que se usan en las columnas del POS.

Para esta funcionalidad, los IDs relevantes son los siguientes.

### 2.1 Estados de solicitud de barra — `id_master = 5`

`master_table.id = 5` corresponde a `estados_solicitud`.

Estos estados se usan en el flujo observado para:

- `bar_ajuste.ind_estado_ingreso`
- `bar_salida_inventario.ind_estado_salida`

| ID parámetro | Nombre en POS | Uso recomendado en PWA |
|---:|---|---|
| `16` | `PENDIETE` | Estado inicial de cabecera de ajuste/salida. En la aplicación se puede mostrar como **PENDIENTE**, pero en base se usa el ID `16`. |
| `20` | `PROCESADO` | Estado final después de aplicar el ajuste y actualizar `bar_inventario`. |

> Nota: en la tabla aparece escrito `PENDIETE`. No conviene corregir el texto en código ni depender del nombre; la PWA debe usar el ID `16`.

### 2.2 Estados de operación — `id_master = 6`

`master_table.id = 6` corresponde a `estado_operacion`.

| ID parámetro | Nombre en POS | Interpretación operativa |
|---:|---|---|
| `22` | `EN PROCESO` | La operativa sigue vendiendo. No debe aplicarse ajuste de cierre. |
| `23` | `CERRADO` | La operativa está cerrada. Es el estado observado cuando el POS registra los ajustes. |
| `24` | `INICIO CIERRE` | Estado válido para registrar paloteo/inventario físico, pero no necesariamente para procesar ajustes definitivos. |

Recomendación para compatibilidad exacta con el POS observado:

```text
Paloteo físico: permitir en estado_operacion = 24.
Aplicación de ajustes: exigir estado_operacion = 23.
```

Esto evita que la PWA actualice `bar_inventario` mientras el POS todavía está en una fase intermedia de cierre.

### 2.3 Estado del inventario físico — `id_master = 17`

`master_table.id = 17` corresponde a `estado_registro_inventario_fisico`.

| ID parámetro | Nombre en POS | Uso recomendado |
|---:|---|---|
| `62` | `EN PROCESO` | Estado observado al crear `bar_inventario_fisico`. No debe documentarse como “Pendiente”. |
| `63` | `FINALIZADO` | Estado posible para marcar que el inventario físico ya fue cerrado/procesado, si se decide usar esta transición desde la PWA. |

Corrección importante respecto a la documentación inicial de paloteo: `estado_registro = 62` no significa `PENDIENTE`; significa `EN PROCESO`.

### 2.4 Tipo de salida de inventario — `id_master = 22`

`master_table.id = 22` corresponde a `tipo_salida_inventario`.

| ID parámetro | Nombre en POS | Campo donde aplica |
|---:|---|---|
| `76` | `MOVIMIENTO` | Movimiento normal de inventario. |
| `77` | `BAJA POR AJUSTE` | Usar en `bar_salida_inventario.ind_tipo_salida` para faltantes. |

Para salidas por ajuste generadas desde la PWA:

```text
bar_salida_inventario.ind_tipo_salida = 77
```

### 2.5 Tipo de ingreso — `id_master = 23`

`master_table.id = 23` corresponde a `tipo_ingreso`.

| ID parámetro | Nombre en POS | Observación |
|---:|---|---|
| `80` | `PROVEEDOR` | Ingreso desde proveedor. No aplica para esta funcionalidad. |
| `81` | `INGRESO POR AJUSTE` | Conceptualmente representa un ingreso por ajuste, pero en el SQL observado de `bar_ajuste` no se ve una columna `ind_tipo_ingreso`. |

Recomendación:

- Tener identificado el ID `81` como parámetro conceptual de ingreso por ajuste.
- No insertarlo en una columna incorrecta.
- Si en otra versión de la tabla existe una columna tipo `ind_tipo_ingreso`, entonces el valor lógico sería `81`.
- Para el flujo observado en `bar_ajuste`, la columna usada por el POS es `ind_tipo_movimiento = 84`.

### 2.6 Tipo de salida / movimiento — `id_master = 24`

`master_table.id = 24` corresponde a `tipo_salida`.

| ID parámetro | Nombre en POS | Campo observado |
|---:|---|---|
| `83` | `SALIDA PRODUCTO` | Se observa en otros movimientos de salida de producto. |
| `84` | `AJUSTE` | Usar en `bar_ajuste.ind_tipo_movimiento` según el SQL observado. |

Para ingresos por ajuste generados desde la PWA, mantener compatibilidad con el POS:

```text
bar_ajuste.ind_tipo_movimiento = 84
```

### 2.7 Tipo de movimiento de valoración — `id_master = 21`

`master_table.id = 21` corresponde a `tipo_movimiento_valoracion`.

| ID parámetro | Nombre en POS | Observación |
|---:|---|---|
| `74` | `INGRESO` | Parámetro de valoración. |
| `75` | `SALIDA` | Parámetro de valoración. |
| `78` | `BAJA POR AJUSTE` | Parámetro de valoración, no observado directamente en las tablas de ajuste de barra del caso 1223. |
| `79` | `INICIAL` | Parámetro de valoración. |

No usar estos IDs en `bar_ajuste.ind_estado_ingreso`, `bar_salida_inventario.ind_estado_salida`, `bar_salida_inventario.ind_tipo_salida` ni `bar_ajuste.ind_tipo_movimiento`, salvo que se implemente una capa explícita de valoración/WAC que lo requiera.

### 2.8 Documento de ingreso — `id_master = 13`

`master_table.id = 13` corresponde a `tipo_documento_ingreso`.

| ID parámetro | Nombre en POS | Observación |
|---:|---|---|
| `38` | `FACTURA` | Documento fiscal/comercial. |
| `39` | `RECIBO` | Documento recibo. |
| `40` | `OTRO` | Usado en ingresos normales observados. |
| `82` | `AJUSTE` | Conceptualmente útil si alguna tabla de ingreso de ajuste pidiera tipo de documento. |

En el SQL observado para `bar_ajuste`, no aparece una columna de tipo documento; por tanto, no debe forzarse el uso de `82` si la tabla no lo pide.

---

## 3. Evidencia observada en los SQL del POS

Los archivos SQL de la operativa `1223` muestran este flujo:

1. **Paso 3:** se registra el inventario físico. Para el producto `62` se guardó en `bar_detalle_fisico` una existencia real de `15.00` unidades y `90.00` detalle/onzas.
2. **Paso 4:** se cierra la operativa y se genera el resumen de cierre. Para el producto `62`, el descuadre queda como:
   - ideal/disponible: `16.00` unidades y `10.00` detalle.
   - físico real: `15.00` unidades y `90.00` detalle.
   - diferencia: `-1.00` unidad y `+80.00` detalle.
3. **Paso 5:** con la operativa ya cerrada, el POS registra movimientos pendientes:
   - `bar_ajuste` + `bar_detalle_ajuste` para el sobrante de `80.00` detalle.
   - `bar_salida_inventario` + `bar_detalle_salida_inv` para el faltante de `1.00` unidad.
4. **Paso 6:** el POS procesa los movimientos:
   - cambia `bar_ajuste.ind_estado_ingreso` de `16` a `20`.
   - cambia `bar_salida_inventario.ind_estado_salida` de `16` a `20`.
   - actualiza `bar_inventario` a `15.00` unidades y `90.00` detalle.
   - inserta eventos en `ope_novedades`.

Conclusión técnica: el POS no modifica la foto histórica del cierre para ocultar el descuadre. El cierre conserva la evidencia y el ajuste corrige `bar_inventario`, que es la base viva para la siguiente operativa.

---

## 4. Modelo de diferencia

Para cada producto inventariado:

```text
diferencia_paq     = fisico_paq     - ideal_paq
diferencia_detalle = fisico_detalle - ideal_detalle
```

Donde:

- `fisico_paq` y `fisico_detalle` vienen de `bar_detalle_fisico` o de la estructura calculada por la PWA.
- `ideal_paq` y `ideal_detalle` vienen del stock ideal calculado por el POS/PWA.
- Si ya existe una tabla/resumen de cierre como `bar_paloteo_cierre`, puede usarse como fuente consolidada porque contiene ideal, físico y diferencia.

### Regla de clasificación

| Diferencia | Acción | Cabecera | Detalle | Indicador cantidad | Cantidad grabada |
|---:|---|---|---|---|---:|
| `> 0` | Ingreso por ajuste | `bar_ajuste` | `bar_detalle_ajuste` | `ind_paq_detalle = '1'` para unidad/paquete; `'0'` para detalle | diferencia positiva |
| `< 0` | Salida por ajuste | `bar_salida_inventario` | `bar_detalle_salida_inv` | `ind_paq_detalle = '1'` para unidad/paquete; `'0'` para detalle | valor absoluto |
| `= 0` | Sin movimiento | — | — | — | — |

Un mismo producto puede generar ingreso y salida al mismo tiempo si una dimensión sobra y otra falta. El producto `62` lo demuestra: falta `1` botella cerrada, pero sobran `80` onzas.

### Aclaración sobre `ind_paq_detalle`

`ind_paq_detalle` no está funcionando como un FK a `parameter_table`. En los SQL observados se usa como bandera de negocio:

```text
'1' = cantidad en unidad / paquete / botella cerrada
'0' = cantidad en detalle / onzas / fracción
```

No confundir con los IDs de unidades de medida (`Oz. = 14`, `Unid. = 57`, etc.).

---

## 5. Tablas involucradas y parámetros correctos

### 5.1 `bar_ajuste`

Cabecera para ingresos por ajuste en barra.

| Campo | Valor POS observado | Parámetro | Recomendación PWA |
|---|---:|---|---|
| `fecha` | fecha actual | — | `CURDATE()` o fecha local de operación/registro. |
| `numero_documento` | `NULL` | — | Mantener `NULL`, salvo regla posterior. |
| `observaciones` | `1262026INGRESO` | — | Mantener formato compatible o usar formato trazable PWA. |
| `recepcionado_por` | nombre completo | — | Usuario administrador que confirma. |
| `ind_estado_ingreso` | `16` | `estados_solicitud.PENDIETE` | Crear pendiente. |
| `ind_tipo_movimiento` | `84` | `tipo_salida.AJUSTE` | Mantener compatibilidad con POS. |
| `id_operacion` | `NULL` | — | Mantener `NULL` si se busca compatibilidad exacta con POS observado. |
| `id_barra` | `1` | — | Barra afectada. |
| `usuario_reg` | usuario POS | — | Usuario autenticado en PWA. |
| `fecha_reg` | fecha actual | — | `CURDATE()` o `NOW()` según tipo de columna. |
| `estado` | `HAB` | — | Registro activo. |

### 5.2 `bar_detalle_ajuste`

Detalle de productos sobrantes.

| Campo | Regla |
|---|---|
| `cantidad` | Diferencia positiva. |
| `precio_costo` | `0.00` en el caso observado. |
| `precio_costo_real` | `NULL`. |
| `observaciones` | `NULL` o texto breve. |
| `ind_paq_detalle` | `'1'` para unidad/paquete; `'0'` para detalle. |
| `id_ajuste` | FK a `bar_ajuste.id`. |
| `id_producto` | Producto afectado. |
| `usuario_reg` | Usuario autenticado. |
| `fecha_reg` | Fecha actual. |
| `estado` | `HAB`. |

### 5.3 `bar_salida_inventario`

Cabecera para salidas o bajas por ajuste en barra.

| Campo | Valor POS observado | Parámetro | Recomendación PWA |
|---|---:|---|---|
| `fecha_salida` | fecha actual | — | `CURDATE()` o fecha local de operación/registro. |
| `correlativo` | `NULL` | — | Mantener `NULL`, salvo regla posterior. |
| `responsable` | nombre completo | — | Usuario administrador que confirma. |
| `ind_estado_salida` | `16` | `estados_solicitud.PENDIETE` | Crear pendiente. |
| `observaciones_salida` | `1262026SALIDA` | — | Mantener formato compatible o trazable PWA. |
| `fecha_recepcion` | `NULL` | — | Mantener `NULL`. |
| `observaciones_recepcion` | `NULL` | — | Mantener `NULL`. |
| `responsable_recepcion` | `NULL` | — | Mantener `NULL`. |
| `id_almacen` | `NULL` | — | Mantener `NULL` para ajuste de barra. |
| `id_barra` | `1` | — | Barra afectada. |
| `id_operacion` | `NULL` | — | Mantener `NULL` si se busca compatibilidad exacta con POS observado. |
| `ind_tipo_salida` | `77` | `tipo_salida_inventario.BAJA POR AJUSTE` | Usar para faltantes. |
| `usuario_reg` | usuario POS | — | Usuario autenticado en PWA. |
| `fecha_reg` | fecha actual | — | `CURDATE()` o `NOW()` según tipo de columna. |
| `estado` | `HAB` | — | Registro activo. |

### 5.4 `bar_detalle_salida_inv`

Detalle de productos faltantes.

| Campo | Regla |
|---|---|
| `cantidad` | Valor absoluto de la diferencia negativa. |
| `ind_paq_detalle` | `'1'` para unidad/paquete; `'0'` para detalle. |
| `id_salida_inventario` | FK a `bar_salida_inventario.id`. |
| `id_producto` | Producto afectado. |
| `usuario_reg` | Usuario autenticado. |
| `fecha_reg` | Fecha actual. |
| `estado` | `HAB`. |

### 5.5 `bar_inventario`

Tabla viva de stock en barra. Después de procesar los ajustes, debe quedar igual al físico real.

La actualización más segura es asignar el valor final físico:

```sql
UPDATE bar_inventario
SET cantidad_paq = :fisico_paq,
    cantidad_detalle = :fisico_detalle,
    fecha_mod = NOW()
WHERE id_barra = :id_barra
  AND id_producto = :id_producto
  AND estado = 'HAB';
```

Esto es preferible a sumar/restar diferencias, porque evita errores por reintentos, redondeos o doble clics nerviosos de esos que convierten una Coca Cola en multiverso contable.

### 5.6 `ope_novedades`

El POS registra eventos después de procesar los ajustes. La PWA debería insertar eventos equivalentes para mantener trazabilidad visible desde el ecosistema POS.

Eventos compatibles:

```text
Se registró un Ajuste en Barra: BARRA {id_barra}, con el correlativo NRO  {id_ajuste} en fecha: {dd/mm/yyyy}
```

```text
Se registró una baja por ajuste de la barra: BARRA {id_barra}, con el correlativo NRO  {id_salida} en fecha: {dd/mm/yyyy}
```

---

## 6. Flujo recomendado para FastAPI

### 6.1 Endpoint de preview

Antes de aplicar, la PWA debe mostrar una vista previa:

```http
GET /api/inventario/ajustes/preview?id_operacion=1223&id_barra=1&id_inventario_fisico=577
```

Debe devolver:

- productos con diferencia;
- si generan ingreso, salida o ambos;
- cantidades por unidad/detalle;
- valor final que quedará en `bar_inventario`;
- advertencias de parámetros o estados.

### 6.2 Endpoint de aplicación

```http
POST /api/inventario/ajustes/aplicar
```

Payload sugerido:

```json
{
  "id_operacion": 1223,
  "id_barra": 1,
  "id_inventario_fisico": 577,
  "modo": "generar_y_procesar",
  "observaciones": "Ajuste generado desde PWA tras paloteo físico"
}
```

Respuesta sugerida:

```json
{
  "status": "success",
  "id_operacion": 1223,
  "id_barra": 1,
  "id_inventario_fisico": 577,
  "id_ajuste": 644,
  "id_salida_inventario": 698,
  "estado_inicial_movimientos": 16,
  "estado_final_movimientos": 20,
  "productos_ajustados": 1,
  "detalles": [
    {
      "id_producto": 62,
      "ideal_paq": 16,
      "ideal_detalle": 10,
      "fisico_paq": 15,
      "fisico_detalle": 90,
      "diferencia_paq": -1,
      "diferencia_detalle": 80,
      "acciones": [
        {
          "tipo": "salida_por_ajuste",
          "tabla": "bar_detalle_salida_inv",
          "ind_paq_detalle": "1",
          "cantidad": 1,
          "ind_tipo_salida": 77
        },
        {
          "tipo": "ingreso_por_ajuste",
          "tabla": "bar_detalle_ajuste",
          "ind_paq_detalle": "0",
          "cantidad": 80,
          "ind_tipo_movimiento": 84
        }
      ],
      "stock_final_bar_inventario": {
        "cantidad_paq": 15,
        "cantidad_detalle": 90
      }
    }
  ]
}
```

---

## 7. Algoritmo backend recomendado

### Paso 1: Validaciones

Validar:

1. Token JWT válido.
2. Usuario activo.
3. `bar_inventario_fisico` existe para `id_operacion`, `id_barra`, `estado='HAB'`.
4. `bar_inventario_fisico.estado_registro` está en un estado permitido. Con parámetros actuales:
   - `62 = EN PROCESO` puede ser permitido si el inventario físico aún no fue finalizado.
   - `63 = FINALIZADO` puede ser exigido si se decide cerrar formalmente el inventario antes del ajuste.
5. `ope_operacion.estado_operacion != 22` siempre.
6. Para compatibilidad estricta con el POS observado, exigir `ope_operacion.estado_operacion = 23` antes de aplicar ajustes.
7. No existe un ajuste PWA ya aplicado para el mismo `id_operacion`, `id_barra`, `id_inventario_fisico`.
8. Existen filas en `bar_inventario` para todos los productos afectados.
9. Existen diferencias distintas de cero.

### Paso 2: Obtener diferencias

Fuente recomendada si existe resumen POS:

```sql
SELECT
    id_producto,
    actual_paq,
    actual_detalle,
    fisico_paq,
    fisico_detalle,
    diferencia_paq,
    diferencia_detalle
FROM bar_paloteo_cierre
WHERE id_operacion = :id_operacion
  AND id_barra = :id_barra
  AND estado = 'HAB'
  AND (diferencia_paq <> 0 OR diferencia_detalle <> 0);
```

Fuente alternativa si la PWA aún no genera/lee `bar_paloteo_cierre`:

- usar el stock ideal calculado por la PWA;
- cruzarlo con `bar_detalle_fisico`;
- calcular `fisico - ideal` con la misma regla del reporte POS.

### Paso 3: Separar ingresos y salidas

```python
if diferencia_paq > 0:
    ingresos.append(producto, "1", diferencia_paq)
elif diferencia_paq < 0:
    salidas.append(producto, "1", abs(diferencia_paq))

if diferencia_detalle > 0:
    ingresos.append(producto, "0", diferencia_detalle)
elif diferencia_detalle < 0:
    salidas.append(producto, "0", abs(diferencia_detalle))
```

### Paso 4: Iniciar transacción y bloquear stock

```sql
START TRANSACTION;

SELECT id, id_producto, cantidad_paq, cantidad_detalle
FROM bar_inventario
WHERE id_barra = :id_barra
  AND id_producto IN (...)
  AND estado = 'HAB'
FOR UPDATE;
```

### Paso 5: Crear cabeceras pendientes

Crear `bar_ajuste` solo si hay ingresos.

```text
bar_ajuste.ind_estado_ingreso = 16
bar_ajuste.ind_tipo_movimiento = 84
```

Crear `bar_salida_inventario` solo si hay salidas.

```text
bar_salida_inventario.ind_estado_salida = 16
bar_salida_inventario.ind_tipo_salida = 77
```

### Paso 6: Crear detalles

Insertar una fila por cada diferencia positiva en `bar_detalle_ajuste`.

Insertar una fila por cada diferencia negativa en `bar_detalle_salida_inv`.

### Paso 7: Procesar movimientos

```sql
UPDATE bar_ajuste
SET ind_estado_ingreso = 20
WHERE id = :id_ajuste;

UPDATE bar_salida_inventario
SET ind_estado_salida = 20
WHERE id = :id_salida_inventario;
```

### Paso 8: Actualizar `bar_inventario`

```sql
UPDATE bar_inventario
SET cantidad_paq = :fisico_paq,
    cantidad_detalle = :fisico_detalle,
    fecha_mod = NOW()
WHERE id_barra = :id_barra
  AND id_producto = :id_producto
  AND estado = 'HAB';
```

### Paso 9: Opcionalmente finalizar inventario físico

Si se decide que la PWA debe cerrar formalmente el ciclo de paloteo:

```sql
UPDATE bar_inventario_fisico
SET estado_registro = 63,
    fecha_mod = CURDATE()
WHERE id = :id_inventario_fisico
  AND id_operacion = :id_operacion
  AND id_barra = :id_barra
  AND estado = 'HAB';
```

Esta decisión debe confirmarse porque en el SQL analizado no se observó una actualización explícita de `estado_registro` de `62` a `63`.

### Paso 10: Registrar novedades y auditoría PWA

Insertar eventos en `ope_novedades` y registrar control interno en una tabla de idempotencia PWA.

### Paso 11: Commit o rollback

```sql
COMMIT;
```

Si algo falla:

```sql
ROLLBACK;
```

---

## 8. Ejemplo completo: producto 62 Coca Cola 3LT

### Datos base

```text
Producto: 62
Ideal: 16 unidades + 10 onzas
Físico: 15 unidades + 90 onzas
Diferencia unidades: 15 - 16 = -1
Diferencia detalle: 90 - 10 = +80
```

### Movimiento de salida por ajuste

Cabecera:

```text
Tabla: bar_salida_inventario
ind_estado_salida = 16   -- estados_solicitud.PENDIETE
ind_tipo_salida   = 77   -- tipo_salida_inventario.BAJA POR AJUSTE
id_barra = 1
id_operacion = NULL, siguiendo patrón observado del POS
estado = HAB
```

Detalle:

```text
Tabla: bar_detalle_salida_inv
cantidad = 1.00
ind_paq_detalle = '1'
id_producto = 62
estado = HAB
```

### Movimiento de ingreso por ajuste

Cabecera:

```text
Tabla: bar_ajuste
ind_estado_ingreso  = 16  -- estados_solicitud.PENDIETE
ind_tipo_movimiento = 84  -- tipo_salida.AJUSTE, según POS observado
id_barra = 1
id_operacion = NULL, siguiendo patrón observado del POS
estado = HAB
```

Detalle:

```text
Tabla: bar_detalle_ajuste
cantidad = 80.00
ind_paq_detalle = '0'
id_producto = 62
precio_costo = 0.00
estado = HAB
```

### Procesamiento

```text
bar_ajuste.ind_estado_ingreso = 20
bar_salida_inventario.ind_estado_salida = 20
bar_inventario.cantidad_paq = 15.00
bar_inventario.cantidad_detalle = 90.00
```

Resultado: el inventario vivo del sistema queda igualado al inventario físico real.

---

## 9. Idempotencia y auditoría PWA

El POS observado no deja un vínculo directo entre:

- `bar_inventario_fisico`,
- `bar_ajuste`,
- `bar_salida_inventario`,
- y la ejecución automática desde PWA.

Para evitar doble aplicación de ajustes, se recomienda agregar una tabla propia de control:

```sql
CREATE TABLE app_paloteo_ajuste_control (
    id INT NOT NULL AUTO_INCREMENT,
    id_operacion INT NOT NULL,
    id_barra INT NOT NULL,
    id_inventario_fisico INT NOT NULL,
    id_ajuste INT DEFAULT NULL,
    id_salida_inventario INT DEFAULT NULL,
    estado VARCHAR(20) NOT NULL,
    payload_json TEXT DEFAULT NULL,
    usuario_reg VARCHAR(255) NOT NULL,
    fecha_reg DATETIME NOT NULL,
    fecha_mod DATETIME DEFAULT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_paloteo_ajuste_unico (id_operacion, id_barra, id_inventario_fisico)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;
```

Estados sugeridos para esta tabla PWA:

```text
PREVIEW_GENERADO
APLICANDO
APLICADO
ERROR
ANULADO
```

Estos estados son propios de la PWA y no deben confundirse con `parameter_table`, salvo que luego se decida crear parámetros oficiales para esta tabla.

---

## 10. Recomendación de constantes backend

Aunque se pueden hardcodear IDs inicialmente, lo más sano es centralizarlos.

```python
class ParametroPOS:
    # master 5: estados_solicitud
    ESTADO_SOLICITUD_PENDIENTE = 16   # texto en DB: PENDIETE
    ESTADO_SOLICITUD_PROCESADO = 20

    # master 6: estado_operacion
    OPERACION_EN_PROCESO = 22
    OPERACION_CERRADO = 23
    OPERACION_INICIO_CIERRE = 24

    # master 17: estado_registro_inventario_fisico
    INVENTARIO_FISICO_EN_PROCESO = 62
    INVENTARIO_FISICO_FINALIZADO = 63

    # master 22: tipo_salida_inventario
    TIPO_SALIDA_INVENTARIO_BAJA_AJUSTE = 77

    # master 23: tipo_ingreso
    TIPO_INGRESO_AJUSTE = 81  # conceptual; no observado en bar_ajuste del caso 1223

    # master 24: tipo_salida
    TIPO_SALIDA_AJUSTE = 84   # usado en bar_ajuste.ind_tipo_movimiento
```

Mejor aún: validar estos IDs contra `parameter_table` al iniciar la aplicación o en un endpoint administrativo de diagnóstico.

Consulta de diagnóstico:

```sql
SELECT id, nombre, id_master, estado
FROM parameter_table
WHERE id IN (16, 20, 22, 23, 24, 62, 63, 77, 81, 84)
ORDER BY id;
```

---

## 11. Pseudocódigo FastAPI / SQLAlchemy

```python
@router.post("/api/inventario/ajustes/aplicar")
def aplicar_ajustes(payload: AplicarAjustesRequest, db: Session, user=Depends(get_user)):
    validar_usuario(user)

    operacion = obtener_operacion(db, payload.id_operacion)

    if operacion.estado_operacion == ParametroPOS.OPERACION_EN_PROCESO:
        raise HTTPException(
            status_code=409,
            detail="No se puede ajustar mientras la operativa está en proceso"
        )

    # Compatibilidad estricta con el flujo POS observado.
    if operacion.estado_operacion != ParametroPOS.OPERACION_CERRADO:
        raise HTTPException(
            status_code=409,
            detail="Para aplicar ajustes automáticos, la operativa debe estar cerrada"
        )

    inventario = obtener_inventario_fisico(db, payload.id_inventario_fisico)

    if inventario.estado_registro not in (
        ParametroPOS.INVENTARIO_FISICO_EN_PROCESO,
        ParametroPOS.INVENTARIO_FISICO_FINALIZADO,
    ):
        raise HTTPException(409, "Estado de inventario físico no permitido")

    validar_no_aplicado_previamente(db, payload)

    diferencias = obtener_diferencias(
        db,
        payload.id_operacion,
        payload.id_barra,
        payload.id_inventario_fisico,
    )

    ingresos, salidas = clasificar_diferencias(diferencias)

    with db.begin():
        bloquear_bar_inventario(
            db,
            payload.id_barra,
            [d.id_producto for d in diferencias],
        )

        id_ajuste = None
        if ingresos:
            id_ajuste = crear_bar_ajuste(
                db,
                payload,
                user,
                ind_estado_ingreso=ParametroPOS.ESTADO_SOLICITUD_PENDIENTE,
                ind_tipo_movimiento=ParametroPOS.TIPO_SALIDA_AJUSTE,
            )
            crear_detalles_ajuste(db, id_ajuste, ingresos, user)

        id_salida = None
        if salidas:
            id_salida = crear_bar_salida_inventario(
                db,
                payload,
                user,
                ind_estado_salida=ParametroPOS.ESTADO_SOLICITUD_PENDIENTE,
                ind_tipo_salida=ParametroPOS.TIPO_SALIDA_INVENTARIO_BAJA_AJUSTE,
            )
            crear_detalles_salida(db, id_salida, salidas, user)

        if id_ajuste:
            procesar_bar_ajuste(
                db,
                id_ajuste,
                nuevo_estado=ParametroPOS.ESTADO_SOLICITUD_PROCESADO,
            )

        if id_salida:
            procesar_bar_salida(
                db,
                id_salida,
                nuevo_estado=ParametroPOS.ESTADO_SOLICITUD_PROCESADO,
            )

        for d in diferencias:
            actualizar_bar_inventario_a_fisico(
                db,
                id_barra=payload.id_barra,
                id_producto=d.id_producto,
                cantidad_paq=d.fisico_paq,
                cantidad_detalle=d.fisico_detalle,
            )

        registrar_novedades(db, payload, id_ajuste, id_salida, user)
        registrar_control_pwa(db, payload, id_ajuste, id_salida, diferencias, user)

        # Opcional, pendiente de decisión funcional.
        # finalizar_inventario_fisico(db, payload.id_inventario_fisico)

    return respuesta_ok(...)
```

---

## 12. Consultas útiles de verificación

### 12.1 Ver parámetros críticos

```sql
SELECT
    p.id,
    p.nombre,
    p.descripcion,
    p.id_master,
    m.nombre AS master_nombre,
    p.estado
FROM parameter_table p
JOIN master_table m ON m.id = p.id_master
WHERE p.id IN (16, 20, 22, 23, 24, 62, 63, 77, 81, 84)
ORDER BY p.id;
```

### 12.2 Ver diferencias pendientes

```sql
SELECT
    id_producto,
    actual_paq,
    actual_detalle,
    fisico_paq,
    fisico_detalle,
    diferencia_paq,
    diferencia_detalle
FROM bar_paloteo_cierre
WHERE id_operacion = :id_operacion
  AND id_barra = :id_barra
  AND estado = 'HAB'
  AND (diferencia_paq <> 0 OR diferencia_detalle <> 0);
```

### 12.3 Ver stock actual antes/después

```sql
SELECT
    id,
    id_barra,
    id_producto,
    cantidad_paq,
    cantidad_detalle,
    fecha_mod
FROM bar_inventario
WHERE id_barra = :id_barra
  AND id_producto IN (...)
  AND estado = 'HAB';
```

### 12.4 Ver ingresos por ajuste generados

```sql
SELECT *
FROM bar_ajuste
WHERE id_barra = :id_barra
  AND fecha = CURDATE()
  AND ind_estado_ingreso IN (16, 20)
  AND ind_tipo_movimiento = 84
ORDER BY id DESC;
```

### 12.5 Ver salidas por ajuste generadas

```sql
SELECT *
FROM bar_salida_inventario
WHERE id_barra = :id_barra
  AND fecha_salida = CURDATE()
  AND ind_estado_salida IN (16, 20)
  AND ind_tipo_salida = 77
ORDER BY id DESC;
```

---

## 13. Decisiones pendientes a confirmar

1. **Momento exacto para aplicar ajustes.**  
   Recomendación técnica: aplicar solo con `ope_operacion.estado_operacion = 23` (`CERRADO`). El paloteo se hace en `24`, pero el ajuste definitivo debería quedar después del cierre.

2. **Transición de `bar_inventario_fisico.estado_registro`.**  
   El SQL observado crea la cabecera con `62 = EN PROCESO`. Falta confirmar si la PWA debe actualizar a `63 = FINALIZADO` después de aplicar ajustes.

3. **Formato de observaciones.**  
   Opciones:
   - Compatible POS: `1262026INGRESO` / `1262026SALIDA`.
   - Más trazable PWA: `PWA-PALOTEO-1223-577-INGRESO` / `PWA-PALOTEO-1223-577-SALIDA`.

4. **Uso del parámetro `81 = INGRESO POR AJUSTE`.**  
   Conceptualmente corresponde a ingreso por ajuste, pero no aparece en el insert observado de `bar_ajuste`. Si la estructura real de `bar_ajuste` no tiene `ind_tipo_ingreso`, no debe usarse ahí.

5. **Origen oficial de diferencias.**  
   Usar `bar_paloteo_cierre` si existe y refleja exactamente el reporte POS. Si no, usar el cálculo PWA validado contra el PDF.

6. **Permisos de usuario.**  
   Definir si solo Administrador/Gerencia pueden aplicar ajustes, aunque Barman pueda registrar el físico.

---

## 14. Conclusión

La implementación desde la PWA debe replicar la lógica del POS en dos etapas internas:

1. Registrar movimientos de ajuste en estado `16` (`PENDIETE` en la tabla de parámetros).
2. Procesarlos a estado `20` (`PROCESADO`) y actualizar `bar_inventario` al valor físico final.

Los IDs clave para mantener compatibilidad son:

```text
16 = PENDIETE / pendiente de procesamiento
20 = PROCESADO
22 = EN PROCESO, operación vendiendo
23 = CERRADO, operación cerrada
24 = INICIO CIERRE, etapa de paloteo
62 = EN PROCESO, inventario físico abierto/en proceso
63 = FINALIZADO, inventario físico finalizado
77 = BAJA POR AJUSTE, salida de inventario
81 = INGRESO POR AJUSTE, parámetro conceptual de tipo ingreso
84 = AJUSTE, usado por POS en bar_ajuste.ind_tipo_movimiento
```

El punto más importante es no modificar la foto histórica del cierre para “hacer que cuadre”. El cierre muestra el descuadre; el ajuste corrige el inventario vivo. Esa separación es sana, auditable y compatible con el comportamiento del POS.
