// ==========================================
// CONFIGURACIÓN Y ESTADO GLOBAL
// ==========================================
// Fix #22: URL dinámica para que funcione tanto en localhost como en producción
const API_BASE = `${window.location.origin}/api`;
let currentToken = localStorage.getItem('token') || null;
let currentOperacionId = null;
let currentIdInventarioPOS = null; // Guardamos el ID del inventario ya registrado para correcciones
const ID_BARRA_ACTUAL = 1; // Podemos hacerlo dinámico después
let productosInventario = [];
let modoEnvioOrigen = 'inventario';

const capturaEstado = {
    inicializado: false,
    indice: 0,
    idsOrdenados: [],
    completos: new Set(),
};

// Elementos del DOM
const loginScreen = document.getElementById('login-screen');
const appScreen = document.getElementById('app-screen');
const loginForm = document.getElementById('login-form');
const btnLogout = document.getElementById('btn-logout');
const listaProductos = document.getElementById('lista-productos');
const submitSection = document.getElementById('submit-section');
const btnGuardar = document.getElementById('btn-guardar');
const observacionesDialog = document.getElementById('observaciones-dialog');
const observacionesDialogTitulo = document.getElementById('observaciones-dialog-titulo');
const observacionesDialogAyuda = document.getElementById('observaciones-dialog-ayuda');
const observacionesOverlay = document.getElementById('observaciones-overlay');
const inputObservaciones = document.getElementById('observaciones-paloteo');
const btnEnviarInventario = document.getElementById('btn-enviar-inventario');
const btnCancelarObservaciones = document.getElementById('btn-cancelar-observaciones');
const capturaCardContainer = document.getElementById('captura-card-container');
const capturaTotalCapturadas = document.getElementById('captura-total-capturadas');
const capturaPorcentaje = document.getElementById('captura-porcentaje');
const capturaBtnAnterior = document.getElementById('captura-btn-anterior');
const capturaBtnSiguiente = document.getElementById('captura-btn-siguiente');
const capturaBtnFinalizar = document.getElementById('captura-btn-finalizar');

