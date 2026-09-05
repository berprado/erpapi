# UX Pour Cost — Análisis de fricción y recomendaciones

**Proyecto:** BackStage API · PWA Frontend · Módulo admin-only  
**Fecha:** 2026-09-03 · **Versión:** 1.0  
**Archivos analizados:** `static/index.html` (líneas 1057–1360), `static/app.js` (líneas 1463–2360), `main.py` (líneas 2226–2499)

---

## Diagnóstico principal

El módulo POUR COST tiene el **mejor diseño conceptual** de los tres módulos admin-only analizados. El enfoque de sandbox en memoria es seguro y correcto; el calculador bidireccional (% → precio / precio → %) es elegante; la paleta semántica de umbrales (verde/ámbar/rojo) funciona visualmente. La fricción identificada es de nivel medio-bajo y se concentra en tres áreas:

1. **Descubrimiento y contexto** — filtros cuya semántica no está explicada (Precios A/B), buscador no descubrible, categorías que se "evaporan" al cambiar tipo
2. **Feedback de incompletos** — el badge "Costo incompleto" señala un problema sin identificar el ingrediente
3. **Sin salida del sandbox** — el admin encuentra el precio óptimo y no tiene cómo exportar ni anotar el resultado

---

## Estructura del layout

El panel `#panel-pourcost` se compone de arriba a abajo:

| Zona | Elemento | Notas |
|---|---|---|
| Tipo | 2 toggles: Cócteles / Productos sueltos | Cambia dataset, endpoint y lógica de modal |
| Horario | 2 toggles: Precios A / Precios B | `id_dia` 1 o 2; sin tooltip que explique qué es cada precio |
| Filtro | `<select>` de categoría | Derivado del dataset activo, no tiene endpoint propio |
| Búsqueda | ❌ No visible dentro del panel | Está en la topbar global, oculta por defecto |
| Contenido | Grid de tarjetas `auto-fill, minmax(240px)` | 1 col en móvil, 2+ en tablet |

**Tarjeta de cóctel:** Categoría + COD · Nombre · Precio + Costo · Badge de pour cost % (color semántico) · Badge "Costo incompleto" si algún ingrediente no tiene WAC.  
**Tarjeta de producto suelto:** Categoría + COD · Nombre · Precio + WAC · Badge de pour cost % · Badge "Sin WAC" si no tiene costo.

Umbrales de color:
- ≤ 28 % → verde (`badge-ok`)
- 28–35 % → ámbar (`badge-caution`)
- > 35 % → rojo (`badge-danger`)
- Sin precio en ese horario → neutro (`badge-info`)

---

## Modal de simulación

El modal `#pourcost-modal` opera exclusivamente en memoria: **ningún dato escrito se envía al backend**.

### Cócteles
1. Header fijo: **Costo / Precio / Pour Cost %** (actualiza en tiempo real)
2. Lista de ingredientes ordenada: Principales primero (fondo cian), Opcionales después (checkbox para incluir/excluir)
3. Por ingrediente: nombre · unidad · cantidad (editable con ± en pasos de 0.5 o teclado) · COGS calculado
4. Calculadora bidireccional:
   - Campo **Target %** → calcula precio exacto + precio redondeado a entero
   - Campo **Precio** → calcula % resultante
   - Solo un campo activo a la vez (flags `pourCostTargetTocadoManualmente` / `pourCostPrecioTocadoManualmente`)
5. Botón "Reiniciar simulación" → re-renderiza el modal con datos originales del servidor

### Productos sueltos
1. Header fijo igual
2. Input único de **WAC (editable en simulación)**
3. Misma calculadora bidireccional

---

## Flujos y pasos

### Consultar el pour cost de un cóctel — 2 pasos
1. Tap en tarjeta → abre modal con datos del servidor
2. Leer header fijo: Costo / Precio / %

✅ Flujo mínimo de lectura. Óptimo.

### Simular cambio de ingrediente — 5 pasos
1. Tap en tarjeta
2. Localizar el ingrediente en la lista (puede requerir scroll)
3. Ajustar cantidad con ± o teclado
4. Header se actualiza en tiempo real
5. Leer nuevo %

✅ Flujo de simulación correcto. El recálculo en tiempo real es el punto fuerte del módulo.

### Calcular precio por target % — 4 pasos
1. Abrir modal
2. (Opcional) Ajustar ingredientes
3. Escribir target % en "% Objetivo"
4. Leer precio sugerido redondeado

✅ Flujo limpio. La distinción exacto/redondeado es valiosa.

### Calcular % resultante dado un precio — 4 pasos
1. Abrir modal
2. (Opcional) Ajustar ingredientes
3. Escribir precio en "Precio de venta"
4. Leer % resultante

✅ Flujo limpio.

