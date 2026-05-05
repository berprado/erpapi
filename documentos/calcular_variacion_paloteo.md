
Necesitamos calcular y mostrar el resultado de la comparacion entre el inventario segun el sistema y el inventario segun el conteo fisico (paloteo) que realizamos, 

### Mi recomendación visual (La combinación ganadora)

Sugiero combinar (Colores + Signos) de la siguiente manera para que la interfaz siga viéndose súper premium:

1.  **Cuando Falta (Merma/Pérdida):** Color **Rosa Neón** (que ya tienes en tu paleta) con el signo **`-`**. Ej: `-2 bot` o `-3.50 oz`. Alerta al cerebro de inmediato de que algo se perdió.
2.  **Cuando Sobra (Exceso):** Color **Amarillo/Ámbar**. Con el signo **`+`**. Ej: `+1 bot` o `+1.50 oz`. Indica precaución (tal vez no se facturó un trago o las medidas servidas fueron muy cortas).
3.  **Cuando Cuadra Perfecto:** Color **Verde Neón**. Con un **`✓`**. Ej: `✓ OK` o `✓ 0 oz`. Refuerza positivamente el buen trabajo.

---

### ¿Cómo lo implementamos?

Vamos a hacer dos pequeños ajustes en tu archivo `static/app.js` para guardar el stock teórico en la tarjeta y luego calcular la diferencia en vivo.

#### 1. Actualizar la función `renderizarProductos`
Primero, guardaremos el stock ideal (`stock_ideal_unidades` y `stock_ideal_onzas`) en la tarjeta usando `dataset`, y agregaremos los pequeños recuadros (`<span id="dif-paq-...">`) donde aparecerá la magia.

Reemplaza el inicio de la creación de la tarjeta en `renderizarProductos` por esto:

```javascript
// ==========================================
// RENDERIZADO Y DINAMISMO UI
// ==========================================
function renderizarProductos(productos) {
    listaProductos.innerHTML = '';

    productos.forEach(p => {
        const div = document.createElement('div');
        div.className = "bg-dark-surface border border-gray-800 rounded-xl p-4 shadow-lg product-card transition-colors focus-within:border-gray-600";
        div.dataset.id = p.id_producto;
        div.dataset.pesable = p.pesable || 0;
        div.dataset.nombre = p.nombre;
        
        // Guardar parámetros metrológicos
        div.dataset.tara = p.tara || 0;
        div.dataset.groz = p.gramos_por_oz || 1; 
        
        // NUEVO: Guardar stock teórico para comparar en vivo
        div.dataset.paqsist = parseFloat(p.stock_ideal_unidades) || 0;
        div.dataset.detsist = parseFloat(p.stock_ideal_onzas) || 0;

        // Info básica
        let html = `
            ${p.categoria_nombre ? `<span class="text-[10px] font-bold tracking-widest uppercase text-gray-500 mb-1 block">${escapeHtml(p.categoria_nombre)}</span>` : ''}
            <h4 class="text-neon-green font-bold text-lg mb-1">${escapeHtml(p.nombre)}</h4>
            <div class="text-[10px] text-gray-600 mb-2 flex gap-3">
                <span>ID: ${p.id_producto}</span>
                <span>Cód: ${escapeHtml(p.codigo)}</span>
            </div>
            
            <!-- Stocks del Sistema (Teóricos) -->
            <div class="text-xs text-gray-400 mb-2 flex gap-4">
                <span class="bg-gray-800 px-2 py-1 rounded">SIST: ${parseFloat(p.stock_ideal_unidades).toFixed(0)} bot.</span>
                ${p.pesable === 1 ? `<span class="bg-gray-800 px-2 py-1 rounded border border-gray-700">SIST: ${parseFloat(p.stock_ideal_onzas).toFixed(2)} oz</span>` : ''}
            </div>

            <!-- Contadores Dinámicos Reales (Físicos) + Diferencias -->
            <div class="text-[11px] font-bold mb-4 flex flex-col gap-2">
                <div class="flex items-center gap-2">
                    <span class="text-white bg-gray-700 px-2 py-1 rounded">BARRA: <span id="val-paq-${p.id_producto}">0</span> bot</span>
                    <span id="dif-paq-${p.id_producto}" class="px-2 py-1 rounded tracking-wider"></span>
                </div>
                ${p.pesable === 1 ? `
                <div class="flex items-center gap-2">
                    <span class="text-white bg-gray-700 px-2 py-1 rounded">BARRA: <span id="val-det-${p.id_producto}">0.00</span> oz</span>
                    <span id="dif-det-${p.id_producto}" class="px-2 py-1 rounded tracking-wider"></span>
                </div>` : ''}
            </div>
            
            <div class="grid grid-cols-2 gap-4">
            // ... (el resto del HTML sigue igual desde "Cerradas")
```

#### 2. Actualizar el "Motor de Cálculo"
Ahora añadiremos una pequeña función auxiliar (`formatearDiferencia`) que aplique el color y el signo, y actualizaremos los escuchadores de eventos para que la usen al instante.

Reemplaza tu bloque **"CÁLCULO EN TIEMPO REAL"** al final del archivo con esto:

```javascript
// ==========================================
// CÁLCULO EN TIEMPO REAL (ONZAS, UNIDADES Y DIFERENCIAS)
// ==========================================

