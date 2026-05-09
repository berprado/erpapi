// ==========================================
// CONFIGURACIÓN Y ESTADO GLOBAL
// ==========================================
// Fix #22: URL dinámica para que funcione tanto en localhost como en producción
const API_BASE = `${window.location.origin}/api`;
let currentToken = localStorage.getItem('token') || null;
let currentOperacionId = null;
const ID_BARRA_ACTUAL = 1; // Podemos hacerlo dinámico después

// Elementos del DOM
const loginScreen = document.getElementById('login-screen');
const appScreen = document.getElementById('app-screen');
const loginForm = document.getElementById('login-form');
const btnLogout = document.getElementById('btn-logout');
const listaProductos = document.getElementById('lista-productos');
const actionBar = document.getElementById('action-bar');
const btnGuardar = document.getElementById('btn-guardar');

// ==========================================
// INICIALIZACIÓN
// ==========================================

// Fix #24: Función helper para escapar HTML y prevenir ataques XSS.
// Se aplica a cualquier valor dinámico (nombres, códigos) antes de inyectarlos con innerHTML.
function escapeHtml(str) {
    if (str == null) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

// Fix #27: Función centralizada para crear el HTML de un input de peso.
// Soporta perfiles múltiples para seleccionar el modelo de botella por registro.
function crearInputPeso(perfilesJson, removable = true) {
    const perfiles = JSON.parse(perfilesJson || '[]');
    let selectHTML = '';

    if (perfiles.length > 1) {
        selectHTML = `<select class="bg-surface-container-low text-data-tabular text-primary-fixed border border-outline-variant rounded-md px-sm py-xs focus:outline-none select-perfil mr-sm cursor-pointer font-semibold">`;
        perfiles.forEach((pf, idx) => {
                const optionValue = (pf.id != null) ? pf.id : idx;
                selectHTML += `<option value="${optionValue}">${escapeHtml(pf.nombre_perfil)}</option>`;
        });
        selectHTML += `</select>`;
    }

    const removeButtonHtml = removable
        ? `<button type="button" onclick="this.parentElement.parentElement.remove()" class="absolute right-sm top-1/2 -translate-y-1/2 text-on-surface-variant hover:text-error transition-colors" aria-label="Eliminar campo de peso">
                    <span class="material-symbols-outlined text-sm">close</span>
                </button>`
        : '';

    return `
        <div class="relative flex items-center item-peso-wrapper gap-sm">
            ${selectHTML}
            <div class="relative flex-1">
                <input type="number" min="0" step="1" class="w-full bg-surface border border-outline-variant rounded-md pl-md pr-lg py-sm text-on-surface input-peso focus:border-error focus:outline-none focus:shadow-cyan-glow-focus font-data-tabular" placeholder="Ej: 950" required>
                ${removeButtonHtml}
            </div>
        </div>
    `;
}

function resolverPerfilSeleccionado(perfiles, select) {
    if (!perfiles || perfiles.length === 0) return { perfil: null, index: -1 };
    if (!select) return { perfil: perfiles[0], index: 0 };

    const valor = select.value;
    const porId = perfiles.findIndex(pf => pf && pf.id != null && String(pf.id) === String(valor));
    if (porId >= 0) return { perfil: perfiles[porId], index: porId };

    const porIndice = parseInt(valor, 10);
    if (!Number.isNaN(porIndice) && porIndice >= 0 && porIndice < perfiles.length) {
        return { perfil: perfiles[porIndice], index: porIndice };
    }

    return { perfil: perfiles[0], index: 0 };
}

function refrescarSelectoresPerfil(card) {
    if (!card) return;

    const perfiles = JSON.parse(card.dataset.perfiles || '[]');
    const wrappers = card.querySelectorAll('.item-peso-wrapper');

    wrappers.forEach((wrapper) => {
        const selectExistente = wrapper.querySelector('.select-perfil');
        const valorActual = selectExistente ? selectExistente.value : '';

        if (selectExistente) {
            selectExistente.remove();
        }

        if (perfiles.length <= 1) {
            return;
        }

        const select = document.createElement('select');
        select.className = 'bg-surface-container-low text-data-tabular text-primary-fixed border border-outline-variant rounded-md px-sm py-xs focus:outline-none select-perfil mr-sm cursor-pointer font-semibold';

        perfiles.forEach((pf, idx) => {
            const option = document.createElement('option');
            option.value = (pf.id != null) ? String(pf.id) : String(idx);
            option.textContent = pf.nombre_perfil;
            select.appendChild(option);
        });

        if (valorActual && Array.from(select.options).some(opt => opt.value === valorActual)) {
            select.value = valorActual;
        }

        wrapper.insertBefore(select, wrapper.firstChild);
    });
}

async function crearModeloBotella(idProducto) {
    const card = document.querySelector(`.product-card[data-id="${idProducto}"]`);
    if (!card) return;

    const nombreProducto = card.dataset.nombre || `ID ${idProducto}`;
    const perfiles = JSON.parse(card.dataset.perfiles || '[]');
    const perfilBase = perfiles[0] || null;

    const nombrePerfil = prompt(`Nuevo modelo para ${nombreProducto}\nNombre del perfil (ej: BOTELLA ALTA):`, '');
    if (nombrePerfil === null) return;
    if (!nombrePerfil.trim()) return alert('Debes ingresar un nombre de perfil.');

    const pesoBrutoTxt = prompt('Peso bruto (gramos):', perfilBase ? String(perfilBase.peso_bruto) : '');
    if (pesoBrutoTxt === null) return;
    const taraTxt = prompt('Tara (gramos):', perfilBase ? String(perfilBase.tara) : '');
    if (taraTxt === null) return;
    const gramosPorOzTxt = prompt('Gramos por onza:', perfilBase ? String(perfilBase.gramos_por_oz) : '29.5735');
    if (gramosPorOzTxt === null) return;
    const toleranciaTxt = prompt('Tolerancia (oz):', perfilBase ? String(perfilBase.tolerancia_oz) : '0');
    if (toleranciaTxt === null) return;

    const pesoBruto = parseFloat(pesoBrutoTxt);
    const tara = parseFloat(taraTxt);
    const gramosPorOz = parseFloat(gramosPorOzTxt);
    const toleranciaOz = parseFloat(toleranciaTxt);

    if ([pesoBruto, tara, gramosPorOz, toleranciaOz].some(Number.isNaN)) {
        return alert('Todos los valores numéricos del modelo deben ser válidos.');
    }

    try {
        const response = await fetch(`${API_BASE}/pesaje/perfiles`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${currentToken}`
            },
            body: JSON.stringify({
                id_producto: idProducto,
                nombre_perfil: nombrePerfil.trim(),
                peso_bruto: pesoBruto,
                tara: tara,
                gramos_por_oz: gramosPorOz,
                tolerancia_oz: toleranciaOz
            })
        });

        if (response.status === 401) return btnLogout.click();

        const data = await response.json();
        if (!response.ok) {
            return alert(`No se pudo crear el modelo: ${data.detail || 'Error desconocido'}`);
        }

        const perfilesActuales = JSON.parse(card.dataset.perfiles || '[]');
        perfilesActuales.push(data);
        card.dataset.perfiles = JSON.stringify(perfilesActuales);
        refrescarSelectoresPerfil(card);
        recalcularTarjeta(card);
        alert('Modelo de botella agregado correctamente.');
    } catch (error) {
        alert('Error de red al crear el modelo de botella.');
    }
}

document.addEventListener('DOMContentLoaded', () => {
    if (currentToken) {
        mostrarPantallaApp();
    } else {
        mostrarPantallaLogin();
    }

    // Configurar Password Toggle (El ojito)
    const togglePassword = document.querySelector('button[type="button"]');
    const passwordInput = document.getElementById('password');
    togglePassword.addEventListener('click', () => {
        const type = passwordInput.getAttribute('type') === 'password' ? 'text' : 'password';
        passwordInput.setAttribute('type', type);
        togglePassword.querySelector('span').textContent = type === 'password' ? 'visibility' : 'visibility_off';
    });
});

// ==========================================
// AUTENTICACIÓN Y NAVEGACIÓN
// ==========================================
loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const usuario = document.getElementById('username').value;
    const contrasena = document.getElementById('password').value;
    const errorBox = document.getElementById('login-error');

    try {
        const response = await fetch(`${API_BASE}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ usuario, contrasena })
        });

        const data = await response.json();

        if (response.ok) {
            currentToken = data.access_token;
            localStorage.setItem('token', currentToken);
            localStorage.setItem('nombres', data.nombres);
            mostrarPantallaApp();
        } else {
            errorBox.textContent = data.detail || "Error al iniciar sesión";
            errorBox.classList.remove('hidden');
        }
    } catch (error) {
        errorBox.textContent = "Error de conexión con el servidor.";
        errorBox.classList.remove('hidden');
    }
});