### Filtrar por horario — 1 paso
1. Tap en "Precios A" o "Precios B"

⚠ Función de 1 tap, pero la semántica de A/B no está explicada en ningún lugar del panel.

---

## Puntos de fricción

### Alta prioridad

**F1 — Buscador oculto fuera del panel**  
`filtrarPourCost()` existe y está conectada a `#topbar-search-input`, pero la función queda completamente oculta dentro del panel. Para catálogos de 50+ cócteles, la búsqueda por nombre es la navegación principal y no se puede descubrir.

**F2 — "Precios A / Precios B" sin contexto**  
Los dos toggles de horario no tienen ningún tooltip, texto de ayuda ni etiqueta explicativa. El admin no sabe si A = turno día, A = lunes–jueves, A = precio normal, etc. El sistema de precios del POS puede tener reglas específicas que el admin debe conocer para seleccionar el toggle correcto, y la UI no ofrece ninguna pista.

**F3 — Badge "Costo incompleto" es solo agregado a nivel de tarjeta** *(marcación por ingrediente ya existe)*  
La API retorna `costo_incompleto: True` a nivel de cóctel — eso sigue siendo cierto y sirve para saber, desde la grilla, qué tarjetas tienen algún ingrediente sin costear. Pero dentro del modal el detalle por ingrediente **ya está resuelto**: `PourCostIngrediente.sin_wac` (schema) se popula por ingrediente en `/api/pourcost/recetas` y el modal ya renderiza una etiqueta "Sin WAC cacheado" en color de advertencia junto al ingrediente afectado (`pourCostCrearFilaIngrediente()`, desde v11.9). El punto de fricción residual, si lo hay, es de jerarquía visual (texto vs. ícono), no de ausencia de dato.

### Prioridad media

**F4 — Sandbox sin salida: resultado no exportable**  
El admin encuentra un precio óptimo (p.ej., "el cóctel X debería costar 185 para quedar en 27%") y no puede hacer nada con ese dato dentro del módulo. No hay forma de copiar, exportar, ni anotar. El resultado existe solo mientras el modal esté abierto.

**F5 — Categorías se "evaporan" al cambiar Cócteles ↔ Productos**  
Al cambiar de tipo, la función `actualizarCategoriasPourCost()` reinicia el `<select>` y solo conserva el valor anterior si el mismo nombre de categoría existe en el nuevo dataset. Si el admin tenía "Whiskies" seleccionado en Cócteles y cambia a Productos, y esa categoría no existe, el select silenciosamente se resetea a "Todas". No hay aviso.

**F6 — WAC editable en modal de producto: ambigüedad de alcance**  
El campo WAC del modal es un `<input>` editable. El admin puede modificarlo para simular un cambio de costo — lo cual es correcto — pero el input luce idéntico a un campo de edición real. No hay indicación inline de que el cambio es solo para esta sesión. El disclaimer "simulación" está en el header del modal, no junto al campo.

**F7 — Sin precio para el horario seleccionado: modal sin baseline**  
Si un producto/cóctel no tiene precio definido para el horario A o B, el badge en la tarjeta muestra neutro y el precio en el modal aparece como "-". La calculadora bidireccional (% → precio) sigue funcionando, pero el campo "Precio de venta" (precio → %) no tiene valor base. El admin debe ingresar un precio desde cero sin saber si ya está en el sistema. No hay mensaje explicativo en el modal.

### Prioridad baja

**F8 — Corregido: el checkbox de ingredientes opcionales ya fue agrandado**  
El checkbox (`h-5 w-5`, 20px) ya está envuelto en un `<label>` con padding negativo/positivo (`-m-xs p-xs`) que amplía el área clickeable más allá del cuadro visual, específicamente para uso táctil en barra (fix v11.9, ver `documentos/pour_cost/pourcost.md` §6.3). No es un punto de fricción activo.

**F9 — Target % y Precio: no hay retroalimentación de cuál campo está "activo"**  
Los flags `pourCostTargetTocadoManualmente` y `pourCostPrecioTocadoManualmente` controlan cuál campo tiene prioridad, pero visualmente ambos inputs se ven iguales cuando ambos tienen valor. No hay indicación de cuál está "conduciendo" el cálculo.

**F10 — Botón "Reiniciar simulación" re-renderiza todo el modal**  
El reset llama a `abrirModalPourCostReceta()` o `abrirModalPourCostProducto()` nuevamente, lo que destruye y recrea todos los nodos del DOM. El scroll de la lista de ingredientes se pierde. Para cócteles con 8+ ingredientes donde el usuario ajustó uno en el fondo de la lista, el reset lo devuelve al tope sin advertencia.

**F11 — Error silencioso al cargar el dataset**  
Si `GET /api/pourcost/recetas` o `/api/pourcost/productos` falla, la grilla queda vacía. No hay mensaje de error visible dentro del panel — solo el empty state genérico (si lo hay) que puede confundirse con "no hay datos".

