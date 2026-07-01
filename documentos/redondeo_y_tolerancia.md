# Redondeo y Tolerancia en Pesaje y Ajustes

Guía de referencia para entender cómo y por qué el sistema redondea pesos a media onza y aplica una banda de tolerancia antes de generar un ajuste de inventario. Refleja el estado del código a partir de **v10.39**.

## 1. Dos mecanismos distintos, no confundir

El sistema tiene **dos problemas diferentes** que se resuelven con dos piezas de lógica separadas. Comparten la misma función de redondeo de base, pero se aplican en momentos distintos y con propósitos distintos:

| Mecanismo | Cuándo actúa | Qué resuelve | Función backend | Función frontend |
|---|---|---|---|---|
| **Redondeo de captura** | Al guardar el paloteo (`bar_detalle_fisico`) | El POS sólo entiende múltiplos de 0.5 oz; el peso en gramos nunca cae justo en un múltiplo | `_redondear_media_onza_half_up` (`main.py:44`) | `redondearOnzasOperativas` (`static/app.js:2061`) |
| **Tolerancia + cuantización de ajuste** | Al calcular diferencias para AJUSTES (`_calcular_diferencias_paloteo`) | Distinguir una diferencia real (faltante/sobrante) de ruido de medición antes de generar un movimiento de inventario | `_obtener_tolerancia_operativa_oz` + `_cuantizar_delta_onzas_operativo` (`main.py:71-86`) | `cuantizarDeltaOnzas` (`static/app.js:2072`) |

El redondeo de captura **siempre** se aplica. La tolerancia de ajuste, en cambio, primero pregunta "¿esta diferencia es lo bastante grande como para importar?" y sólo si la respuesta es sí, redondea.

Ambos existen en backend y frontend con la misma fórmula para que el número que ve el usuario en pantalla coincida exactamente con lo que el backend persiste (ver `CLAUDE.md`).

## 2. Redondeo a media onza (HALF_UP)

### Fórmula

```python
def _redondear_media_onza_half_up(valor: float) -> float:
    redondeado = (Decimal(str(valor)) * Decimal("2")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return float(redondeado / Decimal("2"))
```

Equivalente a `round(valor * 2) / 2`, pero usando `Decimal` con `ROUND_HALF_UP` en vez de redondeo flotante nativo.

### Por qué existe

- El POS trabaja inventario líquido en pasos de **media onza** (11.50, 12.00, 12.50...).
- Una balanza real casi nunca entrega un peso que, convertido a onzas, caiga justo en un múltiplo de 0.5.

### Por qué HALF_UP y por qué `Decimal` y no `round()` de Python

- `round()` de Python usa redondeo banker's (al par más cercano) sobre floats binarios: `round(0.5)` da `0`, no `1`.
- `Decimal(str(valor))` evita errores de representación binaria (`0.1 + 0.2 != 0.3`).
- HALF_UP es la regla "de toda la vida" (0.5 siempre sube), predecible para el usuario y fácil de replicar en JavaScript con `Math.round` sin reimplementar aritmética decimal en el navegador.

### Ejemplos

| Onzas exactas | `valor * 2` | Redondeado (HALF_UP) | Resultado POS |
|---|---|---|---|
| 49.257 | 98.514 | 99 | **49.50** |
| 11.25 (caso límite exacto entre 11.0 y 11.5) | 22.5 | 23 | **11.50** |
| 10.75 (caso límite exacto entre 10.5 y 11.0) | 21.5 | 22 | **11.00** |
| 0.249 | 0.498 | 0 | **0.00** |
| -0.25 (faltante en delta) | -0.5 | -1 | **-0.50** |

Los casos límite (11.25 y 10.75) justifican explícitamente HALF_UP: sin una regla determinística, un valor en el punto medio exacto entre dos múltiplos de 0.5 podría redondearse distinto en backend y frontend.

## 3. Tolerancia operativa (banda muerta antes de ajustar)

### Fórmula

```python
def _obtener_tolerancia_operativa_oz(pesable: int | None) -> float:
    if int(pesable or 0) != 1:
        return 0.0
    return 0.5

def _cuantizar_delta_onzas_operativo(delta_exacto: float, tolerancia_oz: float) -> float:
    if abs(delta_exacto) < tolerancia_oz:
        return 0.0
    return _redondear_media_onza_half_up(delta_exacto)
```

### Por qué existe

El delta `real (paloteo) - ideal (POS)` nunca es perfectamente cero aunque físicamente no falte ni sobre nada:

- **Imprecisión de balanza** y del proceso de pesaje (líquido en boquilla, burbujas, etc.).
- **Evaporación / derrame** entre el cierre del POS y el momento del paloteo.
- **Acumulación de redondeo de captura**: cada pesaje se redondeó a 0.5 oz antes de sumarse, por lo que la suma puede arrastrar un residuo sin que haya pasado nada anómalo.

