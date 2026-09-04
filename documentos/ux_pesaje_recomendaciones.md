# UX Pesaje — Análisis de fricción y recomendaciones

**Proyecto:** BackStage API · PWA Frontend · Módulo admin-only  
**Fecha:** 2026-09-03 · **Versión:** 1.0  
**Archivos analizados:** `static/index.html` (líneas 1017–1260, incluye `#panel-pesaje` y `#pesaje-modal`), `static/app.js` (líneas 644–1451), `main.py` (líneas 908–1326), `schemas.py` (líneas 60–98)

---

## Diagnóstico principal

El módulo PESAJE tiene una base funcional sólida, pero concentra su fricción en tres áreas:

1. **Buscador no descubrible** — el buscador vive fuera del panel en la topbar global y está oculto por defecto
2. **Doble modal encadenado** para crear perfiles — flujo de 7–10 pasos con dos backdrops superpuestos
3. **Transiciones de estado silenciosas** — el flujo "promover" cambia de pestaña un producto sin aviso

Las validaciones y el feedback de errores son en general correctos, aunque duplicados (inline + diálogo modal) en el flujo de error de PUT.

---

## Estructura del layout

El panel `#panel-pesaje` se compone de arriba a abajo:

| Zona | Elemento | Notas |
|---|---|---|
| Cabecera | Título + subtítulo | Sin botón de acción global |
| Filtro 1 | `<select>` de categoría | Ancho completo, carga dinámica desde `/api/pesaje/categorias` |
| Filtro 2 | 3 tabs: Pesables / Incompletos / No pesables | Toggle buttons |
| Contenido | Grid de tarjetas `auto-fill, minmax(240px)` | 1 col en móvil, 2+ en tablet |
| Búsqueda | ❌ No visible dentro del panel | Está en la topbar global, oculta por defecto |

**Tarjeta de producto:** categoría + ID + código (monoespaciado) · nombre · badges de volumen · badge "Comandable" · botones "Editar" y "Calcular" (el segundo solo si pesable y completo). Borde naranja si el perfil está incompleto.

---

## Flujos y pasos requeridos

### Editar un campo de perfil existente — 4 pasos

1. Tap **"Editar"** → abre `#pesaje-modal`
2. Localizar el perfil (puede requerir scroll si hay 3+ modelos)
3. Editar el campo (peso bruto / tara / código de barras) — `gr/oz` es siempre readonly y se recalcula automáticamente
4. Tap **"Guardar"** → PUT → diálogo de éxito → tap **"Aceptar"**

⚠ Tras guardar, `cargarPesaje()` hace un fetch completo y el modal se reinicializa perdiendo la posición de scroll.

### Crear un nuevo modelo de botella — 7–10 pasos

1. Tap **"Editar"** → abre `#pesaje-modal`
2. Scroll hasta el pie → tap **"Agregar modelo"**
3. Se abre `#modelo-botella-dialog` (segundo modal, z-55 sobre z-50)
4. Nombre del modelo (obligatorio; autofill "Estándar" solo si es el primero)
5. Peso bruto (g) — obligatorio
6. Tara (g) — obligatorio
7. gr/oz se calcula automáticamente (readonly)
8. Código de barras (opcional)
9. Tap **"Guardar modelo"** → POST
10. Segundo modal cierra, primero se recarga. Sin diálogo de confirmación de éxito.

⚠ Doble modal encadenado. Si el POST falla, el segundo modal se re-abre con el error en `#mb-error`.

### Eliminar un modelo — 3 pasos

1. Tap **"Editar"** → localizar el perfil
2. Tap **"Eliminar"** → diálogo de confirmación
3. Tap **"Confirmar"** → DELETE → modal se recarga

✅ Flujo correcto. El botón solo aparece cuando hay 2+ perfiles activos (sincronizado con regla del backend).

### Promover un perfil fantasma (pesable=0 → pesable=1) — 4 pasos — flujo implícito

1. Ir a la tab **"No pesables"** (el fantasma solo aparece aquí)
2. Tap **"Editar"** → campos habilitados porque `ind_permite_comandar = 'si'`
3. Completar peso bruto y tara
4. Tap **"Guardar"** → backend detecta elegibilidad y cambia `pesable` a 1

⚠ El producto desaparece de la vista actual sin ningún aviso. El admin puede pensar que se perdió el dato.

### Buscar por nombre — 2+ pasos — no descubrible

1. Tap en el ícono de lupa en la barra superior (no hay indicación dentro del panel)
2. El campo aparece — tipear con debounce de 350ms

⚠ Función crítica para catálogos de 50+ productos, completamente no descubrible.

---

## Puntos de fricción

### Alta prioridad

**F1 — Buscador oculto fuera del panel**  
El filtro por texto (`#topbar-search-input`) vive en la barra global y está `hidden` por defecto. `filtrarPesaje()` existe y funciona, pero nadie la descubre. Para catálogos grandes, esta es la función más importante y la menos visible.

