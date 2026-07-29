// ==========================================
// CONFIGURACIÓN Y ESTADO GLOBAL
// ==========================================
// Fix #22: URL dinámica para que funcione tanto en localhost como en producción
const API_BASE = `${window.location.origin}/api`;
let currentToken = localStorage.getItem('token') || null;
let currentOperacionId = null;
let currentIdInventarioPOS = null; // Guardamos el ID del inventario ya registrado para correcciones
let operativaPermitePaloteo = false;
let currentEstadoOperacion = null; // estado_operacion crudo (22/23/24/...) de la operativa activa
let idBarraActual = 1;
let configuracionPaloteo = {
    selectorEnabled: false,
    defaultBarraId: 1,
    allowedBarras: [1],
};
let productosInventario = [];
let modoEnvioOrigen = 'inventario';
let vistaInicialSoloOperativa = true;

// ==========================================
// AUTOSAVE: CONFIGURACION Y ESTADO
// ==========================================
const AUTOSAVE_SCHEMA_VERSION = '1.0';
const AUTOSAVE_DEBOUNCE_MS = 900;
const AUTOSAVE_INTERVAL_MS = 20000;
const AUTOSAVE_KEY_PREFIX = `backstage:paloteo:draft:v${AUTOSAVE_SCHEMA_VERSION}`;

let autosaveDebounceTimer = null;
let autosaveIntervalId = null;
let autosaveLastHash = '';

const reporteEstado = {
    filtro: 'todos',
    sortBy: null,
    sortDir: 'asc',
};

const capturaEstado = {
    inicializado: false,
    indice: 0,
    idsOrdenados: [],
    completos: new Set(),
    // Busqueda activa desde la barra superior: null = sin busqueda (navega todo
    // el catalogo); array = solo navega entre los indices que matchean la query.
    matches: null,
    matchIndex: 0,
};

// Elementos del DOM
const loginScreen = document.getElementById('login-screen');
const appScreen = document.getElementById('app-screen');
const loginForm = document.getElementById('login-form');
const btnLogout = document.getElementById('btn-logout');
const inventarioCapturaContenido = document.getElementById('inventario-captura-contenido');
const listaProductos = document.getElementById('lista-productos');
const submitSection = document.getElementById('submit-section');
const btnGuardar = document.getElementById('btn-guardar-inventario');
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
const stockBtnGuardar = document.getElementById('stock-btn-guardar');
const reporteBtnPdf = document.getElementById('reporte-btn-pdf');
const reporteFiltroTodosBtn = document.getElementById('reporte-filtro-todos');
const reporteFiltroIngresoBtn = document.getElementById('reporte-filtro-ingreso');
const reporteFiltroSalidaBtn = document.getElementById('reporte-filtro-salida');
const reporteSortBtns = Array.from(document.querySelectorAll('[data-reporte-sort]'));
const ajustesAdminBlock = document.getElementById('ajustes-admin-block');
const ajustesEstadoMsg = document.getElementById('ajustes-estado-msg');
const ajustesAplicadoBadge = document.getElementById('ajustes-aplicado-badge');
const ajustesAplicadoTexto = document.getElementById('ajustes-aplicado-texto');
const ajustesBtnAplicar = document.getElementById('ajustes-btn-aplicar');
const btnTopbarMenu = document.getElementById('btn-topbar-menu');
const topbarMenuDropdown = document.getElementById('topbar-menu-dropdown');
const dummyContentDialog = document.getElementById('dummy-content-dialog');
const dummyContentOverlay = document.getElementById('dummy-content-overlay');
const dummyContentTitle = document.getElementById('dummy-content-title');
const dummyContentBody = document.getElementById('dummy-content-body');
const btnCloseDummyContent = document.getElementById('btn-close-dummy-content');
const autosaveStatus = document.getElementById('autosave-status');
const barraSelectorContainer = document.getElementById('barra-selector-container');
const barraSelector = document.getElementById('barra-selector');

const dummyContentMap = {
    guia: {
        titulo: 'Guia Operativa Dummy',
        lineas: [
            'Bloque A: Validar inventario inicial y confirmar sensores de peso.',
            'Bloque B: Ejecutar corte de prueba con dos referencias de botella.',
            'Bloque C: Registrar observaciones del turno y continuar con paloteo.'
        ]
    },
    boletin: {
        titulo: 'Boletin Dummy',
        lineas: [
            'Novedad 01: Se habilita un tablero de metricas en fase de ensayo.',
            'Novedad 02: Mejoras visuales planificadas para vistas de captura rapida.',
            'Novedad 03: Se agrega canal interno para feedback operativo semanal.'
        ]
    }
};

function _normalizarBarrasPermitidas(lista) {
    if (!Array.isArray(lista)) return [];
    const barras = lista
        .map((valor) => parseInt(valor, 10))
        .filter((valor) => !Number.isNaN(valor) && valor > 0);
    return [...new Set(barras)];
}

function aplicarConfiguracionBarraUI() {
    if (!barraSelectorContainer || !barraSelector) return;

    barraSelector.innerHTML = '';
    configuracionPaloteo.allowedBarras.forEach((barra) => {
        const option = document.createElement('option');
        option.value = String(barra);
        option.textContent = `#${barra}`;
        barraSelector.appendChild(option);
    });

    barraSelector.value = String(idBarraActual);

    const mostrarSelector = configuracionPaloteo.selectorEnabled;
    barraSelectorContainer.classList.toggle('hidden', !mostrarSelector);
    barraSelectorContainer.classList.toggle('flex', mostrarSelector);
}

async function cargarConfiguracionPublica() {
    try {
        const response = await fetch(`${API_BASE}/config/public`);
        if (!response.ok) throw new Error('No se pudo cargar configuración pública.');

        const data = await response.json();
        const paloteo = data && data.paloteo ? data.paloteo : {};
        const defaultBarraId = parseInt(paloteo.default_barra_id, 10);
        const selectorEnabled = Boolean(paloteo.selector_enabled);
        const allowedBarras = _normalizarBarrasPermitidas(paloteo.allowed_barras);

        configuracionPaloteo = {
            selectorEnabled,
            defaultBarraId: (!Number.isNaN(defaultBarraId) && defaultBarraId > 0) ? defaultBarraId : 1,
            allowedBarras: allowedBarras.length > 0 ? allowedBarras : [(!Number.isNaN(defaultBarraId) && defaultBarraId > 0) ? defaultBarraId : 1],
        };

        const barraGuardada = parseInt(localStorage.getItem('paloteo_barra_id') || '', 10);
        const barraInicial = selectorEnabled && configuracionPaloteo.allowedBarras.includes(barraGuardada)
            ? barraGuardada
            : configuracionPaloteo.defaultBarraId;

        idBarraActual = configuracionPaloteo.allowedBarras.includes(barraInicial)
            ? barraInicial
            : configuracionPaloteo.allowedBarras[0];

        localStorage.setItem('paloteo_barra_id', String(idBarraActual));
    } catch (error) {
        configuracionPaloteo = {
            selectorEnabled: false,
            defaultBarraId: 1,
            allowedBarras: [1],
        };
        idBarraActual = 1;
        localStorage.setItem('paloteo_barra_id', '1');
    }

    aplicarConfiguracionBarraUI();
}

function _obtenerUsuarioAutosave() {
    return localStorage.getItem('nombres') || 'anonimo';
}

function _obtenerClaveAutosave() {
    if (!currentOperacionId) return null;
    return `${AUTOSAVE_KEY_PREFIX}:${idBarraActual}:${currentOperacionId}:${_obtenerUsuarioAutosave()}`;
}

function _actualizarEstadoAutosave(tipo, mensaje) {
    if (!autosaveStatus) return;

    autosaveStatus.classList.remove('text-on-surface-variant', 'text-primary-fixed', 'text-error', 'text-tertiary-fixed');
    if (tipo === 'saved') autosaveStatus.classList.add('text-primary-fixed');
    else if (tipo === 'error') autosaveStatus.classList.add('text-error');
    else if (tipo === 'pending') autosaveStatus.classList.add('text-tertiary-fixed');
    else autosaveStatus.classList.add('text-on-surface-variant');

    autosaveStatus.textContent = mensaje;
}

function _snapshotAutosaveActual() {
    if (!currentOperacionId) return null;

    const cards = document.querySelectorAll('#lista-productos .product-card');
    if (!cards.length) return null;

    const items = Array.from(cards).map((card) => {
        const idProducto = parseInt(card.dataset.id, 10);
        const valores = leerValoresCard(card);
        return {
            id_producto: idProducto,
            cerradas: valores.cerradas ?? '',
            pesos: valores.pesos ?? [],
        };
    }).filter((item) => !Number.isNaN(item.id_producto));

    // Productos agregados manualmente (sin movimiento esta operativa): /pendientes
    // nunca los devuelve, asi que se guarda el objeto completo para poder recrear
    // su tarjeta al hidratar el borrador, antes de aplicarle cerradas/pesos.
    const productosManuales = productosInventario.filter((p) => p._agregadoManual);

    return {
        schema_version: AUTOSAVE_SCHEMA_VERSION,
        id_operacion: currentOperacionId,
        id_barra: idBarraActual,
        id_inventario_pos: currentIdInventarioPOS,
        observaciones: inputObservaciones ? inputObservaciones.value : '',
        saved_at: new Date().toISOString(),
        items,
        productos_manuales: productosManuales,
    };
}

function _hashAutosave(snapshot) {
    return JSON.stringify({
        id_operacion: snapshot.id_operacion,
        id_barra: snapshot.id_barra,
        id_inventario_pos: snapshot.id_inventario_pos,
        observaciones: snapshot.observaciones,
        items: snapshot.items,
    });
}

function flushAutosave(modo = 'manual') {
    if (!operativaPermitePaloteo || !currentOperacionId) return;

    const snapshot = _snapshotAutosaveActual();
    if (!snapshot) return;

    const hash = _hashAutosave(snapshot);
    if (hash === autosaveLastHash && modo !== 'force') return;

    const key = _obtenerClaveAutosave();
    if (!key) return;

    try {
        localStorage.setItem(key, JSON.stringify(snapshot));
        autosaveLastHash = hash;
        const hora = new Date().toLocaleTimeString('es-BO', { hour: '2-digit', minute: '2-digit' });
        _actualizarEstadoAutosave('saved', `Borrador guardado automaticamente a las ${hora}.`);
    } catch (error) {
        _actualizarEstadoAutosave('error', 'No se pudo guardar el borrador automatico en este dispositivo.');
        console.error('Autosave error:', error);
    }
}

function scheduleAutosave() {
    if (!operativaPermitePaloteo || !currentOperacionId) return;

    const snapshot = _snapshotAutosaveActual();
    if (!snapshot) return;

    const hash = _hashAutosave(snapshot);
    if (hash === autosaveLastHash) return;

    _actualizarEstadoAutosave('pending', 'Guardando borrador...');

    if (autosaveDebounceTimer) {
        clearTimeout(autosaveDebounceTimer);
    }

    autosaveDebounceTimer = setTimeout(() => {
        flushAutosave('debounce');
    }, AUTOSAVE_DEBOUNCE_MS);
}

function startAutosaveInterval() {
    if (autosaveIntervalId) {
        clearInterval(autosaveIntervalId);
    }
    autosaveIntervalId = setInterval(() => {
        flushAutosave('interval');
    }, AUTOSAVE_INTERVAL_MS);
}

function stopAutosaveInterval() {
    if (autosaveIntervalId) {
        clearInterval(autosaveIntervalId);
        autosaveIntervalId = null;
    }
    if (autosaveDebounceTimer) {
        clearTimeout(autosaveDebounceTimer);
        autosaveDebounceTimer = null;
    }
}

function clearAutosaveDraft() {
    const key = _obtenerClaveAutosave();
    if (!key) return;

    if (autosaveDebounceTimer) {
        clearTimeout(autosaveDebounceTimer);
        autosaveDebounceTimer = null;
    }
    if (autosaveIntervalId) {
        clearInterval(autosaveIntervalId);
        autosaveIntervalId = null;
    }

    localStorage.removeItem(key);
    autosaveLastHash = '';
    _actualizarEstadoAutosave('idle', 'Sin borrador pendiente.');
}

function hydrateAutosaveDraft() {
    if (!operativaPermitePaloteo) return;

    const key = _obtenerClaveAutosave();
    if (!key) return;

    const raw = localStorage.getItem(key);
    if (!raw) {
        _actualizarEstadoAutosave('idle', 'Sin borrador local previo para esta operativa.');
        return;
    }

    try {
        const snapshot = JSON.parse(raw);
        if (!snapshot || snapshot.id_operacion !== currentOperacionId || snapshot.id_barra !== idBarraActual) {
            return;
        }

        if (snapshot.id_inventario_pos && !currentIdInventarioPOS) {
            currentIdInventarioPOS = snapshot.id_inventario_pos;
        }

        // Recrea primero las tarjetas de productos agregados manualmente (no vienen
        // en /pendientes), para que el forEach de abajo encuentre su card al aplicar
        // cerradas/pesos.
        (snapshot.productos_manuales || []).forEach((producto) => {
            if (productosInventario.some((p) => p.id_producto === producto.id_producto)) return;
            agregarProductoManual(producto, { enfocar: false });
        });

        (snapshot.items || []).forEach((item) => {
            const card = document.querySelector(`#lista-productos .product-card[data-id="${item.id_producto}"]`);
            if (!card) return;
            aplicarValoresCard(card, {
                cerradas: item.cerradas,
                pesos: item.pesos || [],
            });
        });

        if (inputObservaciones && snapshot.observaciones && !inputObservaciones.value) {
            inputObservaciones.value = snapshot.observaciones;
        }

        autosaveLastHash = _hashAutosave(snapshot);
        _actualizarEstadoAutosave('saved', 'Borrador local recuperado correctamente.');
    } catch (error) {
        _actualizarEstadoAutosave('error', 'El borrador local esta corrupto y no se pudo recuperar.');
        console.error('Autosave hydration error:', error);
    }
}

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

function cerrarMenuFlotanteTopbar() {
    if (!topbarMenuDropdown || !btnTopbarMenu) return;
    topbarMenuDropdown.classList.add('hidden');
    btnTopbarMenu.setAttribute('aria-expanded', 'false');
}

function alternarMenuFlotanteTopbar() {
    if (!topbarMenuDropdown || !btnTopbarMenu) return;
    const estabaOculto = topbarMenuDropdown.classList.contains('hidden');
    topbarMenuDropdown.classList.toggle('hidden');
    btnTopbarMenu.setAttribute('aria-expanded', estabaOculto ? 'true' : 'false');
}

function cerrarContenidoDummy() {
    if (!dummyContentDialog) return;
    dummyContentDialog.classList.add('hidden');
    dummyContentDialog.setAttribute('aria-hidden', 'true');
}

function abrirContenidoDummy(clave) {
    const contenido = dummyContentMap[clave];
    if (!contenido || !dummyContentDialog || !dummyContentTitle || !dummyContentBody) return;

    dummyContentTitle.textContent = contenido.titulo;
    dummyContentBody.innerHTML = contenido.lineas
        .map((linea) => `<p>${escapeHtml(linea)}</p>`)
        .join('');

    dummyContentDialog.classList.remove('hidden');
    dummyContentDialog.setAttribute('aria-hidden', 'false');
}

// Fix #27: Función centralizada para crear el HTML de un input de peso.
// Soporta perfiles múltiples para seleccionar el modelo de botella por registro.
const ID_CATEGORIA_VINOS = 6;

function esCategoriaVinos(idCategoria) {
    return parseInt(idCategoria, 10) === ID_CATEGORIA_VINOS;
}

function etiquetaDetalleCorta(idCategoria) {
    return esCategoriaVinos(idCategoria) ? 'cop' : 'oz';
}

function etiquetaDetalleLarga(idCategoria) {
    return esCategoriaVinos(idCategoria) ? 'copas' : 'oz';
}

function crearInputPeso(perfilesJson, removable = true, esVino = false) {
    const perfiles = JSON.parse(perfilesJson || '[]');
    let selectHTML = '';
    const soloLectura = !operativaPermitePaloteo;
    const disabledAttr = soloLectura ? ' disabled' : '';
    const placeholder = esVino ? 'Ej: 2' : 'Ej: 950';
    const step = esVino ? '0.5' : '1';

    if (perfiles.length > 1) {
        selectHTML = `<select class="bg-surface-container-low text-data-tabular text-primary-fixed border border-outline-variant rounded-md px-sm py-xs focus:outline-none select-perfil mr-sm cursor-pointer font-semibold"${disabledAttr}>`;
        perfiles.forEach((pf, idx) => {
                const optionValue = (pf.id != null) ? pf.id : idx;
                selectHTML += `<option value="${optionValue}">${escapeHtml(pf.nombre_perfil)}</option>`;
        });
        selectHTML += `</select>`;
    }

    const removeButtonHtml = removable
        ? `<button type="button" onclick="this.parentElement.parentElement.remove()" class="btn-remove-peso absolute right-sm top-1/2 -translate-y-1/2 text-on-surface-variant hover:text-error transition-colors"${disabledAttr} aria-label="Eliminar campo de peso">
                    ${renderCriticalIcon('close', 'ui-icon ui-icon-sm')}
                </button>`
        : '';

    return `
        <div class="relative flex items-center item-peso-wrapper gap-sm">
            ${selectHTML}
            <div class="relative flex-1">
                <input type="number" min="0" step="${step}" class="w-full bg-surface border border-outline-variant rounded-md pl-md pr-lg py-sm text-on-surface input-peso focus:border-error focus:outline-none focus:shadow-cyan-glow-focus font-data-tabular" placeholder="${placeholder}" required${disabledAttr}>
                ${removeButtonHtml}
            </div>
        </div>
    `;
}

// Variante compacta de crearInputPeso para PALOTEO 3: misma estructura/clases
// (item-peso-wrapper, input-peso, select-perfil) para ser compatible con
// leerValoresCard/aplicarValoresCard/recalcularTarjeta, pero con botones ±
// para ajuste rápido en la tabla.
function crearInputPesoCompacto(perfilesJson, removable = true, esVino = false) {
    const perfiles = JSON.parse(perfilesJson || '[]');
    let selectHTML = '';
    const soloLectura = !operativaPermitePaloteo;
    const disabledAttr = soloLectura ? ' disabled' : '';
    const step = esVino ? '0.5' : '1';

    if (perfiles.length > 1) {
        selectHTML = `<select class="select-perfil bg-surface-container-low text-on-surface border border-outline-variant rounded px-1 py-1 text-[10px] focus:outline-none cursor-pointer"${disabledAttr}>`;
        perfiles.forEach((pf, idx) => {
            const optionValue = (pf.id != null) ? pf.id : idx;
            selectHTML += `<option value="${optionValue}">${escapeHtml(pf.nombre_perfil)}</option>`;
        });
        selectHTML += `</select>`;
    }

    const removeButtonHtml = removable
        ? `<button type="button" class="btn-remove-peso flex-none px-1 text-on-surface-variant hover:text-error transition-colors"${disabledAttr} aria-label="Eliminar peso">×</button>`
        : '';

    // Botones +/- de ajuste rápido: solo administradores (ver crearFilaPaloteo3).
    const claseBotonAjustePeso = (esUsuarioAdministrador() && !soloLectura) ? '' : ' hidden';

    return `
        <div class="item-peso-wrapper flex items-center gap-1">
            ${selectHTML}
            <input type="number" min="0" step="${step}" class="input-peso w-14 text-center bg-surface border border-outline-variant rounded px-1 py-1 text-on-surface focus:border-primary-fixed-dim focus:outline-none transition-colors" placeholder="0"${disabledAttr}>
            <button type="button" class="stock-btn-dec-peso${claseBotonAjustePeso} flex-none px-1.5 py-1 bg-surface border border-outline-variant rounded text-on-surface hover:bg-surface-container-highest transition-colors font-semibold leading-none" title="Restar"${disabledAttr}>−</button>
            <button type="button" class="stock-btn-inc-peso${claseBotonAjustePeso} flex-none px-1.5 py-1 bg-surface border border-outline-variant rounded text-on-surface hover:bg-surface-container-highest transition-colors font-semibold leading-none" title="Sumar"${disabledAttr}>+</button>
            ${removeButtonHtml}
        </div>
    `;
}

