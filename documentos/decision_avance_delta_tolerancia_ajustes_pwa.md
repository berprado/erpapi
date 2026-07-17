# Documento de decisión: delta exacto, delta operativo y tolerancia en ajustes de inventario

> ## ⚠️ DOCUMENTO HISTÓRICO — PROPUESTA DESCARTADA (superseded por v10.39)
>
> **Este documento NO describe el comportamiento del sistema y su recomendación NO se implementó.**
> Se conserva únicamente como registro del análisis que llevó a la decisión contraria.
> Para el comportamiento vigente, ver **`documentos/redondeo_y_tolerancia.md`**.
>
> **Qué proponía:** grilla legacy de `0.25` para categorías distintas de VINOS/MEZCLADORES,
> límite inclusivo `<=` para esas categorías, y una tabla nueva `app_ajuste_paloteo_auditoria`
> para registrar el residuo de cuantización (secciones 4, 6, 7 y 8).
>
> **Qué se hizo en su lugar (v10.39, commit `d9e2e20`, 2026-07-01):** se unificó la tolerancia
> a **0.5 oz para todos los productos pesables**, se eliminó la distinción por categoría, se
> mantuvo el límite estricto `<` y **no** se creó la tabla de auditoría propuesta.
>
> **Por qué se descartó:** la premisa central de este documento (sección 3.2 — que
> `delta_det_exacto` puede valer `0.26`, `0.30`, `0.3333`…) es empíricamente falsa.
> `real_det` sale del paloteo ya redondeado a la grilla de 0.5, e `ideal_det` se escribe en
> `bar_inventario` desde ese mismo `real_det` en cada cierre; la resta de dos múltiplos de 0.5
> es siempre múltiplo de 0.5. Verificación en BD: de 217 filas pesables activas en
> `bar_inventario`, **cero** están fuera de la grilla de 0.5. Sin deltas fraccionarios, la
> distorsión que la grilla `0.25` venía a corregir no puede ocurrir, y toda la maquinaria
> propuesta (doble grilla, `<=` vs `<`, tabla de auditoría, `residuo_cuantizacion`) administraría
> un residuo que siempre vale cero. La distorsión que motivó el análisis se había observado sólo
> sobre datos sintéticos (operativa de prueba 1239, delta de 0.25 oz cargado a mano).
>
> **Qué sí sigue vigente de este documento:** los principios de la sección 3.1 (no modificar
> estructuralmente las tablas legacy del POS) y de la sección 5 (`bar_inventario` debe quedar
> igualado al físico final — hoy el código lo cumple sólo para productos que generan ajuste;
> ver el pendiente en `TODO.md`).

**Proyecto:** BackStage | PWA + FastAPI + POS MySQL 5.6  
**Tema:** Cómo avanzar con el pendiente de redondeo/tolerancia en ingresos y salidas por ajuste  
**Versión propuesta:** 0.1  
**Estado:** ❌ Descartada — ver aviso arriba  
**Fecha:** 2026-07-01  

---

## 1. Objetivo del documento

Este documento sirve para tomar una decisión técnica y funcional sobre cómo debe avanzar la PWA al convertir diferencias de paloteo físico en movimientos de ajuste compatibles con el POS legacy.

La decisión se concentra en tres preguntas:

1. Si el comprobante de ajuste debe guardar `delta_det_exacto` o `delta_det_operativo`.
2. Si esa decisión afecta a `bar_inventario` o sólo al comprobante/auditoría.
3. Si la regla de tolerancia debe seguir usando límite estricto `<` o pasar a límite inclusivo `<=`.

Además, incorpora una restricción clave del proyecto:

> Las tablas legacy del POS no deben modificarse estructuralmente y no deben recibir valores que no respeten la granularidad histórica permitida. En particular, los valores escritos en tablas legacy deben ser múltiplos de `0.25`.

---

## 2. Contexto resumido

La PWA compara el inventario físico real contra el inventario ideal del POS:

```text
Delta = Físico real - Ideal POS
```