function renderCriticalIcon(iconName, className = 'ui-icon') {
    const iconPaths = {
        close: [
            '<path d="M18 6L6 18"></path>',
            '<path d="M6 6l12 12"></path>'
        ],
        refresh: [
            '<path d="M21 12a9 9 0 0 1-15.5 6.36"></path>',
            '<path d="M3 12a9 9 0 0 1 15.5-6.36"></path>',
            '<path d="M3 4v5h5"></path>',
            '<path d="M21 20v-5h-5"></path>'
        ],
        check_circle: [
            '<circle cx="12" cy="12" r="9"></circle>',
            '<path d="M8.5 12.5l2.5 2.5 4.5-5"></path>'
        ],
        hourglass_empty: [
            '<path d="M7 3h10"></path>',
            '<path d="M7 21h10"></path>',
            '<path d="M8 3c0 4 4 4.5 4 9s-4 5-4 9"></path>',
            '<path d="M16 3c0 4-4 4.5-4 9s4 5 4 9"></path>'
        ],
        block: [
            '<circle cx="12" cy="12" r="9"></circle>',
            '<path d="M8.5 15.5l7-7"></path>'
        ],
        visibility: [
            '<path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6z"></path>',
            '<circle cx="12" cy="12" r="2.5"></circle>'
        ],
        visibility_off: [
            '<path d="M3 3l18 18"></path>',
            '<path d="M10.6 6.2A10.53 10.53 0 0 1 12 6c6 0 9.5 6 9.5 6a17.7 17.7 0 0 1-4.02 4.4"></path>',
            '<path d="M6.3 6.7A17.36 17.36 0 0 0 2.5 12s3.5 6 9.5 6a9.8 9.8 0 0 0 4-.83"></path>',
            '<path d="M10.9 10.9a2.99 2.99 0 0 0 4.2 4.2"></path>'
        ]
    };

    const paths = iconPaths[iconName];
    if (!paths) {
        return `<span class="material-symbols-outlined ${className}">${escapeHtml(iconName)}</span>`;
    }

    return `<svg class="${className}" viewBox="0 0 24 24" aria-hidden="true">${paths.join('')}</svg>`;
}

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
        ? `<button type="button" onclick="this.parentElement.parentElement.remove()" class="btn-remove-peso absolute right-sm top-1/2 -translate-y-1/2 text-on-surface-variant hover:text-error transition-colors" aria-label="Eliminar campo de peso">
                    ${renderCriticalIcon('close', 'ui-icon ui-icon-sm')}
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

// ==========================================
// MODAL: CREAR MODELO DE BOTELLA
// ==========================================

const modeloBotellaDialog  = document.getElementById('modelo-botella-dialog');
const modeloBotellaOverlay = document.getElementById('modelo-botella-overlay');
const modeloBotellaSubtit  = document.getElementById('modelo-botella-subtitulo');
const mbNombre     = document.getElementById('mb-nombre');
const mbPesoBruto  = document.getElementById('mb-peso-bruto');
const mbTara       = document.getElementById('mb-tara');
const mbGramosOz   = document.getElementById('mb-gramos-oz');
const mbTolerancia = document.getElementById('mb-tolerancia');
const mbError      = document.getElementById('mb-error');
const btnCancelarModelo  = document.getElementById('btn-cancelar-modelo');
const btnConfirmarModelo = document.getElementById('btn-confirmar-modelo');

// ==========================================
// DIÁLOGOS ESTILIZADOS: RESULTADO Y CONFIRMACIÓN
// ==========================================
const resultadoDialog        = document.getElementById('resultado-dialog');
const resultadoOverlay       = document.getElementById('resultado-overlay');
const resultadoIcono         = document.getElementById('resultado-icono');
const resultadoTituloTexto   = document.getElementById('resultado-titulo-texto');
const resultadoMensaje       = document.getElementById('resultado-mensaje');
const resultadoBtnsOk        = document.getElementById('resultado-btns-ok');
const resultadoBtnsConfirm   = document.getElementById('resultado-btns-confirm');
const btnResultadoOk         = document.getElementById('btn-resultado-ok');
const btnResultadoCancelar   = document.getElementById('btn-resultado-cancelar');
const btnResultadoConfirmar  = document.getElementById('btn-resultado-confirmar');

/**
 * Muestra un modal de resultado (éxito o error) y resuelve cuando el usuario lo cierra.
 * @param {Object} opts - { tipo: 'success'|'error', titulo: string, mensaje: string }
 * @returns {Promise<void>}
 */
function mostrarDialogoResultado({ tipo = 'success', titulo, mensaje }) {
    return new Promise((resolve) => {
        // Configurar icono y color según tipo
        if (tipo === 'success') {
            resultadoIcono.textContent = 'check_circle';
            resultadoIcono.style.color = 'var(--color-primary-fixed-dim)';
            resultadoTituloTexto.style.color = '';
        } else {
            resultadoIcono.textContent = 'error';
            resultadoIcono.style.color = 'var(--semantic-danger, #f87171)';
            resultadoTituloTexto.style.color = 'var(--semantic-danger, #f87171)';
        }

        resultadoTituloTexto.textContent = titulo;
        resultadoMensaje.textContent = mensaje || '';

        // Modo resultado: un solo botón "Aceptar"
        resultadoBtnsOk.classList.remove('hidden');
        resultadoBtnsConfirm.classList.add('hidden');

        resultadoDialog.classList.remove('hidden');

        function cerrar() {
            resultadoDialog.classList.add('hidden');
            btnResultadoOk.removeEventListener('click', cerrar);
            resultadoOverlay.removeEventListener('click', cerrar);
            resolve();
        }

        btnResultadoOk.addEventListener('click', cerrar);
        resultadoOverlay.addEventListener('click', cerrar);
    });
}

/**
 * Muestra un modal de confirmación (sí/no) y resuelve con true/false.
 * @param {Object} opts - { titulo: string, mensaje: string }
 * @returns {Promise<boolean>}
 */
function mostrarDialogoConfirmacion({ titulo, mensaje }) {
    return new Promise((resolve) => {
        resultadoIcono.textContent = 'warning';
        resultadoIcono.style.color = 'var(--semantic-warning, #facc15)';
        resultadoTituloTexto.style.color = 'var(--semantic-warning, #facc15)';
        resultadoTituloTexto.textContent = titulo;
        resultadoMensaje.textContent = mensaje || '';

        // Modo confirmación: dos botones
        resultadoBtnsOk.classList.add('hidden');
        resultadoBtnsConfirm.classList.remove('hidden');

        resultadoDialog.classList.remove('hidden');

        function onConfirmar() { cleanup(); resolve(true); }
        function onCancelar()  { cleanup(); resolve(false); }
        function onOverlay()   { cleanup(); resolve(false); }

        function cleanup() {
            resultadoDialog.classList.add('hidden');
            btnResultadoConfirmar.removeEventListener('click', onConfirmar);
            btnResultadoCancelar.removeEventListener('click', onCancelar);
            resultadoOverlay.removeEventListener('click', onOverlay);
        }

        btnResultadoConfirmar.addEventListener('click', onConfirmar);
        btnResultadoCancelar.addEventListener('click', onCancelar);
        resultadoOverlay.addEventListener('click', onOverlay);
    });
}

/** Muestra el modal de nuevo modelo y resuelve con los datos cuando el usuario confirma, o null si cancela. */
function abrirModalModelo(nombreProducto, perfilBase) {
    return new Promise((resolve) => {
        // Subtítulo con nombre del producto
        modeloBotellaSubtit.textContent = nombreProducto;

        // Pre-llenar con valores del perfil base si existe
        mbNombre.value     = '';
        mbPesoBruto.value  = perfilBase ? perfilBase.peso_bruto  : '';
        mbTara.value       = perfilBase ? perfilBase.tara        : '';
        mbGramosOz.value   = perfilBase ? perfilBase.gramos_por_oz : '29.5735';
        mbTolerancia.value = perfilBase ? perfilBase.tolerancia_oz : '0';
        mbError.classList.add('hidden');
        mbError.textContent = '';

        modeloBotellaDialog.classList.remove('hidden');
        mbNombre.focus();

        function mostrarError(msg) {
            mbError.textContent = msg;
            mbError.classList.remove('hidden');
        }

        function cerrar(resultado) {
            modeloBotellaDialog.classList.add('hidden');
            btnConfirmarModelo.removeEventListener('click', onConfirmar);
            btnCancelarModelo.removeEventListener('click', onCancelar);
            modeloBotellaOverlay.removeEventListener('click', onCancelar);
            resolve(resultado);
        }

        function onConfirmar() {
            const nombre    = mbNombre.value.trim().toUpperCase();
            const pesoBruto = parseFloat(mbPesoBruto.value);
            const tara      = parseFloat(mbTara.value);
            const gramosOz  = parseFloat(mbGramosOz.value);
            const tolerancia = parseFloat(mbTolerancia.value);

            if (!nombre) return mostrarError('El nombre del modelo es obligatorio.');
            if ([pesoBruto, tara, gramosOz, tolerancia].some(Number.isNaN)) {
                return mostrarError('Todos los valores numéricos deben ser válidos.');
            }

            cerrar({ nombre, pesoBruto, tara, gramosOz, tolerancia });
        }

        function onCancelar() { cerrar(null); }

        btnConfirmarModelo.addEventListener('click', onConfirmar);
        btnCancelarModelo.addEventListener('click', onCancelar);
        modeloBotellaOverlay.addEventListener('click', onCancelar);
    });
}

async function crearModeloBotella(idProducto) {
    const card = document.querySelector(`#lista-productos .product-card[data-id="${idProducto}"]`);
    if (!card) return;

    const nombreProducto = card.dataset.nombre || `ID ${idProducto}`;
    const perfiles = JSON.parse(card.dataset.perfiles || '[]');
    const perfilBase = perfiles[0] || null;

    const datos = await abrirModalModelo(nombreProducto, perfilBase);
    if (!datos) return; // usuario canceló

    try {
        const response = await fetch(`${API_BASE}/pesaje/perfiles`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${currentToken}`
            },
            body: JSON.stringify({
                id_producto: idProducto,
                nombre_perfil: datos.nombre,
                peso_bruto: datos.pesoBruto,
                tara: datos.tara,
                gramos_por_oz: datos.gramosOz,
                tolerancia_oz: datos.tolerancia
            })
        });

        if (response.status === 401) return btnLogout.click();

        const data = await response.json();
        if (!response.ok) {
            // Re-abrimos el modal con el error visible en lugar de alert()
            mbError.textContent = `No se pudo crear el modelo: ${data.detail || 'Error desconocido'}`;
            mbError.classList.remove('hidden');
            modeloBotellaDialog.classList.remove('hidden');
            return;
        }

        const perfilesActuales = JSON.parse(card.dataset.perfiles || '[]');
        perfilesActuales.push(data);
        card.dataset.perfiles = JSON.stringify(perfilesActuales);
        refrescarSelectoresPerfil(card);
        recalcularTarjeta(card);
        // El modal ya se cerró al confirmar — no usamos alert()
    } catch (error) {
        mbError.textContent = 'Error de red al crear el modelo de botella.';
        mbError.classList.remove('hidden');
        modeloBotellaDialog.classList.remove('hidden');
    }
}

document.addEventListener('DOMContentLoaded', () => {
    if (currentToken) {
        mostrarPantallaApp();
    } else {
        mostrarPantallaLogin();
    }

    // Configurar Password Toggle (El ojito)
    const togglePassword = document.getElementById('toggle-password');
    const passwordInput = document.getElementById('password');
    togglePassword.addEventListener('click', () => {
        const type = passwordInput.getAttribute('type') === 'password' ? 'text' : 'password';
        passwordInput.setAttribute('type', type);
        togglePassword.querySelector('[data-password-icon]').innerHTML = renderCriticalIcon(
            type === 'password' ? 'visibility' : 'visibility_off',
            'ui-icon ui-icon-sm'
        );
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
    // Asegurar que el panel de inventario sea el visible al entrar a la app
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.add('hidden'));
    document.getElementById('panel-inventario').classList.remove('hidden');
    iniciarDashboard();
}

// ==========================================
// LÓGICA DE NEGOCIO (DASHBOARD)
// ==========================================
async function iniciarDashboard() {
    listaProductos.innerHTML = ''; // Limpiar lista
    productosInventario = [];
    resetModoCaptura();
    modoEnvioOrigen = 'inventario';
    _deshabilitarBtnEnvio();
    observacionesDialog.classList.add('hidden');
    inputObservaciones.value = '';
    
    const estadoIcon = document.getElementById('estado-icon');
    const estadoTexto = document.getElementById('estado-texto');
    
    // Fix #28: Resetear clases del icóno antes de cada verificación para evitar acumulación de estilos.
    estadoIcon.className = 'inline-flex text-4xl text-on-surface-variant';
    estadoIcon.style.color = '';
    estadoIcon.style.filter = '';
    estadoIcon.innerHTML = renderCriticalIcon('hourglass_empty');
    estadoIcon.classList.add('animate-pulse');
    estadoIcon.classList.add('status-checking-icon');
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

            // Procesar error: extraer icon y status_class del detalle
            const detail = dataOp.detail && typeof dataOp.detail === 'object' ? dataOp.detail : {};
            const iconoError = detail.icon || 'block';
            const statusClass = detail.status_class || 'status-warning-icon';
            
            estadoIcon.innerHTML = renderCriticalIcon(iconoError);
            estadoIcon.classList.remove('animate-pulse', 'text-primary-fixed', 'text-error', 'text-on-surface-variant', 'success-check-icon', 'status-checking-icon', 'status-warning-icon', 'status-info-icon');
            estadoIcon.classList.add(statusClass);
            
            const estadoTituloErr = document.getElementById('estado-titulo');
            if (estadoTituloErr) {
                estadoTituloErr.textContent = detail.titulo || "Operativa bloqueada";
            }
            
            estadoTexto.textContent = detail.mensaje || "Debes iniciar el cierre de la operativa para realizar el paloteo";
            return; // Bloqueamos la ejecución aquí
        }

        // Luz Verde: Guardamos el ID de operación (estado 24)
        currentOperacionId = dataOp.id_operacion;
        currentIdInventarioPOS = null; // Resetear el ID de inventario previo para nueva operativa
        ocultarBannerCorreccion(); // Ocultar banner de corrección hasta confirmar si hay inventario
        const iconoExito = dataOp.icon || 'check_circle';
        estadoIcon.innerHTML = renderCriticalIcon(iconoExito);
        estadoIcon.classList.remove('animate-pulse', 'text-on-surface-variant', 'text-error', 'status-warning-icon', 'status-checking-icon', 'status-info-icon');
        estadoIcon.classList.add('success-check-icon');
        
        // Actualizar título y mensaje según respuesta del servidor
        const estadoTitulo = document.getElementById('estado-titulo');
        if (estadoTitulo && dataOp.titulo) {
            estadoTitulo.textContent = dataOp.titulo;
        }
        estadoTexto.textContent = dataOp.mensaje;

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
            productosInventario = productos;
            renderizarProductos(productos);
            renderizarPaloteo3(productos);
            _habilitarBtnEnvio();
            
            // NUEVO: Mostrar resumen de productos (total, pesables, no pesables)
            actualizarResumenProductos(productos);

            // NUEVO: Verificar si ya existe inventario registrado y pre-cargar valores
            await cargarInventarioExistente();
        } else {
            productosInventario = [];
            listaProductos.innerHTML = `<div class="text-center text-on-surface-variant py-lg font-body-base">No hay productos consumidos para auditar hoy.</div>`;
            mostrarEstadoVacioPaloteo3();
            ocultarResumenProductos();
        }
    } catch (error) {
        console.error("Error cargando productos", error);
        mostrarEstadoVacioPaloteo3();
        ocultarResumenProductos();
    }
}

// NUEVO: Calcular y mostrar resumen de productos
function actualizarResumenProductos(productos) {
    const total = productos.length;
    const pesables = productos.filter(p => p.pesable === 1).length;
    const noPesables = total - pesables;
    
    document.getElementById('resumen-total').textContent = total;
    document.getElementById('resumen-pesables').textContent = pesables;
    document.getElementById('resumen-no-pesables').textContent = noPesables;
    
    document.getElementById('estado-resumen').classList.remove('hidden');
}

// NUEVO: Ocultar resumen de productos
function ocultarResumenProductos() {
    document.getElementById('estado-resumen').classList.add('hidden');
}

function _habilitarBtnEnvio() {
    btnGuardar.disabled = false;
    btnGuardar.classList.remove('opacity-40', 'cursor-not-allowed', 'text-on-surface-variant');
    btnGuardar.classList.add('text-primary-fixed', 'hover:text-primary-fixed-dim', 'border-primary-fixed-dim', 'glow-cyan-intense');
}

function _deshabilitarBtnEnvio() {
    btnGuardar.disabled = true;
    btnGuardar.classList.remove('text-primary-fixed', 'hover:text-primary-fixed-dim', 'border-primary-fixed-dim', 'glow-cyan-intense');
    btnGuardar.classList.add('opacity-40', 'cursor-not-allowed', 'text-on-surface-variant');
}

// ==========================================
// CARGA DE INVENTARIO EXISTENTE (MODO CORRECCIÓN)
// ==========================================

/**
 * Consulta el backend para verificar si ya existe un inventario físico registrado
 * para la operativa actual. Si existe, setea currentIdInventarioPOS y pre-llena
 * los inputs de las tarjetas con los valores guardados.
 */
async function cargarInventarioExistente() {
    if (!currentOperacionId) return;

    try {
        const response = await fetch(`${API_BASE}/inventario/paloteo/${currentOperacionId}`, {
            headers: { 'Authorization': `Bearer ${currentToken}` }
        });

        if (response.status === 401) return btnLogout.click();
        if (response.status === 404) return; // Sin inventario previo, flujo normal de creación
        if (!response.ok) return; // Otro error, ignorar silenciosamente

        const data = await response.json();
        currentIdInventarioPOS = data.id_inventario_pos;

        if (data.detalles && data.detalles.length > 0) {
            preLlenarInventario(data.detalles);
        }

        // Mostrar banner de modo corrección si la operativa aún admite edición
        if (data.puede_editar) {
            mostrarBannerCorreccion(data.observaciones);
        }

    } catch (error) {
        console.error("Error verificando inventario existente:", error);
    }
}

/**
 * Pre-llena los inputs de cada tarjeta con los valores ya almacenados en la BD.
 * Para productos pesables, recalcula el peso estimado en gramos usando la inversa
 * de la fórmula: peso_estimado = onzas_pos * gramos_por_oz + tara
 */
function preLlenarInventario(detalles) {
    detalles.forEach(detalle => {
        const card = document.querySelector(`#lista-productos .product-card[data-id="${detalle.id_producto}"]`);
        if (!card) return;

        // Pre-llenar botellas cerradas
        const inputCerradas = card.querySelector('.input-cerradas');
        if (inputCerradas) {
            inputCerradas.value = detalle.botellas_cerradas || 0;
        }

        // Pre-llenar peso para productos pesables
        if (parseInt(card.dataset.pesable) === 1 && detalle.onzas_pos > 0) {
            const perfiles = JSON.parse(card.dataset.perfiles || '[]');
            if (perfiles.length > 0) {
                const perfil = perfiles[0];
                const tara = parseFloat(perfil.tara) || 0;
                const gramsPorOz = parseFloat(perfil.gramos_por_oz) || 0;
                if (gramsPorOz > 0) {
                    // Inversa: onzas guardadas → gramos estimados para el input de báscula
                    const pesoEstimado = (detalle.onzas_pos * gramsPorOz) + tara;
                    const primerInput = card.querySelector('.input-peso');
                    if (primerInput) {
                        primerInput.value = pesoEstimado.toFixed(1);
                    }
                }
            }
        }

        // Recalcular deltas visibles con los valores cargados
        recalcularTarjeta(card);
    });
}

