# UX Paloteo — Análisis de fricción y recomendaciones

**Proyecto:** BackStage API · PWA Frontend  
**Fecha:** 2026-09-03 · **Versión:** 1.0  
**Módulos analizados:** PALOTEO 1, PALOTEO 2, PALOTEO 3  

---

## Veredicto ejecutivo

**PALOTEO 2 genera la menor fricción para el caso de uso principal** — captura secuencial de inventario completo en cierre de turno. Su carrusel 1×1 con avance automático por `Enter` permite una cadencia muscular ininterrumpida que los otros dos layouts no alcanzan.

| Rol recomendado | Módulo |
|---|---|
| Captura secuencial (flujo principal) | **PALOTEO 2** |
| Correcciones puntuales | **PALOTEO 3** |
| Revisión global y confirmación de envío | **PALOTEO 1** |

---

## Resumen de fricción por módulo

| Aspecto | PALOTEO 1 | PALOTEO 2 | PALOTEO 3 |
|---|---|---|---|
| Layout | Lista vertical · scroll | Carrusel · 1 producto a la vez | Tabla compacta · alta densidad |
| Fricción captura inicial | 🔴 Alta | 🟢 Baja | 🟡 Media |
| Fricción correcciones | 🟡 Media | 🔴 Alta | 🟢 Baja |
| Fricción revisión global | 🟢 Baja | 🔴 Alta | 🟡 Media |
| Pasos por producto pesable | 4–5 taps | 3–4 taps | 5–8 taps |
| Feedback delta en tiempo real | ✅ Inline | ✅ Inline | Solo en módulo Reporte |
| Buscador de productos | ❌ | ❌ | ✅ |
| Exportar PDF | ❌ | ❌ | ✅ (único) |

---

## PALOTEO 1 — Análisis

**Layout:** Todos los productos apilados verticalmente. Cada tarjeta muestra tres filas de estado (Sistema / Barra / Delta) más inputs de unidades y pesos.

### Fortalezas
- Vista de panorama completo: todos los deltas visibles a la vez.
- Ideal en tablet horizontal o desktop donde el scroll es cómodo.
- Mejor módulo para la revisión post-captura antes de enviar.

### Problemas de fricción

**Sobrecarga visual durante la captura.**  
Las filas Sistema / Barra / Delta son información de *revisión*, no de *entrada*. Tenerlas visibles mientras el usuario tipea complejiza la lectura sin agregar valor en ese momento.

**El scroll rompe la cadencia.**  
Con 15+ productos, el usuario debe desplazarse entre tarjetas. Si necesita corregir un producto anterior, pierde su posición actual sin ningún mecanismo de "volver aquí después".

### Recomendación de rol
Redefinir PALOTEO 1 como vista de **revisión y confirmación**, no de captura. El usuario llega aquí después de capturar en PALOTEO 2 o 3, revisa los deltas y envía desde esta vista.

---

## PALOTEO 2 — Análisis

**Layout:** Un único producto en pantalla. `Enter` avanza entre campos (unidades → peso → siguiente producto) automáticamente.

### Fortalezas
- **Foco cognitivo total:** el usuario piensa en UN producto a la vez.
- **Cadencia rítmica:** `[dato] Enter [dato] Enter → siguiente` es casi automático.
- **Zero scroll:** el carrusel trae el producto al usuario.
- **Auto-advance:** al terminar los campos de un producto, el foco ya está en el primero del siguiente.
- Indicador de progreso "Prod 3/15" + "20%" reduce la ansiedad de "¿cuánto me falta?".

### Problemas de fricción

**Productos sin stock.**  
Para un producto con 0 unidades y sin botellas abiertas, el usuario debe escribir "0" y presionar Enter dos veces. No hay un botón "Sin stock / Saltar". En auditorías con varios productos vacíos, esto acumula fricción.

**Correcciones hacia atrás.**  
Navegar hacia atrás con [← Prev] interrumpe el ritmo. No hay indicador visual de qué productos ya tienen datos vs. cuáles están pendientes.

**Botones de navegación pequeños en móvil.**  
Los botones [← Prev] y [Sigt →] son texto plano. En pantallas táctiles, áreas de tap pequeñas generan errores de toque.

---

## PALOTEO 3 — Análisis

**Layout:** Tabla densa con todos los productos. Inputs compactos + botones `+` y `−` para ajustar valores. Buscador por ID, código o nombre.

### Fortalezas
- Buscador + botones ± = combinación ideal para ajustar un producto específico rápidamente.
- Óptimo para correcciones puntuales ("recuenté una botella más").
- Integración con REPORTE y exportación PDF.

### Problemas de fricción

**Lentitud con valores altos.**  
Los botones ± son óptimos para ajustes de ±1 o ±2. Para 12 botellas desde cero son 12 clicks. La coexistencia de input directo + botones crea ambigüedad sobre qué mecanismo usar.

**Densidad excesiva en móvil.**  
La tabla con tres columnas de controles (input + botón − + botón +) apila elementos muy pequeños en pantallas de 360–390px. Alta probabilidad de tap erróneo entre botones adyacentes.

**Reporte PDF como funcionalidad huérfana.**  
El usuario que captura en PALOTEO 2 y envía el paloteo no tiene acceso al PDF sin cambiar de módulo. No tiene justificación de UX.

---

## Hallazgos transversales

### 1 — Teclado numérico incompleto en móvil

Los inputs de unidades y pesos usan `type="number"`, que en iOS y Android puede mostrar el teclado QWERTY completo. La solución:

```html
<!-- Unidades (enteros) -->
<input type="number" inputmode="numeric" min="0">

<!-- Pesos (decimales) -->
<input type="number" inputmode="decimal" min="0" step="0.01">
```