Cuando el delta es positivo, se genera un **ingreso por ajuste**.  
Cuando el delta es negativo, se genera una **salida / baja por ajuste**.

Las tablas legacy involucradas son:

- `bar_ajuste`
- `bar_detalle_ajuste`
- `bar_salida_inventario`
- `bar_detalle_salida_inv`
- `bar_inventario`

La PWA debe integrarse con esas tablas sin cambiar su estructura.

---

## 3. Principios que deben guiar la decisión

### 3.1 No modificar tablas legacy

No se deben agregar columnas a tablas históricas del POS sólo para resolver trazabilidad fina de la PWA.

Esto aplica especialmente a:

- `bar_detalle_ajuste`
- `bar_detalle_salida_inv`
- `bar_inventario`

Si necesitamos guardar información nueva, debe ir en una tabla propia de la PWA.

---

### 3.2 No escribir valores arbitrarios en legacy

El `delta_det_exacto` puede tener valores como:

```text
0.26 oz
0.30 oz
0.3333 oz
0.41 oz
```

Esos valores pueden ser útiles para auditoría, pero **no deben escribirse crudos** en tablas legacy si no son múltiplos de `0.25`.

Por tanto:

```text
Correcto para legacy: 0.25, 0.50, 0.75, 1.00...
Incorrecto para legacy: 0.26, 0.30, 0.3333, 0.41...
```

---

### 3.3 Separar cálculo, documentación legacy y auditoría PWA

Para evitar confusión, conviene manejar tres conceptos distintos:

| Concepto | Qué representa | Dónde debería vivir |
|---|---|---|
| `delta_det_exacto` | Diferencia matemática real: físico - ideal | Cálculo interno y auditoría PWA |
| `delta_det_legacy` | Cantidad compatible con POS que se escribe en detalle de ajuste/salida | Tablas legacy POS |
| `stock_final_fisico` | Saldo físico final que debe quedar en `bar_inventario` | `bar_inventario` |

Esta separación evita mezclar “lo que realmente se detectó”, “lo que el POS puede documentar” y “cómo debe quedar el stock vivo”.

---

## 4. Respuesta a la pregunta 1

### Pregunta

¿El comprobante de auditoría (`bar_detalle_ajuste` / `bar_detalle_salida_inv`) debería guardar `delta_det_exacto` en vez de `delta_det_operativo` cuando la tolerancia de la categoría es `0.25 oz`?

### Respuesta recomendada

**No debe guardar el `delta_det_exacto` crudo directamente en tablas legacy.**

La razón es que el `delta_det_exacto` puede no ser múltiplo de `0.25`, y las tablas legacy no deben recibir valores arbitrarios.

La decisión recomendada es:

```text
Tablas legacy POS:
    guardar delta compatible con grilla legacy.

Tabla auditoría PWA:
    guardar delta exacto + delta legacy + regla aplicada.
```

### Propuesta concreta

Para productos pesables con tolerancia `0.25 oz`, el monto que se escribe en legacy debería ser:

```text
delta_det_legacy = delta_det_exacto cuantizado a múltiplos de 0.25
```

No a múltiplos de `0.5`, porque ahí aparece la distorsión detectada: una diferencia pequeña en categorías sensibles puede quedar documentada como el doble.

Ejemplo:

| Delta exacto | Regla actual 0.5 | Propuesta legacy 0.25 |
|---:|---:|---:|
| `+0.26` | `+0.50` | `+0.25` |
| `+0.30` | `+0.50` | `+0.25` |
| `+0.39` | `+0.50` | `+0.50` |
| `-0.30` | `-0.50` | `-0.25` |

Para VINOS y MEZCLADORES, donde `0.5 oz` funciona como paso operativo real, se puede mantener grilla `0.5` para evitar cambiar el comportamiento de categorías que no presentan la misma distorsión.

### Decisión práctica

Crear o ajustar una función explícita:

```python
def cuantizar_a_grilla_half_up(valor: Decimal, grilla: Decimal) -> Decimal:
    return (valor / grilla).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * grilla
```

Y usar una grilla según categoría:

```python
if categoria in {6, 22}:       # VINOS, MEZCLADORES
    grilla_legacy = Decimal("0.50")
else:
    grilla_legacy = Decimal("0.25")
```

La grilla `0.25` respeta la restricción legacy y reduce la sobre-documentación.

---

## 5. Respuesta a la pregunta 2

### Pregunta

Si se cambia la forma de documentar el delta, ¿afecta a `bar_inventario` o sólo al texto/monto del comprobante?

### Respuesta recomendada

**No debe afectar a `bar_inventario`.**

`bar_inventario` debe seguir quedando igual al inventario físico final:

```sql
UPDATE bar_inventario
SET cantidad_paq = :fisico_paq,
    cantidad_detalle = :fisico_detalle,
    fecha_mod = NOW()
WHERE id_barra = :id_barra
  AND id_producto = :id_producto
  AND estado = 'HAB';
```

Esto es importante porque `bar_inventario` representa el stock vivo para la siguiente operativa. Su función no es “contar la historia del ajuste”, sino quedar sincronizado con la realidad física.

### Qué sí cambia

Cambiaría el monto que se escribe en:

- `bar_detalle_ajuste.cantidad`
- `bar_detalle_salida_inv.cantidad`

Y también cambiaría lo que se muestra en el preview de ajustes.

### Qué debe registrar la PWA

Como puede existir una pequeña diferencia entre `delta_det_exacto` y `delta_det_legacy`, la PWA debe registrar trazabilidad propia.

Ejemplo:

```text
Ideal POS:            10.20 oz
Físico real:          10.50 oz
Delta exacto:         +0.30 oz
Delta legacy:         +0.25 oz
Stock final físico:   10.50 oz
Residuo cuantización: +0.05 oz
```

Ese residuo no debe asustarnos, pero debe quedar explicado. El sistema no se está contradiciendo; está adaptando el movimiento legacy a una grilla permitida.

---

## 6. Respuesta a la pregunta 3

### Pregunta

¿Conviene mantener el límite estricto `<` o cambiar a `<=`?

### Respuesta recomendada

**Conviene aplicar `<=` para categorías con tolerancia `0.25 oz`.**

La razón es funcional: si la tolerancia es `0.25`, entonces una diferencia exactamente igual a `0.25` debería interpretarse como dentro del margen tolerado.

Regla recomendada para categorías sensibles:

```python
if abs(delta_det_exacto) <= tolerancia_oz:
    delta_det_legacy = Decimal("0.00")
else:
    delta_det_legacy = cuantizar_a_grilla_half_up(delta_det_exacto, grilla_legacy)
```

Con esto:

| Delta exacto | Tolerancia | Resultado |
|---:|---:|---|
| `+0.24` | `0.25` | No ajusta |
| `+0.25` | `0.25` | No ajusta |
| `+0.26` | `0.25` | Ajusta |

### Cuidado con VINOS y MEZCLADORES

Para categorías con tolerancia `0.5 oz`, hay que decidir si un delta exacto de `0.5` debe considerarse ruido o ajuste real.

Como en VINOS y MEZCLADORES `0.5 oz` se considera paso operativo real, recomiendo no cambiar esa categoría sin validación funcional.

Por tanto, la implementación más segura es:

```text
Categorías con tolerancia 0.25:
    usar <=

VINOS / MEZCLADORES con tolerancia 0.5:
    mantener < inicialmente, salvo decisión funcional contraria
```

Esto reduce el riesgo de regresión y ataca directamente el problema detectado en categorías donde la distorsión sí aparece.

---

## 7. Decisión recomendada consolidada

La ruta recomendada para avanzar es:

1. **No modificar tablas legacy del POS.**
2. **No escribir deltas exactos crudos en tablas legacy.**
3. **Crear una tabla PWA de auditoría para guardar el delta exacto.**
4. **Cambiar la cuantización de ajuste para categorías con tolerancia `0.25 oz`:** usar grilla legacy `0.25` en vez de `0.5`.
5. **Cambiar la regla del límite a `<=` para categorías con tolerancia `0.25 oz`.**
6. **Mantener `bar_inventario` igualado al físico final.**
7. **Mantener para VINOS/MEZCLADORES la lógica actual hasta confirmar si `0.5 oz` exacto debe seguir generando ajuste.**