function mostrarBannerCorreccion(observaciones) {
    const banner = document.getElementById('banner-correccion');
    if (!banner) return;
    const textoSpan = document.getElementById('banner-correccion-texto');
    if (textoSpan) {
        textoSpan.textContent = observaciones
            ? `Datos previos cargados · Obs: ${observaciones}`
            : 'Datos previos cargados';
    }
    banner.classList.remove('hidden');
}

function ocultarBannerCorreccion() {
    const banner = document.getElementById('banner-correccion');
    if (banner) banner.classList.add('hidden');
}

// ==========================================
// RENDERIZADO Y DINAMISMO UI
// ==========================================
function crearTarjetaProductoElement(p, scope = 'inv') {
    const esCaptura = scope === 'captura';
    const sufijoScope = esCaptura ? `cap-${p.id_producto}` : `${p.id_producto}`;
    const pesosContainerId = esCaptura ? `pesos-cap-${p.id_producto}` : `pesos-${p.id_producto}`;
    const btnAddPesoClass = esCaptura ? 'btn-add-peso-captura' : 'btn-add-peso';
    const btnAddModeloClass = esCaptura ? 'btn-add-modelo-captura' : 'btn-add-modelo';

    const div = document.createElement('div');
    div.className = "bg-surface-container border border-outline-variant rounded-md p-md shadow-lg product-card transition-colors focus-within:border-primary-fixed-dim chassis-panel";
    div.dataset.scope = scope;
    div.dataset.id = p.id_producto;
    div.dataset.pesable = p.pesable || 0;
    div.dataset.nombre = p.nombre;
    const perfilesJson = JSON.stringify(p.perfiles || []);
    div.dataset.perfiles = perfilesJson;
    div.dataset.tolerancia = (p.perfiles && p.perfiles.length > 0) ? p.perfiles[0].tolerancia_oz : 0;
    div.dataset.paqsist = parseFloat(p.stock_ideal_unidades) || 0;
    div.dataset.detsist = parseFloat(p.stock_ideal_onzas) || 0;
    div.dataset.onzasMax = parseFloat(p.onzas_por_botella_llena) || 0;

    let html = `
        ${p.categoria_nombre ? `<span class="text-label-mono font-label-mono tracking-widest uppercase text-on-surface-variant mb-xs block">${escapeHtml(p.categoria_nombre)}</span>` : ''}
        <h4 class="text-primary-fixed font-headline-md text-lg mb-xs neon-text-primary">${escapeHtml(p.nombre)}</h4>
        <div class="text-data-tabular text-on-surface-variant mb-md flex gap-md">
            <span>ID: ${p.id_producto}</span>
            <span class="border-l border-outline-variant pl-sm">Cód: ${escapeHtml(p.codigo)}</span>
        </div>

        <div class="space-y-sm mb-lg text-data-tabular font-semibold">
            <div class="flex items-center card-row-system border px-sm py-sm rounded-md gap-sm">
                <div class="w-10 flex items-center justify-center text-on-surface-variant">
                    <span class="material-symbols-outlined">computer</span>
                </div>
                <div class="flex-1 flex items-center justify-between gap-sm border-l border-outline-variant pl-md min-w-0">
                    <span class="text-label-mono uppercase tracking-widest text-on-surface-variant leading-tight">
                        <span class="block sm:inline">Sistema</span>
                        <span class="block sm:inline">(Ideal)</span>
                    </span>
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
                    <span class="text-label-mono uppercase tracking-widest leading-tight" style="color: var(--semantic-action)">
                        <span class="block sm:inline">Barra</span>
                        <span class="block sm:inline">(Real)</span>
                    </span>
                    <div class="flex items-center gap-sm sm:gap-md" style="color: var(--semantic-action)">
                        <span class="w-16 text-right"><span id="val-paq-${sufijoScope}">0</span> bot</span>
                        <span class="text-outline-variant">|</span>
                        <span class="w-20 text-right"><span id="val-det-${sufijoScope}">0.00</span> oz</span>
                    </div>
                </div>
            </div>

            <div class="flex items-center card-row-delta border px-sm py-sm rounded-md gap-sm">
                <div class="w-10 flex items-center justify-center" style="color: var(--semantic-info)">
                    <span class="material-symbols-outlined">stacked_line_chart</span>
                </div>
                <div class="flex-1 flex items-center justify-between gap-sm border-l pl-md min-w-0" style="border-color: var(--semantic-info)">
                    <span class="text-label-mono uppercase tracking-widest leading-tight" style="color: var(--semantic-info)">
                        <span class="block sm:inline">Delta</span>
                        <span class="block sm:inline">(R-I)</span>
                    </span>
                    <div class="flex items-center gap-sm sm:gap-md min-w-0">
                        <div id="dif-paq-${sufijoScope}" class="w-16 text-right"></div>
                        <span style="color: var(--semantic-info); opacity: 0.5">|</span>
                        <div id="dif-det-${sufijoScope}" class="w-20 text-right"></div>
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
                <div class="pesos-container grid grid-cols-1 gap-sm" id="${pesosContainerId}">
                    ${crearInputPeso(perfilesJson, false)}
                </div>
                <div class="mt-sm flex flex-wrap gap-sm">
                    <button type="button" data-id-producto="${p.id_producto}" class="${btnAddPesoClass} btn-action w-full sm:w-auto text-label-mono font-semibold flex items-center justify-center sm:justify-start gap-xs transition-colors uppercase tracking-widest rounded-sharp border px-sm py-xs">
                        <span class="material-symbols-outlined text-sm">add_circle</span> + Botella
                    </button>
                    <button type="button" data-id-producto="${p.id_producto}" class="${btnAddModeloClass} btn-info w-full sm:w-auto text-label-mono font-semibold flex items-center justify-center sm:justify-start gap-xs transition-colors uppercase tracking-widest rounded-sharp border px-sm py-xs">
                        <span class="material-symbols-outlined text-sm">labs</span> + Modelo
                    </button>
                </div>
            </div>` : ''}
        </div>
    `;

    div.innerHTML = html;
    return div;
}

function renderizarProductos(productos) {
    listaProductos.innerHTML = '';

    productos.forEach(p => {
        const card = crearTarjetaProductoElement(p, 'inv');
        listaProductos.appendChild(card);
    });

    inicializarCalculos(listaProductos);
}

function mostrarEstadoVacioPaloteo3() {
    const stockList = document.getElementById('stock-list');
    const emptyState = document.getElementById('stock-empty-state');
    if (stockList) stockList.innerHTML = '';
    if (emptyState) emptyState.classList.remove('hidden');
}

function crearFilaPaloteo3(producto) {
    const row = document.createElement('div');
    row.className = 'stock-row grid gap-xs px-sm py-xs items-center hover:bg-surface-container-highest transition-colors';
    row.style.gridTemplateColumns = '2.5rem 4rem 1fr 4.5rem 5rem 4rem 4rem 4rem';
    row.dataset.search = `${producto.id_producto || ''} ${producto.codigo || ''} ${producto.nombre || ''}`.toLowerCase();

    const perfiles = Array.isArray(producto.perfiles) ? producto.perfiles : [];
    const perfilBase = perfiles.length > 0 ? perfiles[0] : null;
    const tara = perfilBase ? (parseFloat(perfilBase.tara) || 0) : 0;
    const gramosPorOz = perfilBase ? (parseFloat(perfilBase.gramos_por_oz) || 29.5735) : 29.5735;
    const idealUnidades = parseFloat(producto.stock_ideal_unidades) || 0;
    const idealOnzas = parseFloat(producto.stock_ideal_onzas) || 0;

    row.innerHTML = `
        <span class="text-data-tabular text-on-surface-variant text-right text-xs">${escapeHtml(String(producto.id_producto ?? ''))}</span>
        <span class="text-data-tabular text-on-surface text-right text-xs truncate" title="${escapeHtml(String(producto.codigo ?? ''))}">${escapeHtml(String(producto.codigo ?? '—'))}</span>
        <span class="text-xs text-on-surface truncate" title="${escapeHtml(producto.nombre || '')}">${escapeHtml(producto.nombre || '')}</span>
        <input type="number" min="0" step="1" value="0" class="stock-input-unidades w-full text-right text-xs bg-surface border border-outline-variant rounded px-xs py-xs text-data-tabular text-on-surface focus:border-primary-fixed-dim focus:outline-none focus:shadow-cyan-glow-focus transition-colors" data-ideal-unidades="${idealUnidades}">
        <input type="number" min="0" step="0.1" value="0" class="stock-input-peso w-full text-right text-xs bg-surface border border-outline-variant rounded px-xs py-xs text-data-tabular text-on-surface focus:border-primary-fixed-dim focus:outline-none focus:shadow-cyan-glow-focus transition-colors" data-tara="${tara}" data-gramos-oz="${gramosPorOz}" data-ideal-onzas="${idealOnzas}">
        <span class="stock-oz text-data-tabular text-on-surface text-right text-xs font-semibold">0.00</span>
        <span class="stock-dif-unid text-right text-xs font-semibold"></span>
        <span class="stock-dif-oz text-right text-xs font-semibold"></span>
    `;

    recalcularFilaPaloteo3(row);
    return row;
}

function recalcularFilaPaloteo3(row) {
    if (!row) return;

    const inputUnidades = row.querySelector('.stock-input-unidades');
    const inputPeso = row.querySelector('.stock-input-peso');
    const ozEl = row.querySelector('.stock-oz');
    const difUnidEl = row.querySelector('.stock-dif-unid');
    const difOzEl = row.querySelector('.stock-dif-oz');
    if (!inputUnidades || !inputPeso || !ozEl || !difUnidEl || !difOzEl) return;

    const unidadesReales = parseInt(inputUnidades.value, 10) || 0;
    const pesoIngresado = parseFloat(inputPeso.value) || 0;
    const tara = parseFloat(inputPeso.dataset.tara) || 0;
    const gramosPorOz = parseFloat(inputPeso.dataset.gramosOz) || 29.5735;
    const idealUnidades = parseFloat(inputUnidades.dataset.idealUnidades) || 0;
    const idealOnzas = parseFloat(inputPeso.dataset.idealOnzas) || 0;

    const margenError = 10.0;
    let onzasReales = 0;
    if (gramosPorOz > 0 && pesoIngresado >= (tara - margenError)) {
        const pesoLiquido = Math.max(0, pesoIngresado - tara);
        onzasReales = pesoLiquido / gramosPorOz;
    }

    const difUnidades = unidadesReales - idealUnidades;
    const difOnzas = onzasReales - idealOnzas;

    ozEl.textContent = onzasReales.toFixed(2);
    difUnidEl.innerHTML = formatearDiferencia(difUnidades, false);
    difOzEl.innerHTML = formatearDiferencia(difOnzas, true);
}

function renderizarPaloteo3(productos) {
    const stockList = document.getElementById('stock-list');
    const emptyState = document.getElementById('stock-empty-state');
    if (!stockList) return;

    if (!productos || productos.length === 0) {
        mostrarEstadoVacioPaloteo3();
        return;
    }

    stockList.innerHTML = '';
    if (emptyState) emptyState.classList.add('hidden');
    productos.forEach(producto => {
        stockList.appendChild(crearFilaPaloteo3(producto));
    });
}

// Fix #27: Ahora usa crearInputPeso() en lugar de duplicar el HTML del input.
window.agregarInputPeso = function(idProducto, perfilesJson) {
    const card = document.querySelector(`#lista-productos .product-card[data-id="${idProducto}"]`);
    const perfiles = perfilesJson || (card ? card.dataset.perfiles : '[]');
    const container = document.getElementById(`pesos-${idProducto}`);
    if (!container) return;
    const inputWrapper = document.createElement('div');
    inputWrapper.innerHTML = crearInputPeso(perfiles, true);
    container.appendChild(inputWrapper.firstElementChild);
}

