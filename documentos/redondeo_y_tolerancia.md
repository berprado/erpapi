# Redondeo y Tolerancia en Pesaje y Ajustes

Guía de referencia para entender **por qué** el sistema redondea pesos a media onza y **por qué** aplica una banda de tolerancia antes de generar un ajuste de inventario. Sirve como base para evaluar el pendiente de `TODO.md` sobre el redondeo del monto documentado en categorías con tolerancia 0.25 oz.

## 1. Dos mecanismos distintos, no confundir

El sistema tiene **dos problemas diferentes** que se resuelven con dos piezas de lógica separadas. Comparten la misma función de redondeo de base, pero se aplican en momentos distintos y con propósitos distintos:

| Mecanismo | Cuándo actúa | Qué resuelve | Función backend | Función frontend |
|---|---|---|---|---|
| **Redondeo de captura** | Al guardar el paloteo (`bar_detalle_fisico`) | El POS sólo entiende múltiplos de 0.5 oz; el peso medido en gramos nunca cae justo en un múltiplo | `_redondear_media_onza_half_up` (`main.py:44`) | `redondearOnzasOperativas` (`static/app.js:2061`) |
| **Tolerancia + cuantización de ajuste** | Al calcular diferencias para AJUSTES (`_calcular_diferencias_paloteo`) | Distinguir una diferencia real (faltante/sobrante) de ruido de medición antes de generar un movimiento de inventario | `_obtener_tolerancia_operativa_oz` + `_cuantizar_delta_onzas_operativo` (`main.py:71-86`) | `cuantizarDeltaOnzas` (`static/app.js:2072`) |

El redondeo de captura **siempre** se aplica (no hay banda muerta: cualquier peso, por mínimo que sea, se redondea a su múltiplo de 0.5 más cercano). La tolerancia de ajuste, en cambio, primero pregunta "¿esta diferencia es lo bastante grande como para importar?" y sólo si la respuesta es sí, redondea.

Ambos existen en backend y frontend con la misma fórmula para que el número que ve el usuario en pantalla durante el paloteo coincida exactamente con lo que el backend termina persistiendo (regla general del proyecto, ver `CLAUDE.md`).

## 2. Redondeo a media onza (HALF_UP)

### Fórmula

```python
def _redondear_media_onza_half_up(valor: float) -> float:
    redondeado = (Decimal(str(valor)) * Decimal("2")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return float(redondeado / Decimal("2"))
```

Equivalente a `round(valor * 2) / 2`, pero usando `Decimal` con `ROUND_HALF_UP` en vez de redondeo flotante nativo.

### Por qué existe

- El POS (y el negocio) trabajan inventario líquido en pasos de **media onza** (11.50, 12.00, 12.50...), no en gramos ni en onzas con decimales arbitrarios.
- Una balanza real casi nunca entrega un peso que, convertido a onzas, caiga justo en un múltiplo de 0.5. Hace falta una regla determinística para llevar cualquier valor exacto a la grilla de 0.5 que el POS entiende.

### Por qué HALF_UP y por qué `Decimal` y no `round()` de Python

- `round()` de Python usa redondeo banker's (al par más cercano) sobre floats binarios, lo que puede dar resultados distintos a los que un humano esperaría en el punto medio exacto (ej. `round(0.5)` da `0`, no `1`).
- Convertir a `Decimal(str(valor))` evita el problema clásico de representación binaria de floats (ej. `0.1 + 0.2 != 0.3`), que podría desviar un valor que matemáticamente cae justo en el límite.
- HALF_UP es la regla "de toda la vida" (0.5 siempre sube) — predecible para el usuario y fácil de replicar en JavaScript (`Math.round`) sin reimplementar aritmética decimal en el navegador.

### Ejemplos

| Onzas exactas (medición) | `valor * 2` | Redondeado a entero (HALF_UP) | Resultado POS |
|---|---|---|---|
| 49.257 | 98.514 | 99 | **49.50** |
| 11.25 (caso límite, justo a mitad de camino entre 11.0 y 11.5) | 22.5 | 23 | **11.50** |
| 10.75 (caso límite, justo a mitad de camino entre 10.5 y 11.0) | 21.5 | 22 | **11.00** |
| 0.249 | 0.498 | 0 | **0.00** |
| -0.25 (faltante exacto en un delta) | -0.5 | -1 | **-0.50** |

Los dos casos límite (11.25 y 10.75) son los que justifican explícitamente la regla HALF_UP: sin una regla determinística, un peso que cae justo a mitad de camino entre dos múltiplos de 0.5 podría redondearse para arriba o para abajo según la implementación, y backend/frontend podrían discrepar.

## 3. Tolerancia operativa (banda muerta antes de ajustar)

### Fórmula