btnLogout.addEventListener('click', () => {
    localStorage.removeItem('token');
    localStorage.removeItem('nombres');
    currentToken = null;
    mostrarPantallaLogin();
});

function mostrarPantallaLogin() {
    loginScreen.classList.remove('hidden');
    appScreen.classList.add('hidden');
    document.getElementById('password').value = '';
}

function mostrarPantallaApp() {
    loginScreen.classList.add('hidden');
    appScreen.classList.remove('hidden');
    document.getElementById('user-display').textContent = localStorage.getItem('nombres');
    iniciarDashboard();
}

// ==========================================
// LÓGICA DE NEGOCIO (DASHBOARD)
// ==========================================
async function iniciarDashboard() {
    listaProductos.innerHTML = ''; // Limpiar lista
    actionBar.classList.add('hidden');
    
    const estadoIcon = document.getElementById('estado-icon');
    const estadoTexto = document.getElementById('estado-texto');
    
    // Fix #28: Resetear clases del icóno antes de cada verificación para evitar acumulación de estilos.
    estadoIcon.className = 'material-symbols-outlined text-4xl text-on-surface-variant';
    estadoIcon.textContent = "hourglass_empty";
    estadoIcon.classList.add('animate-pulse');
    estadoTexto.textContent = "Verificando estado de la caja...";
    const estadoTituloReset = document.getElementById('estado-titulo');
    if (estadoTituloReset) estadoTituloReset.textContent = "Verificando operativa...";

    // 1. Verificar "Guardia de Seguridad" (Estado de Operación)
    try {
        const responseOp = await fetch(`${API_BASE}/operacion/activa`, {
            headers: { 'Authorization': `Bearer ${currentToken}` }
        });
        
        const dataOp = await responseOp.json();

        if (!responseOp.ok) {
            // Error 401: Token expirado
            if(responseOp.status === 401) return btnLogout.click();

            // Caja en proceso u otro error
            estadoIcon.textContent = "block";
            estadoIcon.classList.remove('animate-pulse', 'text-primary-fixed');
            estadoIcon.classList.add('text-error');
            const estadoTituloErr = document.getElementById('estado-titulo');
            if (estadoTituloErr) estadoTituloErr.textContent = "Operativa no disponible";
            estadoTexto.textContent = dataOp.detail || "No se puede realizar el paloteo.";
            return; // Bloqueamos la ejecución aquí
        }

        // Luz Verde: Guardamos el ID de operación
        currentOperacionId = dataOp.id_operacion;
        estadoIcon.textContent = "check_circle";
        estadoIcon.classList.remove('animate-pulse', 'text-on-surface-variant', 'text-error');
        estadoIcon.classList.add('text-secondary');
        // Actualizar título y mensaje según respuesta del servidor
        const estadoTitulo = document.getElementById('estado-titulo');
        if (estadoTitulo && dataOp.titulo) {
            estadoTitulo.textContent = dataOp.titulo;
        }
        estadoTexto.textContent = dataOp.mensaje; // "Puedes registrar el Inventario Físico"

        // 2. Cargar Lista de Productos Pendientes
        cargarProductos();

    } catch (error) {
        estadoTexto.textContent = "Error de conexión con el servidor.";
    }
}