**F2 — Recarga completa del listado tras cada guardado**  
`cargarPesaje()` hace un fetch HTTP completo y re-renderiza toda la grilla. El modal de edición se reinicializa perdiendo la posición de scroll. Para productos con 4+ perfiles, el admin tiene que volver a hacer scroll.

**F3 — Doble modal encadenado para crear perfil**  
`#pesaje-modal` (z-50) → `#modelo-botella-dialog` (z-55). Dos backdrops superpuestos. No es un wizard con pasos numerados. En móvil, el resultado son dos overlays oscuros apilados.

**F4 — Flujo "Promover" sin feedback**  
Al guardar un perfil `pesable=0` que cumple los criterios, el backend cambia automáticamente `pesable` a 1 y el producto desaparece del tab activo sin ningún aviso, toast ni mensaje explicativo.

### Prioridad media

**F5 — Botón "Eliminar" ausente sin explicación**  
Si hay un solo perfil activo, el botón simplemente no aparece. Sin tooltip ni texto de ayuda. El admin puede pensar que la función está rota o que no tiene permisos.

**F6 — Label "gr/oz" inconsistente**  
En el modal de edición: "gr/oz". En el modal de creación: "g / oz (calculado)". Inconsistencia que genera duda sobre si el campo es editable.

**F7 — Guardado parcial no comunicado**  
El PUT acepta `peso_bruto` sin tara. La UI no informa esta posibilidad. El admin puede dudar entre ingresar la tara ahora o esperar.

**F8 — Error duplicado: inline + diálogo modal**  
Al fallar un PUT, el error aparece en el `errorEl` inline y también en `mostrarDialogoResultado`. El admin ve el mismo error dos veces.

**F9 — "Peso bruto (copas)" es semánticamente confuso**  
Para vinos, el label del campo cambia a "Peso bruto (copas)", pero el dato esperado es el número de copas estándar por botella, no un peso. Un admin nuevo ingresará gramos.

**F10 — Sin confirmación de éxito al crear modelo**  
El POST exitoso cierra el segundo modal sin `mostrarDialogoResultado` de éxito. La única confirmación es ver el nuevo perfil en la lista — que puede quedar fuera del área visible.

### Prioridad baja

**F11 — Error silencioso al cargar categorías**  
Si `GET /api/pesaje/categorias` falla, el select queda solo con "Todas las categorías" sin aviso. El filtro queda no funcional silenciosamente.

**F12 — Doble fetch al alternar Pesables/Incompletos**  
Ambas tabs hacen el mismo request. Cambiar entre ellas dispara un nuevo fetch aunque los datos estén en memoria.

---

## Discrepancias frontend ↔ backend

**D1 — `tolerancia_oz` no visible ni editable**  
El schema incluye `tolerancia_oz`, pero `ActualizarPesajeConfigRequest` no lo acepta y la UI no lo muestra. La tolerancia activa siempre es 0.5 oz (fijada en `_obtener_tolerancia_operativa_oz`). El admin no puede saber cuál es la tolerancia activa sin leer el código.

**D2 — Asimetría crear vs. editar**  
POST requiere `peso_bruto > 0` y `tara >= 0` obligatorios. PUT acepta tara nula (guardado parcial). Asimetría con sentido de negocio pero no comunicada en la UI.

**D3 — Promoción silenciosa**  
El PUT puede cambiar `pesable` de 0 a 1 sin indicarlo en la respuesta al usuario. El diálogo de éxito (`titulo: 'Modelo guardado'`, `mensaje: 'Se guardaron los cambios de "..." correctamente.'`) no menciona el cambio de estado.

**D4 — `volumen_oz` nulo deja gr/oz en blanco**  
Si `volumen_oz` es `null` o `0`, el input gr/oz queda vacío sin mensaje explicativo. El admin no sabe si debe ingresarlo o si hay un problema con el catálogo.

**D5 — Fantasmas clasificados en "No pesables" en lugar de "Incompletos"**  
Un producto con `pesable=0` pero `ind_permite_comandar='si'` aparece en "No pesables". Para el admin, ese producto necesita configuración y debería estar en "Incompletos" o en una sub-tab "Pendientes".

---

## Recomendaciones priorizadas

### Quick Wins (máximo impacto, mínimo esfuerzo)

| # | Recomendación | Impacto | Esfuerzo |
|---|---|---|---|
| 01 | Mover buscador dentro del panel PESAJE | Alto | Mínimo |
| 02 | Toast explicativo al promover perfil fantasma | Alto | Bajo |
| 03 | Renombrar "Peso bruto (copas)" a "Copas por botella" + texto de ayuda | Alto | Mínimo |

### Mejoras de presentación (un sprint)