function agregarInputPesoEnCard(card) {
    if (!card) return;
    const idProducto = parseInt(card.dataset.id, 10);
    const esCaptura = card.dataset.scope === 'captura';
    const containerId = esCaptura ? `pesos-cap-${idProducto}` : `pesos-${idProducto}`;
    const container = card.querySelector(`#${containerId}`) || document.getElementById(containerId);
    if (!container) return;

    const inputWrapper = document.createElement('div');
    inputWrapper.innerHTML = crearInputPeso(card.dataset.perfiles || '[]', true);
    container.appendChild(inputWrapper.firstElementChild);
}

// ==========================================
// ENVÍO AL SERVIDOR Y VALIDACIONES
// ==========================================
function abrirDialogoObservaciones(origen = 'inventario') {
    modoEnvioOrigen = origen;
    // Asegurar que el panel correcto sea visible detrás del modal
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.add('hidden'));
    if (origen === 'captura') {
        document.getElementById('panel-logs').classList.remove('hidden');
    } else {
        document.getElementById('panel-inventario').classList.remove('hidden');
    }

    const esCorreccion = currentIdInventarioPOS !== null;

    if (observacionesDialogTitulo) {
        observacionesDialogTitulo.innerHTML = esCorreccion
            ? '<span class="material-symbols-outlined text-sm">edit_note</span> Observaciones de la corrección (opcional)'
            : '<span class="material-symbols-outlined text-sm">edit_note</span> Observaciones del cierre (opcional)';
    }

    if (observacionesDialogAyuda) {
        observacionesDialogAyuda.textContent = 'Puedes dejar este campo en blanco y enviar de todas formas.';
    }

    observacionesDialog.classList.remove('hidden');
    inputObservaciones.focus();
}