async function cargarProductos() {
    try {
        const response = await fetch(`${API_BASE}/inventario/pendientes`, {
            headers: { 'Authorization': `Bearer ${currentToken}` }
        });

        // Fix #25: Manejar token expirado igual que en iniciarDashboard()
        if (response.status === 401) return btnLogout.click();

        const productos = await response.json();

        if (response.ok && productos.length > 0) {
            renderizarProductos(productos);
            actionBar.classList.remove('hidden'); // Mostrar barra de guardado
            actionBar.classList.add('flex');
        } else {
            listaProductos.innerHTML = `<div class="text-center text-on-surface-variant py-lg font-body-base">No hay productos consumidos para auditar hoy.</div>`;
        }
    } catch (error) {
        console.error("Error cargando productos", error);
    }
}

// ==========================================
// RENDERIZADO Y DINAMISMO UI
// ==========================================
function renderizarProductos(productos) {
    listaProductos.innerHTML = '';

    productos.forEach(p => {
        // Crear la tarjeta (card)
        const div = document.createElement('div');
        div.className = "bg-surface-container border border-outline-variant rounded-md p-md shadow-lg product-card transition-colors focus-within:border-primary-fixed-dim chassis-panel";
        div.dataset.id = p.id_producto;
        div.dataset.pesable = p.pesable || 0;
        div.dataset.nombre = p.nombre;
        const perfilesJson = JSON.stringify(p.perfiles || []);
        div.dataset.perfiles = perfilesJson;
        
        // NUEVO: Guardar los datos matemáticos en el DOM para usarlos en vivo
        div.dataset.tolerancia = (p.perfiles && p.perfiles.length > 0) ? p.perfiles[0].tolerancia_oz : 0;
        div.dataset.paqsist = parseFloat(p.stock_ideal_unidades) || 0;
        div.dataset.detsist = parseFloat(p.stock_ideal_onzas) || 0;

        // Info básica
        let html = `
            ${p.categoria_nombre ? `<span class="text-label-mono font-label-mono tracking-widest uppercase text-on-surface-variant mb-xs block">${escapeHtml(p.categoria_nombre)}</span>` : ''}
            <h4 class="text-primary-fixed font-headline-md text-lg mb-xs neon-text-primary">${escapeHtml(p.nombre)}</h4>
            <div class="text-data-tabular text-on-surface-variant mb-md flex gap-md">
                <span>ID: ${p.id_producto}</span>
                <span class="border-l border-outline-variant pl-sm">Cód: ${escapeHtml(p.codigo)}</span>
            </div>
            
            <!-- Resumen superior: SISTEMA / BARRA / DELTA (Semantic Brand Tokens) -->
            <div class="space-y-sm mb-lg text-data-tabular font-semibold">
                <div class="flex items-center card-row-system border px-sm py-sm rounded-md gap-sm">
                    <div class="w-10 flex items-center justify-center text-on-surface-variant">
                        <span class="material-symbols-outlined">computer</span>
                    </div>
                    <div class="flex-1 flex items-center justify-between gap-sm border-l border-outline-variant pl-md min-w-0">
                        <span class="text-label-mono uppercase tracking-widest text-on-surface-variant shrink-0">Sistema (Ideal)</span>
                        <div class="flex items-center gap-sm sm:gap-md text-on-surface min-w-0">
                            <span class="w-16 text-right">${parseFloat(p.stock_ideal_unidades).toFixed(0)} bot</span>
                            <span class="text-outline-variant">|</span>
                            <span class="w-20 text-right">${parseFloat(p.stock_ideal_onzas).toFixed(2)} oz</span>
                        </div>
                    </div>
                </div>

                <div class="flex items-center card-row-bar border px-sm py-sm rounded-md gap-sm">
                    <div class="w-10 flex items-center justify-center" style="color: var(--semantic-action)">
                        <span class="material-symbols-outlined">local_bar</span>
                    </div>
                    <div class="flex-1 flex items-center justify-between gap-sm border-l border-outline-variant pl-md min-w-0">
                        <span class="text-label-mono uppercase tracking-widest" style="color: var(--semantic-action)">Barra (Real)</span>
                        <div class="flex items-center gap-sm sm:gap-md" style="color: var(--semantic-action)">
                            <span class="w-16 text-right"><span id="val-paq-${p.id_producto}">0</span> bot</span>
                            <span class="text-outline-variant">|</span>
                            <span class="w-20 text-right"><span id="val-det-${p.id_producto}">0.00</span> oz</span>
                        </div>
                    </div>
                </div>

                <div class="flex items-center card-row-delta border px-sm py-sm rounded-md gap-sm">
                    <div class="w-10 flex items-center justify-center" style="color: var(--semantic-info)">
                        <span class="material-symbols-outlined">stacked_line_chart</span>
                    </div>
                    <div class="flex-1 flex items-center justify-between gap-sm border-l" style="border-color: var(--semantic-info)" class="pl-md min-w-0">
                        <span class="text-label-mono uppercase tracking-widest" style="color: var(--semantic-info)">Delta (R-I)</span>
                        <div class="flex items-center gap-sm sm:gap-md min-w-0">
                            <div id="dif-paq-${p.id_producto}" class="w-16 text-right"></div>
                            <span style="color: var(--semantic-info); opacity: 0.5">|</span>
                            <div id="dif-det-${p.id_producto}" class="w-20 text-right"></div>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="grid ${p.pesable === 1 ? 'grid-cols-1 sm:grid-cols-2' : 'grid-cols-1'} gap-md items-start">
                <div>
                    <label class="block text-label-mono font-label-mono text-on-surface-variant mb-xs tracking-widest uppercase">Unidades</label>
                    <input type="number" min="0" class="w-full bg-surface border border-outline-variant rounded-md px-md py-sm text-on-surface input-cerradas focus:border-primary-fixed-dim focus:outline-none focus:shadow-cyan-glow-focus font-data-tabular" placeholder="0">
                </div>

                ${p.pesable === 1 ? `
                <div class="border-t border-outline-variant pt-md sm:border-t-0 sm:border-l sm:pt-0 sm:pl-md">
                    <label class="block text-label-mono font-label-mono text-on-surface-variant mb-xs tracking-widest uppercase">Peso</label>
                    <div class="pesos-container grid grid-cols-1 gap-sm" id="pesos-${p.id_producto}">
                        ${crearInputPeso(perfilesJson, false)}
                    </div>
                    <div class="mt-sm flex flex-wrap gap-sm">
                        <button type="button" data-id-producto="${p.id_producto}" class="btn-add-peso btn-action text-label-mono font-semibold flex items-center gap-xs transition-colors uppercase tracking-widest rounded-sharp border px-sm py-xs">
                            <span class="material-symbols-outlined text-sm">add_circle</span> + Botella
                        </button>
                        <button type="button" data-id-producto="${p.id_producto}" class="btn-add-modelo btn-highlight text-label-mono font-semibold flex items-center gap-xs transition-colors uppercase tracking-widest rounded-sharp border px-sm py-xs">
                            <span class="material-symbols-outlined text-sm">labs</span> + Modelo
                        </button>
                    </div>
                </div>` : ''}
            </div>
        `;

        div.innerHTML = html;
        listaProductos.appendChild(div);
    });

    inicializarCalculos();
}
// Fix #27: Ahora usa crearInputPeso() en lugar de duplicar el HTML del input.
window.agregarInputPeso = function(idProducto, perfilesJson) {
    const card = document.querySelector(`.product-card[data-id="${idProducto}"]`);
    const perfiles = perfilesJson || (card ? card.dataset.perfiles : '[]');
    const container = document.getElementById(`pesos-${idProducto}`);
    if (!container) return;
    const inputWrapper = document.createElement('div');
    inputWrapper.innerHTML = crearInputPeso(perfiles, true);
    container.appendChild(inputWrapper.firstElementChild);
}

