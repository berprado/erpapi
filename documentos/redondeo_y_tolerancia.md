# Redondeo y Tolerancia en Pesaje y Ajustes

Guía de referencia para entender cómo y por qué el sistema redondea pesos a media onza y aplica una banda de tolerancia antes de generar un ajuste de inventario. Refleja el estado del código a partir de **v10.39**.

## 1. Dos mecanismos distintos, no confundir

El sistema tiene **dos problemas diferentes** que se resuelven con dos piezas de lógica separadas. Comparten la misma función de redondeo de base, pero se aplican en momentos distintos y con propósitos distintos:

| Mecanismo | Cuándo actúa | Qué resuelve | Función backend | Función frontend |
|---|---|---|---|---|
| **Redondeo de captura** | Al guardar el paloteo (`bar_detalle_fisico`) | El POS sólo entiende múltiplos de 0.5 oz; el peso en gramos nunca cae justo en un múltiplo | `_redondear_media_onza_half_up` (`main.py:76`) | `redondearOnzasOperativas` (`static/app.js:2322`) |
| **Tolerancia + cuantización de ajuste** | Al calcular diferencias para AJUSTES (`_calcular_diferencias_paloteo`) | Distinguir una diferencia real (faltante/sobrante) de ruido de medición antes de generar un movimiento de inventario | `_obtener_tolerancia_operativa_oz` + `_cuantizar_delta_onzas_operativo` (`main.py:103-119`) | `cuantizarDeltaOnzas` (`static/app.js:2333`) |

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
- HALF_UP es la regla "de toda la vida": el empate se aleja de cero (`+0.25` → `+0.5`, `-0.25` → `-0.5`), predecible para el usuario.

**Cuidado al replicarlo en JavaScript: `Math.round` NO es HALF_UP.** `Math.round` resuelve los empates hacia +∞, así que `Math.round(-0.5)` da `-0`: un delta de `-0.25 oz` (escalado `-0.5`) se convertiría en `0` en vez de `-0.5`, y un faltante en el límite exacto se pintaría como "sin diferencia". Por eso `redondearOnzasOperativas` (`static/app.js:2322`) implementa el empate lejos-de-cero a mano, con `Math.floor(x + 0.5 + ε)` para positivos y `Math.ceil(x - 0.5 - ε)` para negativos. No "simplificar" esa función a `Math.round(valor * 2) / 2`: rompe todos los deltas negativos en el punto medio.

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
- **Residuo del redondeo de captura**: el total de onzas de cada producto se redondea **una sola vez** a la grilla de 0.5 — NO botella por botella; `total_onzas` se acumula exacto en el loop y se redondea al final (`main.py:409-411`, y el frontend replica el mismo orden en `app.js:4348-4354`). Eso deja un residuo de hasta ±0.25 oz **por producto**, no acumulativo por botella. El caso 3 de la sección 6 muestra por qué redondear cada botella por separado sería incorrecto.

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
- Backend: `main.py:411` — `onzas_redondeadas_pos = _redondear_media_onza_half_up(total_onzas)`, dentro de `_procesar_items_paloteo`.
- El valor exacto sin redondear se conserva en `app_paloteo_registro_crudo.onzas_calculadas` para auditoría.
- Frontend: `redondearOnzasOperativas` (`static/app.js:2322`) — muestra en vivo el total durante la captura (PALOTEO 1/2/3) y en el módulo CONVERSOR.

**Tolerancia + cuantización (cálculo de diferencias para AJUSTES):**
- Backend: `_calcular_diferencias_paloteo` (`main.py:1317`) — fuente de verdad única compartida por el preview (`/api/inventario/consolidar/preview`, `main.py:1478`) y por aplicar ajustes (`/api/inventario/ajustes/aplicar`, `main.py:1586`). Es el **único** punto del sistema donde la tolerancia decide algo; en el resto (listado de pendientes, CONVERSOR) la `tolerancia_oz` sólo se reporta dentro del perfil.
- Sólo `delta_det_operativo` (no el exacto) se escribe en `bar_detalle_ajuste` / `bar_detalle_salida_inv` (`main.py:1678-1692`).
- La banda decide si el producto **existe o no** para el ajuste: el filtro `deltas_con_diferencia` (`main.py:1587-1589`) descarta todo producto cuya única diferencia esté en onzas y caiga dentro de la banda. Si todos caen dentro, la respuesta es `status: "skipped"` y no se crea ninguna cabecera de ajuste/salida.
- Frontend: `cuantizarDeltaOnzas` + `formatearDiferencia` (`static/app.js:2333`, `4281`) — replican la misma lógica para pintar diferencias en el módulo REPORTE/AJUSTES usando la `tolerancia_oz` que cada producto trae en su perfil (resuelta por el backend antes de enviarla). Nota: `formatearDiferencia` aplica además un epsilon propio de `0.01` para decidir si pinta el ícono de "sin diferencia" — es umbral de presentación, no tolerancia.