function cerrarDialogoObservaciones() {
    observacionesDialog.classList.add('hidden');
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.add('hidden'));
    if (modoEnvioOrigen === 'captura') {
        document.getElementById('panel-logs').classList.remove('hidden');
    } else {
        document.getElementById('panel-inventario').classList.remove('hidden');
    }
}

// ==========================================
// VALIDACIONES DE INVENTARIO
// ==========================================

/**
 * Valida los campos de una tarjeta de producto.
 * Retorna: { camposVacios: [], erroresPeso: [], advertenciasOnzas: [] }
 */
function validarTarjeta(card) {
    const resultado = {
        camposVacios: [],
        erroresPeso: [],
        advertenciasOnzas: [],
    };

    const pesable = parseInt(card.dataset.pesable, 10) === 1;
    const perfiles = JSON.parse(card.dataset.perfiles || '[]');
    const onzasMax = parseFloat(card.dataset.onzasMax) || 0;

    const inputCerradas = card.querySelector('.input-cerradas');
    if (!inputCerradas || inputCerradas.value.trim() === '') {
        resultado.camposVacios.push('unidades');
    }

    if (pesable) {
        const wrappers = card.querySelectorAll('.item-peso-wrapper');
        wrappers.forEach((wrapper, idx) => {
            const inp = wrapper.querySelector('.input-peso');
            if (!inp) return;

            if (inp.value.trim() === '') {
                resultado.camposVacios.push(`peso_${idx + 1}`);
                return;
            }

            const pesoIngresado = parseFloat(inp.value);
            if (isNaN(pesoIngresado)) {
                resultado.camposVacios.push(`peso_${idx + 1}`);
                return;
            }

            const select = wrapper.querySelector('.select-perfil');
            const { perfil } = resolverPerfilSeleccionado(perfiles, select);
            if (!perfil) return;

            const pesoBruto = parseFloat(perfil.peso_bruto);
            const tara = parseFloat(perfil.tara);
            const gramsPorOz = parseFloat(perfil.gramos_por_oz);
            const nombrePerfil = perfil.nombre_perfil || `Botella ${idx + 1}`;

            // Error duro: peso supera el peso bruto de la botella
            if (!isNaN(pesoBruto) && pesoBruto > 0 && pesoIngresado > pesoBruto) {
                resultado.erroresPeso.push({ pesoIngresado, pesoBruto, nombrePerfil });
            }

            // Advertencia: onzas calculadas superan la capacidad de la botella
            if (onzasMax > 0 && !isNaN(tara) && !isNaN(gramsPorOz) && gramsPorOz > 0) {
                const margenError = 10.0;
                if (pesoIngresado >= (tara - margenError)) {
                    const pesoLiquido = Math.max(0, pesoIngresado - tara);
                    const onzasCalculadas = pesoLiquido / gramsPorOz;
                    if (onzasCalculadas > onzasMax) {
                        resultado.advertenciasOnzas.push({ onzasCalculadas, onzasMaximas: onzasMax, nombrePerfil });
                    }
                }
            }
        });
    }

    return resultado;
}

/**
 * Ejecuta validaciones sobre un conjunto de tarjetas.
 * Orden: errores de peso (bloqueo duro) → onzas excedidas (advertencia) → campos vacíos (advertencia con relleno a 0).
 * Retorna true si se puede continuar, false si el usuario cancela o hay error bloqueante.
 */