En una frase:

> El POS legacy recibe sólo valores que entiende; la PWA guarda la verdad fina para auditoría.

---

## 8. Propuesta de tabla de auditoría PWA

Tabla sugerida: `app_ajuste_paloteo_auditoria`

```sql
CREATE TABLE app_ajuste_paloteo_auditoria (
    id INT(11) NOT NULL AUTO_INCREMENT,

    id_operacion INT(11) NOT NULL,
    id_barra INT(11) NOT NULL,
    id_inventario_fisico INT(11) DEFAULT NULL,
    id_producto INT(11) NOT NULL,

    ind_paq_detalle CHAR(1) NOT NULL COMMENT '1=unidad/paquete, 0=detalle/onzas',
    tipo_accion VARCHAR(30) NOT NULL COMMENT 'INGRESO_AJUSTE, SALIDA_AJUSTE, SIN_MOVIMIENTO',

    ideal_paq DECIMAL(10,2) DEFAULT NULL,
    ideal_detalle DECIMAL(10,4) DEFAULT NULL,
    fisico_paq DECIMAL(10,2) DEFAULT NULL,
    fisico_detalle DECIMAL(10,4) DEFAULT NULL,

    delta_paq_exacto DECIMAL(10,4) DEFAULT NULL,
    delta_det_exacto DECIMAL(10,4) DEFAULT NULL,

    tolerancia_oz DECIMAL(10,2) DEFAULT NULL,
    regla_tolerancia VARCHAR(10) DEFAULT NULL COMMENT '< o <=',
    grilla_legacy_oz DECIMAL(10,2) DEFAULT NULL COMMENT '0.25 o 0.50',

    delta_legacy DECIMAL(10,2) DEFAULT NULL,
    residuo_cuantizacion DECIMAL(10,4) DEFAULT NULL,

    id_ajuste INT(11) DEFAULT NULL,
    id_detalle_ajuste INT(11) DEFAULT NULL,
    id_salida_inventario INT(11) DEFAULT NULL,
    id_detalle_salida_inv INT(11) DEFAULT NULL,

    procesado TINYINT(1) NOT NULL DEFAULT 0,
    usuario_reg VARCHAR(255) DEFAULT NULL,
    fecha_reg DATETIME NOT NULL,
    fecha_mod DATETIME DEFAULT NULL,
    estado VARCHAR(3) NOT NULL DEFAULT 'HAB',

    PRIMARY KEY (id),
    KEY idx_app_ajuste_aud_op_barra (id_operacion, id_barra),
    KEY idx_app_ajuste_aud_producto (id_producto),
    KEY idx_app_ajuste_aud_inventario (id_inventario_fisico)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;
```

### Nota sobre idempotencia

Si esta tabla también se usará para impedir doble aplicación, conviene agregar una clave única lógica. Ejemplo:

```sql
ALTER TABLE app_ajuste_paloteo_auditoria
ADD UNIQUE KEY uk_ajuste_paloteo_producto_dim (
    id_operacion,
    id_barra,
    id_inventario_fisico,
    id_producto,
    ind_paq_detalle
);
```

Esto evita que el mismo producto/dimensión se procese dos veces para el mismo inventario físico.

---

## 9. Algoritmo recomendado

### 9.1 Para unidades / botellas cerradas

No aplicar tolerancia ni redondeo.

```python
delta_paq = fisico_paq - ideal_paq

if delta_paq > 0:
    crear_ingreso(ind_paq_detalle="1", cantidad=delta_paq)
elif delta_paq < 0:
    crear_salida(ind_paq_detalle="1", cantidad=abs(delta_paq))
```

Las botellas cerradas se cuentan, no se pesan. Aquí no hay ruido de balanza.

---

### 9.2 Para detalle / onzas