```python
def _obtener_tolerancia_operativa_oz(pesable: int | None, id_categoria: int | None) -> float:
    if int(pesable or 0) != 1:
        return 0.0
    if int(id_categoria or 0) in {6, 22}:
        return 0.5
    return 0.25

def _cuantizar_delta_onzas_operativo(delta_exacto: float, tolerancia_oz: float) -> float:
    if abs(delta_exacto) < tolerancia_oz:
        return 0.0
    return _redondear_media_onza_half_up(delta_exacto)
```

### Por qué existe

El delta que dispara un ajuste es `real (paloteo) - ideal (POS)`. Ese delta nunca es perfectamente cero aunque físicamente no falte ni sobre nada, porque:

- **Imprecisión de balanza** y del propio proceso de pesaje (líquido residual en la boquilla, burbujas, etc.).
- **Evaporación / derrame** de líquido en botellas abiertas entre el cierre del POS y el momento del paloteo.
- **Redondeo de captura** (sección 2): cada pesaje individual ya se redondeó a 0.5 oz antes de sumarse, así que la suma puede arrastrar un residuo de hasta ±0.25 oz por botella abierta sólo por el redondeo, sin que haya pasado nada anómalo.

Sin una banda de tolerancia, **cada paloteo generaría ajustes microscópicos en casi todos los productos pesables**, ensuciando el historial de auditoría con movimientos que no representan una pérdida o sobrante real, sólo ruido de medición.

### Por qué la tolerancia varía por categoría (0.5 vs 0.25)

Los perfiles de pesaje actuales se agrupan así (consulta a `app_producto_pesaje_config_api` / `alm_categoria` en BD de test):

| Categoría | id | Tolerancia | Perfiles pesables activos |
|---|---|---|---|
| VINOS | 6 | **0.5 oz** | 2 |
| MEZCLADORES | 22 | **0.5 oz** | 10 |
| GINVIP | 21 | 0.25 oz | 43 |
| GIN | 9 | 0.25 oz | 33 |
| LICOR | 3 | 0.25 oz | 24 |
| TEQUILAS | 8 | 0.25 oz | 20 |
| WHISKYS | 1 | 0.25 oz | 19 |
| RON | 2 | 0.25 oz | 13 |
| SINGANI | 5 | 0.25 oz | 12 |
| VODKAS | 7 | 0.25 oz | 10 |
| FERNET | 4 | 0.25 oz | 5 |

- **VINOS y MEZCLADORES (0.5 oz):** para estos productos, **0.5 oz ya es el paso mínimo operativo real** del proceso (ver nota en `TODO.md`), así que una tolerancia de 0.5 simplemente coincide con la granularidad con la que de verdad se mide/sirve el producto. No hay distorsión porque no existe un "medio paso" intermedio relevante.
- **Resto de categorías pesables (0.25 oz):** son licores de mayor rotación/valor (whisky, ron, gin, tequila...) donde interesa una sensibilidad más fina — la mitad del paso de redondeo (0.5 / 2 = 0.25) — para detectar mermas reales sin ser tan estricto como para marcar cualquier ruido sub-0.25 como ajuste.
- **Productos no pesables (`pesable=0`, tolerancia 0.0):** se cuentan por unidad (botella cerrada), no se pesan, así que no hay ruido de balanza que filtrar — cualquier diferencia en `cantidad_detalle` (que en la práctica debería ser 0 para estos productos) se trata como real.

La columna `tolerancia_oz` que existe en `app_producto_pesaje_config_api` (default `1.50`) **no se usa** para este cálculo — es una columna heredada, no editable desde el alta de un modelo. El valor real siempre sale de `_obtener_tolerancia_operativa_oz` por categoría, tanto al listar pendientes (`main.py:1066`) como al consolidar diferencias (`main.py:1285`).

### Importante: el límite es estricto (`<`, no `<=`)

`abs(delta_exacto) < tolerancia_oz` — un delta **igual** a la tolerancia **no** se filtra como ruido, se trata como ajuste real y pasa a redondearse. Esto es intencional (mejor pecar de generar un ajuste de más que de ocultar una diferencia real en el límite), pero combinado con el redondeo a 0.5 produce el caso límite documentado en la sección 4.

## 4. Ejemplos combinados (banda muerta + redondeo) con casos límite

Categoría con tolerancia 0.5 (VINOS/MEZCLADORES):

| delta exacto (real - ideal) | ¿`abs(delta) < 0.5`? | delta operativo guardado |
|---|---|---|
| +0.20 | sí → ruido | **0.0** (no se ajusta) |
| +0.49 | sí → ruido | **0.0** (no se ajusta) |
| +0.50 (límite) | no → es ajuste | redondea a **+0.5** |
| +0.74 | no → es ajuste | redondea a **+0.5** |
| +0.76 | no → es ajuste | redondea a **+1.0** |
| -0.50 (límite, faltante) | no → es ajuste | redondea a **-0.5** |