async function ejecutarValidacionesGlobales(cards) {
    const erroresPeso = [];
    const advertenciasOnzas = [];
    const camposVaciosPorCard = [];

    cards.forEach(card => {
        const nombre = card.dataset.nombre;
        const res = validarTarjeta(card);
        if (res.erroresPeso.length > 0) erroresPeso.push({ nombre, detalles: res.erroresPeso });
        if (res.advertenciasOnzas.length > 0) advertenciasOnzas.push({ nombre, detalles: res.advertenciasOnzas });
        if (res.camposVacios.length > 0) camposVaciosPorCard.push({ card, nombre, campos: res.camposVacios });
    });

    // 1. Bloqueo duro: peso > peso_bruto
    if (erroresPeso.length > 0) {
        const lista = erroresPeso.map(e => {
            const detalles = e.detalles.map(d =>
                `  • ${d.nombrePerfil}: ingresado ${d.pesoIngresado.toFixed(1)} g, máximo ${d.pesoBruto.toFixed(1)} g`
            ).join('\n');
            return `${e.nombre}:\n${detalles}`;
        }).join('\n\n');
        await mostrarDialogoResultado({
            tipo: 'error',
            titulo: 'Peso inválido',
            mensaje: `El peso ingresado supera el peso bruto de la botella. Corrige los valores antes de continuar:\n\n${lista}`,
        });
        return false;
    }

    // 2. Advertencia confirmable: onzas > capacidad por botella
    if (advertenciasOnzas.length > 0) {
        const lista = advertenciasOnzas.map(e => {
            const detalles = e.detalles.map(d =>
                `  • ${d.nombrePerfil}: ${d.onzasCalculadas.toFixed(2)} oz (máx. ${d.onzasMaximas.toFixed(2)} oz)`
            ).join('\n');
            return `${e.nombre}:\n${detalles}`;
        }).join('\n\n');
        const confirmar = await mostrarDialogoConfirmacion({
            titulo: 'Capacidad de botella excedida',
            mensaje: `El peso ingresado equivale a más onzas de las que cabe en la botella. ¿Confirmas que el valor es correcto?\n\n${lista}`,
        });
        if (!confirmar) return false;
    }

    // 3. Advertencia confirmable: campos vacíos (se rellenan con 0 al confirmar)
    if (camposVaciosPorCard.length > 0) {
        const lista = camposVaciosPorCard.map(p => {
            const campos = p.campos.map(c =>
                c === 'unidades' ? 'unidades cerradas' : `peso botella ${c.replace('peso_', '')}`
            ).join(', ');
            return `• ${p.nombre}: ${campos}`;
        }).join('\n');
        const confirmar = await mostrarDialogoConfirmacion({
            titulo: 'Campos sin completar',
            mensaje: `Los siguientes campos están vacíos y se registrarán como 0. ¿Confirmas que representan cero?\n\n${lista}\n\nPresiona Volver para completarlos.`,
        });
        if (!confirmar) return false;

        // Rellenar vacíos con 0
        camposVaciosPorCard.forEach(({ card, campos }) => {
            campos.forEach(campo => {
                if (campo === 'unidades') {
                    const inp = card.querySelector('.input-cerradas');
                    if (inp) inp.value = '0';
                } else {
                    const idx = parseInt(campo.replace('peso_', ''), 10) - 1;
                    const wrappers = card.querySelectorAll('.item-peso-wrapper');
                    if (wrappers[idx]) {
                        const inp = wrappers[idx].querySelector('.input-peso');
                        if (inp) inp.value = '0';
                    }
                }
            });
            recalcularTarjeta(card);
        });
    }

    return true;
}

async function construirPayloadInventario(observaciones = null) {
    const payload = {
        id_operacion: currentOperacionId,
        id_barra: ID_BARRA_ACTUAL,
        observaciones,
        items: []
    };

    const cards = document.querySelectorAll('#lista-productos .product-card');
    let valido = true;

    cards.forEach(card => {
        const idProducto = parseInt(card.dataset.id);
        const pesable = parseInt(card.dataset.pesable);

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
        }

        // Seguridad: rechazar números negativos
        if (cerradas < 0 || pesosAbiertas.some(p => p.peso < 0)) {
            valido = false;
        }

        payload.items.push({
            id_producto: idProducto,
            botellas_cerradas: cerradas,
            pesos_abiertas: pesosAbiertas
        });
    });

    if (!valido) {
        await mostrarDialogoResultado({
            tipo: 'error',
            titulo: 'Datos inválidos',
            mensaje: 'No puedes ingresar números negativos en el inventario.'
        });
        return null;
    }

    return payload;
}