Sin tolerancia, **cada paloteo generaría ajustes en casi todos los productos pesables**, llenando el historial con movimientos que son sólo ruido de medición.

### Por qué 0.5 oz uniforme para todos los productos pesables (desde v10.39)

La tolerancia operativa es **0.5 oz para todos los productos pesables**, sin distinción por categoría. La razón es que 0.5 oz coincide exactamente con el paso mínimo de la grilla de redondeo del POS:

- `real_det` (del paloteo) es siempre múltiplo de 0.5 — lo garantiza el redondeo de captura.
- `ideal_det` (de `bar_inventario`) es siempre múltiplo de 0.5 — lo garantiza el endpoint de aplicar ajustes, que escribe `real_det` (múltiplo de 0.5) directamente en `bar_inventario` cada cierre.
- Por lo tanto, `delta_det_exacto = real_det - ideal_det` siempre cae en múltiplo de 0.5.
- Un delta múltiplo de 0.5 al cuantizarse a la grilla de 0.5 produce el mismo valor: **residuo cero, distorsión cero**.

Esto se verificó con una consulta directa a la BD de test: no existe ningún producto pesable con `bar_inventario.cantidad_detalle` fuera de múltiplos de 0.5.

### Por qué el mismatch tolerancia/grilla sí sería un problema

Si la tolerancia fuera **menor** que la grilla de redondeo (ej. tolerancia 0.25 con grilla 0.5), el delta mínimo que pasaría la banda (ej. 0.25 oz) se amplificaría al redondearse al siguiente múltiplo de 0.5 (quedando 0.50 oz en el comprobante). La tolerancia 0.5 uniforme elimina ese mismatch por definición.

### Tolerancia para productos no pesables

`pesable=0` → tolerancia `0.0`. Los productos no pesables se cuentan por unidades enteras, no se miden con balanza, así que no hay ruido de medición que filtrar. Cualquier diferencia en `cantidad_detalle` se trata directamente como ajuste real.

## 4. Ejemplos (banda muerta + redondeo) con casos límite

Todos los productos pesables usan la misma regla desde v10.39:

| delta exacto (real - ideal) | ¿`abs(delta) < 0.5`? | delta operativo documentado |
|---|---|---|
| +0.10 | sí → ruido | **0.0** (no se ajusta) |
| +0.49 | sí → ruido | **0.0** (no se ajusta) |
| +0.50 (límite) | no → es ajuste | redondea a **+0.50** (sin distorsión) |
| +0.74 | no → es ajuste | redondea a **+0.50** |
| +0.75 (caso límite) | no → es ajuste | redondea a **+1.00** |
| +1.00 | no → es ajuste | redondea a **+1.00** |
| -0.50 (faltante exacto) | no → es ajuste | redondea a **-0.50** |

El límite es estricto (`<`, no `<=`): un delta de exactamente 0.50 oz **sí** dispara ajuste. Esto es intencional — en la práctica no ocurre (con datos limpios `real_det` e `ideal_det` son múltiplos de 0.5, por lo que 0.50 exacto representa una diferencia real de una media onza).

## 5. Dónde se aplica cada cosa (mapa de código)

**Redondeo de captura (paloteo → `bar_detalle_fisico.cantidad_detalle`):**
- Backend: `main.py:298` — `onzas_redondeadas_pos = _redondear_media_onza_half_up(total_onzas)`, dentro de `_procesar_items_paloteo`.
- El valor exacto sin redondear se conserva en `app_paloteo_registro_crudo.onzas_calculadas` para auditoría.
- Frontend: `redondearOnzasOperativas` — muestra en vivo el total durante la captura (PALOTEO 1/2/3) y en el módulo CONVERSOR.

**Tolerancia + cuantización (cálculo de diferencias para AJUSTES):**
- Backend: `_calcular_diferencias_paloteo` (`main.py:1232`) — fuente de verdad única compartida por el preview (`/api/inventario/consolidar/preview`) y por aplicar ajustes (`/api/inventario/ajustes/aplicar`).
- Sólo `delta_det_operativo` (no el exacto) se escribe en `bar_detalle_ajuste` / `bar_detalle_salida_inv` (`main.py:1593-1606`).
- `bar_inventario` se iguala siempre al físico exacto (`real_det`) sin pasar por la cuantización (`main.py:1625`).
- Frontend: `cuantizarDeltaOnzas` + `formatearDiferencia` (`static/app.js:2072`, `3948`) — replican la misma lógica para pintar diferencias en el módulo REPORTE/AJUSTES usando la `tolerancia_oz` que cada producto trae en su perfil (resuelta por el backend antes de enviarla).

**No pasa por este pipeline:** `delta_paq` (botellas cerradas) — no tiene tolerancia ni redondeo; cualquier diferencia en unidades enteras se usa directamente.