| # | Recomendación | Impacto | Esfuerzo |
|---|---|---|---|
| 04 | Eliminar el diálogo modal duplicado en errores de PUT | Medio | Mínimo |
| 05 | Tooltip o aviso cuando "Eliminar" no aparece | Medio | Mínimo |
| 06 | Consistencia de label "gr/oz (calculado)" en modal de edición | Bajo | Mínimo |
| 07 | Nota de guardado parcial en el modal de edición | Medio | Mínimo |

### Mejoras de arquitectura (evaluación previa)

| # | Recomendación | Impacto | Esfuerzo |
|---|---|---|---|
| 08 | Badge/sub-tab para perfiles fantasma en "No pesables" | Medio | Medio |
| 09 | Reemplazar doble modal por formulario inline o panel lateral | Alto | Alto |

---

## Detalle de implementación — Quick wins

### Rec 01 — Buscador dentro del panel

Agregar en el HTML, entre el select de categoría y los tabs de filtro:

```html
<!-- En panel-pesaje, después del select de categoría -->
<div class="search-container">
  <input type="search"
         id="pesaje-search-inline"
         placeholder="Buscar producto por nombre, ID o código..."
         oninput="filtrarPesaje()">
</div>
```

Y en `filtrarPesaje()` de `app.js`, leer también de `#pesaje-search-inline`:

```javascript
function filtrarPesaje() {
  const termino = (
    document.getElementById('topbar-search-input')?.value ||
    document.getElementById('pesaje-search-inline')?.value || ''
  ).toLowerCase().trim();
  // resto de la lógica existente...
}
```

### Rec 02 — Toast al promover fantasma

En `app.js`, antes de llamar a `cargarPesaje()` después del PUT exitoso, verificar si cambió `pesable`:

```javascript
// Guardar estado previo antes del fetch
const pesablePrevio = perfilActual.pesable;

// Después de la respuesta exitosa del PUT (no existe un componente de "toast" en el
// proyecto; el mecanismo real de aviso es mostrarDialogoResultado(), ya usado para
// el diálogo de éxito de este mismo flujo — ver static/app.js:665):
const data = await resp.json();
if (pesablePrevio === 0 && data.pesable === 1) {
  mostrarDialogoResultado({
    tipo: 'success',
    titulo: 'Modelo guardado',
    mensaje: 'El producto fue configurado como pesable y se movió a la pestaña Pesables.',
  });
} else {
  mostrarDialogoResultado({ tipo: 'success', titulo: 'Modelo guardado', mensaje: 'Se guardaron los cambios correctamente.' });
}
cargarPesaje();
```

### Rec 03 — Renombrar "Copas" para vinos

En `crearFilaPerfilPesaje()` de `app.js`, el label hoy se arma en un template literal, no en una variable dedicada:

```javascript
// Antes (app.js, dentro del template de crearFilaPerfilPesaje()):
`Peso bruto (${esVino ? 'copas' : 'g'})`

// Después:
`${esVino ? 'Copas por botella' : 'Peso bruto (g)'}`
// + agregar un texto de ayuda cuando esVino: 'Número de copas estándar que rinde esta botella.'
```

Nota: el modal de creación `#modelo-botella-dialog` (`index.html`) **no** tiene esta rama condicional — su label "Peso bruto (g)" está fijo para toda categoría, vino incluido (no hay lógica `esVino` en `abrirModalModelo()`). Si se quiere el mismo tratamiento ahí, es una adición nueva, no un "mismo cambio" a un label ya condicional.

---

## Código compartido con PALOTEO

| Función | Compartida | Rol |
|---|---|---|
| `esCategoriaVinos(idCategoria)` | Paloteo + Pesaje | Detecta categoría ID 6 para lógica diferencial |
| `etiquetaDetalleCorta/Larga()` | Todos | "oz" vs "cop" / "copas" |
| `mostrarDialogoResultado()` | Todos | Diálogo success/error modal |
| `mostrarDialogoConfirmacion()` | Pesaje + eliminar paloteo | Confirmación sí/no |
| `fetchAutenticado()` | Todos | HTTP con token JWT + manejo `SesionExpiradaError` |
| `escapeHtml()` | Todos | Sanitización XSS antes de `innerHTML` |

No hay lógica duplicada que requiera unificación inmediata. La separación entre PESAJE y PALOTEO es limpia: PESAJE tiene su propio estado (`pesajeEstado`, `pesajeModalProductoActualId`) y endpoints independientes.

---

## Cache busting obligatorio

Cualquier modificación a los archivos del frontend requiere:
1. Bump de `CACHE_NAME` en `static/sw.js` (+0.1 MINOR para cambios incrementales)
2. Bump del `?v=X.Y` en los assets de `static/index.html`
3. Mantener ambas versiones en sincronía numérica

---

*BackStage API · Análisis UX Pesaje · v1.0 · 2026-09-03*