// Función auxiliar para pintar las diferencias (Verde/Rosa/Amarillo)
function formatearDiferencia(diferencia, isOz = false) {
    const sufijo = isOz ? "oz" : "bot";
    
    // Si la diferencia es casi 0 (tolerancia para decimales en onzas)
    if (Math.abs(diferencia) < 0.01) {
        return `<span class="text-neon-green border border-neon-green/30 bg-neon-green/10 flex items-center gap-1"><span class="material-symbols-outlined text-[14px]">check_circle</span> OK</span>`;
    } 
    
    // Si falta producto (Negativo)
    if (diferencia < 0) {
        const val = isOz ? diferencia.toFixed(2) : Math.round(diferencia);
        return `<span class="text-neon-pink border border-neon-pink/30 bg-neon-pink/10">${val} ${sufijo}</span>`; // El signo '-' ya viene en el número
    } 
    
    // Si sobra producto (Positivo)
    const val = isOz ? diferencia.toFixed(2) : Math.round(diferencia);
    return `<span class="text-yellow-400 border border-yellow-400/30 bg-yellow-400/10">+${val} ${sufijo}</span>`;
}

// Función central para recalcular una tarjeta específica
function recalcularTarjeta(card) {
    if (!card) return;

    const idProducto = card.dataset.id;
    const pesable = parseInt(card.dataset.pesable);
    
    // Variables Teóricas (Sistema)
    const paqSist = parseFloat(card.dataset.paqsist) || 0;
    const detSist = parseFloat(card.dataset.detsist) || 0;
    
    // 1. Lógica de PAQ/BARRA (Botellas Cerradas)
    const inputCerradas = card.querySelector('.input-cerradas');
    const paqBarra = parseInt(inputCerradas.value) || 0;
    const spanPaq = document.getElementById(`val-paq-${idProducto}`);
    const difPaqSpan = document.getElementById(`dif-paq-${idProducto}`);
    
    if (spanPaq) spanPaq.textContent = paqBarra;
    if (difPaqSpan) difPaqSpan.innerHTML = formatearDiferencia(paqBarra - paqSist, false);
    
    // 2. Lógica de DET/BARRA (Onzas Físicas)
    if (pesable === 1) {
        const tara = parseFloat(card.dataset.tara);
        const groz = parseFloat(card.dataset.groz);
        const inputsPeso = card.querySelectorAll('.input-peso');
        const spanDet = document.getElementById(`val-det-${idProducto}`);
        const difDetSpan = document.getElementById(`dif-det-${idProducto}`);
        
        let detBarra = 0;
        const margenError = 10.0; 
        
        inputsPeso.forEach(inp => {
            const pesoMedido = parseFloat(inp.value);
            if (!isNaN(pesoMedido) && pesoMedido >= (tara - margenError)) {
                const pesoLiquido = Math.max(0, pesoMedido - tara);
                detBarra += (pesoLiquido / groz);
            }
        });
        
        if (spanDet) spanDet.textContent = detBarra.toFixed(2);
        if (difDetSpan) difDetSpan.innerHTML = formatearDiferencia(detBarra - detSist, true);
    }
}

// Escuchar tipeo en los inputs
listaProductos.addEventListener('input', (e) => {
    if (e.target.classList.contains('input-cerradas') || e.target.classList.contains('input-peso')) {
        recalcularTarjeta(e.target.closest('.product-card'));
    }
});

// Escuchar clics al botón [X] de eliminar botella
listaProductos.addEventListener('click', (e) => {
    if (e.target.closest('button') && e.target.closest('button').querySelector('.material-symbols-outlined')?.textContent === 'close') {
        const card = e.target.closest('.product-card');
        // Usamos setTimeout para dejar que el DOM elimine el input primero, y luego recalculamos
        setTimeout(() => recalcularTarjeta(card), 50);
    }
});

// NUEVO: Disparar el recálculo inicial cuando los productos se cargan
// Esto asegura que si al abrir la app todo está en "0", se muestre la diferencia en rojo de inmediato.
function inicializarCalculos() {
    document.querySelectorAll('.product-card').forEach(card => {
        recalcularTarjeta(card);
    });
}
```

**Y por último**, para que estas diferencias aparezcan apenas se carga la lista (mostrando todo en rojo alertando al bartender de que todo falta hasta que empiece a pesar), añade esta línea al final de tu función `renderizarProductos`:

```javascript
        div.innerHTML = html;
        listaProductos.appendChild(div);
    });

    // Añadir esta línea justo después del forEach
    inicializarCalculos(); 
}
```

**¿El resultado?**
Ahora el bartender no solo está introduciendo datos; está jugando un "minijuego" donde el objetivo es poner toda la pantalla en verde `✓ OK`. Si por error pone que hay 15 botellas de Sprite, verá inmediatamente un enorme y amarillo `+11 bot`. 