**Igualación de `bar_inventario` (matiz importante):**
- `bar_inventario` se iguala al físico exacto (`real_det`, sin cuantizar) **para todo producto que genere un ajuste** — no para todos los productos paloteados. El loop de igualación (`main.py:1653`, escritura en `main.py:1709-1710`) itera `deltas_con_diferencia`, es decir la lista **ya filtrada por tolerancia**, así que un producto tolerado nunca llega a esa actualización.
- Hoy esto es un no-op y no produce divergencia: si el producto fue tolerado, su `delta_det_exacto` es `0.0` exacto (`real_det == ideal_det`), por lo que escribir la fila no cambiaría nada. La equivalencia depende enteramente del invariante "todos los deltas son múltiplos de 0.5" — el mismo que justifica la banda de 0.5.
- Si ese invariante se rompiera, el producto quedaría fuera del ajuste **y** con `bar_inventario` conservando el ideal viejo. Existe además una asimetría: si el mismo producto tiene diferencia de botellas (`delta_paq`), sí entra a la lista y ahí se le escribe `cantidad_detalle = real_det`, tolerancia de onzas incluida.
- Hacer que la igualación sea incondicional (fuera del filtro) es el pendiente registrado en `TODO.md`.

**No pasa por este pipeline:** `delta_paq` (botellas cerradas) — no tiene tolerancia ni redondeo; cualquier diferencia en unidades enteras se usa directamente.

## 6. Casos completos de punta a punta (datos reales de la BD de test)

Cuatro casos trabajados con productos y perfiles reales de la BD de test (`adminerp_copy`), verificados el 2026-07-17 ejecutando las funciones reales de `main.py` (no cálculo a mano). Cada caso ilustra un concepto distinto; los ideales de `bar_inventario` son datos de escenario, no necesariamente los vigentes en BD.

Perfiles usados:

| Producto | id | Perfil | Tara | g/oz | Botella llena |
|---|---|---|---|---|---|
| BRIGHTON PINK 700ML | 494 | 254 | 558 g | 29.063830 | 23.5 oz |
| GEORGE FORSTER 2LT | 495 | 255 | 987 g | 27.733333 | 67.5 oz |

### Caso 1 — El ruido lo absorbe el redondeo de captura; la banda nunca actúa

BRIGHTON PINK. Ideal: 2 paq + 19.00 oz. Físico: 2 cerradas + 1 abierta de **1106 g**.

```text
peso_liquido  = 1106 - 558 = 548 g
onzas exactas = 548 / 29.063830 = 18.855051 oz     (merma fisica real: 0.145 oz)
real_det      = HALF_UP(18.855051) = 19.0          <- lo que se guarda
delta_det     = 19.0 - 19.00 = 0.0  ->  operativo 0.0  ->  NO entra al ajuste
```

Físicamente faltan 0.145 oz, pero el sistema no ajusta nada — y hace bien: esa merma está por debajo de lo que el POS puede representar. Quien la absorbió fue el **redondeo de captura** (18.855 → 19.0), no la banda: para cuando la banda miró el delta, ya era 0.0 exacto. Si este fuera el único producto de la operativa, `/ajustes/aplicar` respondería `status: "skipped"` sin crear cabecera alguna.

**Lección:** el filtro real del ruido de medición es el redondeo de captura. La banda es una red de seguridad que, con el invariante múltiplo-de-0.5 vigente, nunca cambia un resultado.

### Caso 2 — Delta exacto de 0.5: el límite estricto, y la zona donde los enfoques divergen