async function enviarInventario(payload) {
    const textoOriginalConfirmar = btnGuardar.innerHTML;
    const textoOriginalEnviar = btnEnviarInventario.innerHTML;

    try {
        btnGuardar.disabled = true;
        btnEnviarInventario.disabled = true;
        btnGuardar.innerHTML = `${renderCriticalIcon('refresh', 'ui-icon animate-spin')} Procesando...`;
        btnEnviarInventario.innerHTML = `${renderCriticalIcon('refresh', 'ui-icon animate-spin')} Enviando...`;

        // Decidir si hacer POST (crear) o PUT (corregir)
        const esCorreccion = currentIdInventarioPOS !== null;
        const metodo = esCorreccion ? 'PUT' : 'POST';
        const url = esCorreccion 
            ? `${API_BASE}/inventario/paloteo/${currentIdInventarioPOS}`
            : `${API_BASE}/inventario/paloteo`;

        const response = await fetch(url, {
            method: metodo,
            headers: { 
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${currentToken}` 
            },
            body: JSON.stringify(payload)
        });

        const result = await response.json();

        if (response.ok) {
            // Guardar el ID del inventario registrado para futuras correcciones
            if (!esCorreccion) {
                currentIdInventarioPOS = result.id_inventario_pos;
            }
            
            const accion = esCorreccion ? '¡Inventario Corregido!' : '¡Inventario Guardado!';
            inputObservaciones.value = '';
            cerrarDialogoObservaciones();
            // NO recargar dashboard para mantener los datos en pantalla permitiendo más correcciones
            await mostrarDialogoResultado({
                tipo: 'success',
                titulo: accion,
                mensaje: result.mensaje
            });
        } else {
            await mostrarDialogoResultado({
                tipo: 'error',
                titulo: 'Error del servidor',
                mensaje: result.detail || 'Error desconocido'
            });
        }
    } catch (error) {
        await mostrarDialogoResultado({
            tipo: 'error',
            titulo: 'Error de red',
            mensaje: 'No se pudo conectar con el servidor. Revisa tu conexión e intenta de nuevo.'
        });
    } finally {
        btnGuardar.disabled = false;
        btnEnviarInventario.disabled = false;
        btnGuardar.innerHTML = textoOriginalConfirmar;
        btnEnviarInventario.innerHTML = textoOriginalEnviar;
    }
}

btnGuardar.addEventListener('click', async () => {
    const todasLasCards = Array.from(document.querySelectorAll('#lista-productos .product-card'));
    const valido = await ejecutarValidacionesGlobales(todasLasCards);
    if (!valido) return;
    abrirDialogoObservaciones('inventario');
});

btnCancelarObservaciones.addEventListener('click', () => {
    cerrarDialogoObservaciones();
});

observacionesOverlay.addEventListener('click', () => {
    cerrarDialogoObservaciones();
});

// ==========================================
// NAVEGACIÓN POR TABS (BOTTOM NAV)
// ==========================================

/** Mapeo tab → panel. El panel de inventario es el panel "home" sin tab propio. */
const TAB_PANEL_MAP = {
    stock: 'panel-stock',
    scan:  'panel-scan',
    logs:  'panel-logs',
};

/**
 * Muestra el panel correspondiente al tab y marca el tab como activo.
 * Si el tab no tiene panel asignado (ej. ENVIO), no cambia el panel visible.
 * @param {string} tabName
 */
function navegarATab(tabName) {
    const panelId = TAB_PANEL_MAP[tabName];
    if (!panelId) return; // ENVIO no navega a ningún panel

    // Ocultar todos los paneles
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.add('hidden'));

    // Mostrar el panel destino
    const panelDestino = document.getElementById(panelId);
    if (panelDestino) panelDestino.classList.remove('hidden');

    if (tabName === 'logs') {
        inicializarModoCaptura();
    }

    // Actualizar estado visual de tabs (excepto btn-guardar que tiene su propio estado)
    document.querySelectorAll('[data-tab]').forEach(btn => {
        const esActivo = btn.dataset.tab === tabName;
        btn.classList.toggle('active-tab', esActivo);
        btn.classList.toggle('text-primary-fixed', esActivo);
        btn.classList.toggle('border-primary-fixed', esActivo);
        btn.classList.toggle('text-on-surface-variant', !esActivo);
        btn.classList.toggle('border-outline-variant', !esActivo);
    });
}

function resetModoCaptura() {
    capturaEstado.inicializado = false;
    capturaEstado.indice = 0;
    capturaEstado.idsOrdenados = [];
    capturaEstado.completos = new Set();

    if (capturaCardContainer) capturaCardContainer.innerHTML = '';
    if (capturaTotalCapturadas) capturaTotalCapturadas.textContent = '0';
    if (capturaPorcentaje) capturaPorcentaje.textContent = '0%';
}

function esDesktopParaCaptura() {
    return !(window.matchMedia && window.matchMedia('(pointer: coarse)').matches);
}

function getCardInventarioById(idProducto) {
    return document.querySelector(`#lista-productos .product-card[data-id="${idProducto}"]`);
}

function leerValoresCard(card) {
    if (!card) return { cerradas: '', pesos: [] };
    const cerradasInput = card.querySelector('.input-cerradas');
    const cerradas = cerradasInput ? cerradasInput.value : '';

    const pesos = [];
    card.querySelectorAll('.item-peso-wrapper').forEach(wrapper => {
        const input = wrapper.querySelector('.input-peso');
        const select = wrapper.querySelector('.select-perfil');
        pesos.push({
            peso: input ? input.value : '',
            perfilValue: select ? select.value : null,
        });
    });

    return { cerradas, pesos };
}

function aplicarValoresCard(card, valores) {
    if (!card || !valores) return;

    const cerradasInput = card.querySelector('.input-cerradas');
    if (cerradasInput) cerradasInput.value = valores.cerradas ?? '';

    const perfilesJson = card.dataset.perfiles || '[]';
    const pesosContainer = card.querySelector('.pesos-container');
    if (!pesosContainer) {
        recalcularTarjeta(card);
        return;
    }

    const objetivo = Math.max(1, (valores.pesos || []).length || 1);
    while (pesosContainer.querySelectorAll('.item-peso-wrapper').length < objetivo) {
        const wrapper = document.createElement('div');
        wrapper.innerHTML = crearInputPeso(perfilesJson, true);
        pesosContainer.appendChild(wrapper.firstElementChild);
    }
    while (pesosContainer.querySelectorAll('.item-peso-wrapper').length > objetivo) {
        const wrappers = pesosContainer.querySelectorAll('.item-peso-wrapper');
        if (wrappers.length <= 1) break;
        wrappers[wrappers.length - 1].remove();
    }

    const wrappers = card.querySelectorAll('.item-peso-wrapper');
    wrappers.forEach((wrapper, idx) => {
        const input = wrapper.querySelector('.input-peso');
        const select = wrapper.querySelector('.select-perfil');
        const valor = valores.pesos && valores.pesos[idx] ? valores.pesos[idx] : { peso: '', perfilValue: null };
        if (input) input.value = valor.peso ?? '';
        if (select && valor.perfilValue != null) select.value = valor.perfilValue;
    });

    recalcularTarjeta(card);
}

function tarjetaCompleta(card) {
    if (!card) return false;
    const pesable = parseInt(card.dataset.pesable, 10) === 1;
    const cerradasValor = card.querySelector('.input-cerradas')?.value;

    if (cerradasValor == null || cerradasValor === '') return false;
    if (!pesable) return true;

    let tienePesoValido = false;
    card.querySelectorAll('.input-peso').forEach(input => {
        const val = parseFloat(input.value);
        if (!Number.isNaN(val) && val >= 0) {
            tienePesoValido = true;
        }
    });
    return tienePesoValido;
}

function syncCapturaConInventario() {
    if (!capturaEstado.inicializado || capturaEstado.idsOrdenados.length === 0) return;
    const idProducto = capturaEstado.idsOrdenados[capturaEstado.indice];
    const cardCaptura = capturaCardContainer.querySelector('.product-card[data-scope="captura"]');
    const cardInventario = getCardInventarioById(idProducto);
    if (!cardCaptura || !cardInventario) return;

    const valores = leerValoresCard(cardCaptura);
    aplicarValoresCard(cardInventario, valores);

    if (tarjetaCompleta(cardCaptura)) {
        capturaEstado.completos.add(idProducto);
    } else {
        capturaEstado.completos.delete(idProducto);
    }
}

function actualizarResumenCaptura() {
    const total = capturaEstado.idsOrdenados.length;
    const completas = capturaEstado.completos.size;
    const pct = total > 0 ? Math.round((completas / total) * 100) : 0;

    // Los spans de índice viven dentro de la tarjeta activa (se recrean en cada render)
    const elIndiceActual = document.getElementById('captura-indice-actual');
    const elIndiceTotal = document.getElementById('captura-indice-total');
    if (elIndiceActual) elIndiceActual.textContent = total > 0 ? String(capturaEstado.indice + 1) : '0';
    if (elIndiceTotal) elIndiceTotal.textContent = String(total);

    if (capturaTotalCapturadas) capturaTotalCapturadas.textContent = String(completas);
    if (capturaPorcentaje) capturaPorcentaje.textContent = `${pct}%`;

    if (capturaBtnAnterior) capturaBtnAnterior.disabled = capturaEstado.indice <= 0;
    if (capturaBtnAnterior) capturaBtnAnterior.classList.toggle('opacity-40', capturaEstado.indice <= 0);
}

function renderTarjetaCaptura(indice) {
    if (!capturaEstado.inicializado || capturaEstado.idsOrdenados.length === 0) {
        capturaCardContainer.innerHTML = `<div class="text-center text-on-surface-variant py-lg font-body-base">No hay productos disponibles para captura.</div>`;
        actualizarResumenCaptura();
        return;
    }

    const idProducto = capturaEstado.idsOrdenados[indice];
    const producto = productosInventario.find(p => p.id_producto === idProducto);
    if (!producto) return;

    capturaCardContainer.innerHTML = '';
    const card = crearTarjetaProductoElement(producto, 'captura');

    // Insertar contador de posición en la esquina superior derecha de la tarjeta
    const total = capturaEstado.idsOrdenados.length;
    const badgeContador = document.createElement('div');
    badgeContador.className = 'flex items-center justify-end gap-xs mb-sm';
    badgeContador.innerHTML = `<span class="text-[10px] font-label-mono text-on-surface-variant uppercase tracking-widest">Producto</span><span id="captura-indice-actual" class="text-sm font-semibold text-primary-fixed">${indice + 1}</span><span class="text-[10px] font-label-mono text-on-surface-variant">de</span><span id="captura-indice-total" class="text-sm font-semibold text-primary-fixed">${total}</span>`;
    card.insertBefore(badgeContador, card.firstChild);

    capturaCardContainer.appendChild(card);

    const cardInventario = getCardInventarioById(idProducto);
    if (cardInventario) {
        aplicarValoresCard(card, leerValoresCard(cardInventario));
    } else {
        recalcularTarjeta(card);
    }

    actualizarResumenCaptura();
}

async function navegarCaptura(delta = 1) {
    if (!capturaEstado.inicializado || capturaEstado.idsOrdenados.length === 0) return;
    syncCapturaConInventario();

    // Al avanzar, validar la tarjeta actual antes de navegar
    if (delta > 0) {
        const cardCaptura = capturaCardContainer.querySelector('.product-card[data-scope="captura"]');
        if (cardCaptura) {
            const valido = await ejecutarValidacionesGlobales([cardCaptura]);
            if (!valido) return;
        }
    }

    const siguienteIndice = Math.max(0, Math.min(capturaEstado.idsOrdenados.length - 1, capturaEstado.indice + delta));
    capturaEstado.indice = siguienteIndice;
    renderTarjetaCaptura(capturaEstado.indice);
}

function inicializarModoCaptura() {
    if (!productosInventario || productosInventario.length === 0) {
        resetModoCaptura();
        return;
    }

    if (!capturaEstado.inicializado) {
        capturaEstado.idsOrdenados = productosInventario.map(p => p.id_producto);
        capturaEstado.indice = 0;
        capturaEstado.completos = new Set();
        capturaEstado.inicializado = true;
    }

    renderTarjetaCaptura(capturaEstado.indice);
}

// Listener para todos los botones de tab con data-tab
document.querySelectorAll('[data-tab]').forEach(btn => {
    btn.addEventListener('click', () => {
        navegarATab(btn.dataset.tab);
    });
});

// Buscador en panel Stock
const stockSearchInput = document.getElementById('stock-search');
if (stockSearchInput) {
    stockSearchInput.addEventListener('input', () => {
        const query = stockSearchInput.value.toLowerCase().trim();
        document.querySelectorAll('#stock-list .stock-row').forEach(row => {
            const searchText = row.dataset.search || '';
            row.classList.toggle('hidden', query.length > 0 && !searchText.includes(query));
        });
    });
}

const stockList = document.getElementById('stock-list');
if (stockList) {
    stockList.addEventListener('input', (e) => {
        if (e.target.classList.contains('stock-input-unidades') || e.target.classList.contains('stock-input-peso')) {
            const row = e.target.closest('.stock-row');
            recalcularFilaPaloteo3(row);
        }
    });
}

if (capturaBtnAnterior) {
    capturaBtnAnterior.addEventListener('click', () => navegarCaptura(-1));
}

if (capturaBtnSiguiente) {
    capturaBtnSiguiente.addEventListener('click', () => navegarCaptura(1));
}

if (capturaBtnFinalizar) {
    capturaBtnFinalizar.addEventListener('click', async () => {
        if (!capturaEstado.inicializado || capturaEstado.idsOrdenados.length === 0) return;

        syncCapturaConInventario();
        const todasLasCards = Array.from(document.querySelectorAll('#lista-productos .product-card'));
        const valido = await ejecutarValidacionesGlobales(todasLasCards);
        if (!valido) return;

        abrirDialogoObservaciones('captura');
    });
}

if (capturaCardContainer) {
    capturaCardContainer.addEventListener('input', (e) => {
        if (e.target.classList.contains('input-cerradas') || e.target.classList.contains('input-peso')) {
            const card = e.target.closest('.product-card');
            recalcularTarjeta(card);
            const idActual = capturaEstado.idsOrdenados[capturaEstado.indice];
            if (tarjetaCompleta(card)) {
                capturaEstado.completos.add(idActual);
            } else {
                capturaEstado.completos.delete(idActual);
            }
            actualizarResumenCaptura();
        }
    });

    capturaCardContainer.addEventListener('change', (e) => {
        if (e.target.classList.contains('select-perfil')) {
            const card = e.target.closest('.product-card');
            recalcularTarjeta(card);
            syncCapturaConInventario();
            actualizarResumenCaptura();
        }
    });

    capturaCardContainer.addEventListener('click', async (e) => {
        const btnAdd = e.target.closest('.btn-add-peso-captura');
        if (btnAdd) {
            const card = capturaCardContainer.querySelector('.product-card[data-scope="captura"]');
            agregarInputPesoEnCard(card);
            recalcularTarjeta(card);
            syncCapturaConInventario();
            return;
        }

        const btnModelo = e.target.closest('.btn-add-modelo-captura');
        if (btnModelo) {
            const idProducto = parseInt(btnModelo.dataset.idProducto, 10);
            if (!isNaN(idProducto)) {
                await crearModeloBotella(idProducto);
                renderTarjetaCaptura(capturaEstado.indice);
            }
            return;
        }

        if (e.target.closest('.btn-remove-peso')) {
            const card = capturaCardContainer.querySelector('.product-card[data-scope="captura"]');
            setTimeout(() => {
                recalcularTarjeta(card);
                syncCapturaConInventario();
                actualizarResumenCaptura();
            }, 20);
        }
    });

    capturaCardContainer.addEventListener('keydown', (e) => {
        if (e.key !== 'Enter') return;
        if (!esDesktopParaCaptura()) return;
        if (!(e.target.classList.contains('input-cerradas') || e.target.classList.contains('input-peso'))) return;

        const card = capturaCardContainer.querySelector('.product-card[data-scope="captura"]');
        if (!card) return;
        e.preventDefault();

        navegarCaptura(1);
    });
}

document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !observacionesDialog.classList.contains('hidden')) {
        cerrarDialogoObservaciones();
        return;
    }

    const panelLogsVisible = !document.getElementById('panel-logs').classList.contains('hidden');
    if (!panelLogsVisible) return;

    if (event.ctrlKey && event.key === 'ArrowRight') {
        event.preventDefault();
        navegarCaptura(1);
    }

    if (event.ctrlKey && event.key === 'ArrowLeft') {
        event.preventDefault();
        navegarCaptura(-1);
    }
});

btnEnviarInventario.addEventListener('click', async () => {
    const observaciones = inputObservaciones.value.trim() || null;
    const payload = await construirPayloadInventario(observaciones);
    if (!payload) return;
    await enviarInventario(payload);
});

// ==========================================
// CÁLCULO EN TIEMPO REAL (ONZAS, UNIDADES Y DIFERENCIAS)
// ==========================================

// Función auxiliar para pintar las diferencias (Verde/Roja/Amarillo con Electric Industrial)
function formatearDiferencia(diferencia, isOz = false) {
    const sufijo = isOz ? "oz" : "bot";

    // Tolerancia para decimales (evitar ruido por redondeos)
    if (Math.abs(diferencia) < 0.01) {
        return `<span class="text-data-tabular font-semibold" style="color: var(--semantic-action)">${renderCriticalIcon('check_circle', 'ui-icon ui-icon-sm')}</span>`;
    }

    if (diferencia < 0) {
        const val = isOz ? diferencia.toFixed(2) : Math.round(diferencia);
        return `<span class="text-data-tabular font-semibold" style="color: var(--semantic-danger)">${val} ${sufijo}</span>`;
    }

    const val = isOz ? diferencia.toFixed(2) : Math.round(diferencia);
    return `<span class="text-data-tabular font-semibold" style="color: var(--semantic-danger)">+${val} ${sufijo}</span>`;
}

// Recalcula una tarjeta y actualiza PAQ/BARRA, DET/BARRA y sus diferencias contra el sistema
function recalcularTarjeta(card) {
    if (!card) return;

    const idProducto = card.dataset.id;
    const scope = card.dataset.scope === 'captura' ? `cap-${idProducto}` : `${idProducto}`;
    const pesable = parseInt(card.dataset.pesable);

    // Variables del sistema
    const paqSist = parseFloat(card.dataset.paqsist) || 0;
    const detSist = parseFloat(card.dataset.detsist) || 0;

    // 1. PAQ/BARRA
    const inputCerradas = card.querySelector('.input-cerradas');
    const paqBarra = parseInt(inputCerradas.value) || 0;
    const spanPaq = card.querySelector(`#val-paq-${scope}`) || document.getElementById(`val-paq-${scope}`);
    const difPaqSpan = card.querySelector(`#dif-paq-${scope}`) || document.getElementById(`dif-paq-${scope}`);

    if (spanPaq) spanPaq.textContent = paqBarra;
    if (difPaqSpan) difPaqSpan.innerHTML = formatearDiferencia(paqBarra - paqSist, false);

    // 2. DET/BARRA
    if (pesable === 1) {
        const perfiles = JSON.parse(card.dataset.perfiles || '[]');
        const tolerancia = parseFloat(card.dataset.tolerancia) || 0;
        const inputsPeso = card.querySelectorAll('.input-peso');
        const spanDet = card.querySelector(`#val-det-${scope}`) || document.getElementById(`val-det-${scope}`);
        const difDetSpan = card.querySelector(`#dif-det-${scope}`) || document.getElementById(`dif-det-${scope}`);

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
    if (e.target.closest('.btn-remove-peso')) {
        const card = e.target.closest('.product-card');
        setTimeout(() => recalcularTarjeta(card), 50);
    }
});

function inicializarCalculos() {
    document.querySelectorAll('#lista-productos .product-card').forEach(card => {
        recalcularTarjeta(card);
    });
}