```python
delta_det_exacto = fisico_detalle - ideal_detalle

tolerancia_oz = obtener_tolerancia_operativa(pesable, id_categoria)
grilla_legacy = obtener_grilla_legacy(id_categoria)
regla = obtener_regla_tolerancia(id_categoria)

if dentro_de_tolerancia(delta_det_exacto, tolerancia_oz, regla):
    delta_det_legacy = Decimal("0.00")
else:
    delta_det_legacy = cuantizar_a_grilla_half_up(delta_det_exacto, grilla_legacy)
```

Funciones sugeridas:

```python
def obtener_grilla_legacy(id_categoria: int) -> Decimal:
    if id_categoria in {6, 22}:   # VINOS, MEZCLADORES
        return Decimal("0.50")
    return Decimal("0.25")


def obtener_regla_tolerancia(id_categoria: int) -> str:
    if id_categoria in {6, 22}:
        return "<"     # mantener comportamiento actual inicialmente
    return "<="        # categorías sensibles con tolerancia 0.25


def dentro_de_tolerancia(delta: Decimal, tolerancia: Decimal, regla: str) -> bool:
    if regla == "<=":
        return abs(delta) <= tolerancia
    return abs(delta) < tolerancia
```

---

## 10. Casos de prueba recomendados

### 10.1 Categoría con tolerancia `0.25 oz`

| Delta exacto | Regla tolerancia | ¿Ajusta? | Grilla legacy | Delta legacy esperado |
|---:|---|---|---:|---:|
| `+0.24` | `<= 0.25` | No | `0.25` | `0.00` |
| `+0.25` | `<= 0.25` | No | `0.25` | `0.00` |
| `+0.26` | `<= 0.25` | Sí | `0.25` | `+0.25` |
| `+0.30` | `<= 0.25` | Sí | `0.25` | `+0.25` |
| `+0.38` | `<= 0.25` | Sí | `0.25` | `+0.50` |
| `-0.26` | `<= 0.25` | Sí | `0.25` | `-0.25` |

### 10.2 VINOS / MEZCLADORES con tolerancia `0.5 oz`

Manteniendo regla actual `<`:

| Delta exacto | Regla tolerancia | ¿Ajusta? | Grilla legacy | Delta legacy esperado |
|---:|---|---|---:|---:|
| `+0.49` | `< 0.50` | No | `0.50` | `0.00` |
| `+0.50` | `< 0.50` | Sí | `0.50` | `+0.50` |
| `+0.74` | `< 0.50` | Sí | `0.50` | `+0.50` |
| `+0.76` | `< 0.50` | Sí | `0.50` | `+1.00` |

Esta parte debe validarse funcionalmente antes de cambiarla, porque en estas categorías `0.5` representa paso operativo real.

---

## 11. Cambios sugeridos en backend

### 11.1 Cambiar nombres para evitar confusión

El nombre actual `delta_det_operativo` puede ser ambiguo. Recomiendo separar:

```text
delta_det_exacto
delta_det_legacy
grilla_legacy_oz
residuo_cuantizacion
```

### 11.2 Mantener una sola fuente de verdad

El preview y la aplicación real de ajustes deben usar la misma función backend.

No debe existir una lógica distinta en:

- `/api/inventario/consolidar/preview`
- `/api/inventario/ajustes/aplicar`
- frontend `static/app.js`

El frontend puede mostrar, pero la decisión final debe venir del backend.

### 11.3 Mostrar al usuario ambos valores cuando exista diferencia

En el módulo de ajustes, mostrar algo como:

```text
Diferencia exacta detectada: +0.30 oz
Ajuste POS a registrar: +0.25 oz
Residuo por cuantización: +0.05 oz
```

Esto evita que el administrador sienta que el sistema está “inventando” números.

---

## 12. Cambios sugeridos en frontend

En el preview de ajustes:

- Mostrar `delta_det_exacto` como información técnica/auditoría.
- Mostrar `delta_det_legacy` como cantidad que realmente se enviará al POS.
- Indicar si el movimiento fue omitido por tolerancia.
- Indicar la regla aplicada: `<= 0.25`, `< 0.50`, etc.