Categoría con tolerancia 0.25 (todas las demás pesables — WHISKYS, RON, TEQUILAS, etc.):

| delta exacto (real - ideal) | ¿`abs(delta) < 0.25`? | delta operativo guardado |
|---|---|---|
| +0.10 | sí → ruido | **0.0** (no se ajusta) |
| +0.24 | sí → ruido | **0.0** (no se ajusta) |
| **+0.25 (límite)** | **no → es ajuste** | redondea a **+0.5** ⚠️ |
| +0.30 | no → es ajuste | redondea a **+0.5** |
| -0.25 (límite, faltante) | no → es ajuste | redondea a **-0.5** ⚠️ |

La fila marcada con ⚠️ es el caso real registrado en `TODO.md` (operativa sintética 1239, JARANA SILVER 1LT — id 297, categoría TEQUILAS): un delta exacto de **0.25 oz** dispara el ajuste (correcto, no es ruido) pero el monto que queda escrito en `bar_detalle_ajuste`/`bar_detalle_salida_inv` es **0.50 oz**, el doble de la diferencia real que lo originó. `bar_inventario` sí queda igualado al físico (el delta exacto se usa para calcular el nuevo saldo, no el redondeado), pero el comprobante de auditoría sobre-reporta la magnitud del movimiento. Esto **no** ocurre en categorías con tolerancia 0.5, porque ahí 0.5 ya es el paso mínimo y el redondeo no introduce distorsión adicional.

## 5. Dónde se aplica cada cosa (mapa de código)

**Redondeo de captura (paloteo → `bar_detalle_fisico.cantidad_detalle`):**
- Backend: `main.py:298` (`onzas_redondeadas_pos = _redondear_media_onza_half_up(total_onzas)`), dentro de `procesar_paloteo`.
- El valor exacto sin redondear se conserva aparte en `app_paloteo_registro_crudo.onzas_calculadas` para auditoría (ver `documentos/DOCUMENTACION_ALMACENAMIENTO_PALOTEO.md`).
- Frontend: `redondearOnzasOperativas` se usa para mostrar en vivo el total mientras se captura (PALOTEO 1/2/3) y en el módulo CONVERSOR.

**Tolerancia + cuantización (cálculo de diferencias para AJUSTES):**
- Backend: `_calcular_diferencias_paloteo` (`main.py:1232`) calcula `delta_det_exacto` (real - ideal) y `delta_det_operativo` (tras tolerancia + redondeo) por producto. Es la única fuente de verdad, compartida por el preview (`/api/inventario/consolidar/preview`) y por aplicar ajustes (`/api/inventario/ajustes/aplicar`), así ambos ven exactamente la misma diferencia.
- Sólo `delta_det_operativo` (no el exacto) es lo que se escribe en los movimientos de `bar_detalle_ajuste` / `bar_detalle_salida_inv` (`main.py:1593-1606`).
- Frontend: `cuantizarDeltaOnzas` + `formatearDiferencia` (`static/app.js:2072`, `3948`) replican la misma lógica para pintar el color/ícono de diferencia en el módulo REPORTE/AJUSTES, usando la tolerancia que cada producto trae en `tolerancia_oz` dentro de su perfil (que el backend ya resolvió por categoría antes de enviarla).

**No pasa por este pipeline:** las diferencias de `delta_paq` (botellas cerradas, unidades enteras) no tienen tolerancia ni redondeo — un faltante/sobrante de unidades enteras siempre se usa tal cual, porque no hay "ruido de medición" posible al contar botellas.

## 6. Resumen para decidir el pendiente del TODO

El comportamiento actual es **consistente y deliberado** en todo menos en un punto: cuando el delta exacto cae justo en el límite de una tolerancia de 0.25 (o lo supera por poco, ej. 0.30), el redondeo a 0.5 puede duplicar el monto documentado respecto a la causa real. Las preguntas a resolver para el pendiente son:

1. ¿El comprobante de auditoría (`bar_detalle_ajuste`/`bar_detalle_salida_inv`) debería guardar `delta_det_exacto` en vez de `delta_det_operativo` cuando la tolerancia de la categoría es 0.25, ya que en ese caso 0.5 no es realmente "el paso mínimo del producto" sino sólo el paso de redondeo del POS?
2. Si se cambia, ¿afecta a `bar_inventario` (que ya usa el delta exacto para el nuevo saldo) o sólo al texto/monto del comprobante?
3. ¿Conviene mantener el límite estricto (`<`, no `<=`) o sería más consistente usar `<=` para que un delta exactamente igual a la tolerancia se trate como ruido en vez de como ajuste?