// Paso de ± en unidad de detalle (gramos o copas) equivalente al medio paso
// operativo del perfil seleccionado. Si no hay perfil resoluble, usa 1.
function calcularStepPesoGramos(perfiles, select) {
    const { perfil } = resolverPerfilSeleccionado(perfiles, select);
    const groz = perfil ? parseFloat(perfil.gramos_por_oz) : NaN;
    if (isNaN(groz) || groz <= 0) return 1;
    return Math.max(1, Math.round(groz / 2));
}

function ajustarValorNumerico(input, incrementar, paso, decimales = 0) {
    if (!input) return;
    let valor = parseFloat(input.value) || 0;
    valor = incrementar ? (valor + paso) : Math.max(0, valor - paso);
    valor = decimales > 0 ? parseFloat(valor.toFixed(decimales)) : Math.round(valor);
    input.value = valor;
    input.dispatchEvent(new Event('input', { bubbles: true }));
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
const mbNombreHint = document.getElementById('mb-nombre-hint');
const mbPesoBruto  = document.getElementById('mb-peso-bruto');
const mbTara       = document.getElementById('mb-tara');
const mbGramosOz   = document.getElementById('mb-gramos-oz');
const mbBarcode    = document.getElementById('mb-barcode');
const mbVolumenOz  = document.getElementById('mb-volumen-oz');
const mbError      = document.getElementById('mb-error');
const btnCancelarModelo  = document.getElementById('btn-cancelar-modelo');
const btnConfirmarModelo = document.getElementById('btn-confirmar-modelo');
const PESAJE_NOMBRE_PERFIL_DEFAULT = 'Estándar';

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
 * Muestra un modal de resultado (éxito, advertencia o error) y resuelve cuando el usuario lo cierra.
 * @param {Object} opts - { tipo: 'success'|'warning'|'error', titulo: string, mensaje: string }
 * @returns {Promise<void>}
 */
function mostrarDialogoResultado({ tipo = 'success', titulo, mensaje }) {
    return new Promise((resolve) => {
        // Configurar icono y color según tipo
        if (tipo === 'success') {
            resultadoIcono.textContent = 'check_circle';
            resultadoIcono.style.color = 'var(--color-primary-fixed-dim)';
            resultadoTituloTexto.style.color = '';
        } else if (tipo === 'warning') {
            resultadoIcono.textContent = 'visibility';
            resultadoIcono.style.color = 'var(--semantic-warning, #facc15)';
            resultadoTituloTexto.style.color = 'var(--semantic-warning, #facc15)';
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
function abrirModalModelo(nombreProducto, perfilBase, volumenOz, forzarEstandar = false, esVino = false) {
    return new Promise((resolve) => {
        // Subtítulo con nombre del producto
        modeloBotellaSubtit.textContent = nombreProducto;
        mbVolumenOz.textContent = volumenOz ? volumenOz.toFixed(2) : '-';

        // Pre-llenar con valores del perfil base si existe
        mbNombre.value    = forzarEstandar ? PESAJE_NOMBRE_PERFIL_DEFAULT : '';
        mbNombre.readOnly = forzarEstandar;
        if (mbNombreHint) {
            mbNombreHint.classList.toggle('hidden', !forzarEstandar);
        }
        mbPesoBruto.value = perfilBase ? perfilBase.peso_bruto : '';
        mbTara.value      = esVino ? '0' : (perfilBase ? perfilBase.tara : '');
        mbBarcode.value   = perfilBase ? (perfilBase.barcode || '') : '';
        mbTara.readOnly = esVino;
        mbError.classList.add('hidden');
        mbError.textContent = '';

        function actualizarGramosOz() {
            const pesoBruto = parseFloat(mbPesoBruto.value);
            const tara = parseFloat(mbTara.value);
            if (esVino && !Number.isNaN(pesoBruto)) {
                mbGramosOz.value = '1.000000';
                return;
            }
            if (!volumenOz || Number.isNaN(pesoBruto) || Number.isNaN(tara)) {
                mbGramosOz.value = '';
                return;
            }
            mbGramosOz.value = ((pesoBruto - tara) / volumenOz).toFixed(6);
        }
        actualizarGramosOz();

        modeloBotellaDialog.classList.remove('hidden');
        mbNombre.focus();

        function mostrarError(msg) {
            mbError.textContent = msg;
            mbError.classList.remove('hidden');
        }

        function cerrar(resultado) {
            modeloBotellaDialog.classList.add('hidden');
            mbNombre.readOnly = false;
            mbTara.readOnly = false;
            if (mbNombreHint) {
                mbNombreHint.classList.add('hidden');
            }
            btnConfirmarModelo.removeEventListener('click', onConfirmar);
            btnCancelarModelo.removeEventListener('click', onCancelar);
            modeloBotellaOverlay.removeEventListener('click', onCancelar);
            mbPesoBruto.removeEventListener('input', actualizarGramosOz);
            mbTara.removeEventListener('input', actualizarGramosOz);
            resolve(resultado);
        }

        function onConfirmar() {
            const nombre    = forzarEstandar ? PESAJE_NOMBRE_PERFIL_DEFAULT : mbNombre.value.trim().toUpperCase();
            const pesoBruto = parseFloat(mbPesoBruto.value);
            const tara      = esVino ? 0 : parseFloat(mbTara.value);
            const barcode   = mbBarcode.value.trim();

            if (!nombre) return mostrarError('El nombre del modelo es obligatorio.');
            if ([pesoBruto, tara].some(Number.isNaN)) {
                return mostrarError('Todos los valores numéricos deben ser válidos.');
            }
            if (esVino && tara !== 0) {
                return mostrarError('En categoría VINOS la tara debe ser 0.');
            }

            cerrar({ nombre, pesoBruto, tara, barcode: barcode || null });
        }

        function onCancelar() { cerrar(null); }

        btnConfirmarModelo.addEventListener('click', onConfirmar);
        btnCancelarModelo.addEventListener('click', onCancelar);
        modeloBotellaOverlay.addEventListener('click', onCancelar);
        mbPesoBruto.addEventListener('input', actualizarGramosOz);
        mbTara.addEventListener('input', actualizarGramosOz);
    });
}

// ==========================================
// MÓDULO PESAJE (CRUD app_producto_pesaje_config_api)
// ==========================================

// pesajeEstado.filtro: 'pesables' (completos) | 'incompletos' (pesables con
// algun perfil sin peso_bruto/tara) | 'no_pesables'. Las dos primeras piden
// el mismo pesable=1 al backend y se separan en el cliente (ver
// pesajeProductoTieneIncompleto); "incompletos" no es un concepto que
// aplique a no pesables, que no tienen peso_bruto/tara.
const pesajeEstado = {
    filtro: 'pesables',
    nombre: '',
    idCategoria: '',
    datos: [],
};

const pesajeCategoriaSel         = document.getElementById('pesaje-categoria');
const pesajeFiltroPesablesBtn    = document.getElementById('pesaje-filtro-pesables');
const pesajeFiltroIncompletosBtn = document.getElementById('pesaje-filtro-incompletos');
const pesajeFiltroNoPesablesBtn  = document.getElementById('pesaje-filtro-no-pesables');
const pesajeList                = document.getElementById('pesaje-list');
const pesajeEmptyState          = document.getElementById('pesaje-empty-state');

let categoriasPesajeCargadas = false;
let categoriasPesajeCargaPromise = null;

async function cargarCategoriasPesaje() {
    if (categoriasPesajeCargadas || !pesajeCategoriaSel) return;
    if (categoriasPesajeCargaPromise) {
        await categoriasPesajeCargaPromise;
        return;
    }

    categoriasPesajeCargaPromise = (async () => {
    try {
        const response = await fetchAutenticado(`${API_BASE}/pesaje/categorias`);
        if (!response.ok) return;
        const categorias = await response.json();

        // Limpia opciones dinámicas previas por seguridad ante recargas de UI.
        pesajeCategoriaSel
            .querySelectorAll('option[data-pesaje-categoria="1"]')
            .forEach((opt) => opt.remove());

        // Evita duplicados aunque el backend repita filas o entren 2 cargas.
        const categoriasUnicas = new Map();
        categorias.forEach((cat) => {
            const id = String(cat.id_categoria);
            if (!categoriasUnicas.has(id)) {
                categoriasUnicas.set(id, cat);
            }
        });

        categoriasUnicas.forEach((cat) => {
            const option = document.createElement('option');
            option.value = cat.id_categoria;
            option.textContent = cat.nombre_categoria;
            option.dataset.pesajeCategoria = '1';
            pesajeCategoriaSel.appendChild(option);
        });

        if (pesajeEstado.idCategoria) {
            pesajeCategoriaSel.value = pesajeEstado.idCategoria;
        }

        categoriasPesajeCargadas = true;
    } catch (error) {
        // Silencioso: el filtro de categoría queda solo con "Todas"
    } finally {
        categoriasPesajeCargaPromise = null;
    }

    })();

    await categoriasPesajeCargaPromise;
}

function actualizarUIFiltrosPesaje() {
    const estilos = [
        { btn: pesajeFiltroPesablesBtn, activo: pesajeEstado.filtro === 'pesables' },
        { btn: pesajeFiltroIncompletosBtn, activo: pesajeEstado.filtro === 'incompletos' },
        { btn: pesajeFiltroNoPesablesBtn, activo: pesajeEstado.filtro === 'no_pesables' },
    ];
    estilos.forEach(({ btn, activo }) => {
        if (!btn) return;
        btn.classList.toggle('bg-primary-container', activo);
        btn.classList.toggle('text-black', activo);
        btn.classList.toggle('border-primary-fixed-dim', activo);
        btn.classList.toggle('bg-surface', !activo);
        btn.classList.toggle('text-on-surface', !activo);
        btn.classList.toggle('border-outline-variant', !activo);
    });
}

/** Indicador de carga del listado de PESAJE: mismo spinner (flechas girando)
 * que se usa al registrar un paloteo / generar PDF. Ocupa todo el ancho de la
 * grilla y se reemplaza al renderizar las tarjetas. */
function mostrarCargandoPesaje() {
    if (pesajeEmptyState) pesajeEmptyState.classList.add('hidden');
    if (!pesajeList) return;
    pesajeList.innerHTML = `
        <div class="col-span-full flex items-center justify-center gap-sm py-lg text-on-surface-variant font-label-mono uppercase tracking-widest text-[11px]" aria-live="polite" style="grid-column: 1 / -1;">
            ${renderCriticalIcon('refresh', 'ui-icon animate-spin-ccw')}
            Cargando...
        </div>`;
}

async function cargarPesaje() {
    if (!pesajeList) return;
    mostrarCargandoPesaje();
    await cargarCategoriasPesaje();
    actualizarUIFiltrosPesaje();

    const params = new URLSearchParams();
    // 'pesables' e 'incompletos' piden el mismo pesable=1; se separan al renderizar.
    params.set('pesable', pesajeEstado.filtro === 'no_pesables' ? '0' : '1');
    if (pesajeEstado.nombre) params.set('nombre', pesajeEstado.nombre);
    if (pesajeEstado.idCategoria) params.set('id_categoria', pesajeEstado.idCategoria);

    try {
        const response = await fetchAutenticado(`${API_BASE}/pesaje/config?${params.toString()}`);
        if (response.status === 403) {
            pesajeList.innerHTML = '';
            pesajeEmptyState.textContent = 'No tienes permisos para acceder a este módulo.';
            pesajeEmptyState.classList.remove('hidden');
            return;
        }
        pesajeEstado.datos = response.ok ? await response.json() : [];
    } catch (error) {
        if (error instanceof SesionExpiradaError) return;
        pesajeEstado.datos = [];
    }

    renderizarPesaje();
}

/** Un producto pesable "esta incompleto" si algun perfil no tiene peso_bruto
 * o tara cargados. No aplica a no pesables (no tienen esos campos). */
function pesajePerfilesReales(producto) {
    return (producto.perfiles || []).filter((p) => p.id !== null && p.id !== undefined);
}

function pesajeProductoTieneIncompleto(producto) {
    if (producto.pesable !== 1) return false;
    const perfilesReales = pesajePerfilesReales(producto);
    if (perfilesReales.length === 0) return true;
    return perfilesReales.some(
        (p) => p.peso_bruto === null || p.tara === null || p.peso_bruto <= 0 || p.gramos_por_oz <= 0
    );
}

function renderizarPesaje() {
    pesajeList.innerHTML = '';

    const productos = new Map();
    pesajeEstado.datos.forEach((item) => {
        if (!productos.has(item.id_producto)) {
            productos.set(item.id_producto, {
                id_producto: item.id_producto,
                nombre_producto: item.nombre_producto,
                codigo_producto: item.codigo_producto,
                nombre_categoria: item.nombre_categoria,
                pesable: item.pesable,
                volumen_oz: item.volumen_oz,
                medida: item.medida,
                nombre_unidad_medida: item.nombre_unidad_medida,
                nombre_unidad_medida_detalle: item.nombre_unidad_medida_detalle,
                nombre_ind_permite_comandar: item.nombre_ind_permite_comandar,
                perfiles: [],
            });
        }
        productos.get(item.id_producto).perfiles.push(item);
    });

    // 'pesables' e 'incompletos' llegan con el mismo fetch (pesable=1) y se
    // separan aca; 'no_pesables' se muestra entero (no aplica el concepto).
    let listaProductos = Array.from(productos.values());
    if (pesajeEstado.filtro === 'pesables') {
        listaProductos = listaProductos.filter((p) => !pesajeProductoTieneIncompleto(p));
    } else if (pesajeEstado.filtro === 'incompletos') {
        listaProductos = listaProductos.filter((p) => pesajeProductoTieneIncompleto(p));
    }

    pesajeEmptyState.textContent = pesajeEstado.filtro === 'incompletos'
        ? 'No hay productos pesables con configuración incompleta.'
        : 'No se encontraron productos con estos filtros.';
    pesajeEmptyState.classList.toggle('hidden', listaProductos.length > 0);

    listaProductos.forEach((producto) => {
        pesajeList.appendChild(crearTarjetaResumenPesaje(producto));
    });

    // Si el modal de edicion esta abierto (ej. se acaba de completar el
    // ultimo perfil de un producto), refrescar su contenido con los datos
    // nuevos en vez de dejarlo desactualizado. Se busca en el mapa sin
    // filtrar: el producto puede haber cambiado de pestaña.
    if (pesajeModalProductoActualId != null) {
        const actualizado = productos.get(pesajeModalProductoActualId);
        if (actualizado) {
            renderizarModalPesaje(actualizado);
        } else {
            cerrarModalPesaje();
        }
    }
}

/** Formatea "medida + unidad" o "cantidad_detalle + unidad_detalle" para la
 * tarjeta resumen, sin decimales innecesarios (750 en vez de 750.00). */
function formatearMedidaPesaje(valor, unidad) {
    if (valor === null || valor === undefined || !unidad) return null;
    const numero = Number(valor);
    const texto = Number.isInteger(numero) ? String(numero) : numero.toFixed(2);
    return `${texto} ${unidad}`;
}

// Estilo unificado de botones de accion en PESAJE (tarjetas y ambos modales),
// tomado del boton EDITAR. Los callers agregan el ancho (flex-1 / w-full).
const PESAJE_BTN_CLASS = 'bg-surface border border-outline-variant text-on-surface py-sm px-md rounded-sharp text-[10px] font-label-mono uppercase tracking-widest hover:border-primary-fixed-dim hover:text-primary-fixed transition-colors flex items-center justify-center gap-xs';

function crearTarjetaResumenPesaje(producto) {
    const div = document.createElement('div');
    div.className = 'bg-surface-container border border-outline-variant rounded-md p-md shadow-lg transition-colors flex flex-col gap-xs';

    const medidaTxt = formatearMedidaPesaje(producto.medida, producto.nombre_unidad_medida);
    const detalleTxt = formatearMedidaPesaje(producto.volumen_oz, producto.nombre_unidad_medida_detalle);
    const perfilesReales = pesajePerfilesReales(producto);

    // Estado comandable: Sí/No. La BD guarda 'Si' (sin tilde) en
    // parameter_table (id_master=20); normalizamos a minúsculas y sin tilde
    // para no depender de la ortografía exacta del dato.
    const comandarRaw = (producto.nombre_ind_permite_comandar || '').trim().toLowerCase();
    const permiteComandar = comandarRaw === 'si' || comandarRaw === 'sí';
    const estadoComandable = permiteComandar ? 'Sí' : 'No';

    // CALCULAR (calculadora peso→onzas, ex-módulo CONVERSOR) solo aplica a
    // productos pesables con todos sus perfiles completos. En no pesables o
    // incompletos, la tarjeta muestra únicamente EDITAR.
    const puedeCalcular = producto.pesable === 1 && !pesajeProductoTieneIncompleto(producto);

    div.innerHTML = `
        <div class="text-[11px] text-on-surface-variant font-label-mono uppercase tracking-wider mb-xs flex items-center flex-wrap gap-xs">
            ${producto.nombre_categoria ? `<span>${escapeHtml(producto.nombre_categoria)}</span>` : ''}
            ${producto.nombre_categoria ? `<span class="border-l border-outline-variant pl-xs">ID: ${producto.id_producto}</span>` : `<span>ID: ${producto.id_producto}</span>`}
            <span class="border-l border-outline-variant pl-xs">COD ${escapeHtml(producto.codigo_producto)}</span>
        </div>
        <p class="text-sm font-semibold text-on-surface leading-tight mb-xs">${escapeHtml(producto.nombre_producto)}</p>
        <div class="flex flex-wrap gap-xs text-[10px] font-label-mono text-on-surface-variant mb-xs">
            ${medidaTxt ? `<span class="bg-surface-container-low px-xs py-[1px] rounded">${escapeHtml(medidaTxt)}</span>` : ''}
            ${detalleTxt ? `<span class="bg-surface-container-low px-xs py-[1px] rounded">${escapeHtml(detalleTxt)}</span>` : ''}
        </div>
        <div class="flex flex-wrap gap-xs items-center mb-sm">
            <span class="badge-info text-[9px] font-label-mono px-xs py-[1px] rounded uppercase tracking-widest">Comandable: ${estadoComandable}</span>
            ${perfilesReales.length > 1 ? `<span class="badge-info text-[9px] font-label-mono px-xs py-[1px] rounded uppercase tracking-widest">${perfilesReales.length} modelos</span>` : ''}
        </div>
        <div class="flex gap-xs mt-auto pt-xs border-t border-outline-variant">
            <button type="button" class="pesaje-btn-editar flex-1 ${PESAJE_BTN_CLASS}">
                <span class="material-symbols-outlined text-sm">edit</span>Editar
            </button>
            ${puedeCalcular ? `
            <button type="button" class="pesaje-btn-calcular flex-1 ${PESAJE_BTN_CLASS}">
                <span class="material-symbols-outlined text-sm">calculate</span>Calcular
            </button>` : ''}
        </div>
    `;

    const btnEditar = div.querySelector('.pesaje-btn-editar');
    if (btnEditar) btnEditar.addEventListener('click', () => abrirModalPesaje(producto));

    const btnCalcular = div.querySelector('.pesaje-btn-calcular');
    if (btnCalcular) btnCalcular.addEventListener('click', () => abrirCalculadoraDesdePesaje(producto));

    return div;
}

// ==========================================
// MODAL DE EDICION DE PESAJE: se abre al hacer click en una tarjeta resumen.
// Reutiliza crearFilaPerfilPesaje tal cual (mismos inputs/Guardar/Eliminar);
// solo cambia donde se monta (modal en vez de tarjeta inline).
// ==========================================
const pesajeModal          = document.getElementById('pesaje-modal');
const pesajeModalOverlay    = document.getElementById('pesaje-modal-overlay');
const btnClosePesajeModal   = document.getElementById('btn-close-pesaje-modal');
const pesajeModalCategoria  = document.getElementById('pesaje-modal-categoria');
const pesajeModalId         = document.getElementById('pesaje-modal-id');
const pesajeModalCodigo     = document.getElementById('pesaje-modal-codigo');
const pesajeModalNombre     = document.getElementById('pesaje-modal-nombre');
const pesajeModalMedidas    = document.getElementById('pesaje-modal-medidas');
const pesajeModalPerfiles   = document.getElementById('pesaje-modal-perfiles');

let pesajeModalProductoActualId = null;

function renderizarModalPesaje(producto) {
    if (!pesajeModalPerfiles) return;

    const medidaTxt = formatearMedidaPesaje(producto.medida, producto.nombre_unidad_medida);
    const detalleTxt = formatearMedidaPesaje(producto.volumen_oz, producto.nombre_unidad_medida_detalle);
    const medidasCompletas = [medidaTxt, detalleTxt].filter(Boolean).join(' | ');

    pesajeModalCategoria.textContent = producto.nombre_categoria || '';
    if (pesajeModalId) pesajeModalId.textContent = `ID: ${producto.id_producto}`;
    pesajeModalCodigo.textContent = `COD ${producto.codigo_producto}`;
    pesajeModalNombre.textContent = producto.nombre_producto;
    if (pesajeModalMedidas) pesajeModalMedidas.textContent = medidasCompletas;

    pesajeModalPerfiles.innerHTML = '';
    const perfilesReales = pesajePerfilesReales(producto);
    perfilesReales.forEach((perfil) => {
        pesajeModalPerfiles.appendChild(crearFilaPerfilPesaje(producto, perfil));
    });

    if (producto.pesable === 1 && perfilesReales.length === 0) {
        const aviso = document.createElement('div');
        aviso.className = 'border border-outline-variant rounded-md p-sm text-[11px] font-label-mono uppercase tracking-widest text-on-surface-variant';
        aviso.textContent = 'Sin modelos configurados. Agrega el primer modelo para este producto.';
        pesajeModalPerfiles.appendChild(aviso);
    }

    if (producto.pesable === 1) {
        const btnAgregar = document.createElement('button');
        btnAgregar.type = 'button';
        btnAgregar.className = `w-full mt-sm ${PESAJE_BTN_CLASS}`;
        btnAgregar.innerHTML = '<span class="material-symbols-outlined text-sm">add</span> Agregar modelo';
        btnAgregar.addEventListener('click', () => agregarModeloPesaje(producto));
        pesajeModalPerfiles.appendChild(btnAgregar);
    }
}

function abrirModalPesaje(producto) {
    if (!pesajeModal) return;
    pesajeModalProductoActualId = producto.id_producto;
    renderizarModalPesaje(producto);
    pesajeModal.classList.remove('hidden');
    pesajeModal.setAttribute('aria-hidden', 'false');
}

function cerrarModalPesaje() {
    if (!pesajeModal) return;
    pesajeModalProductoActualId = null;
    pesajeModal.classList.add('hidden');
    pesajeModal.setAttribute('aria-hidden', 'true');
}

if (btnClosePesajeModal) btnClosePesajeModal.addEventListener('click', cerrarModalPesaje);
if (pesajeModalOverlay) pesajeModalOverlay.addEventListener('click', cerrarModalPesaje);

function crearFilaPerfilPesaje(producto, perfil) {
    const row = document.createElement('div');

    const esPesable = producto.pesable === 1;
    const esVino = esCategoriaVinos(producto.id_categoria);
    const puedeEliminar = esPesable && producto.perfiles.length > 1;
    const esIncompleto = esPesable && (perfil.peso_bruto === null || perfil.tara === null || perfil.peso_bruto <= 0 || perfil.gramos_por_oz <= 0);

    row.className = esIncompleto
        ? 'border rounded-md p-sm space-y-xs'
        : 'border border-outline-variant rounded-md p-sm space-y-xs';
    if (esIncompleto) {
        row.style.borderColor = 'var(--semantic-warning)';
    }

    row.innerHTML = `
        ${esPesable ? `
        <p class="text-[11px] font-label-mono uppercase tracking-widest text-on-surface-variant flex items-center gap-xs">
            Modelo de Botella
        </p>
        <h4 class="text-sm font-semibold text-on-surface">
            ${perfil.nombre_perfil}
            ${esIncompleto ? `
            <span class="inline-flex items-center gap-[2px] normal-case tracking-normal text-xs ml-2" style="color: var(--semantic-warning);">
                <span class="material-symbols-outlined" style="font-size: 13px;">warning</span>
                Incompleto
            </span>
            ` : ''}
        </h4>
        ` : ''}
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-sm ${esPesable ? '' : 'hidden'}">
            <div>
                <label class="text-[10px] font-label-mono uppercase tracking-widest text-on-surface-variant block mb-xs">Peso bruto (${esVino ? 'copas' : 'g'})</label>
                <input type="number" min="0" step="0.01" class="pesaje-input-peso-bruto w-full bg-surface border border-outline-variant rounded-md px-md py-sm text-sm text-on-surface font-data-tabular" value="${perfil.peso_bruto ?? ''}">
            </div>
            <div>
                <label class="text-[10px] font-label-mono uppercase tracking-widest text-on-surface-variant block mb-xs">Tara (${esVino ? 'constante' : 'g'})</label>
                <input type="number" min="0" step="0.01" class="pesaje-input-tara w-full bg-surface border border-outline-variant rounded-md px-md py-sm text-sm text-on-surface font-data-tabular" value="${esVino ? 0 : (perfil.tara ?? '')}" ${esVino ? 'readonly' : ''}>
            </div>
            <div>
                <label class="text-[10px] font-label-mono uppercase tracking-widest text-on-surface-variant block mb-xs">gr/oz</label>
                <input type="text" readonly class="pesaje-input-gramos-oz w-full bg-surface-container border border-outline-variant rounded-md px-md py-sm text-sm text-on-surface-variant font-data-tabular cursor-not-allowed" value="${esVino ? 1 : (perfil.gramos_por_oz ?? '')}">
            </div>
        </div>
        <div>
            <label class="text-[10px] font-label-mono uppercase tracking-widest text-on-surface-variant block mb-xs">Código de barras</label>
            <input type="text" class="pesaje-input-barcode w-full bg-surface border border-outline-variant rounded-md px-md py-sm text-sm text-on-surface font-data-tabular" value="${perfil.barcode || ''}">
        </div>
        <p class="pesaje-error hidden text-xs text-error"></p>
        <div class="flex gap-xs justify-end pt-xs">
            <button type="button" class="pesaje-btn-guardar ${PESAJE_BTN_CLASS}">
                <span class="material-symbols-outlined text-sm">save</span>Guardar
            </button>
            ${puedeEliminar ? `<button type="button" class="pesaje-btn-eliminar ${PESAJE_BTN_CLASS}"><span class="material-symbols-outlined text-sm">delete</span>Eliminar</button>` : ''}
        </div>
    `;

    const errorEl        = row.querySelector('.pesaje-error');
    const btnGuardar      = row.querySelector('.pesaje-btn-guardar');
    const btnEliminar     = row.querySelector('.pesaje-btn-eliminar');
    const inputPesoBruto  = row.querySelector('.pesaje-input-peso-bruto');
    const inputTara       = row.querySelector('.pesaje-input-tara');
    const inputGramosOz   = row.querySelector('.pesaje-input-gramos-oz');
    const inputBarcode    = row.querySelector('.pesaje-input-barcode');

    if (esPesable && inputGramosOz) {
        const actualizarGramosOz = () => {
            const pesoBruto = parseFloat(inputPesoBruto.value);
            const tara = parseFloat(inputTara.value);
            if (esVino) {
                inputGramosOz.value = '1.000000';
                return;
            }
            if (!producto.volumen_oz || Number.isNaN(pesoBruto) || Number.isNaN(tara)) {
                inputGramosOz.value = '';
                return;
            }
            inputGramosOz.value = ((pesoBruto - tara) / producto.volumen_oz).toFixed(6);
        };
        inputPesoBruto.addEventListener('input', actualizarGramosOz);
        inputTara.addEventListener('input', actualizarGramosOz);
    }

    btnGuardar.addEventListener('click', async () => {
        errorEl.classList.add('hidden');
        const body = { barcode: inputBarcode.value.trim() || null };
        if (esPesable) {
            body.peso_bruto = parseFloat(inputPesoBruto.value);
            body.tara = esVino ? 0 : parseFloat(inputTara.value);
            if (Number.isNaN(body.peso_bruto) || Number.isNaN(body.tara)) {
                errorEl.textContent = 'Peso bruto y tara deben ser numéricos.';
                errorEl.classList.remove('hidden');
                return;
            }
            if (esVino && body.tara !== 0) {
                errorEl.textContent = 'En categoría VINOS la tara debe ser 0.';
                errorEl.classList.remove('hidden');
                return;
            }
        }

        const textoOriginalGuardar = btnGuardar.innerHTML;
        btnGuardar.disabled = true;
        btnGuardar.setAttribute('aria-busy', 'true');
        btnGuardar.innerHTML = `${renderCriticalIcon('refresh', 'ui-icon animate-spin-ccw')} Guardando...`;

        try {
            const response = await fetchAutenticado(`${API_BASE}/pesaje/config/${perfil.id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });
            const data = await response.json();
            if (!response.ok) {
                errorEl.textContent = data.detail || 'No se pudo guardar.';
                errorEl.classList.remove('hidden');
                await mostrarDialogoResultado({
                    tipo: 'error',
                    titulo: 'No se pudo guardar',
                    mensaje: data.detail || 'Ocurrió un error al guardar el modelo.',
                });
                return;
            }
            await cargarPesaje();
            await mostrarDialogoResultado({
                tipo: 'success',
                titulo: 'Modelo guardado',
                mensaje: `Se guardaron los cambios de "${perfil.nombre_perfil}" correctamente.`,
            });
        } catch (error) {
            if (error instanceof SesionExpiradaError) return;
            errorEl.textContent = 'Error de red al guardar.';
            errorEl.classList.remove('hidden');
            await mostrarDialogoResultado({
                tipo: 'error',
                titulo: 'Error de red',
                mensaje: 'No se pudo conectar con el servidor para guardar los cambios.',
            });
        } finally {
            // Si el guardado fue exitoso, cargarPesaje() ya recreó esta fila
            // (btnGuardar quedó desprendido); restaurar aquí es inocuo. En los
            // caminos de error, restaura el botón para permitir reintentar.
            btnGuardar.disabled = false;
            btnGuardar.removeAttribute('aria-busy');
            btnGuardar.innerHTML = textoOriginalGuardar;
        }
    });

    if (btnEliminar) {
        btnEliminar.addEventListener('click', async () => {
            const confirmado = await mostrarDialogoConfirmacion({
                titulo: 'Eliminar modelo',
                mensaje: `¿Eliminar el modelo "${perfil.nombre_perfil}"?`
            });
            if (!confirmado) return;

            try {
                const response = await fetchAutenticado(`${API_BASE}/pesaje/config/${perfil.id}`, {
                    method: 'DELETE'
                });
                const data = await response.json();
                if (!response.ok) {
                    errorEl.textContent = data.detail || 'No se pudo eliminar.';
                    errorEl.classList.remove('hidden');
                    return;
                }
                await cargarPesaje();
            } catch (error) {
                if (error instanceof SesionExpiradaError) return;
                errorEl.textContent = 'Error de red al eliminar.';
                errorEl.classList.remove('hidden');
            }
        });
    }

    return row;
}

async function agregarModeloPesaje(producto) {
    const perfilesReales = pesajePerfilesReales(producto);
    const perfilBase = perfilesReales[0] || null;
    const datos = await abrirModalModelo(
        producto.nombre_producto,
        perfilBase,
        producto.volumen_oz,
        perfilesReales.length === 0,
        esCategoriaVinos(producto.id_categoria)
    );
    if (!datos) return; // usuario canceló

    try {
        const response = await fetchAutenticado(`${API_BASE}/pesaje/perfiles`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                id_producto: producto.id_producto,
                nombre_perfil: datos.nombre,
                peso_bruto: datos.pesoBruto,
                tara: datos.tara,
                barcode: datos.barcode
            })
        });

        const data = await response.json();
        if (!response.ok) {
            mbError.textContent = `No se pudo crear el modelo: ${data.detail || 'Error desconocido'}`;
            mbError.classList.remove('hidden');
            modeloBotellaDialog.classList.remove('hidden');
            return;
        }

        await cargarPesaje();
    } catch (error) {
        if (error instanceof SesionExpiradaError) return;
        mbError.textContent = 'Error de red al crear el modelo de botella.';
        mbError.classList.remove('hidden');
        modeloBotellaDialog.classList.remove('hidden');
    }
}

let pesajeBusquedaTimeout = null;
function filtrarPesaje(query) {
    pesajeEstado.nombre = query.trim();
    clearTimeout(pesajeBusquedaTimeout);
    pesajeBusquedaTimeout = setTimeout(() => {
        cargarPesaje();
    }, 350);
}

if (pesajeCategoriaSel) {
    pesajeCategoriaSel.addEventListener('change', () => {
        pesajeEstado.idCategoria = pesajeCategoriaSel.value;
        cargarPesaje();
    });
}

if (pesajeFiltroPesablesBtn) {
    pesajeFiltroPesablesBtn.addEventListener('click', () => {
        pesajeEstado.filtro = 'pesables';
        cargarPesaje();
    });
}

if (pesajeFiltroIncompletosBtn) {
    pesajeFiltroIncompletosBtn.addEventListener('click', () => {
        pesajeEstado.filtro = 'incompletos';
        cargarPesaje();
    });
}

if (pesajeFiltroNoPesablesBtn) {
    pesajeFiltroNoPesablesBtn.addEventListener('click', () => {
        pesajeEstado.filtro = 'no_pesables';
        cargarPesaje();
    });
}

// ==========================================
// CALCULADORA PESO -> ONZAS (ex-módulo CONVERSOR, ahora integrada en las
// tarjetas de PESAJE vía el botón CALCULAR). Sin estado de operativa ni
// persistencia; calcula todo en cliente reutilizando redondearOnzasOperativas()
// y resolverPerfilSeleccionado(). El listado/tab independiente se eliminó: los
// datos vienen del producto ya cargado en la tarjeta de PESAJE.
// ==========================================

const conversorModal            = document.getElementById('conversor-modal');
const conversorModalOverlay     = document.getElementById('conversor-modal-overlay');
const btnCloseConversorModal    = document.getElementById('btn-close-conversor-modal');
const conversorProductoNombre   = document.getElementById('conversor-producto-nombre');
const conversorProductoCodigo   = document.getElementById('conversor-producto-codigo');
const conversorBotellasContainer = document.getElementById('conversor-botellas-container');
const conversorBtnAgregar       = document.getElementById('conversor-btn-agregar');
const conversorTotalExacto      = document.getElementById('conversor-total-exacto');
const conversorTotalRedondeado  = document.getElementById('conversor-total-redondeado');

let conversorProductoActual = null;

/** Abre la calculadora desde una tarjeta de PESAJE. Adapta la forma del
 * producto de pesaje (nombre_producto/codigo_producto + perfiles con
 * peso_bruto/tara/gramos_por_oz) a la que espera el modal de la calculadora,
 * descartando perfiles incompletos (sin tara o sin gr/oz no se puede convertir). */
function abrirCalculadoraDesdePesaje(producto) {
    const perfilesCompletos = (producto.perfiles || []).filter(
        (pf) => pf.tara !== null && pf.tara !== undefined &&
                pf.gramos_por_oz !== null && pf.gramos_por_oz !== undefined
    );
    if (perfilesCompletos.length === 0) return;

    seleccionarProductoConversor({
        id_producto: producto.id_producto,
        nombre: producto.nombre_producto,
        codigo: producto.codigo_producto,
        perfiles: perfilesCompletos.map((pf) => ({
            id: pf.id,
            nombre_perfil: pf.nombre_perfil,
            peso_bruto: pf.peso_bruto,
            tara: pf.tara,
            gramos_por_oz: pf.gramos_por_oz,
        })),
    });
}

function seleccionarProductoConversor(producto) {
    conversorProductoActual = producto;
    conversorProductoNombre.textContent = producto.nombre;
    conversorProductoCodigo.textContent = producto.codigo;
    conversorBotellasContainer.innerHTML = '';
    agregarBotellaConversor();
    abrirModalConversor();
}

function abrirModalConversor() {
    if (!conversorModal) return;
    conversorModal.classList.remove('hidden');
    conversorModal.setAttribute('aria-hidden', 'false');
}

function cerrarModalConversor() {
    if (!conversorModal) return;
    conversorModal.classList.add('hidden');
    conversorModal.setAttribute('aria-hidden', 'true');
    limpiarConversor();
}

function crearFilaBotellaConversor(perfiles) {
    const wrapper = document.createElement('div');
    wrapper.className = 'relative flex items-center item-peso-wrapper gap-sm';

    let selectHTML = '';
    if (perfiles.length > 1) {
        selectHTML = `<select class="bg-surface-container-low text-data-tabular text-primary-fixed border border-outline-variant rounded-md px-sm py-xs focus:outline-none select-perfil mr-sm cursor-pointer font-semibold">`;
        selectHTML += perfiles.map((pf, idx) =>
            `<option value="${pf.id != null ? pf.id : idx}">${escapeHtml(pf.nombre_perfil)}</option>`
        ).join('');
        selectHTML += `</select>`;
    }

    wrapper.innerHTML = `
        ${selectHTML}
        <div class="relative flex-1">
            <input type="number" min="0" step="1" class="w-full bg-surface border border-outline-variant rounded-md pl-md pr-lg py-sm text-on-surface input-peso focus:border-primary-fixed-dim focus:outline-none focus:shadow-cyan-glow-focus font-data-tabular" placeholder="Peso en gramos">
            <button type="button" class="btn-remove-peso absolute right-sm top-1/2 -translate-y-1/2 text-on-surface-variant hover:text-error transition-colors" aria-label="Eliminar botella">
                ${renderCriticalIcon('close', 'ui-icon ui-icon-sm')}
            </button>
        </div>
        <span class="conversor-fila-onzas shrink-0 text-[11px] text-secondary-fixed font-data-tabular w-16 text-right">0 oz</span>
    `;

    wrapper.querySelector('.input-peso').addEventListener('input', recalcularConversor);
    const select = wrapper.querySelector('.select-perfil');
    if (select) select.addEventListener('change', recalcularConversor);
    wrapper.querySelector('.btn-remove-peso').addEventListener('click', () => {
        wrapper.remove();
        recalcularConversor();
    });

    return wrapper;
}

function agregarBotellaConversor() {
    if (!conversorProductoActual) return;
    const fila = crearFilaBotellaConversor(conversorProductoActual.perfiles);
    conversorBotellasContainer.appendChild(fila);
    recalcularConversor();
}

function recalcularConversor() {
    if (!conversorProductoActual) return;
    const perfiles = conversorProductoActual.perfiles;
    let totalExacto = 0;

    conversorBotellasContainer.querySelectorAll('.item-peso-wrapper').forEach((wrapper) => {
        const inputPeso = wrapper.querySelector('.input-peso');
        const select = wrapper.querySelector('.select-perfil');
        const spanOnzas = wrapper.querySelector('.conversor-fila-onzas');

        const { perfil } = resolverPerfilSeleccionado(perfiles, select);
        const peso = parseFloat(inputPeso.value);
        let onzas = 0;

        if (perfil && !Number.isNaN(peso) && peso >= 0) {
            const pesoLiquido = Math.max(0, peso - perfil.tara);
            onzas = pesoLiquido / perfil.gramos_por_oz;
        }

        spanOnzas.textContent = `${onzas.toFixed(2)} oz`;
        totalExacto += onzas;
    });

    conversorTotalExacto.textContent = totalExacto.toFixed(2);
    conversorTotalRedondeado.textContent = (redondearOnzasOperativas(totalExacto) ?? 0).toFixed(1);
}

function limpiarConversor() {
    conversorProductoActual = null;
    conversorBotellasContainer.innerHTML = '';
    conversorTotalExacto.textContent = '0';
    conversorTotalRedondeado.textContent = '0';
}

if (conversorBtnAgregar) {
    conversorBtnAgregar.addEventListener('click', agregarBotellaConversor);
}

if (conversorModalOverlay) {
    conversorModalOverlay.addEventListener('click', cerrarModalConversor);
}

if (btnCloseConversorModal) {
    btnCloseConversorModal.addEventListener('click', cerrarModalConversor);
}

document.addEventListener('DOMContentLoaded', () => {
    if (currentToken && tokenExpirado(currentToken)) {
        // Token vencido de una sesión anterior: directo al login, sin flash de app.
        cerrarSesion();
    } else if (currentToken) {
        mostrarPantallaApp();
    } else {
        mostrarPantallaLogin();
    }

    inicializarFabScrollTop('pesaje-fab-scroll-top', 'panel-pesaje');
    inicializarFabScrollTop('inventario-fab-scroll-top', 'panel-inventario');
    inicializarFabScrollTop('stock-fab-scroll-top', 'panel-stock');
    inicializarFabScrollTop('scan-fab-scroll-top', 'panel-scan');

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

    if (btnTopbarMenu && topbarMenuDropdown) {
        btnTopbarMenu.addEventListener('click', (event) => {
            event.stopPropagation();
            alternarMenuFlotanteTopbar();
        });

        topbarMenuDropdown.addEventListener('click', (event) => {
            const tabTrigger = event.target.closest('[data-tab]');
            if (tabTrigger) {
                cerrarMenuFlotanteTopbar();
                return;
            }

            const trigger = event.target.closest('[data-dummy-link]');
            if (!trigger) return;

            cerrarMenuFlotanteTopbar();
            abrirContenidoDummy(trigger.dataset.dummyLink);
        });

        document.addEventListener('click', (event) => {
            if (!event.target.closest('.floating-menu-container')) {
                cerrarMenuFlotanteTopbar();
            }
        });
    }

    if (dummyContentOverlay) {
        dummyContentOverlay.addEventListener('click', cerrarContenidoDummy);
    }

    if (btnCloseDummyContent) {
        btnCloseDummyContent.addEventListener('click', cerrarContenidoDummy);
    }

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            cerrarMenuFlotanteTopbar();
            cerrarContenidoDummy();
            cerrarModalConversor();
        }
    });

    if (barraSelector) {
        barraSelector.addEventListener('change', () => {
            const siguienteBarra = parseInt(barraSelector.value || '', 10);
            if (Number.isNaN(siguienteBarra) || siguienteBarra <= 0) return;
            if (!configuracionPaloteo.allowedBarras.includes(siguienteBarra)) return;

            idBarraActual = siguienteBarra;
            localStorage.setItem('paloteo_barra_id', String(idBarraActual));

            if (currentToken) {
                iniciarDashboard();
            }
        });
    }
});

// ==========================================
// AUTENTICACIÓN Y NAVEGACIÓN
// ==========================================

/** La sesión ya se cerró (token vencido o 401): los catch deben abortar en silencio. */
class SesionExpiradaError extends Error {
    constructor() {
        super('Sesión expirada');
        this.name = 'SesionExpiradaError';
    }
}

/** Lee el claim exp del JWT sin validar firma (solo para UX de expiración;
 * la validación real siempre la hace el backend). */
function tokenExpirado(token) {
    try {
        const payloadB64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
        const payload = JSON.parse(atob(payloadB64));
        if (!payload.exp) return false;
        // Margen de 30s para no disparar requests con un token a punto de vencer.
        return payload.exp * 1000 <= Date.now() + 30000;
    } catch (error) {
        return true; // Token ilegible: tratarlo como vencido.
    }
}

/** fetch con Authorization y manejo centralizado de sesión expirada.
 * Si no hay token vigente o el backend responde 401, cierra la sesión y lanza
 * SesionExpiradaError para que el caller aborte su flujo sin mostrar errores. */
async function fetchAutenticado(url, options = {}) {
    if (!currentToken || tokenExpirado(currentToken)) {
        cerrarSesion();
        throw new SesionExpiradaError();
    }
    const headers = { ...(options.headers || {}), 'Authorization': `Bearer ${currentToken}` };
    const response = await fetch(url, { ...options, headers });
    if (response.status === 401) {
        cerrarSesion();
        throw new SesionExpiradaError();
    }
    return response;
}

function cerrarSesion() {
    cerrarMenuFlotanteTopbar();
    localStorage.removeItem('token');
    localStorage.removeItem('nombres');
    localStorage.removeItem('is_admin');
    currentToken = null;
    mostrarPantallaLogin();
}

loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const usuario = document.getElementById('username').value.trim();
    const contrasena = document.getElementById('password').value;
    const btnLogin = document.getElementById('btn-login');

    // Estado de carga: mismo spinner de flechas girando que usa PESAJE.
    const textoOriginalLogin = btnLogin.innerHTML;
    btnLogin.disabled = true;
    btnLogin.setAttribute('aria-busy', 'true');
    btnLogin.innerHTML = `${renderCriticalIcon('refresh', 'ui-icon animate-spin-ccw')} Ingresando...`;

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
            localStorage.setItem('is_admin', data.is_admin ? '1' : '0');
            mostrarPantallaApp();
        } else {
            // Mismo modal de resultado que usa el resto de la PWA. Sin await:
            // el finally restaura el botón mientras el modal sigue visible.
            const detalle = typeof data.detail === 'string' ? data.detail : 'Error al iniciar sesión.';
            mostrarDialogoResultado({ tipo: 'error', titulo: 'No se pudo iniciar sesión', mensaje: detalle });
        }
    } catch (error) {
        mostrarDialogoResultado({
            tipo: 'error',
            titulo: 'Error de red',
            mensaje: 'No se pudo conectar con el servidor. Revisa tu conexión e intenta de nuevo.'
        });
    } finally {
        btnLogin.disabled = false;
        btnLogin.removeAttribute('aria-busy');
        btnLogin.innerHTML = textoOriginalLogin;
    }
});

btnLogout.addEventListener('click', cerrarSesion);

function esUsuarioAdministrador() {
    return localStorage.getItem('is_admin') === '1';
}

function mostrarPantallaLogin() {
    loginScreen.classList.remove('hidden');
    appScreen.classList.add('hidden');
    document.getElementById('password').value = '';
}

function actualizarVistaInicialInventario() {
    if (!inventarioCapturaContenido) return;
    inventarioCapturaContenido.classList.toggle('hidden', vistaInicialSoloOperativa);
}

async function mostrarPantallaApp() {
    loginScreen.classList.add('hidden');
    appScreen.classList.remove('hidden');
    document.getElementById('user-display').textContent = localStorage.getItem('nombres');
    const menuItemPesaje = document.getElementById('menu-item-pesaje');
    if (menuItemPesaje) menuItemPesaje.classList.toggle('hidden', !esUsuarioAdministrador());
    await cargarConfiguracionPublica();
    // Asegurar que el panel de inventario sea el visible al entrar a la app
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.add('hidden'));
    document.getElementById('panel-inventario').classList.remove('hidden');
    vistaInicialSoloOperativa = true;
    actualizarVistaInicialInventario();
    iniciarDashboard();
}

// ==========================================
// LÓGICA DE NEGOCIO (DASHBOARD)
// ==========================================
async function iniciarDashboard() {
    listaProductos.innerHTML = ''; // Limpiar lista
    productosInventario = [];
    vistaInicialSoloOperativa = true;
    actualizarVistaInicialInventario();
    operativaPermitePaloteo = false;
    stopAutosaveInterval();
    _actualizarEstadoAutosave('idle', 'Autosave inactivo: esperando operativa en INICIO CIERRE.');
    resetModoCaptura();
    modoEnvioOrigen = 'inventario';
    _deshabilitarBtnEnvio();
    ocultarBannerSoloLectura();
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
        const responseOp = await fetchAutenticado(`${API_BASE}/operacion/activa`);
        
        const dataOp = await responseOp.json();

        if (!responseOp.ok) {
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

            estadoTexto.textContent = `${detail.mensaje || "Debes iniciar el cierre de la operativa para realizar el paloteo"} Puedes consultar el último paloteo registrado, pero no editarlo.`;
            _actualizarEstadoAutosave('idle', 'Autosave bloqueado: operativa fuera de INICIO CIERRE.');

            // Modo solo lectura: dejamos los módulos accesibles para consultar
            // el último paloteo registrado, sin permitir registrar ni corregir nada.
            currentOperacionId = detail.id_operacion || null;
            currentEstadoOperacion = detail.estado_operacion ?? null;
            operativaPermitePaloteo = false;
            currentIdInventarioPOS = null;
            ocultarBannerCorreccion();
            mostrarBannerSoloLectura();
            actualizarPanelAjustes();

            if (currentOperacionId) {
                cargarProductos();
            } else {
                listaProductos.innerHTML = `<div class="text-center text-on-surface-variant py-lg font-body-base">No hay datos de paloteo para consultar.</div>`;
            }
            return;
        }

        // Luz Verde: Guardamos el ID de operación (estado 24)
        currentOperacionId = dataOp.id_operacion;
        currentEstadoOperacion = dataOp.estado_operacion ?? null;
        operativaPermitePaloteo = true;
        currentIdInventarioPOS = null; // Resetear el ID de inventario previo para nueva operativa
        ocultarBannerCorreccion(); // Ocultar banner de corrección hasta confirmar si hay inventario
        ocultarBannerSoloLectura();
        actualizarPanelAjustes();
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
        if (error instanceof SesionExpiradaError) return;
        estadoTexto.textContent = "Error de conexión con el servidor.";
    }
}

async function cargarProductos() {
    try {
        const response = await fetchAutenticado(`${API_BASE}/inventario/pendientes`, {
            headers: { 'X-Barra-Id': String(idBarraActual) }
        });

        const productos = await response.json();

        if (response.ok && productos.length > 0) {
            productosInventario = productos;
            renderizarProductos(productos);
            _habilitarBtnEnvio();
            
            // NUEVO: Mostrar resumen de productos (total, pesables, no pesables)
            actualizarResumenProductos(productos);

            // NUEVO: Verificar si ya existe inventario registrado y pre-cargar valores
            await cargarInventarioExistente();

            // Recuperar borrador local (si existe) sobre la base oficial del backend.
            hydrateAutosaveDraft();

            // Renderizar PALOTEO 3 después de cargar datos existentes para mantener un solo origen de datos
            renderizarPaloteo3(productos);
            startAutosaveInterval();
            actualizarResumenProgresoInventario();
            enfocarPrimerCampoInventario();
        } else {
            productosInventario = [];
            listaProductos.innerHTML = `<div class="text-center text-on-surface-variant py-lg font-body-base">No hay productos consumidos para auditar hoy.</div>`;
            mostrarEstadoVacioPaloteo3();
            ocultarResumenProductos();
            actualizarResumenProgresoInventario();
        }
    } catch (error) {
        if (error instanceof SesionExpiradaError) return;
        console.error("Error cargando productos", error);
        mostrarEstadoVacioPaloteo3();
        ocultarResumenProductos();
        _actualizarEstadoAutosave('error', 'Autosave en espera por fallo de carga de productos.');
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

// Los tres botones de registro (PALOTEO 1/2/3) se habilitan/deshabilitan de
// forma identica, solo con el atributo disabled (el estilo de disabled/
// habilitado vive en las clases base disabled:opacity-50/disabled:cursor-not-allowed
// del HTML, compartidas por los tres). Antes btnGuardar recibia ademas un
// set de clases propio (text-primary-fixed/glow-cyan-intense) que lo hacia
// verse distinto a stockBtnGuardar/capturaBtnFinalizar.
function _habilitarBtnEnvio() {
    if (!operativaPermitePaloteo) {
        _deshabilitarBtnEnvio();
        return;
    }

    btnGuardar.disabled = false;
    if (btnEnviarInventario) btnEnviarInventario.disabled = false;
    if (stockBtnGuardar) stockBtnGuardar.disabled = false;
    if (capturaBtnFinalizar) capturaBtnFinalizar.disabled = false;
}

function _deshabilitarBtnEnvio() {
    btnGuardar.disabled = true;
    if (btnEnviarInventario) btnEnviarInventario.disabled = true;
    if (stockBtnGuardar) stockBtnGuardar.disabled = true;
    if (capturaBtnFinalizar) capturaBtnFinalizar.disabled = true;
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
        const response = await fetchAutenticado(`${API_BASE}/inventario/paloteo/${currentOperacionId}`);
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
        if (error instanceof SesionExpiradaError) return;
        console.error("Error verificando inventario existente:", error);
    }
}

/**
 * Pre-llena los inputs de cada tarjeta con los valores ya almacenados en la BD.
 * Prioriza restaurar los pesos crudos capturados para no reconstruir gramos desde
 * onzas ya redondeadas. Solo usa el peso estimado como compatibilidad retroactiva.
 */
function preLlenarInventario(detalles) {
    detalles.forEach(detalle => {
        const card = document.querySelector(`#lista-productos .product-card[data-id="${detalle.id_producto}"]`);
        if (!card) return;

        let pesosRestaurados = [];
        if (parseInt(card.dataset.pesable, 10) === 1) {
            pesosRestaurados = Array.isArray(detalle.pesos_abiertas)
                ? detalle.pesos_abiertas
                    .filter((entrada) => entrada && entrada.peso != null)
                    .map((entrada) => ({
                        peso: entrada.peso,
                        perfilValue: entrada.perfil_id != null ? String(entrada.perfil_id) : String(entrada.perfil_index ?? 0),
                    }))
                : [];

            if (pesosRestaurados.length === 0 && detalle.onzas_pos > 0) {
                const perfiles = JSON.parse(card.dataset.perfiles || '[]');
                if (perfiles.length > 0) {
                    const perfil = perfiles[0];
                    const tara = parseFloat(perfil.tara) || 0;
                    const gramsPorOz = parseFloat(perfil.gramos_por_oz) || 0;
                    if (gramsPorOz > 0) {
                        pesosRestaurados = [{
                            peso: ((detalle.onzas_pos * gramsPorOz) + tara).toFixed(1),
                            perfilValue: (perfil.id != null) ? String(perfil.id) : '0',
                        }];
                    }
                }
            }
        }

        aplicarValoresCard(card, {
            cerradas: detalle.botellas_cerradas || 0,
            pesos: pesosRestaurados,
        });
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

function mostrarBannerSoloLectura() {
    const banner = document.getElementById('banner-solo-lectura');
    if (!banner) return;

    const estabaOculto = banner.classList.contains('hidden');
    banner.classList.remove('hidden');

    if (estabaOculto) {
        mostrarDialogoResultado({
            tipo: 'warning',
            titulo: 'Modo Lectura',
            mensaje: 'Estás viendo el último paloteo registrado. No se pueden hacer cambios mientras la operativa no esté en estado de cierre.',
        });
    }
}

function ocultarBannerSoloLectura() {
    const banner = document.getElementById('banner-solo-lectura');
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
    const esVino = esCategoriaVinos(p.id_categoria);
    const unidadDetalle = etiquetaDetalleCorta(p.id_categoria);

    const div = document.createElement('div');
    div.className = "bg-surface-container border border-outline-variant rounded-md p-md shadow-lg product-card transition-colors focus-within:border-primary-fixed-dim chassis-panel";
    div.dataset.scope = scope;
    div.dataset.id = p.id_producto;
    div.dataset.codigo = p.codigo || '';
    div.dataset.search = `${p.id_producto || ''} ${p.codigo || ''} ${p.nombre || ''}`.toLowerCase();
    div.dataset.idCategoria = p.id_categoria || '';
    div.dataset.pesable = p.pesable || 0;
    div.dataset.nombre = p.nombre;
    div.dataset.categoria = p.categoria_nombre || '';
    div.dataset.esVino = esVino ? '1' : '0';
    const perfilesJson = JSON.stringify(p.perfiles || []);
    const perfilBase = (p.perfiles && p.perfiles.length > 0) ? p.perfiles[0] : null;
    div.dataset.perfiles = perfilesJson;
    div.dataset.tolerancia = String(perfilBase ? (parseFloat(perfilBase.tolerancia_oz) || 0) : 0);
    div.dataset.paqsist = parseFloat(p.stock_ideal_unidades) || 0;
    div.dataset.detsist = parseFloat(p.stock_ideal_onzas) || 0;
    div.dataset.onzasMax = parseFloat(p.onzas_por_botella_llena) || 0;

    let html = `
        <div class="id-codigo-row text-[11px] text-outline mb-xs flex items-center flex-wrap gap-xs">
            ${p.categoria_nombre ? `<span class="font-label-mono uppercase tracking-[0.08em] text-outline">${escapeHtml(p.categoria_nombre)}</span><span class="border-l border-outline-variant pl-xs">ID: ${p.id_producto}</span>` : `<span>ID: ${p.id_producto}</span>`}
            <span class="border-l border-outline-variant pl-xs">COD: ${escapeHtml(p.codigo)}</span>
            ${p._agregadoManual ? `<span class="badge-info text-[9px] font-label-mono uppercase tracking-widest px-xs py-[1px] rounded ml-auto">Sin movimiento</span>` : ''}
        </div>
        <h4 class="text-primary-fixed font-headline-md text-lg mb-md neon-text-primary">${escapeHtml(p.nombre)}</h4>

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
                        <span class="w-20 text-right">${parseFloat(p.stock_ideal_onzas).toFixed(2)} ${unidadDetalle}</span>
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
                        <span class="w-20 text-right"><span id="val-det-${sufijoScope}">0.00</span> ${unidadDetalle}</span>
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
                <input type="number" min="0" class="w-full bg-surface border border-outline-variant rounded-md px-md py-sm text-on-surface input-cerradas focus:border-primary-fixed-dim focus:outline-none focus:shadow-cyan-glow-focus font-data-tabular" placeholder="0"${!operativaPermitePaloteo ? ' disabled' : ''}>
            </div>

            ${p.pesable === 1 ? `
            <div class="border-t border-outline-variant pt-md sm:border-t-0 sm:border-l sm:pt-0 sm:pl-md">
                <label class="block text-label-mono font-label-mono text-on-surface-variant mb-xs tracking-widest uppercase">${esVino ? 'Copas' : 'Peso'}</label>
                <div class="pesos-container grid grid-cols-1 gap-sm" id="${pesosContainerId}">
                    ${crearInputPeso(perfilesJson, false, esVino)}
                </div>
                <div class="mt-sm flex flex-wrap gap-sm">
                    <button type="button" data-id-producto="${p.id_producto}" class="${btnAddPesoClass} btn-action w-full sm:w-auto text-label-mono font-semibold flex items-center justify-center sm:justify-start gap-xs transition-colors uppercase tracking-widest rounded-sharp border px-sm py-xs"${!operativaPermitePaloteo ? ' disabled' : ''}>
                        + Botella
                    </button>
                </div>
            </div>` : ''}
        </div>
    `;

    div.innerHTML = html;

    if (p._agregadoManual) {
        div.classList.add('card-agregado-manual');
        if (esCaptura) {
            // El header de navegacion Prev/Sigt de PALOTEO 2 ocupa la esquina
            // superior; el boton de quitar va inline junto a ID/Codigo en vez
            // de superpuesto arriba (variante 'absoluta').
            const filaIdCodigo = div.querySelector('.id-codigo-row');
            if (filaIdCodigo) filaIdCodigo.appendChild(crearBotonQuitarManual(p, 'inline'));
        } else {
            div.classList.add('relative');
            div.appendChild(crearBotonQuitarManual(p, 'absoluta'));
        }
    }

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
    actualizarResumenProgresoPaloteo3();
}

function crearFilaPaloteo3(producto) {
    const row = document.createElement('div');
    row.className = 'stock-row grid gap-xs px-sm py-sm items-start sm:items-center hover:bg-surface-container-highest transition-colors';
    // Responsive: apilado en móvil (1 col), grid 4 cols en desktop (sm+)
    row.style.gridTemplateColumns = '1fr';
    row.classList.add('sm:gap-xs');

    // Aplicar grid desktop con media query inline para mejor compatibilidad
    row.setAttribute('data-mobile-stack', 'true');

    row.dataset.idProducto = String(producto.id_producto || '');
    // dataset.id se mantiene en sincronía con idProducto para reutilizar
    // leerValoresCard/aplicarValoresCard/recalcularTarjeta sin duplicar lógica.
    row.dataset.id = String(producto.id_producto || '');
    row.dataset.search = `${producto.id_producto || ''} ${producto.codigo || ''} ${producto.nombre || ''}`.toLowerCase();
    row.dataset.codigo = String(producto.codigo || '—');
    row.dataset.nombre = String(producto.nombre || '');
    row.dataset.idCategoria = String(producto.id_categoria || '');

    const perfiles = Array.isArray(producto.perfiles) ? producto.perfiles : [];
    const perfilBase = perfiles.length > 0 ? perfiles[0] : null;
    const idealUnidades = parseFloat(producto.stock_ideal_unidades) || 0;
    const esPesable = parseInt(producto.pesable, 10) === 1;
    const esVino = esCategoriaVinos(producto.id_categoria);
    const toleranciaOz = perfilBase ? (parseFloat(perfilBase.tolerancia_oz) || 0) : 0;
    const perfilesJson = JSON.stringify(perfiles);

    row.dataset.idealUnidades = String(idealUnidades);
    row.dataset.categoria = String(producto.categoria_nombre || '');
    row.dataset.pesable = esPesable ? '1' : '0';
    row.dataset.esVino = esVino ? '1' : '0';
    row.dataset.tolerancia = String(toleranciaOz);
    row.dataset.perfiles = perfilesJson;
    row.dataset.paqsist = String(idealUnidades);
    row.dataset.detsist = String(parseFloat(producto.stock_ideal_onzas) || 0);

    const soloLecturaFila = !operativaPermitePaloteo;
    const claseBotonAjusteUnidades = (esUsuarioAdministrador() && !soloLecturaFila) ? '' : ' hidden';
    const disabledAttrFila = soloLecturaFila ? ' disabled' : '';

    row.innerHTML = `
        <div class="contents">
            <!-- Primera línea: código + nombre (ancho completo) -->
            <div class="col-span-full flex items-center gap-xs min-h-10">
                <span class="text-data-tabular text-on-surface text-right text-xs font-semibold bg-surface-container-low px-xs py-[2px] rounded min-w-max" title="${escapeHtml(String(producto.codigo ?? ''))}">${escapeHtml(String(producto.codigo ?? '—'))}</span>
                <span class="text-xs text-on-surface truncate" title="${escapeHtml(producto.nombre || '')}">${escapeHtml(producto.nombre || '')}</span>
                ${producto._agregadoManual ? `<span class="badge-info text-[9px] font-label-mono uppercase tracking-widest px-xs py-[1px] rounded shrink-0 ml-auto">Sin movimiento</span>` : ''}
            </div>

            <!-- Segunda línea: input de unidades y, si aplica, pesos con botones integrados -->
            <div class="col-span-full flex flex-wrap gap-sm text-xs">
                <!-- Unidades con botones +/- (solo administradores) -->
                <div class="flex items-center gap-1">
                    <span class="material-symbols-outlined text-on-surface-variant" style="font-size:1.4rem;" title="Unidades">123</span>
                    <input type="number" min="0" step="1" class="input-cerradas stock-input-unidades w-14 text-center bg-surface border border-outline-variant rounded px-1 py-1 text-on-surface focus:border-primary-fixed-dim focus:outline-none focus:shadow-cyan-glow-focus transition-colors" placeholder="0"${disabledAttrFila}>
                    <button type="button" class="stock-btn-dec-unid${claseBotonAjusteUnidades} flex-none px-1.5 py-1 bg-surface border border-outline-variant rounded flex items-center justify-center text-on-surface hover:bg-surface-container-highest active:bg-surface-container-highest transition-colors font-semibold leading-none" title="Restar"${disabledAttrFila}>−</button>
                    <button type="button" class="stock-btn-inc-unid${claseBotonAjusteUnidades} flex-none px-1.5 py-1 bg-surface border border-outline-variant rounded flex items-center justify-center text-on-surface hover:bg-surface-container-highest active:bg-surface-container-highest transition-colors font-semibold leading-none" title="Sumar"${disabledAttrFila}>+</button>
                </div>

                ${esPesable ? `
                <!-- Pesos (una o más botellas abiertas) con botones +/- y selector de perfil si aplica -->
                <div class="flex items-center gap-1">
                    <span class="material-symbols-outlined text-on-surface-variant" style="font-size:1.1rem;" title="${esVino ? 'Copas' : 'Peso'}">balance</span>
                    <div class="pesos-container flex flex-col gap-1" id="stock-pesos-${producto.id_producto}">
                        ${crearInputPesoCompacto(perfilesJson, false, esVino)}
                    </div>
                    <button type="button" class="stock-btn-add-peso flex-none px-1.5 py-1 bg-surface border border-outline-variant rounded text-on-surface hover:bg-surface-container-highest transition-colors" title="Agregar botella abierta"${disabledAttrFila}>
                        <span class="material-symbols-outlined" style="font-size:1rem;">add</span>
                    </button>
                </div>` : ''}
            </div>
        </div>
    `;

    if (producto._agregadoManual) {
        row.classList.add('card-agregado-manual');
        const lineaCodigoNombre = row.querySelector('.col-span-full');
        if (lineaCodigoNombre) lineaCodigoNombre.appendChild(crearBotonQuitarManual(producto, 'inline'));
    }

    // Precarga: si ya hay datos capturados en la tarjeta de inventario (PALOTEO 1/2),
    // refleja unidades, todos los pesos abiertos y el perfil elegido en cada uno.
    const cardInventario = getCardInventarioById(producto.id_producto);
    if (cardInventario) {
        aplicarValoresCard(row, leerValoresCard(cardInventario), crearInputPesoCompacto);
    }

    return row;
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

    renderizarReportePaloteo3();
    actualizarResumenProgresoPaloteo3();
}

function refrescarPaloteo3DesdeInventario() {
    if (!productosInventario || productosInventario.length === 0) return;
    renderizarPaloteo3(productosInventario);
}

function obtenerFilasReportePaloteo3() {
    const filas = [];

    document.querySelectorAll('#stock-list .stock-row').forEach(row => {
        const inputUnidades = row.querySelector('.stock-input-unidades');
        if (!inputUnidades) return;

        const idProducto = row.dataset.idProducto || '';
        const codigo = row.dataset.codigo || '—';
        const nombre = row.dataset.nombre || '';
        const unidadesReales = parseInt(inputUnidades.value, 10) || 0;

        const idealUnidades = parseFloat(row.dataset.idealUnidades) || 0;

        // El delta de onzas se toma de la tarjeta de Paloteo 1/2 (recalcularTarjeta),
        // que es la única fuente que conoce el modelo de botella seleccionado por
        // cada peso y suma correctamente todas las botellas pesadas. Recalcularlo
        // aquí de forma independiente (perfiles[0] + un solo input) producía un
        // delta distinto al mostrado en la franja DELTA de Paloteo 1/2.
        // difOnzas parte del total YA REDONDEADO a grilla POS (igual que backend real_det),
        // para que la tolerancia se aplique sobre la misma base que /aplicar. difOnzasExactas
        // es el crudo sin redondear, solo para auditoría/columna "DIF REAL" del PDF.
        let difOnzas = null;
        let difOnzasExactas = null;
        // DET POS/DET BAR (columnas de contexto del PDF): mismo origen que las franjas
        // SISTEMA (IDEAL) / BARRA (REAL) de las tarjetas de Paloteo 1/2. detBar se deriva
        // de detPos + difOnzas (ya redondeado a grilla POS) en vez de recalcular el peso,
        // por la misma razon que difOnzas: es la unica fuente que ya respeta el perfil de
        // botella seleccionado por input y suma todas las botellas pesadas.
        let detPos = null;
        let detBar = null;
        let pesoGramos = null;
        const cardInventario = document.querySelector(`#lista-productos .product-card[data-id="${idProducto}"]`);
        if (cardInventario && cardInventario.dataset.pesable === '1') {
            const valorDetSist = parseFloat(cardInventario.dataset.detsist);
            detPos = Number.isNaN(valorDetSist) ? null : valorDetSist;
            if (cardInventario.dataset.difDetOperativoBase !== undefined) {
                const valorOperativo = parseFloat(cardInventario.dataset.difDetOperativoBase);
                difOnzas = Number.isNaN(valorOperativo) ? null : valorOperativo;
            }
            if (cardInventario.dataset.difDetExacta !== undefined) {
                const valorExacto = parseFloat(cardInventario.dataset.difDetExacta);
                difOnzasExactas = Number.isNaN(valorExacto) ? null : valorExacto;
            }
            if (detPos !== null && difOnzas !== null) {
                detBar = detPos + difOnzas;
            }
            if (cardInventario.dataset.pesoTotalGramos) {
                const valorPeso = parseFloat(cardInventario.dataset.pesoTotalGramos);
                pesoGramos = Number.isNaN(valorPeso) ? null : valorPeso;
            }
        }

        filas.push({
            idProducto,
            codigo,
            nombre,
            toleranciaOz: parseFloat(row.dataset.tolerancia) || 0,
            paqPos: idealUnidades,
            paqBar: unidadesReales,
            detPos,
            pesoGramos,
            detBar,
            difUnidades: unidadesReales - idealUnidades,
            difOnzas,
            difOnzasExactas,
        });
    });

    return filas;
}

function redondearOnzasOperativas(valor) {
    if (valor == null || Number.isNaN(Number(valor))) return null;
    const numero = Number(valor);
    const escalado = numero * 2.0;
    const epsilon = 1e-9;
    const entero = escalado >= 0
        ? Math.floor(escalado + 0.5 + epsilon)
        : Math.ceil(escalado - 0.5 - epsilon);
    return entero * 0.5;
}

function cuantizarDeltaOnzas(valor, toleranciaOz = 0) {
    if (valor == null || Number.isNaN(Number(valor))) return null;

    const numero = Number(valor);
    if (Math.abs(numero) < toleranciaOz) {
        return 0;
    }

    return redondearOnzasOperativas(numero);
}

function aplicarEstadoReporte(filasBase) {
    const filasNormalizadas = filasBase.map((fila) => {
        const clon = { ...fila };

        // difOnzasExactas ya viene crudo desde obtenerFilasReportePaloteo3 (auditoria/exportacion).
        // difOnzas ya viene en base al total redondeado a grilla POS; acá solo se le aplica
        // la banda de tolerancia para decidir el ajuste operativo real.
        clon.difOnzas = cuantizarDeltaOnzas(clon.difOnzas, clon.toleranciaOz || 0);

        return clon;
    });

    const filasFiltradas = filasNormalizadas.filter((fila) => {
        if (reporteEstado.filtro === 'ingreso') {
            return fila.difUnidades > 0 || fila.difOnzas > 0;
        }
        if (reporteEstado.filtro === 'salida') {
            return fila.difUnidades < 0 || fila.difOnzas < 0;
        }
        return true;
    }).map((fila) => {
        const clon = { ...fila };
        if (reporteEstado.filtro === 'ingreso') {
            clon.difUnidades = clon.difUnidades > 0 ? clon.difUnidades : null;
            clon.difOnzas = clon.difOnzas > 0 ? clon.difOnzas : null;
            // difOnzasExactas debe seguir a difOnzas: si la ounces operativa no
            // clasifica como ingreso, la cruda tampoco puede filtrarse al PDF.
            clon.difOnzasExactas = clon.difOnzas != null ? clon.difOnzasExactas : null;
        }
        if (reporteEstado.filtro === 'salida') {
            clon.difUnidades = clon.difUnidades < 0 ? clon.difUnidades : null;
            clon.difOnzas = clon.difOnzas < 0 ? clon.difOnzas : null;
            clon.difOnzasExactas = clon.difOnzas != null ? clon.difOnzasExactas : null;
        }
        return clon;
    });

    if (reporteEstado.sortBy) {
        filasFiltradas.sort((a, b) => {
            let comparacion = 0;
            if (reporteEstado.sortBy === 'idProducto') {
                comparacion = (parseInt(a.idProducto, 10) || 0) - (parseInt(b.idProducto, 10) || 0);
            } else if (reporteEstado.sortBy === 'codigo') {
                comparacion = String(a.codigo || '').localeCompare(String(b.codigo || ''), 'es', { sensitivity: 'base' });
            } else if (reporteEstado.sortBy === 'nombre') {
                comparacion = String(a.nombre || '').localeCompare(String(b.nombre || ''), 'es', { sensitivity: 'base' });
            }

            if (comparacion === 0) {
                comparacion = (parseInt(a.idProducto, 10) || 0) - (parseInt(b.idProducto, 10) || 0);
            }

            return reporteEstado.sortDir === 'asc' ? comparacion : -comparacion;
        });
    }

    return filasFiltradas;
}

function obtenerFilasReporteProcesadas() {
    return aplicarEstadoReporte(obtenerFilasReportePaloteo3());
}

function actualizarUIFiltrosReporte() {
    const estilos = [
        { btn: reporteFiltroTodosBtn, activo: reporteEstado.filtro === 'todos' },
        { btn: reporteFiltroIngresoBtn, activo: reporteEstado.filtro === 'ingreso' },
        { btn: reporteFiltroSalidaBtn, activo: reporteEstado.filtro === 'salida' },
    ];

    estilos.forEach(({ btn, activo }) => {
        if (!btn) return;
        btn.classList.toggle('bg-primary-container', activo);
        btn.classList.toggle('text-black', activo);
        btn.classList.toggle('border-primary-fixed-dim', activo);
        btn.classList.toggle('bg-surface', !activo);
        btn.classList.toggle('text-on-surface', !activo);
        btn.classList.toggle('border-outline-variant', !activo);
    });
}

function actualizarUIOrdenReporte() {
    reporteSortBtns.forEach((btn) => {
        const sortKey = btn.dataset.reporteSort;
        const esActivo = reporteEstado.sortBy === sortKey;
        const flecha = esActivo ? (reporteEstado.sortDir === 'asc' ? ' ↑' : ' ↓') : '';
        const textoBase = btn.dataset.baseLabel || btn.textContent.replace(' ↑', '').replace(' ↓', '');
        btn.dataset.baseLabel = textoBase;
        btn.textContent = `${textoBase}${flecha}`;
        btn.classList.toggle('text-primary-fixed', esActivo);
        btn.classList.toggle('text-on-surface-variant', !esActivo);
        btn.classList.toggle('font-bold', esActivo);
        btn.classList.toggle('font-medium', !esActivo);
    });
}

function renderizarReportePaloteo3() {
    const reporteList = document.getElementById('reporte-list');
    const emptyState = document.getElementById('reporte-empty-state');
    if (!reporteList) return;

    const filas = obtenerFilasReporteProcesadas();
    reporteList.innerHTML = '';

    actualizarUIFiltrosReporte();
    actualizarUIOrdenReporte();

    if (!filas.length) {
        if (emptyState) {
            if (reporteEstado.filtro === 'ingreso') {
                emptyState.textContent = 'No hay productos con ingreso por ajuste.';
            } else if (reporteEstado.filtro === 'salida') {
                emptyState.textContent = 'No hay productos con salida por ajuste.';
            } else {
                emptyState.textContent = 'No hay datos capturados en Paloteo 3 para generar reporte.';
            }
        }
        if (emptyState) emptyState.classList.remove('hidden');
        return;
    }

    if (emptyState) emptyState.classList.add('hidden');

    filas.forEach((fila, index) => {
        const colorUnid = fila.difUnidades == null
            ? 'var(--on-surface-variant)'
            : fila.difUnidades > 0
            ? 'var(--semantic-warning)'
            : fila.difUnidades < 0
                ? 'var(--semantic-danger)'
                : 'var(--semantic-action)';

        const colorOz = fila.difOnzas == null
            ? 'var(--on-surface-variant)'
            : fila.difOnzas > 0
            ? 'var(--semantic-warning)'
            : fila.difOnzas < 0
                ? 'var(--semantic-danger)'
                : 'var(--semantic-action)';

        const textoUnid = fila.difUnidades == null
            ? ''
            : `${fila.difUnidades > 0 ? '+' : ''}${Math.round(fila.difUnidades)}`;
        const textoOz = fila.difOnzas == null
            ? ''
            : `${fila.difOnzas > 0 ? '+' : ''}${fila.difOnzas.toFixed(2)} oz`;

        const row = document.createElement('div');
        row.className = 'grid gap-[2px] px-xs py-xs items-center hover:bg-surface-container-highest transition-colors';
        row.style.gridTemplateColumns = '2rem 2.9rem minmax(0, 1fr) clamp(3.2rem, 14vw, 4.5rem) clamp(4rem, 17vw, 5.25rem)';
        const codigoUpper = String(fila.codigo ?? '').toUpperCase();
        const nombreUpper = String(fila.nombre ?? '').toUpperCase();
        row.innerHTML = `
            <span class="text-data-tabular text-on-surface-variant/80 text-left text-[10px] font-normal truncate" title="${escapeHtml(String(fila.idProducto))}">${escapeHtml(String(fila.idProducto))}</span>
            <span class="text-data-tabular text-on-surface-variant text-left text-[10px] font-normal truncate" title="${escapeHtml(codigoUpper)}">${escapeHtml(codigoUpper)}</span>
            <span class="text-[12px] sm:text-[13px] font-semibold text-on-surface truncate uppercase" title="${escapeHtml(nombreUpper)}">${escapeHtml(nombreUpper)}</span>
            <span class="text-right text-[11px] font-semibold" style="color: ${colorUnid}">${textoUnid}</span>
            <span class="text-right text-[11px] font-semibold" style="color: ${colorOz}">${textoOz}</span>
        `;
        reporteList.appendChild(row);
    });
}

async function exportarReportePaloteo3Pdf() {
    const textoOriginalBtnPdf = reporteBtnPdf ? reporteBtnPdf.innerHTML : '';
    if (reporteBtnPdf) {
        reporteBtnPdf.disabled = true;
        reporteBtnPdf.setAttribute('aria-busy', 'true');
        reporteBtnPdf.innerHTML = `${renderCriticalIcon('refresh', 'ui-icon animate-spin-ccw')} Generando PDF...`;
    }

    const todasLasFilas = obtenerFilasReporteProcesadas();
    const filas = todasLasFilas.filter(f => (f.difUnidades ?? 0) !== 0 || (f.difOnzas ?? 0) !== 0);
    const tipoReporte = reporteEstado.filtro === 'ingreso'
        ? 'ingreso'
        : reporteEstado.filtro === 'salida'
            ? 'salida'
            : 'general';

    try {
        if (!filas.length) {
            const mensaje = todasLasFilas.length === 0
                ? 'No hay productos cargados en Paloteo 3.'
                : 'Todos los productos coinciden con el inventario ideal. No hay diferencias que reportar.';
            await mostrarDialogoResultado({ tipo: 'warning', titulo: 'Sin diferencias para exportar', mensaje });
            return;
        }

        const payload = {
            id_operacion: currentOperacionId,
            id_barra: idBarraActual,
            usuario: localStorage.getItem('nombres') || 'No identificado',
            tipo_reporte: tipoReporte,
            filas: filas.map(f => ({
                // Exacta para analisis y operativa para comparacion con POS (paso 0.5 oz)
                difOnzasExactas: f.difOnzasExactas ?? f.difOnzas,
                difOnzasPos: f.difOnzas,
                idProducto: f.idProducto,
                codigo: f.codigo,
                nombre: f.nombre,
                paqPos: f.paqPos,
                paqBar: f.paqBar,
                detPos: f.detPos,
                pesoGramos: f.pesoGramos,
                detBar: f.detBar,
                difUnidades: f.difUnidades,
                difOnzas: f.difOnzas,
            })),
        };

        const resp = await fetchAutenticado('/api/paloteo3/exportar-pdf', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });

        if (!resp.ok) {
            await mostrarDialogoResultado({ tipo: 'error', titulo: 'Error al generar PDF', mensaje: `El servidor respondió con error ${resp.status}.` });
            return;
        }

        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        const sufijoDescarga = tipoReporte === 'ingreso'
            ? '_INGRESO'
            : tipoReporte === 'salida'
                ? '_SALIDA'
                : '';
        a.download = `PALOTEO_${currentOperacionId}${sufijoDescarga}.pdf`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
    } catch (_) {
        if (_ instanceof SesionExpiradaError) return;
        await mostrarDialogoResultado({ tipo: 'error', titulo: 'Error de red', mensaje: 'No se pudo conectar con el servidor para generar el PDF.' });
        return;
    } finally {
        if (reporteBtnPdf) {
            reporteBtnPdf.disabled = false;
            reporteBtnPdf.removeAttribute('aria-busy');
            reporteBtnPdf.innerHTML = textoOriginalBtnPdf;
        }
    }
}

// ==========================================
// MÓDULO AJUSTES: aplicar diferencias paloteo-vs-POS (solo admin, operativa CERRADA)
// ==========================================
let ajustesPreviewActual = null; // último preview de BD cargado, usado para armar el mensaje de confirmación

function _mostrarEstadoAjustes(mensaje) {
    if (!ajustesEstadoMsg) return;
    ajustesEstadoMsg.textContent = mensaje;
    ajustesEstadoMsg.classList.remove('hidden');
}

function _ocultarEstadoAjustes() {
    if (ajustesEstadoMsg) ajustesEstadoMsg.classList.add('hidden');
}

async function actualizarPanelAjustes() {
    if (!ajustesAdminBlock) return;

    if (!esUsuarioAdministrador()) {
        ajustesAdminBlock.classList.add('hidden');
        return;
    }
    ajustesAdminBlock.classList.remove('hidden');

    if (ajustesBtnAplicar) ajustesBtnAplicar.classList.add('hidden');
    if (ajustesAplicadoBadge) ajustesAplicadoBadge.classList.add('hidden');
    ajustesPreviewActual = null;

    if (!currentOperacionId || currentEstadoOperacion !== 23) {
        _mostrarEstadoAjustes('Disponible solo cuando la operativa está CERRADA (estado 23).');
        return;
    }

    _mostrarEstadoAjustes('Verificando diferencias contra la base de datos...');

    try {
        const resp = await fetchAutenticado(`${API_BASE}/inventario/consolidar/preview`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Barra-Id': String(idBarraActual),
            },
            body: JSON.stringify({ id_operacion: currentOperacionId, id_barra: idBarraActual }),
        });

        const data = await resp.json();

        if (!resp.ok) {
            const detalle = typeof data.detail === 'string' ? data.detail : 'No se pudo verificar el estado de los ajustes.';
            _mostrarEstadoAjustes(detalle);
            return;
        }

        if (data.ya_aplicado) {
            _ocultarEstadoAjustes();
            if (ajustesAplicadoTexto) {
                const fecha = data.aplicado_en ? new Date(data.aplicado_en).toLocaleString() : '';
                ajustesAplicadoTexto.textContent = `Ajustes aplicados${data.aplicado_por ? ` por ${data.aplicado_por}` : ''}${fecha ? ` el ${fecha}` : ''}.`;
            }
            if (ajustesAplicadoBadge) ajustesAplicadoBadge.classList.remove('hidden');
            return;
        }

        if (data.status === 'skipped') {
            _mostrarEstadoAjustes('El inventario físico coincide con el ideal. No hay diferencias que ajustar.');
            return;
        }

        ajustesPreviewActual = data;
        _ocultarEstadoAjustes();
        if (ajustesBtnAplicar) ajustesBtnAplicar.classList.remove('hidden');
    } catch (_) {
        if (_ instanceof SesionExpiradaError) return;
        _mostrarEstadoAjustes('Error de conexión al verificar los ajustes.');
    }
}

async function aplicarAjustesInventario() {
    if (!ajustesPreviewActual || !currentOperacionId) return;

    const { productos_con_diferencia, movimientos_generados } = ajustesPreviewActual.resumen || {};
    const confirmar = await mostrarDialogoConfirmacion({
        titulo: 'Aplicar ajustes de inventario',
        mensaje: `Se generarán ${movimientos_generados ?? '?'} movimiento(s) sobre ${productos_con_diferencia ?? '?'} producto(s) y se actualizará el inventario vivo. Esta acción es irreversible. ¿Continuar?`,
    });
    if (!confirmar) return;

    const textoOriginal = ajustesBtnAplicar.innerHTML;
    ajustesBtnAplicar.disabled = true;
    ajustesBtnAplicar.setAttribute('aria-busy', 'true');
    ajustesBtnAplicar.innerHTML = `${renderCriticalIcon('refresh', 'ui-icon animate-spin-ccw')} Aplicando...`;

    try {
        const resp = await fetchAutenticado(`${API_BASE}/inventario/ajustes/aplicar`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Barra-Id': String(idBarraActual),
            },
            body: JSON.stringify({ id_operacion: currentOperacionId, id_barra: idBarraActual }),
        });

        const data = await resp.json();

        if (resp.ok && data.status === 'success') {
            await mostrarDialogoResultado({ tipo: 'success', titulo: 'Ajustes aplicados', mensaje: data.mensaje });
        } else if (resp.ok && data.status === 'skipped') {
            await mostrarDialogoResultado({ tipo: 'error', titulo: 'Sin diferencias', mensaje: data.mensaje });
        } else {
            const detalle = typeof data.detail === 'string' ? data.detail : 'No se pudo aplicar el ajuste de inventario.';
            await mostrarDialogoResultado({ tipo: 'error', titulo: 'No se pudo aplicar', mensaje: detalle });
        }
    } catch (_) {
        if (_ instanceof SesionExpiradaError) return;
        await mostrarDialogoResultado({ tipo: 'error', titulo: 'Error de red', mensaje: 'No se pudo conectar con el servidor para aplicar los ajustes.' });
    } finally {
        ajustesBtnAplicar.disabled = false;
        ajustesBtnAplicar.removeAttribute('aria-busy');
        ajustesBtnAplicar.innerHTML = textoOriginal;
        await actualizarPanelAjustes();
    }
}

if (ajustesBtnAplicar) {
    ajustesBtnAplicar.addEventListener('click', aplicarAjustesInventario);
}

function syncFilaPaloteo3ConInventario(row) {
    if (!row) return;

    const idProducto = parseInt(row.dataset.idProducto, 10);
    if (isNaN(idProducto)) return;

    const card = getCardInventarioById(idProducto);
    if (!card) return;

    // Round-trip completo (unidades + todas las botellas abiertas + perfil
    // elegido en cada una), reutilizando el mismo mecanismo que PALOTEO 2
    // (modo captura 1x1) usa para sincronizar contra la tarjeta canónica.
    aplicarValoresCard(card, leerValoresCard(row));
    actualizarResumenProgresoInventario();
    scheduleAutosave();
}

function syncTodasFilasPaloteo3ConInventario() {
    document.querySelectorAll('#stock-list .stock-row').forEach(row => {
        syncFilaPaloteo3ConInventario(row);
    });
}

// Fix #27: Ahora usa crearInputPeso() en lugar de duplicar el HTML del input.
window.agregarInputPeso = function(idProducto, perfilesJson) {
    const card = document.querySelector(`#lista-productos .product-card[data-id="${idProducto}"]`);
    const perfiles = perfilesJson || (card ? card.dataset.perfiles : '[]');
    const esVino = card ? esCategoriaVinos(card.dataset.idCategoria) : false;
    const container = document.getElementById(`pesos-${idProducto}`);
    if (!container) return;
    const inputWrapper = document.createElement('div');
    inputWrapper.innerHTML = crearInputPeso(perfiles, true, esVino);
    container.appendChild(inputWrapper.firstElementChild);
}

function agregarInputPesoEnCard(card) {
    if (!card) return;
    const idProducto = parseInt(card.dataset.id, 10);
    const esCaptura = card.dataset.scope === 'captura';
    const containerId = esCaptura ? `pesos-cap-${idProducto}` : `pesos-${idProducto}`;
    const container = card.querySelector(`#${containerId}`) || document.getElementById(containerId);
    if (!container) return;
    const esVino = esCategoriaVinos(card.dataset.idCategoria);

    const inputWrapper = document.createElement('div');
    inputWrapper.innerHTML = crearInputPeso(card.dataset.perfiles || '[]', true, esVino);
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
 * Retorna: { camposVacios: [], erroresPeso: [], erroresCapacidad: [] }
 */
function validarTarjeta(card) {
    const resultado = {
        camposVacios: [],
        erroresPeso: [],
        erroresCapacidad: [],
    };

    const pesable = parseInt(card.dataset.pesable, 10) === 1;
    const esVino = esCategoriaVinos(card.dataset.idCategoria);
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
            if (!esVino && !isNaN(pesoBruto) && pesoBruto > 0 && pesoIngresado > pesoBruto) {
                resultado.erroresPeso.push({ pesoIngresado, pesoBruto, nombrePerfil });
            }

            // Error duro: onzas calculadas superan la capacidad de la botella
            if (onzasMax > 0 && !isNaN(tara) && !isNaN(gramsPorOz) && gramsPorOz > 0) {
                const margenError = 10.0;
                if (pesoIngresado >= (tara - margenError)) {
                    const pesoLiquido = Math.max(0, pesoIngresado - tara);
                    const onzasCalculadas = pesoLiquido / gramsPorOz;
                    if (onzasCalculadas > onzasMax) {
                        resultado.erroresCapacidad.push({ onzasCalculadas, onzasMaximas: onzasMax, nombrePerfil });
                    }
                }
            }
        });
    }

    return resultado;
}

/**
 * Ejecuta validaciones sobre un conjunto de tarjetas.
 * Orden: errores de peso/capacidad (bloqueo duro) → campos vacíos (advertencia con relleno a 0).
 * Retorna true si se puede continuar, false si el usuario cancela o hay error bloqueante.
 */
async function ejecutarValidacionesGlobales(cards) {
    const erroresPeso = [];
    const erroresCapacidad = [];
    const camposVaciosPorCard = [];

    cards.forEach(card => {
        const nombre = card.dataset.nombre;
        const esVino = esCategoriaVinos(card.dataset.idCategoria);
        const unidadDetalle = etiquetaDetalleLarga(card.dataset.idCategoria);
        const res = validarTarjeta(card);
        if (res.erroresPeso.length > 0) erroresPeso.push({ nombre, esVino, detalles: res.erroresPeso });
        if (res.erroresCapacidad.length > 0) erroresCapacidad.push({ nombre, unidadDetalle, detalles: res.erroresCapacidad });
        if (res.camposVacios.length > 0) camposVaciosPorCard.push({ card, nombre, campos: res.camposVacios });
    });

    // 1. Bloqueo duro: peso > peso_bruto
    if (erroresPeso.length > 0) {
        const lista = erroresPeso.map(e => {
            const unidad = e.esVino ? 'cop' : 'g';
            const detalles = e.detalles.map(d =>
                `  • ${d.nombrePerfil}: ingresado ${d.pesoIngresado.toFixed(1)} ${unidad}, máximo ${d.pesoBruto.toFixed(1)} ${unidad}`
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

    // 2. Bloqueo duro: onzas > capacidad por botella
    if (erroresCapacidad.length > 0) {
        const lista = erroresCapacidad.map(e => {
            const detalles = e.detalles.map(d =>
                `  • ${d.nombrePerfil}: ${d.onzasCalculadas.toFixed(2)} ${e.unidadDetalle} (máx. ${d.onzasMaximas.toFixed(2)} ${e.unidadDetalle})`
            ).join('\n');
            return `${e.nombre}:\n${detalles}`;
        }).join('\n\n');
        await mostrarDialogoResultado({
            tipo: 'error',
            titulo: 'Capacidad de botella excedida',
            mensaje: `El peso ingresado equivale a más onzas de las que caben en la botella. Corrige los valores antes de continuar:\n\n${lista}`,
        });
        return false;
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
        id_barra: idBarraActual,
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
        btnGuardar.innerHTML = `${renderCriticalIcon('refresh', 'ui-icon animate-spin-ccw')} Procesando...`;
        btnEnviarInventario.innerHTML = `${renderCriticalIcon('refresh', 'ui-icon animate-spin-ccw')} Enviando...`;

        // Decidir si hacer POST (crear) o PUT (corregir)
        const esCorreccion = currentIdInventarioPOS !== null;
        const metodo = esCorreccion ? 'PUT' : 'POST';
        const url = esCorreccion 
            ? `${API_BASE}/inventario/paloteo/${currentIdInventarioPOS}`
            : `${API_BASE}/inventario/paloteo`;

        const response = await fetchAutenticado(url, {
            method: metodo,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const result = await response.json();

        if (response.ok) {
            // Guardar el ID del inventario registrado para futuras correcciones
            if (!esCorreccion) {
                currentIdInventarioPOS = result.id_inventario_pos;
            }

            clearAutosaveDraft();
            
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
        if (!(error instanceof SesionExpiradaError)) {
            await mostrarDialogoResultado({
                tipo: 'error',
                titulo: 'Error de red',
                mensaje: 'No se pudo conectar con el servidor. Revisa tu conexión e intenta de nuevo.'
            });
        }
    } finally {
        btnGuardar.disabled = !operativaPermitePaloteo;
        btnEnviarInventario.disabled = !operativaPermitePaloteo;
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
    stock:      'panel-stock',
    inventario: 'panel-inventario',
    scan:       'panel-scan',
    logs:       'panel-logs',
    pesaje:     'panel-pesaje',
};

// ==========================================
// BARRA DE BUSQUEDA UNICA (icono expandible en el navbar superior)
// Un solo input compartido por los modulos que necesitan buscar; se reconfigura
// (placeholder + funcion de filtrado) segun el tab activo. En AJUSTES no aplica,
// asi que el icono de buscar queda oculto. Colapsada por defecto para no competir
// por espacio con el logo/selector de barra en pantallas chicas.
// ==========================================
const topbarSearchContainer    = document.getElementById('topbar-search-container');
const topbarSearchInput        = document.getElementById('topbar-search-input');
const topbarSearchContador     = document.getElementById('topbar-search-contador');
const btnTopbarSearchToggle    = document.getElementById('btn-topbar-search-toggle');
const topbarSearchToggleIcon   = document.getElementById('topbar-search-toggle-icon');
const navbarLogoFull           = document.getElementById('navbar-logo-full');
const navbarLogoIsotipo        = document.getElementById('navbar-logo-isotipo');
const topbarSearchCatalogoPanel = document.getElementById('topbar-search-catalogo-resultados');
const topbarSearchCatalogoLista = document.getElementById('topbar-search-catalogo-lista');
const btnVerCatalogoCompleto    = document.getElementById('btn-ver-catalogo-completo');
const btnAgregarTodosCatalogo   = document.getElementById('btn-agregar-todos-catalogo');

const BUSQUEDA_POR_TAB = {
    inventario: { placeholder: 'Buscar por ID, código o nombre...', handler: filtrarInventarioPaloteo1, permiteAgregarCatalogo: true },
    logs:       { placeholder: 'Buscar producto para saltar a su tarjeta...', handler: buscarYNavegarCaptura, permiteAgregarCatalogo: true },
    stock:      { placeholder: 'Buscar por ID, código o nombre...', handler: filtrarStockPaloteo3, permiteAgregarCatalogo: true },
    pesaje:     { placeholder: 'Buscar por nombre de producto...', handler: filtrarPesaje },
};

let busquedaTopbarAbierta = false;

/** Colapsa el buscador y restaura logo/selector de barra a su estado normal. */
function cerrarBusquedaTopbar() {
    busquedaTopbarAbierta = false;
    if (topbarSearchContainer) topbarSearchContainer.classList.add('hidden');
    if (navbarLogoFull) navbarLogoFull.classList.remove('hidden');
    if (navbarLogoIsotipo) navbarLogoIsotipo.classList.add('hidden');
    if (topbarSearchToggleIcon) topbarSearchToggleIcon.textContent = 'search';
    if (btnTopbarSearchToggle) btnTopbarSearchToggle.setAttribute('aria-expanded', 'false');
    aplicarConfiguracionBarraUI(); // restaura el selector de barra segun su config real

    if (topbarSearchInput) topbarSearchInput.value = '';
    if (topbarSearchContador) topbarSearchContador.classList.add('hidden');
    ocultarResultadosCatalogo();
    const tabActivo = document.querySelector('[data-tab].active-tab')?.dataset.tab;
    const config = BUSQUEDA_POR_TAB[tabActivo];
    if (config) config.handler('');
}

/** Expande el buscador: oculta el logo completo y el selector de barra para dejarle espacio. */
function abrirBusquedaTopbar() {
    busquedaTopbarAbierta = true;
    if (topbarSearchContainer) topbarSearchContainer.classList.remove('hidden');
    if (navbarLogoFull) navbarLogoFull.classList.add('hidden');
    if (navbarLogoIsotipo) navbarLogoIsotipo.classList.remove('hidden');
    if (barraSelectorContainer) barraSelectorContainer.classList.add('hidden');
    if (topbarSearchToggleIcon) topbarSearchToggleIcon.textContent = 'close';
    if (btnTopbarSearchToggle) btnTopbarSearchToggle.setAttribute('aria-expanded', 'true');
    if (topbarSearchInput) requestAnimationFrame(() => topbarSearchInput.focus());
}

/** Muestra/oculta el icono de buscar y reconfigura el filtro segun el tab activo. */
function actualizarBarraBusqueda(tabName) {
    if (busquedaTopbarAbierta) cerrarBusquedaTopbar();

    const config = BUSQUEDA_POR_TAB[tabName];
    if (btnTopbarSearchToggle) btnTopbarSearchToggle.classList.toggle('hidden', !config);
    if (btnVerCatalogoCompleto) btnVerCatalogoCompleto.classList.toggle('hidden', !config?.permiteAgregarCatalogo);
    if (config) {
        if (topbarSearchInput) topbarSearchInput.placeholder = config.placeholder;
        config.handler('');
    }
}

if (btnTopbarSearchToggle) {
    btnTopbarSearchToggle.addEventListener('click', () => {
        if (busquedaTopbarAbierta) {
            cerrarBusquedaTopbar();
        } else {
            abrirBusquedaTopbar();
        }
    });
}

if (topbarSearchInput) {
    topbarSearchInput.addEventListener('input', () => {
        const tabActivo = document.querySelector('[data-tab].active-tab')?.dataset.tab;
        const config = BUSQUEDA_POR_TAB[tabActivo];
        if (!config) return;

        config.handler(topbarSearchInput.value);

        if (config.permiteAgregarCatalogo) {
            manejarBusquedaCatalogo(topbarSearchInput.value, tabActivo);
        }
    });
}

if (btnVerCatalogoCompleto) {
    btnVerCatalogoCompleto.addEventListener('click', () => {
        if (topbarSearchInput) topbarSearchInput.value = '';
        cargarCatalogoCompletoYMostrar();
    });
}

if (btnAgregarTodosCatalogo) {
    btnAgregarTodosCatalogo.addEventListener('click', () => agregarTodosDelCatalogo());
}

// ==========================================
// AGREGAR PRODUCTO SIN MOVIMIENTO (busqueda en catalogo completo)
// Cuando la busqueda local (productos con movimiento) no encuentra nada,
// se ofrece buscar en el catalogo completo de la barra y agregar el
// resultado al conteo activo. Ver documentos del plan "agregar productos
// sin movimiento" para el contexto de negocio.
//
// "Paloteo completo": btn-ver-catalogo-completo trae el catalogo entero
// (con y sin movimiento) en el mismo panel, y btn-agregar-todos-catalogo
// agrega de una vez todo lo listado (sea el catalogo completo o el
// resultado de una busqueda puntual), para recontar sin cargar producto
// por producto.
// ==========================================
let catalogoBusquedaDebounceTimer = null;
const CATALOGO_BUSQUEDA_DEBOUNCE_MS = 300;
const CATALOGO_BUSQUEDA_MIN_CHARS = 2;
const CATALOGO_COMPLETO_LIMITE = 500;

/** Ultima lista de productos renderizada en el panel de catalogo, para que
 * "Agregar todos" sepa exactamente que agregar sin repetir la busqueda. */
let ultimosResultadosCatalogo = [];

/** Cuenta cuantas tarjetas/filas locales quedaron visibles tras filtrar, por tab. */
function contarCoincidenciasLocales(tabName) {
    if (tabName === 'inventario') {
        return document.querySelectorAll('#lista-productos .product-card[data-scope="inv"]:not(.hidden)').length;
    }
    if (tabName === 'stock') {
        return document.querySelectorAll('#stock-list .stock-row:not(.hidden)').length;
    }
    if (tabName === 'logs') {
        return Array.isArray(capturaEstado.matches) ? capturaEstado.matches.length : capturaEstado.idsOrdenados.length;
    }
    return Infinity; // tabs sin soporte de catalogo: nunca dispara la busqueda
}

function ocultarResultadosCatalogo() {
    if (catalogoBusquedaDebounceTimer) {
        clearTimeout(catalogoBusquedaDebounceTimer);
        catalogoBusquedaDebounceTimer = null;
    }
    if (topbarSearchCatalogoPanel) topbarSearchCatalogoPanel.classList.add('hidden');
    if (topbarSearchCatalogoLista) topbarSearchCatalogoLista.innerHTML = '';
    if (btnAgregarTodosCatalogo) btnAgregarTodosCatalogo.classList.add('hidden');
    ultimosResultadosCatalogo = [];
}

/** Decide si hay que ir a buscar en el catalogo completo (debounced) segun los resultados locales. */
function manejarBusquedaCatalogo(query, tabName) {
    if (catalogoBusquedaDebounceTimer) clearTimeout(catalogoBusquedaDebounceTimer);

    const q = query.trim();
    if (q.length < CATALOGO_BUSQUEDA_MIN_CHARS) {
        ocultarResultadosCatalogo();
        return;
    }

    if (contarCoincidenciasLocales(tabName) > 0) {
        ocultarResultadosCatalogo();
        return;
    }

    catalogoBusquedaDebounceTimer = setTimeout(() => buscarEnCatalogoYMostrar(q), CATALOGO_BUSQUEDA_DEBOUNCE_MS);
}

async function buscarEnCatalogoYMostrar(query) {
    try {
        const response = await fetchAutenticado(`${API_BASE}/inventario/catalogo/buscar?busqueda=${encodeURIComponent(query)}`, {
            headers: { 'X-Barra-Id': String(idBarraActual) }
        });
        if (!response.ok) { ocultarResultadosCatalogo(); return; }

        const resultados = await response.json();
        const idsYaCargados = new Set(productosInventario.map(p => p.id_producto));
        const nuevos = resultados.filter(p => !idsYaCargados.has(p.id_producto));

        renderizarResultadosCatalogo(nuevos);
    } catch (error) {
        if (error instanceof SesionExpiradaError) return;
        console.error('Error buscando en catalogo completo', error);
        ocultarResultadosCatalogo();
    }
}

/**
 * Trae TODO el catalogo de la barra (con y sin movimiento), para "paloteo
 * completo": recontar el catalogo entero en vez de solo lo que tuvo
 * movimiento. Disparado explicitamente por btn-ver-catalogo-completo, no por
 * el debounce de tipeo (por eso ignora contarCoincidenciasLocales).
 */
async function cargarCatalogoCompletoYMostrar() {
    try {
        const response = await fetchAutenticado(`${API_BASE}/inventario/catalogo/buscar?limite=${CATALOGO_COMPLETO_LIMITE}`, {
            headers: { 'X-Barra-Id': String(idBarraActual) }
        });
        if (!response.ok) { ocultarResultadosCatalogo(); return; }

        const resultados = await response.json();
        const idsYaCargados = new Set(productosInventario.map(p => p.id_producto));
        const nuevos = resultados.filter(p => !idsYaCargados.has(p.id_producto));

        renderizarResultadosCatalogo(nuevos);
    } catch (error) {
        if (error instanceof SesionExpiradaError) return;
        console.error('Error cargando el catalogo completo', error);
        ocultarResultadosCatalogo();
    }
}

/** Agrega de una vez todos los productos listados actualmente en el panel de
 * catalogo (ya sea de una busqueda puntual o del catalogo completo). Pide
 * confirmacion porque puede tratarse de decenas/cientos de productos. */
async function agregarTodosDelCatalogo() {
    const productos = ultimosResultadosCatalogo;
    if (!productos.length) return;

    const confirmado = await mostrarDialogoConfirmacion({
        titulo: 'Agregar todos los productos',
        mensaje: `¿Agregar los ${productos.length} productos listados al conteo? Vas a tener que completar cantidad y/o peso de cada uno.`,
    });
    if (!confirmado) return;

    productos.forEach(p => agregarProductoManual(p, { enfocar: false }));

    ocultarResultadosCatalogo();
    if (topbarSearchInput) topbarSearchInput.value = '';
    scheduleAutosave();
}

function renderizarResultadosCatalogo(productos) {
    if (!topbarSearchCatalogoPanel || !topbarSearchCatalogoLista) return;

    if (!productos.length) {
        ocultarResultadosCatalogo();
        return;
    }

    ultimosResultadosCatalogo = productos;
    if (btnAgregarTodosCatalogo) {
        btnAgregarTodosCatalogo.textContent = `Agregar todos (${productos.length})`;
        btnAgregarTodosCatalogo.classList.remove('hidden');
    }

    topbarSearchCatalogoLista.innerHTML = '';
    productos.forEach(p => {
        const fila = document.createElement('button');
        fila.type = 'button';
        fila.className = 'w-full flex items-center justify-between gap-sm px-sm py-sm text-left hover:bg-surface-container-highest transition-colors border-b border-outline-variant last:border-b-0';
        fila.innerHTML = `
            <span class="min-w-0 truncate text-sm text-on-surface">
                <span class="text-on-surface-variant text-xs">${escapeHtml(String(p.codigo || ''))}</span>
                ${escapeHtml(p.nombre || '')}
            </span>
            <span class="shrink-0 text-[11px] font-label-mono uppercase tracking-widest text-primary-fixed flex items-center gap-1">
                <span class="material-symbols-outlined" style="font-size:1rem;">add</span> Agregar
            </span>
        `;
        fila.addEventListener('click', () => agregarProductoManual(p));
        topbarSearchCatalogoLista.appendChild(fila);
    });

    topbarSearchCatalogoPanel.classList.remove('hidden');
}

/**
 * Crea el boton "x" para quitar un producto agregado manualmente. Oculto en
 * modo solo-lectura. variante='absoluta' lo posiciona en la esquina superior
 * derecha de una card de bloque (PALOTEO 1); variante='inline' lo deja como
 * un boton mas dentro de una fila/linea flex (PALOTEO 3, y PALOTEO 2 porque
 * ahi la esquina superior ya la ocupa el header Prev/Sigt de la captura).
 */
function crearBotonQuitarManual(producto, variante = 'inline') {
    const btn = document.createElement('button');
    btn.type = 'button';
    // Mismo estilo que los botones de cerrar de GUIA OPERATIVA/BOLETIN DUMMY
    // (#btn-close-dummy-content) y del icono de busqueda/menu del navbar.
    btn.className = variante === 'absoluta'
        ? 'btn-quitar-manual topbar-icon-btn absolute top-xs right-xs'
        : 'btn-quitar-manual topbar-icon-btn ml-auto';
    btn.setAttribute('aria-label', 'Quitar producto (agregado sin movimiento)');
    btn.title = 'Quitar producto (agregado sin movimiento)';
    btn.innerHTML = '<span class="material-symbols-outlined text-base">close</span>';
    if (!operativaPermitePaloteo) btn.classList.add('hidden');
    btn.addEventListener('click', (e) => {
        e.stopPropagation();
        quitarProductoManual(producto);
    });
    return btn;
}

/**
 * Agrega un producto que no tuvo movimiento esta operativa al conteo activo,
 * replicando exactamente lo que hace cargarProductos() para uno cargado por
 * movimiento: misma forma de dato, mismas tarjetas/filas, mismo pipeline de
 * envio (construirPayloadInventario lee siempre #lista-productos). No-op si
 * el producto ya esta cargado.
 */
function agregarProductoManual(producto, { enfocar = true } = {}) {
    if (productosInventario.some(p => p.id_producto === producto.id_producto)) return;

    producto._agregadoManual = true;
    productosInventario.push(producto);

    // La marca visual (card-agregado-manual + badge) y el boton de quitar se
    // aplican dentro de crearTarjetaProductoElement/crearFilaPaloteo3 segun
    // producto._agregadoManual, para que sobrevivan a cualquier re-render
    // (refrescarPaloteo3DesdeInventario, renderTarjetaCaptura, hidratacion).
    const card = crearTarjetaProductoElement(producto, 'inv');
    listaProductos.appendChild(card);
    recalcularTarjeta(card);

    const stockListEl = document.getElementById('stock-list');
    if (stockListEl) {
        const emptyState = document.getElementById('stock-empty-state');
        if (emptyState) emptyState.classList.add('hidden');
        const fila = crearFilaPaloteo3(producto);
        stockListEl.appendChild(fila);
    }

    if (capturaEstado.inicializado) {
        capturaEstado.idsOrdenados.push(producto.id_producto);
    }

    actualizarResumenProductos(productosInventario);

    if (!enfocar) return; // hidratacion de autosave: recrear en silencio, sin tocar el buscador ni la vista

    ocultarResultadosCatalogo();
    if (topbarSearchInput) topbarSearchInput.value = '';
    const tabActivo = document.querySelector('[data-tab].active-tab')?.dataset.tab;
    const config = BUSQUEDA_POR_TAB[tabActivo];
    if (config) config.handler('');

    enfocarProductoRecienAgregado(producto, tabActivo, card);
    scheduleAutosave();
}

/** Lleva la atencion del usuario a la tarjeta/fila recien agregada, en el tab activo. */
function enfocarProductoRecienAgregado(producto, tabActivo, cardInventario) {
    if (tabActivo === 'inventario') {
        cardInventario.scrollIntoView({ behavior: 'smooth', block: 'center' });
        const input = cardInventario.querySelector('.input-cerradas');
        if (input) requestAnimationFrame(() => focarYSeleccionar(input));
        return;
    }

    if (tabActivo === 'stock') {
        const fila = document.querySelector(`#stock-list .stock-row[data-id="${producto.id_producto}"]`);
        if (fila) {
            fila.scrollIntoView({ behavior: 'smooth', block: 'center' });
            const input = fila.querySelector('.input-cerradas');
            if (input) requestAnimationFrame(() => focarYSeleccionar(input));
        }
        return;
    }

    if (tabActivo === 'logs' && capturaEstado.inicializado) {
        capturaEstado.matches = null;
        capturaEstado.matchIndex = 0;
        capturaEstado.indice = capturaEstado.idsOrdenados.length - 1;
        renderTarjetaCaptura(capturaEstado.indice);
    }
}

/**
 * Quita del conteo activo un producto agregado manualmente (deshace un alta
 * por error). Si el paloteo ya se guardo (currentIdInventarioPOS existe),
 * primero da de baja la fila en bar_detalle_fisico via DELETE; si la
 * confirmacion del backend falla, no toca nada local para no desincronizar
 * la UI de la BD.
 */
async function quitarProductoManual(producto) {
    const confirmado = await mostrarDialogoConfirmacion({
        titulo: 'Quitar producto',
        mensaje: `¿Quitar "${producto.nombre}" del conteo? Fue agregado manualmente (sin movimiento esta operativa).`,
    });
    if (!confirmado) return;

    if (currentIdInventarioPOS) {
        try {
            const response = await fetchAutenticado(`${API_BASE}/inventario/paloteo/${currentIdInventarioPOS}/producto/${producto.id_producto}`, {
                method: 'DELETE',
                headers: { 'X-Barra-Id': String(idBarraActual) }
            });

            if (!response.ok) {
                const data = await response.json().catch(() => ({}));
                await mostrarDialogoResultado({
                    tipo: 'error',
                    titulo: 'No se pudo quitar',
                    mensaje: data.detail || 'No se pudo quitar el producto del inventario guardado.',
                });
                return;
            }
        } catch (error) {
            if (error instanceof SesionExpiradaError) return;
            console.error('Error quitando producto manual', error);
            await mostrarDialogoResultado({
                tipo: 'error',
                titulo: 'Error de conexión',
                mensaje: 'No se pudo conectar con el servidor para quitar el producto.',
            });
            return;
        }
    }

    const idx = productosInventario.findIndex(p => p.id_producto === producto.id_producto);
    if (idx !== -1) productosInventario.splice(idx, 1);

    document.querySelector(`#lista-productos .product-card[data-id="${producto.id_producto}"]`)?.remove();
    document.querySelector(`#stock-list .stock-row[data-id="${producto.id_producto}"]`)?.remove();

    const stockListEl = document.getElementById('stock-list');
    if (stockListEl && stockListEl.querySelectorAll('.stock-row').length === 0) {
        const emptyState = document.getElementById('stock-empty-state');
        if (emptyState) emptyState.classList.remove('hidden');
    }

    const posCaptura = capturaEstado.idsOrdenados.indexOf(producto.id_producto);
    if (posCaptura !== -1) {
        capturaEstado.idsOrdenados.splice(posCaptura, 1);
        capturaEstado.matches = null;
        capturaEstado.matchIndex = 0;
        if (capturaEstado.indice >= capturaEstado.idsOrdenados.length) {
            capturaEstado.indice = Math.max(0, capturaEstado.idsOrdenados.length - 1);
        }
        const tabActivo = document.querySelector('[data-tab].active-tab')?.dataset.tab;
        if (tabActivo === 'logs') {
            renderTarjetaCaptura(capturaEstado.indice);
        }
    }

    actualizarResumenProductos(productosInventario);
    scheduleAutosave();
}

/**
 * Muestra el panel correspondiente al tab y marca el tab como activo.
 * Si el tab no tiene panel asignado (ej. ENVIO), no cambia el panel visible.
 * @param {string} tabName
 */
function navegarATab(tabName) {
    const panelId = TAB_PANEL_MAP[tabName];
    if (!panelId) return; // ENVIO no navega a ningún panel

    if (tabName === 'inventario' && vistaInicialSoloOperativa) {
        vistaInicialSoloOperativa = false;
        actualizarVistaInicialInventario();
    }

    // Ocultar todos los paneles
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.add('hidden'));

    // Mostrar el panel destino
    const panelDestino = document.getElementById(panelId);
    if (panelDestino) panelDestino.classList.remove('hidden');

    actualizarBarraBusqueda(tabName);

    if (tabName === 'logs') {
        inicializarModoCaptura();
    }

    if (tabName === 'stock') {
        enfocarPrimerCampoPaloteo3();
    }

    if (tabName === 'scan') {
        renderizarReportePaloteo3();
    }

    if (tabName === 'pesaje') {
        cargarPesaje();
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

    fabsScrollTop.forEach((actualizar) => actualizar());
}

/**
 * FAB de "volver al inicio", reutilizable en cualquier panel.
 * Muestra el boton (id fabId) solo cuando el panel (id panelId) esta visible
 * y la pagina esta desplazada mas alla de UMBRAL_SCROLL_FAB; al hacer click
 * hace scroll suave al inicio. Para replicarlo en otro modulo: agregar un
 * boton con clase "fab-scroll-top" dentro del panel y llamar a esta funcion
 * con sus ids.
 */
const UMBRAL_SCROLL_FAB = 240;
const fabsScrollTop = [];

function inicializarFabScrollTop(fabId, panelId) {
    const fab = document.getElementById(fabId);
    const panel = document.getElementById(panelId);
    if (!fab || !panel) return;

    function actualizarVisibilidad() {
        const panelVisible = !panel.classList.contains('hidden');
        const debeMostrarse = panelVisible && window.scrollY > UMBRAL_SCROLL_FAB;
        fab.classList.toggle('hidden', !debeMostrarse);
    }

    window.addEventListener('scroll', actualizarVisibilidad, { passive: true });
    fab.addEventListener('click', () => {
        window.scrollTo({ top: 0, behavior: 'smooth' });
    });

    fabsScrollTop.push(actualizarVisibilidad);
    actualizarVisibilidad();
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

function aplicarValoresCard(card, valores, builderInputPeso = crearInputPeso) {
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
        wrapper.innerHTML = builderInputPeso(perfilesJson, true);
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

// Actualiza un contador "X / Y (Z%)" de items completos dentro de un contenedor.
// Reutiliza tarjetaCompleta(), que solo depende de .input-cerradas/.input-peso
// y data-pesable, asi que sirve tanto para .product-card (Paloteo 1) como
// para .stock-row (Paloteo 3).
function actualizarResumenProgreso(contenedor, selectorItem, idCompletados, idTotal, idPct) {
    if (!contenedor) return;
    const items = [...contenedor.querySelectorAll(selectorItem)];
    const total = items.length;
    const completos = items.filter(tarjetaCompleta).length;
    const pct = total > 0 ? Math.round((completos / total) * 100) : 0;

    const elCompletados = document.getElementById(idCompletados);
    const elTotal = document.getElementById(idTotal);
    const elPct = document.getElementById(idPct);
    if (elCompletados) elCompletados.textContent = String(completos);
    if (elTotal) elTotal.textContent = String(total);
    if (elPct) elPct.textContent = `${pct}%`;
}

function actualizarResumenProgresoInventario() {
    actualizarResumenProgreso(listaProductos, '.product-card', 'inventario-completados', 'inventario-total-items', 'inventario-pct-completados');
}

function actualizarResumenProgresoPaloteo3() {
    actualizarResumenProgreso(document.getElementById('stock-list'), '.stock-row', 'stock-completados', 'stock-total-items', 'stock-pct-completados');
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

    refrescarPaloteo3DesdeInventario();
    scheduleAutosave();
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

// select() en type="number" no es confiable en mobile: cambio temporal a text para seleccionar
function focarYSeleccionar(input) {
    const tipo = input.type;
    input.type = 'text';
    input.focus();
    input.setSelectionRange(0, input.value.length);
    input.type = tipo;
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

    // Insertar navegación y contador centrados en el encabezado de la tarjeta.
    const total = capturaEstado.idsOrdenados.length;
    const headerCaptura = document.createElement('div');
    headerCaptura.className = 'mb-sm w-full grid grid-cols-3 items-center gap-xs';

    const claseBotonCapturaCompacto = 'w-full h-9 bg-surface border border-outline-variant text-on-surface rounded-sharp px-xs uppercase tracking-[0.08em] text-[10px] font-label-mono flex items-center justify-center gap-[2px] hover:border-primary-fixed-dim hover:text-primary-fixed transition-colors';

    const botonAnterior = document.createElement('button');
    botonAnterior.type = 'button';
    botonAnterior.className = `${claseBotonCapturaCompacto} w-[4.75rem] justify-self-start`;
    botonAnterior.innerHTML = '<span class="material-symbols-outlined text-[16px]">arrow_back</span> Prev';

    const botonSiguiente = document.createElement('button');
    botonSiguiente.type = 'button';
    botonSiguiente.className = `${claseBotonCapturaCompacto} w-[4.75rem] justify-self-end`;
    botonSiguiente.innerHTML = 'Sigt <span class="material-symbols-outlined text-[16px]">arrow_forward</span>';

    // Con busqueda activa, PREV/SIGT recorren solo las coincidencias.
    const buscandoActivo = Array.isArray(capturaEstado.matches);
    const totalMatches = buscandoActivo ? capturaEstado.matches.length : 0;
    const esPrimerProducto = buscandoActivo ? (totalMatches === 0 || capturaEstado.matchIndex <= 0) : indice <= 0;
    const esUltimoProducto = buscandoActivo ? (totalMatches === 0 || capturaEstado.matchIndex >= totalMatches - 1) : indice >= (total - 1);
    botonAnterior.classList.toggle('invisible', esPrimerProducto);
    botonAnterior.disabled = esPrimerProducto;
    botonSiguiente.classList.toggle('invisible', esUltimoProducto);
    botonSiguiente.disabled = esUltimoProducto;

    botonAnterior.addEventListener('click', () => navegarCaptura(-1));
    botonSiguiente.addEventListener('click', () => navegarCaptura(1));

    const topbarContador = document.getElementById('topbar-search-contador');
    if (topbarContador) {
        if (buscandoActivo) {
            topbarContador.textContent = totalMatches > 0
                ? `${capturaEstado.matchIndex + 1}/${totalMatches}`
                : 'Sin match';
            topbarContador.classList.remove('hidden');
        } else {
            topbarContador.classList.add('hidden');
        }
    }

    const pctAvance = total > 0 ? Math.round(((indice + 1) / total) * 100) : 0;

    const contador = document.createElement('div');
    contador.className = 'justify-self-center flex items-center justify-center gap-1 text-center leading-none min-w-max';
    contador.innerHTML = `<span id="captura-indice-actual" class="text-[12px] sm:text-sm font-semibold text-primary-fixed tabular-nums">${indice + 1}</span><span class="text-[9px] sm:text-[10px] font-label-mono text-on-surface-variant uppercase tracking-[0.12em]">/</span><span id="captura-indice-total" class="text-[12px] sm:text-sm font-semibold text-primary-fixed tabular-nums">${total}</span><span id="captura-indice-pct" class="text-[9px] sm:text-[10px] font-label-mono text-on-surface-variant tabular-nums">&nbsp;(${pctAvance}%)</span>`;

    headerCaptura.appendChild(botonAnterior);
    headerCaptura.appendChild(contador);
    headerCaptura.appendChild(botonSiguiente);
    card.insertBefore(headerCaptura, card.firstChild);

    capturaCardContainer.appendChild(card);

    const cardInventario = getCardInventarioById(idProducto);
    if (cardInventario) {
        aplicarValoresCard(card, leerValoresCard(cardInventario));
    } else {
        recalcularTarjeta(card);
    }

    actualizarResumenCaptura();

    // Auto-focus en el primer campo al cargar la tarjeta
    const primerInput = card.querySelector('.input-cerradas');
    if (primerInput) {
        requestAnimationFrame(() => focarYSeleccionar(primerInput));
    }

    // Navegación por Enter: cerradas → primer peso → ... → último peso → siguiente producto
    card.addEventListener('keydown', (e) => {
        if (e.key !== 'Enter') return;

        const inputCerradas = card.querySelector('.input-cerradas');
        const inputsPeso = [...card.querySelectorAll('.input-peso')];
        const foco = document.activeElement;

        if (foco === inputCerradas) {
            e.preventDefault();
            if (inputsPeso.length > 0) {
                focarYSeleccionar(inputsPeso[0]);
            } else {
                navegarCaptura(1);
            }
            return;
        }

        const idxPeso = inputsPeso.indexOf(foco);
        if (idxPeso !== -1) {
            e.preventDefault();
            if (idxPeso < inputsPeso.length - 1) {
                focarYSeleccionar(inputsPeso[idxPeso + 1]);
            } else {
                navegarCaptura(1);
            }
        }
    });
}

async function navegarCaptura(delta = 1) {
    if (!capturaEstado.inicializado || capturaEstado.idsOrdenados.length === 0) return;
    syncCapturaConInventario();

    // Al avanzar, validar la tarjeta actual antes de navegar — pero solo si se puede
    // editar; en modo solo lectura los inputs estan deshabilitados y no tiene sentido
    // pedir confirmar campos vacios de un paloteo que no se va a registrar.
    if (delta > 0 && operativaPermitePaloteo) {
        const cardCaptura = capturaCardContainer.querySelector('.product-card[data-scope="captura"]');
        if (cardCaptura) {
            const valido = await ejecutarValidacionesGlobales([cardCaptura]);
            if (!valido) return;
        }
    }

    if (capturaEstado.matches && capturaEstado.matches.length > 0) {
        // Busqueda activa: PREV/SIGT recorren solo las coincidencias, no todo el catalogo.
        const totalMatches = capturaEstado.matches.length;
        const siguienteMatchIndex = Math.max(0, Math.min(totalMatches - 1, capturaEstado.matchIndex + delta));
        capturaEstado.matchIndex = siguienteMatchIndex;
        capturaEstado.indice = capturaEstado.matches[siguienteMatchIndex];
    } else {
        const siguienteIndice = Math.max(0, Math.min(capturaEstado.idsOrdenados.length - 1, capturaEstado.indice + delta));
        capturaEstado.indice = siguienteIndice;
    }
    renderTarjetaCaptura(capturaEstado.indice);
}

/**
 * Busqueda de la barra superior para PALOTEO 2: en vez de ocultar tarjetas (aqui
 * solo se ve una a la vez), salta directo a la primera coincidencia y deja que
 * PREV/SIGT recorran solo las coincidencias mientras la busqueda este activa.
 */
function buscarYNavegarCaptura(query) {
    if (!capturaEstado.inicializado || capturaEstado.idsOrdenados.length === 0) return;

    const q = query.trim().toLowerCase();
    if (!q) {
        capturaEstado.matches = null;
        capturaEstado.matchIndex = 0;
        renderTarjetaCaptura(capturaEstado.indice);
        return;
    }

    const matches = [];
    capturaEstado.idsOrdenados.forEach((idProducto, idx) => {
        const producto = productosInventario.find(p => p.id_producto === idProducto);
        if (!producto) return;
        const texto = `${producto.id_producto || ''} ${producto.codigo || ''} ${producto.nombre || ''}`.toLowerCase();
        if (texto.includes(q)) matches.push(idx);
    });

    capturaEstado.matches = matches;
    capturaEstado.matchIndex = 0;
    if (matches.length > 0) {
        capturaEstado.indice = matches[0];
    }
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
function filtrarStockPaloteo3(query) {
    const q = query.toLowerCase().trim();
    document.querySelectorAll('#stock-list .stock-row').forEach(row => {
        const searchText = row.dataset.search || '';
        row.classList.toggle('hidden', q.length > 0 && !searchText.includes(q));
    });
}

function filtrarInventarioPaloteo1(query) {
    const q = query.toLowerCase().trim();
    document.querySelectorAll('#lista-productos .product-card[data-scope="inv"]').forEach(card => {
        const searchText = card.dataset.search || '';
        card.classList.toggle('hidden', q.length > 0 && !searchText.includes(q));
    });
}

const stockList = document.getElementById('stock-list');
if (stockList) {
    stockList.addEventListener('input', (e) => {
        if (e.target.classList.contains('input-cerradas') || e.target.classList.contains('input-peso')) {
            const row = e.target.closest('.stock-row');
            syncFilaPaloteo3ConInventario(row);
            renderizarReportePaloteo3();
            actualizarResumenProgresoPaloteo3();
            scheduleAutosave();
        }
    });

    stockList.addEventListener('change', (e) => {
        if (e.target.classList.contains('select-perfil')) {
            const row = e.target.closest('.stock-row');
            syncFilaPaloteo3ConInventario(row);
            renderizarReportePaloteo3();
            scheduleAutosave();
        }
    });

    stockList.addEventListener('click', (e) => {
        const row = e.target.closest('.stock-row');
        if (!row) return;

        if (e.target.closest('.stock-btn-dec-unid') || e.target.closest('.stock-btn-inc-unid')) {
            e.preventDefault();
            const incrementar = !!e.target.closest('.stock-btn-inc-unid');
            ajustarValorNumerico(row.querySelector('.input-cerradas'), incrementar, 1);
            return;
        }

        const btnDecPeso = e.target.closest('.stock-btn-dec-peso');
        const btnIncPeso = e.target.closest('.stock-btn-inc-peso');
        if (btnDecPeso || btnIncPeso) {
            e.preventDefault();
            const wrapper = (btnDecPeso || btnIncPeso).closest('.item-peso-wrapper');
            const input = wrapper ? wrapper.querySelector('.input-peso') : null;
            const select = wrapper ? wrapper.querySelector('.select-perfil') : null;
            const perfiles = JSON.parse(row.dataset.perfiles || '[]');
            const paso = calcularStepPesoGramos(perfiles, select);
            ajustarValorNumerico(input, !!btnIncPeso, paso);
            return;
        }

        if (e.target.closest('.stock-btn-add-peso')) {
            e.preventDefault();
            const container = row.querySelector('.pesos-container');
            if (container) {
                const wrapper = document.createElement('div');
                wrapper.innerHTML = crearInputPesoCompacto(
                    row.dataset.perfiles || '[]',
                    true,
                    esCategoriaVinos(row.dataset.idCategoria)
                );
                container.appendChild(wrapper.firstElementChild);
            }
            return;
        }

        if (e.target.closest('.btn-remove-peso')) {
            e.preventDefault();
            const wrapper = e.target.closest('.item-peso-wrapper');
            if (wrapper) wrapper.remove();
            syncFilaPaloteo3ConInventario(row);
            renderizarReportePaloteo3();
            actualizarResumenProgresoPaloteo3();
            scheduleAutosave();
            return;
        }
    });

    // Navegación por Enter entre filas: cerradas → primer peso → ... → último peso → cerradas de la siguiente fila.
    stockList.addEventListener('keydown', (e) => {
        if (e.key !== 'Enter') return;
        if (!(e.target.classList.contains('input-cerradas') || e.target.classList.contains('input-peso'))) return;

        const row = e.target.closest('.stock-row');
        if (!row) return;
        e.preventDefault();

        const inputsPeso = [...row.querySelectorAll('.input-peso')];

        if (e.target.classList.contains('input-cerradas')) {
            if (inputsPeso.length > 0) {
                focarYSeleccionar(inputsPeso[0]);
            } else {
                avanzarALaSiguienteFilaPaloteo3(row);
            }
            return;
        }

        const idxPeso = inputsPeso.indexOf(e.target);
        if (idxPeso !== -1) {
            if (idxPeso < inputsPeso.length - 1) {
                focarYSeleccionar(inputsPeso[idxPeso + 1]);
            } else {
                avanzarALaSiguienteFilaPaloteo3(row);
            }
        }
    });
}

function avanzarALaSiguienteFilaPaloteo3(filaActual) {
    const siguienteFila = filaActual.nextElementSibling;
    if (!siguienteFila || !siguienteFila.classList.contains('stock-row')) return;

    const siguienteInput = siguienteFila.querySelector('.input-cerradas');
    if (siguienteInput) {
        siguienteFila.scrollIntoView({ behavior: 'smooth', block: 'center' });
        focarYSeleccionar(siguienteInput);
    }
}

// Auto-focus en el primer campo de la lista al entrar al tab de PALOTEO 3 (igual que PALOTEO 1/2).
function enfocarPrimerCampoPaloteo3() {
    const primerInput = document.querySelector('#stock-list .stock-row .input-cerradas');
    if (primerInput) {
        requestAnimationFrame(() => focarYSeleccionar(primerInput));
    }
}

// Persistir borrador al segundo plano o cierre abrupto de pestaña.
document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') {
        flushAutosave('visibility');
    }
});

window.addEventListener('pagehide', () => {
    flushAutosave('pagehide');
});

if (stockBtnGuardar) {
    stockBtnGuardar.addEventListener('click', async () => {
        // Sincroniza la captura de PALOTEO 3 con el origen único de datos antes de validar/enviar.
        syncTodasFilasPaloteo3ConInventario();

        const todasLasCards = Array.from(document.querySelectorAll('#lista-productos .product-card'));
        const valido = await ejecutarValidacionesGlobales(todasLasCards);
        if (!valido) return;

        abrirDialogoObservaciones('inventario');
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
            // Sin esto, lo tecleado en Paloteo 2 solo vive en la tarjeta de captura:
            // REPORTE (que lee la tarjeta de #lista-productos) queda desactualizado y
            // al volver a Paloteo 2 se reconstruye desde esa misma tarjeta sin sincronizar.
            syncCapturaConInventario();
            actualizarResumenCaptura();
            scheduleAutosave();
        }
    });

    capturaCardContainer.addEventListener('change', (e) => {
        if (e.target.classList.contains('select-perfil')) {
            const card = e.target.closest('.product-card');
            recalcularTarjeta(card);
            syncCapturaConInventario();
            actualizarResumenCaptura();
            scheduleAutosave();
        }
    });

    capturaCardContainer.addEventListener('click', async (e) => {
        const btnAdd = e.target.closest('.btn-add-peso-captura');
        if (btnAdd) {
            const card = capturaCardContainer.querySelector('.product-card[data-scope="captura"]');
            agregarInputPesoEnCard(card);
            recalcularTarjeta(card);
            syncCapturaConInventario();
            scheduleAutosave();
            return;
        }

        if (e.target.closest('.btn-remove-peso')) {
            const card = capturaCardContainer.querySelector('.product-card[data-scope="captura"]');
            setTimeout(() => {
                recalcularTarjeta(card);
                syncCapturaConInventario();
                actualizarResumenCaptura();
                scheduleAutosave();
            }, 20);
        }
    });
}

document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !observacionesDialog.classList.contains('hidden')) {
        cerrarDialogoObservaciones();
        return;
    }

    const panelLogsVisible = !document.getElementById('panel-logs').classList.contains('hidden');
    if (!panelLogsVisible) return;

    if (!esDesktopParaCaptura()) return;

    const elementoActivo = document.activeElement;
    const focoEnCampoEditable = elementoActivo && (
        elementoActivo.tagName === 'INPUT'
        || elementoActivo.tagName === 'TEXTAREA'
        || elementoActivo.tagName === 'SELECT'
        || elementoActivo.isContentEditable
    );

    if (focoEnCampoEditable) return;

    if (event.key === 'ArrowRight') {
        event.preventDefault();
        navegarCaptura(1);
    }

    if (event.key === 'ArrowLeft') {
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
function formatearDiferencia(diferencia, isDetalle = false, toleranciaDetalle = 0, unidadDetalle = 'oz') {
    const diferenciaOperativa = isDetalle ? (cuantizarDeltaOnzas(diferencia, toleranciaDetalle) ?? 0) : diferencia;
    const sufijo = isDetalle ? unidadDetalle : 'bot';

    // Tolerancia para decimales (evitar ruido por redondeos)
    if (Math.abs(diferenciaOperativa) < 0.01) {
        return `<span class="text-data-tabular font-semibold" style="color: var(--semantic-action)">${renderCriticalIcon('check_circle', 'ui-icon ui-icon-sm')}</span>`;
    }

    if (diferenciaOperativa < 0) {
        const val = isOz ? diferenciaOperativa.toFixed(2) : Math.round(diferenciaOperativa);
        return `<span class="text-data-tabular font-semibold" style="color: var(--semantic-danger)">${val} ${sufijo}</span>`;
    }

    const val = isDetalle ? diferenciaOperativa.toFixed(2) : Math.round(diferenciaOperativa);
    return `<span class="text-data-tabular font-semibold" style="color: var(--semantic-warning)">+${val} ${sufijo}</span>`;
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
        const unidadDetalle = etiquetaDetalleCorta(card.dataset.idCategoria);
        const inputsPeso = card.querySelectorAll('.input-peso');
        const spanDet = card.querySelector(`#val-det-${scope}`) || document.getElementById(`val-det-${scope}`);
        const difDetSpan = card.querySelector(`#dif-det-${scope}`) || document.getElementById(`dif-det-${scope}`);

        let detBarra = 0;
        let pesoTotalGramos = 0;
        let hayPesosValidos = false;
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
                pesoTotalGramos += pesoMedido;
                hayPesosValidos = true;
            }
        });

        const detBarraOperativo = redondearOnzasOperativas(detBarra) ?? 0;
        const difDetExacta = detBarra - detSist;
        // Base para tolerancia/ajuste: igual que el backend, que compara el YA REDONDEADO
        // bar_detalle_fisico.cantidad_detalle contra el ideal (no el peso crudo). Usar
        // difDetExacta acá desalinea la banda de tolerancia con lo que aplica /aplicar
        // (ver documentos/redondeo_y_tolerancia.md).
        const difDetOperativoBase = detBarraOperativo - detSist;

        // Fuente canónica para REPORTE: ya respeta el perfil de botella
        // seleccionado por input y suma todas las botellas pesadas.
        card.dataset.difDetExacta = String(difDetExacta);
        card.dataset.difDetOperativoBase = String(difDetOperativoBase);
        // Peso bruto total introducido (columna PESO del PDF). Vacío cuando no
        // hay pesos válidos, para distinguir "no se pesó" de "pesó 0 g".
        card.dataset.pesoTotalGramos = hayPesosValidos ? String(pesoTotalGramos) : '';

        if (spanDet) spanDet.textContent = detBarraOperativo.toFixed(2);
        if (difDetSpan) difDetSpan.innerHTML = formatearDiferencia(difDetOperativoBase, true, tolerancia, unidadDetalle);
    }
}

listaProductos.addEventListener('input', (e) => {
    if (e.target.classList.contains('input-cerradas') || e.target.classList.contains('input-peso')) {
        recalcularTarjeta(e.target.closest('.product-card'));
        refrescarPaloteo3DesdeInventario();
        actualizarResumenProgresoInventario();
        scheduleAutosave();
    }
});

listaProductos.addEventListener('change', (e) => {
    if (e.target.classList.contains('select-perfil')) {
        recalcularTarjeta(e.target.closest('.product-card'));
        refrescarPaloteo3DesdeInventario();
        scheduleAutosave();
    }
});

listaProductos.addEventListener('click', (e) => {
    const btnAdd = e.target.closest('.btn-add-peso');
    if (btnAdd) {
        const idProducto = parseInt(btnAdd.dataset.idProducto, 10);
        if (!isNaN(idProducto)) {
            agregarInputPeso(idProducto);
            refrescarPaloteo3DesdeInventario();
            scheduleAutosave();
        }
        return;
    }
});

listaProductos.addEventListener('click', (e) => {
    if (e.target.closest('.btn-remove-peso')) {
        const card = e.target.closest('.product-card');
        setTimeout(() => {
            recalcularTarjeta(card);
            actualizarResumenProgresoInventario();
            scheduleAutosave();
        }, 50);
    }
});

// Auto-focus en el primer campo de la lista al cargar (igual que PALOTEO 2).
function enfocarPrimerCampoInventario() {
    const panelInventario = document.getElementById('panel-inventario');
    if (panelInventario && panelInventario.classList.contains('hidden')) return;

    const primerInput = listaProductos.querySelector('.product-card .input-cerradas');
    if (primerInput) {
        requestAnimationFrame(() => focarYSeleccionar(primerInput));
    }
}

// Navegación por Enter entre tarjetas: cerradas → primer peso → ... → último peso → cerradas de la siguiente tarjeta.
function avanzarAlSiguienteProductoInventario(cardActual) {
    const siguienteCard = cardActual.nextElementSibling;
    if (!siguienteCard || !siguienteCard.classList.contains('product-card')) return;

    const siguienteInput = siguienteCard.querySelector('.input-cerradas');
    if (siguienteInput) {
        siguienteCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
        focarYSeleccionar(siguienteInput);
    }
}

listaProductos.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter') return;
    if (!(e.target.classList.contains('input-cerradas') || e.target.classList.contains('input-peso'))) return;

    const card = e.target.closest('.product-card');
    if (!card) return;
    e.preventDefault();

    const inputsPeso = [...card.querySelectorAll('.input-peso')];

    if (e.target.classList.contains('input-cerradas')) {
        if (inputsPeso.length > 0) {
            focarYSeleccionar(inputsPeso[0]);
        } else {
            avanzarAlSiguienteProductoInventario(card);
        }
        return;
    }

    const idxPeso = inputsPeso.indexOf(e.target);
    if (idxPeso !== -1) {
        if (idxPeso < inputsPeso.length - 1) {
            focarYSeleccionar(inputsPeso[idxPeso + 1]);
        } else {
            avanzarAlSiguienteProductoInventario(card);
        }
    }
});

function inicializarCalculos() {
    document.querySelectorAll('#lista-productos .product-card').forEach(card => {
        recalcularTarjeta(card);
    });
}

if (reporteBtnPdf) {
    reporteBtnPdf.addEventListener('click', async () => {
        await exportarReportePaloteo3Pdf();
    });
}

if (reporteFiltroTodosBtn) {
    reporteFiltroTodosBtn.addEventListener('click', () => {
        reporteEstado.filtro = 'todos';
        renderizarReportePaloteo3();
    });
}

if (reporteFiltroIngresoBtn) {
    reporteFiltroIngresoBtn.addEventListener('click', () => {
        reporteEstado.filtro = 'ingreso';
        renderizarReportePaloteo3();
    });
}

if (reporteFiltroSalidaBtn) {
    reporteFiltroSalidaBtn.addEventListener('click', () => {
        reporteEstado.filtro = 'salida';
        renderizarReportePaloteo3();
    });
}

if (reporteSortBtns.length > 0) {
    reporteSortBtns.forEach((btn) => {
        btn.addEventListener('click', () => {
            const sortBy = btn.dataset.reporteSort;
            if (!sortBy) return;

            if (reporteEstado.sortBy === sortBy) {
                reporteEstado.sortDir = reporteEstado.sortDir === 'asc' ? 'desc' : 'asc';
            } else {
                reporteEstado.sortBy = sortBy;
                reporteEstado.sortDir = 'asc';
            }
            renderizarReportePaloteo3();
        });
    });
}