Ejemplo de etiqueta:

```text
Dentro de tolerancia: no se genera ajuste.
```

Ejemplo de alerta:

```text
El delta exacto fue +0.30 oz. Se registrará +0.25 oz porque el POS sólo recibe múltiplos permitidos.
```

---

## 13. Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Cambiar comportamiento de VINOS/MEZCLADORES accidentalmente | Ajustes omitidos o alterados | Mantener inicialmente regla actual para categorías 6 y 22 |
| Escribir valores no permitidos en legacy | Inconsistencia POS/reportes | Validar múltiplo de `0.25` antes de insertar |
| Diferencia entre delta exacto y delta legacy | Dudas de auditoría | Guardar residuo en tabla PWA |
| Preview y aplicación calculan distinto | Usuario ve una cosa y se aplica otra | Unificar cálculo en backend |
| Doble aplicación de ajustes | Stock duplicado o incorrecto | Clave única/idempotencia PWA + transacción |

---

## 14. Criterios de aceptación

La implementación debería considerarse correcta si cumple lo siguiente:

1. No modifica estructura de tablas legacy del POS.
2. Nunca escribe en legacy cantidades detalle que no sean múltiplos de `0.25`.
3. Para categorías con tolerancia `0.25`, un delta exacto de `0.25` no genera ajuste.
4. Para categorías con tolerancia `0.25`, un delta exacto de `0.30` genera un movimiento legacy de `0.25`, no de `0.50`.
5. `bar_inventario` queda igual al físico final.
6. La tabla PWA guarda `delta_det_exacto`, `delta_legacy`, `grilla_legacy_oz`, `regla_tolerancia` y `residuo_cuantizacion`.
7. El preview y la aplicación real muestran/aplican los mismos valores.
8. Los ajustes siguen usando los parámetros correctos del POS:
   - `16 = PENDIETE`
   - `20 = PROCESADO`
   - `77 = BAJA POR AJUSTE`
   - `84 = AJUSTE`

---

## 15. Plan de avance recomendado

### Fase 1: Decisión y validación funcional

Confirmar estas reglas:

```text
Categorías 0.25:
    tolerancia inclusiva <=
    grilla legacy 0.25

VINOS / MEZCLADORES:
    mantener regla actual <
    grilla legacy 0.50
```

### Fase 2: Backend

- Crear función genérica `cuantizar_a_grilla_half_up`.
- Reemplazar uso fijo de redondeo a `0.5` en ajustes por grilla según categoría.
- Registrar auditoría PWA.
- Asegurar transacción e idempotencia.

### Fase 3: Frontend

- Ajustar preview de diferencias.
- Mostrar delta exacto, delta legacy y motivo.
- Evitar que el frontend tenga reglas independientes del backend.

### Fase 4: Pruebas

Probar escenarios sintéticos con:

- Producto de TEQUILAS con delta `0.25`, `0.26`, `0.30`, `0.38`.
- Producto de VINOS con delta `0.49`, `0.50`, `0.76`.
- Producto no pesable con diferencia en unidad.
- Caso mixto: faltan unidades pero sobran onzas.

### Fase 5: Documentación final

Actualizar:

- Documentación de ingresos y salidas por ajuste.
- Guía de referencia de redondeo/tolerancia.
- README técnico de backend.
- Comentarios de funciones críticas en `main.py`.

---

## 16. Conclusión

La decisión más equilibrada es no forzar el `delta_det_exacto` dentro de las tablas legacy, pero tampoco seguir usando una cuantización única a `0.5` para todas las categorías.

La solución recomendada es:

```text
Calcular exacto.
Aplicar tolerancia.
Cuantizar a la grilla legacy permitida por categoría.
Guardar el valor legacy en POS.
Guardar el valor exacto y la explicación en auditoría PWA.
Actualizar bar_inventario al físico final.
```

Así el POS sigue tranquilo en su mundo legacy, la PWA gana trazabilidad fina y nosotros evitamos que una media onza fantasma se convierta en protagonista del cierre.