GEORGE FORSTER. Ideal: 0 paq + 40.00 oz. Físico: 0 cerradas + 1 abierta de **2107 g**.

```text
peso_liquido  = 2107 - 987 = 1120 g
onzas exactas = 1120 / 27.733333 = 40.384616 oz    (sobrante fisico real: +0.385 oz)
real_det      = HALF_UP(40.384616) = 40.5
delta_det     = 40.5 - 40.00 = +0.5
banda: |0.5| < 0.5 ? NO (limite estricto)  ->  operativo +0.5  ->  INGRESO por ajuste de 0.50 oz
```

Se crea cabecera en `bar_ajuste` (estado 16, movimiento 84), fila en `bar_detalle_ajuste` con `cantidad = 0.50` / `ind_paq_detalle = '0'`, y `bar_inventario` queda en `(0, 40.5)`.

Este caso cae en la **zona de divergencia** `[0.25, 0.5)` del delta crudo — el mismo escenario del bug CAMPARI (v10.42):

| Enfoque | Cálculo | Resultado |
|---|---|---|
| Sistema actual (redondear captura → banda sobre el delta ya en grilla) | 40.5 − 40.0 = 0.5, pasa la banda | **ajusta +0.5** |
| Banda sobre el delta crudo (el bug de v10.42) | 0.3846 < 0.5 → tolerado | no ajusta |
| HALF_UP directo sobre el delta crudo | HALF_UP(0.3846) = 0.5 | ajusta +0.5 |

**Lección:** la banda debe evaluarse sobre la misma grilla en la que se escribe. Aplicada al crudo, un sobrante real queda invisible en pantalla mientras el backend sí lo ajusta.

### Caso 3 — Varias botellas abiertas: se redondea la SUMA, no cada botella

BRIGHTON PINK. Ideal: 20.50 oz. Físico: **2 botellas abiertas de 855 g cada una**.

```text
cada botella:  (855 - 558) / 29.063830 = 10.21889 oz
total exacto:  20.43777 oz
SISTEMA    (redondea la suma):        HALF_UP(20.43777) = 20.5  ->  delta 0.0  ->  sin ajuste
HIPOTETICO (redondea cada botella):   10.0 + 10.0       = 20.0  ->  delta -0.5 ->  salida FANTASMA de 0.5 oz
```

Dos botellas apenas por encima de la media onza pierden cada una ~0.22 oz si se redondean por separado; redondeando la suma, esos residuos se compensan. El código acumula `total_onzas` exacto y redondea una única vez (`main.py:409-411`); el frontend hace exactamente lo mismo (`app.js:4348-4354`).

**Lección:** redondear botella por botella acumularía residuo por botella y fabricaría ajustes fantasma. El residuo real es de hasta ±0.25 oz por producto, una sola vez.

### Caso 4 — Caso mixto: botellas y onzas viajan por tuberías distintas

GEORGE FORSTER. Ideal: 2 paq + 5.0 oz. Físico: **1 cerrada + 2 abiertas (1120 g y 2817 g)** — la historia típica: durante la noche se abrió una botella cerrada sin que el POS lo registrara.

```text
botella vieja: (1120 - 987) / 27.733333 =  4.79567 oz
botella nueva: (2817 - 987) / 27.733333 = 65.98558 oz   (ambas <= 67.5 de botella llena)
total exacto:  70.78125  ->  real_det = 71.0

delta_paq = 1 - 2   = -1     (sin banda ni redondeo: las botellas se cuentan)
delta_det = 71.0 - 5.0 = +66.0  ->  pasa la banda  ->  operativo +66.0
```

Un solo producto genera **dos documentos**: salida por ajuste de 1 unidad (`bar_detalle_salida_inv`, `ind_paq_detalle = '1'`) e ingreso por ajuste de 66.00 oz (`bar_detalle_ajuste`, `ind_paq_detalle = '0'`), con ambas cabeceras creadas. El neto cuenta la historia física: −1 botella (67.5 oz) + 66.0 oz = **−1.5 oz**, lo servido de la botella nueva sin registro.

**Lección:** `delta_paq` nunca pasa por tolerancia ni redondeo. Un producto puede ser sobrante en onzas y faltante en unidades a la vez, y cada dimensión genera su propio movimiento.