---

## Discrepancias frontend ↔ backend

**D1 — Corregido: el backend ya identifica el ingrediente sin WAC**  
`PourCostIngrediente.sin_wac: bool` (`schemas.py`) se popula por ingrediente en `/api/pourcost/recetas` (`main.py`), y el frontend ya lo usa para marcar la fila problemática en el modal. No hay gap frontend↔backend en este punto.

**D2 — WAC de ingredientes de receta no tiene timestamp de actualización**  
El campo de ingredientes de combo/receta es `wac_actual` (no `wac_unitario`), viene de `vw_pourcost_receta` (`schemas.py:258`, poblado en `main.py:2422`) y puede estar desactualizado si el ERP actualizó costos recientemente. Ese path no incluye un timestamp. Distinto es el caso de productos sueltos e insumos: ahí sí existe `PourCostProducto.fecha_actualizacion_wac` / el mismo campo en `PourCostInsumo` (`schemas.py:288,291,309`, poblado desde `v9_cache_wac_producto` en `main.py:2471`) — el dato ya lo devuelve la API, simplemente el frontend no lo muestra. `wac_unitario` es un nombre de campo distinto, exclusivo de esos dos endpoints (productos/insumos), y no aplica a ingredientes de receta.

**D3 — Precios A/B: la etiqueta "A" / "B" no está en la API**  
El backend recibe `id_dia` (1 o 2). La interpretación de "A" y "B" es solo fronted. Si el POS tiene nombres reales para esos schedules, la API no los expone y el UI no puede mostrarlos.

**D4 — `GET /api/pourcost/insumos` existe pero no está en la UI**  
El endpoint retorna el listado de insumos con WAC. No existe ningún panel, tab ni acceso desde la UI actual. Es funcionalidad de backend sin interfaz de usuario.

---

## Fortalezas del módulo (para preservar)

| Fortaleza | Impacto |
|---|---|
| Sandbox en memoria — ninguna edición persiste | Seguridad total: el admin experimenta sin riesgo |
| Recálculo en tiempo real al modificar cantidades | Feedback inmediato de la simulación |
| Calculadora bidireccional (% → precio, precio → %) | Cubre los dos casos de uso reales del admin |
| Thresholds semánticos (verde/ámbar/rojo) con umbrales claros (28 / 35 %) | Diagnóstico instantáneo del catálogo |
| Orden de ingredientes: Principales antes que Opcionales | Reduce el tiempo de lectura del modal |
| `inputmode="decimal"` en inputs de cantidad | Teclado decimal en móvil |
| `pourCostCompararIngredientes()` para ordenar la lista | Consistencia independiente del orden del backend |
| Precio exacto + precio redondeado en la sugerencia | El negocio trabaja sin centavos — información correcta |

---

## Recomendaciones priorizadas

### Quick Wins (máximo impacto, mínimo esfuerzo)

| # | Recomendación | Impacto | Esfuerzo |
|---|---|---|---|
| 01 | Mover buscador dentro del panel POUR COST | Alto | Mínimo |
| 02 | Tooltip en toggles Precios A/B explicando cada horario | Alto | Mínimo |
| ~~03~~ | ~~Marcar con ícono de advertencia el ingrediente sin WAC~~ — ya implementado (ver Rec 03) | — | — |

### Mejoras de presentación (un sprint)

| # | Recomendación | Impacto | Esfuerzo |
|---|---|---|---|
| 04 | Nota inline junto al campo WAC: "Solo en simulación" | Medio | Mínimo |
| 05 | Resaltar visualmente cuál calculadora está activa (Target % o Precio) | Medio | Mínimo |
| 06 | Mensaje explicativo en modal cuando no hay precio para el horario | Medio | Mínimo |
| 07 | Toast al resetear categoría al cambiar tipo Cócteles ↔ Productos | Bajo | Mínimo |

### Mejoras de funcionalidad (evaluación previa)

| # | Recomendación | Impacto | Esfuerzo |
|---|---|---|---|
| 08 | Botón "Copiar resultado" — copia precio sugerido al portapapeles | Medio | Bajo |
| 09 | Construir UI para `/api/pourcost/insumos` (listado de WAC de insumos) | Medio | Medio |
| 10 | Exportar análisis de precios a PDF (similar al PDF de PALOTEO 3) | Medio | Alto |

---

## Detalle de implementación — Quick wins

### Rec 01 — Buscador dentro del panel

Agregar en el HTML, después del select de categoría:

```html
<!-- En panel-pourcost, después del select de categoría -->
<div class="search-container">
  <input type="search"
         id="pourcost-search-inline"
         placeholder="Buscar por nombre o código..."
         oninput="filtrarPourCost(this.value)">
</div>
```