`inputmode="numeric"` fuerza el teclado de dígitos puro. `inputmode="decimal"` agrega el punto/coma decimal. Impacto inmediato, esfuerzo mínimo.

**Archivos afectados:** `crearInputPeso()`, `crearInputPesoCompacto()`, inputs de `input-cerradas` en `crearTarjetaProductoElement()` y `crearFilaPaloteo3()`.

### 2 — Ambigüedad de unidades en el campo de peso

El label del campo es simplemente "Peso". La balanza del bar muestra gramos. El sistema espera gramos y convierte internamente a onzas. El label debe decir **"Peso (g)"** — o **"Peso (oz)"** si el perfil trabaja en onzas. El valor `gramos_por_oz` del perfil ya está disponible en el frontend.

### 3 — Feedback de progreso frío en PALOTEO 2

El contador "Prod 3/15" es informativo pero sin impacto visual. Una barra de progreso de 4–6px de alto (CSS puro) en la parte superior del carrusel amplifica la sensación de avance, especialmente hacia el final de listas largas.

### 4 — Reporte PDF como funcionalidad huérfana

La exportación PDF vive únicamente en PALOTEO 3. El lugar natural es el estado de éxito post-envío, accesible desde cualquier módulo.

### 5 — Sin indicador de estado por producto en PALOTEO 2

El contador global no revela cuáles productos tienen datos y cuáles están en blanco. Un punto de color junto al contador (verde = tiene dato, gris = vacío) resolvería esto con una línea de CSS + la función `leerValoresCard()` ya existente.

---

## Recomendaciones priorizadas

### Quick Wins (máximo impacto, mínimo esfuerzo)

| # | Recomendación | Impacto | Esfuerzo |
|---|---|---|---|
| 01 | `inputmode` en todos los inputs numéricos | Alto | Mínimo |
| 02 | Label de unidad en campo de peso: "Peso (g)" | Alto | Mínimo |
| 03 | Barra de progreso visual en PALOTEO 2 | Medio | Mínimo |

**Estas tres mejoras no tocan la lógica de negocio, no requieren cambios en el backend y pueden deployarse en el mismo sprint.**

### Mejoras de flujo (sprint dedicado)

| # | Recomendación | Impacto | Esfuerzo |
|---|---|---|---|
| 04 | Botón "Sin stock / Saltar" en PALOTEO 2 | Medio | Bajo |
| 05 | Indicador de estado por producto en navegador de PALOTEO 2 | Medio | Bajo |
| 06 | PALOTEO 2 como tab activo por defecto (o selector inicial por dispositivo) | Alto | Medio |
| 07 | Mover exportación PDF al estado post-envío | Medio | Medio |

### Mejoras de arquitectura (evaluación previa)

| # | Recomendación | Impacto | Esfuerzo |
|---|---|---|---|
| 08 | Separar modo captura de modo revisión en tarjeta de PALOTEO 1 | Alto | Alto |

---

## Detalle de recomendaciones seleccionadas

### Rec 01 — inputmode en inputs numéricos

```html
<!-- En crearInputPeso() y crearInputPesoCompacto() -->
<!-- Unidades (enteros): -->
<input type="number" inputmode="numeric" min="0" class="input-cerradas">

<!-- Pesos (decimales): -->
<input type="number" inputmode="decimal" min="0" step="0.01" class="input-peso">
```

### Rec 03 — Barra de progreso en PALOTEO 2

Agregar en el HTML del panel-logs un `<div id="barra-progreso-p2">` con estilos CSS, y en `navegarCaptura()`:

```javascript
// En app.js — función navegarCaptura() o la que actualiza el contador
const pct = ((indiceActual + 1) / totalProductos) * 100;
document.querySelector('#barra-progreso-p2').style.width = pct + '%';
```

### Rec 04 — Botón "Sin stock / Saltar" en PALOTEO 2

```javascript
// Lógica del botón "Sin stock":
function saltarProductoSinStock() {
  const card = obtenerTarjetaCanonica(productoActual.id_producto);
  // Setear cerradas=0, limpiar pesos
  aplicarValoresCard(card, { cerradas: 0, pesos: [] }, crearInputPeso);
  // Sincronizar y avanzar
  syncCapturaConInventario(card);
  if (indiceActual < totalProductos - 1) navegarCaptura(indiceActual + 1);
}
```

---

## Contexto del análisis

### Arquitectura compartida entre los tres módulos

Los tres módulos comparten (~70% del código):
- **Fuente canónica de datos:** `#lista-productos .product-card` (PALOTEO 1)
- **Sincronización bidireccional:** `syncCapturaConInventario()`, `syncFilaPaloteo3ConInventario()`
- **Validación global:** `validarTarjeta()`, `ejecutarValidacionesGlobales()`
- **Autosave:** `flushAutosave()`, `hydrateAutosaveDraft()` en `localStorage`
- **Constructores de inputs:** `crearInputPeso()`, `crearInputPesoCompacto()`
- **Cálculo de diferencias:** `recalcularTarjeta()`, `formatearDiferencia()`

Código específico por módulo (~30%): renderizado, navegación modal y funciones de reporte.

### Cache busting obligatorio

Cualquier modificación a los archivos del frontend requiere:
1. Bump de `CACHE_NAME` en `static/sw.js` (+0.1 MINOR para cambios incrementales)
2. Bump del `?v=X.Y` en los assets de `static/index.html`
3. Mantener ambas versiones en sincronía numérica

---

*BackStage API · Análisis UX Paloteo · v1.0 · 2026-09-03*