// ==========================================
// ENVÍO AL SERVIDOR Y VALIDACIONES
// ==========================================
btnGuardar.addEventListener('click', async () => {
    // 1. Recolectar datos del DOM
    const payload = {
        id_operacion: currentOperacionId,
        id_barra: ID_BARRA_ACTUAL,
        observaciones: document.getElementById('observaciones-paloteo').value.trim() || null,
        items: []
    };

    const cards = document.querySelectorAll('.product-card');
    let validacionExitosa = true;
    let advertenciaFatFinger = false;
    let mensajeFatFinger = "";

    cards.forEach(card => {
        const idProducto = parseInt(card.dataset.id);
        const pesable = parseInt(card.dataset.pesable);
        const nombreProducto = card.dataset.nombre;
        
        const inputCerradas = card.querySelector('.input-cerradas');
        const cerradas = parseInt(inputCerradas.value) || 0;

        let pesosAbiertas = [];
        if (pesable === 1) {
            const wrappersPeso = card.querySelectorAll('.item-peso-wrapper');
            const perfiles = JSON.parse(card.dataset.perfiles || '[]');

            wrappersPeso.forEach(wrapper => {
                const inp = wrapper.querySelector('.input-peso');
                if (!inp) return;

                const val = parseFloat(inp.value);
                if (isNaN(val)) return;

                const select = wrapper.querySelector('.select-perfil');
                const { perfil, index } = resolverPerfilSeleccionado(perfiles, select);

                pesosAbiertas.push({
                    peso: val,
                    perfil_id: (perfil && perfil.id != null) ? perfil.id : null,
                    perfil_index: index >= 0 ? index : 0
                });
            });

            // VALIDACIÓN FAT FINGER: ¿Demasiadas botellas abiertas?
            if (pesosAbiertas.length > 3) {
                advertenciaFatFinger = true;
                mensajeFatFinger += `- Registraste ${pesosAbiertas.length} botellas abiertas de ${nombreProducto}.\n`;
            }
        }

        // VALIDACIÓN MATEMÁTICA: Números negativos (por si saltan el HTML)
        if (cerradas < 0 || pesosAbiertas.some(p => p.peso < 0)) {
            validacionExitosa = false;
        }

        payload.items.push({
            id_producto: idProducto,
            botellas_cerradas: cerradas,
            pesos_abiertas: pesosAbiertas
        });
    });

    if (!validacionExitosa) {
        return alert("Error: No puedes ingresar números negativos en el inventario.");
    }

    if (advertenciaFatFinger) {
        const confirmar = confirm(`⚠️ ADVERTENCIA (Revisa tus datos):\n${mensajeFatFinger}\n¿Estás completamente seguro de que estos datos son correctos?`);
        if (!confirmar) return; // Si el usuario cancela, detenemos el envío
    }

    // 2. Enviar a FastAPI
    try {
        btnGuardar.disabled = true;
        btnGuardar.innerHTML = `<span class="material-symbols-outlined animate-spin">refresh</span> Procesando...`;

        const response = await fetch(`${API_BASE}/inventario/paloteo`, {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${currentToken}` 
            },
            body: JSON.stringify(payload)
        });

        const result = await response.json();

        if (response.ok) {
            alert(`✅ ¡Inventario Guardado!\n${result.mensaje}`);
            // Limpiar y resetear
            document.getElementById('observaciones-paloteo').value = '';
            iniciarDashboard(); // Recargar para mostrar que ya no hay pendientes
        } else {
            alert(`❌ Error del servidor: ${result.detail || "Error desconocido"}`);
        }
    } catch (error) {
        alert("❌ Error de red al intentar guardar.");
    } finally {
        btnGuardar.disabled = false;
        btnGuardar.innerHTML = `<span class="material-symbols-outlined">save</span> Confirmar Inventario`;
    }
});

// ==========================================
// CÁLCULO EN TIEMPO REAL (ONZAS, UNIDADES Y DIFERENCIAS)
// ==========================================

// Función auxiliar para pintar las diferencias (Verde/Roja/Amarillo con Electric Industrial)
function formatearDiferencia(diferencia, isOz = false) {
    const sufijo = isOz ? "oz" : "bot";

    // Tolerancia para decimales (evitar ruido por redondeos)
    if (Math.abs(diferencia) < 0.01) {
        return '<span class="text-data-tabular font-semibold" style="color: var(--semantic-action)"><span class="material-symbols-outlined text-sm align-middle">check_circle</span></span>';
    }

    if (diferencia < 0) {
        const val = isOz ? diferencia.toFixed(2) : Math.round(diferencia);
        return `<span class="text-data-tabular font-semibold" style="color: var(--semantic-danger)">${val} ${sufijo}</span>`;
    }

    const val = isOz ? diferencia.toFixed(2) : Math.round(diferencia);
    return `<span class="text-data-tabular font-semibold" style="color: var(--semantic-warning)">+${val} ${sufijo}</span>`;
}

// Recalcula una tarjeta y actualiza PAQ/BARRA, DET/BARRA y sus diferencias contra el sistema
function recalcularTarjeta(card) {
    if (!card) return;

    const idProducto = card.dataset.id;
    const pesable = parseInt(card.dataset.pesable);

    // Variables del sistema
    const paqSist = parseFloat(card.dataset.paqsist) || 0;
    const detSist = parseFloat(card.dataset.detsist) || 0;

    // 1. PAQ/BARRA
    const inputCerradas = card.querySelector('.input-cerradas');
    const paqBarra = parseInt(inputCerradas.value) || 0;
    const spanPaq = document.getElementById(`val-paq-${idProducto}`);
    const difPaqSpan = document.getElementById(`dif-paq-${idProducto}`);

    if (spanPaq) spanPaq.textContent = paqBarra;
    if (difPaqSpan) difPaqSpan.innerHTML = formatearDiferencia(paqBarra - paqSist, false);

    // 2. DET/BARRA
    if (pesable === 1) {
        const perfiles = JSON.parse(card.dataset.perfiles || '[]');
        const tolerancia = parseFloat(card.dataset.tolerancia) || 0;
        const inputsPeso = card.querySelectorAll('.input-peso');
        const spanDet = document.getElementById(`val-det-${idProducto}`);
        const difDetSpan = document.getElementById(`dif-det-${idProducto}`);

        let detBarra = 0;
        const margenError = 10.0;

        inputsPeso.forEach(inp => {
            const wrapper = inp.closest('.item-peso-wrapper');
            const select = wrapper ? wrapper.querySelector('.select-perfil') : null;
            const { perfil } = resolverPerfilSeleccionado(perfiles, select);

            if (!perfil) return;

            const tara = parseFloat(perfil.tara);
            const groz = parseFloat(perfil.gramos_por_oz);
            const pesoMedido = parseFloat(inp.value);

            if (isNaN(tara) || isNaN(groz) || groz <= 0 || isNaN(pesoMedido)) return;

            if (pesoMedido >= (tara - margenError)) {
                const pesoLiquido = Math.max(0, pesoMedido - tara);
                detBarra += (pesoLiquido / groz);
            }
        });

        if (spanDet) spanDet.textContent = detBarra.toFixed(2);
        if (difDetSpan) difDetSpan.innerHTML = formatearDiferencia(detBarra - detSist, true, tolerancia);
    }
}

listaProductos.addEventListener('input', (e) => {
    if (e.target.classList.contains('input-cerradas') || e.target.classList.contains('input-peso')) {
        recalcularTarjeta(e.target.closest('.product-card'));
    }
});

listaProductos.addEventListener('change', (e) => {
    if (e.target.classList.contains('select-perfil')) {
        recalcularTarjeta(e.target.closest('.product-card'));
    }
});

listaProductos.addEventListener('click', (e) => {
    const btnAdd = e.target.closest('.btn-add-peso');
    if (btnAdd) {
        const idProducto = parseInt(btnAdd.dataset.idProducto, 10);
        if (!isNaN(idProducto)) {
            agregarInputPeso(idProducto);
        }
        return;
    }

    const btnModelo = e.target.closest('.btn-add-modelo');
    if (btnModelo) {
        const idProducto = parseInt(btnModelo.dataset.idProducto, 10);
        if (!isNaN(idProducto)) {
            crearModeloBotella(idProducto);
        }
        return;
    }
});

listaProductos.addEventListener('click', (e) => {
    if (e.target.closest('button') && e.target.closest('button').querySelector('.material-symbols-outlined')?.textContent === 'close') {
        const card = e.target.closest('.product-card');
        setTimeout(() => recalcularTarjeta(card), 50);
    }
});

function inicializarCalculos() {
    document.querySelectorAll('.product-card').forEach(card => {
        recalcularTarjeta(card);
    });
}