En `filtrarPourCost()` de `app.js`, leer también de `#pourcost-search-inline`:

```javascript
function filtrarPourCost(query) {
  const termino = (
    query ||
    document.getElementById('topbar-search-input')?.value ||
    document.getElementById('pourcost-search-inline')?.value || ''
  ).toLowerCase().trim();
  // resto de la lógica existente...
}
```

### Rec 02 — Tooltip en toggles Precios A/B

En el HTML del panel, agregar atributos `title` y `aria-label` a cada botón:

```html
<!-- Precios A (id real: pourcost-horario-a, index.html:1078) -->
<button id="pourcost-horario-a"
        title="Precios A — aplica de lunes a jueves"
        aria-label="Ver precios del horario A">
  Precios A
</button>

<!-- Precios B (id real: pourcost-horario-b, index.html:1079) -->
<button id="pourcost-horario-b"
        title="Precios B — aplica viernes, sábado y domingo"
        aria-label="Ver precios del horario B">
  Precios B
</button>
```

*Ajustar el texto del `title` al calendario real del negocio.*

### Rec 03 — Marcar ingrediente sin WAC *(ya implementado)*

El campo `sin_wac` por ingrediente y su marcación visual ya existen (ver F3/D1 corregidos arriba):

- Backend: `PourCostIngrediente.sin_wac: bool` (`schemas.py:259`), poblado en `/api/pourcost/recetas` (`main.py:2422-2423`).
- Frontend: `pourCostCrearFilaIngrediente()` (`app.js:2036`) ya renderiza `<p style="color:var(--semantic-warning)">Sin WAC cacheado</p>` por fila cuando `ingrediente.sin_wac` es `true`.

No queda trabajo pendiente en esta recomendación — se retira de los Quick Wins.

### Rec 05 — Indicar cuál calculadora está activa

Aplicar estilos dinámicos cuando un campo es tocado manualmente:

```javascript
// En el handler del campo Target %:
pourCostModalTarget.addEventListener('input', () => {
  pourCostTargetTocadoManualmente = true;
  pourCostPrecioTocadoManualmente = false;
  pourCostModalTarget.classList.add('border-primary-fixed-dim');
  pourCostModalPrecioInput.classList.remove('border-primary-fixed-dim');
  pourCostModalPrecioInput.classList.add('opacity-50');
  // cálculo existente...
});
```

---

## Contexto de acceso y estado global

```javascript
// Estado global del módulo
const pourCostEstado = {
  tipo:        'cocteles',   // 'cocteles' | 'productos'
  idDia:       1,            // 1 = Precios A, 2 = Precios B
  recetas:     [],           // cache del fetch de cócteles
  productos:   [],           // cache del fetch de productos
  idCategoria: '',
  nombre:      '',
};

// Umbrales semánticos (hardcoded, no vienen del backend)
const POURCOST_UMBRAL_OK      = 28;   // ≤ 28 % → verde
const POURCOST_UMBRAL_CAUTION = 35;   // 28–35 % → ámbar; > 35 % → rojo

// Sandbox — se descarta al cerrar o reabrir el modal
let pourCostSimulacion         = null;
let pourCostUltimoItemAbierto  = null;
```

El módulo **no escribe nada al backend**. Todo lo que el admin modifica en el modal existe únicamente en `pourCostSimulacion` hasta que se cierra o se abre otro ítem.

---

## Endpoints y fuentes de datos

| Endpoint | Descripción | Parámetros |
|---|---|---|
| `GET /api/pourcost/recetas` | Cócteles con ingredientes y pour cost % | `id_dia`, `id_categoria` (opt.) |
| `GET /api/pourcost/productos` | Productos sueltos con WAC y pour cost % | `id_dia` |
| `GET /api/pourcost/insumos` | Insumos con WAC (**sin UI actualmente**) | — |
| `GET /api/pourcost/menu` | Ítems de menú | — |

Las categorías se derivan en cliente del dataset activo — no hay endpoint propio.  
El WAC de ingredientes de receta viene de `vw_pourcost_receta` (campo `wac_actual`) y no tiene timestamp de actualización; el WAC de productos sueltos/insumos viene de `v9_cache_wac_producto` (campo `wac_unitario`) y sí trae `fecha_actualizacion_wac`, aunque el frontend hoy no la muestra (ver D2).

---

## Cache busting obligatorio

Cualquier modificación a los archivos del frontend requiere:
1. Bump de `CACHE_NAME` en `static/sw.js` (+0.1 MINOR para cambios incrementales)
2. Bump del `?v=X.Y` en los assets de `static/index.html`
3. Mantener ambas versiones en sincronía numérica

---

*BackStage API · Análisis UX Pour Cost · v1.0 · 2026-09-03*
