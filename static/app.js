// ==========================================
// CONFIGURACIÓN Y ESTADO GLOBAL
// ==========================================
const API_BASE = "http://localhost:8000/api";
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
    
    estadoIcon.textContent = "hourglass_empty";
    estadoIcon.classList.add('animate-pulse');
    estadoTexto.textContent = "Verificando estado de la caja...";

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
            estadoIcon.classList.remove('animate-pulse', 'text-neon-green');
            estadoIcon.classList.add('text-neon-pink');
            estadoTexto.textContent = dataOp.detail || "No se puede realizar el paloteo.";
            return; // Bloqueamos la ejecución aquí
        }

        // Luz Verde: Guardamos el ID de operación
        currentOperacionId = dataOp.id_operacion;
        estadoIcon.textContent = "check_circle";
        estadoIcon.classList.remove('animate-pulse');
        estadoTexto.textContent = dataOp.mensaje; // "Luz verde..."

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
        const productos = await response.json();

        if (response.ok && productos.length > 0) {
            renderizarProductos(productos);
            actionBar.classList.remove('hidden'); // Mostrar barra de guardado
            actionBar.classList.add('flex');
        } else {
            listaProductos.innerHTML = `<div class="text-center text-gray-500 py-10">No hay productos consumidos para auditar hoy.</div>`;
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
        div.className = "bg-dark-surface border border-gray-800 rounded-xl p-4 shadow-lg product-card transition-colors focus-within:border-gray-600";
        div.dataset.id = p.id_producto;
        div.dataset.pesable = p.pesable || 0;
        div.dataset.nombre = p.nombre;

        // Info básica
        let html = `
            ${p.categoria_nombre ? `<span class="text-[10px] font-bold tracking-widest uppercase text-gray-500 mb-1 block">${p.categoria_nombre}</span>` : ''}
            <h4 class="text-neon-green font-bold text-lg mb-1">${p.nombre}</h4>
            <div class="text-[10px] text-gray-600 mb-2 flex gap-3">
                <span>ID: ${p.id_producto}</span>
                <span>Cód: ${p.codigo}</span>
            </div>
            <div class="text-xs text-gray-400 mb-4 flex gap-4">
                <span class="bg-gray-800 px-2 py-1 rounded">Teórico: ${parseFloat(p.stock_ideal_unidades).toFixed(0)} botellas</span>
                ${p.pesable === 1 ? `<span class="bg-gray-800 px-2 py-1 rounded border border-gray-700">Tara: ${parseFloat(p.tara).toFixed(0)}g</span>` : ''}
            </div>
            
            <div class="grid grid-cols-2 gap-4">
                <div>
                    <label class="block text-[10px] font-bold text-gray-400 mb-1 tracking-wider uppercase">Cerradas</label>
                    <input type="number" min="0" class="w-full bg-dark-bg border border-gray-700 rounded-lg px-3 py-2 text-white input-cerradas focus:border-neon-green focus:outline-none focus:ring-1 focus:ring-neon-green" placeholder="0">
                </div>
            </div>
        `;

        // Sección Pesaje (Solo si es pesable)
        if (p.pesable === 1) {
            html += `
            <div class="mt-4 border-t border-gray-800 pt-4">
                <label class="block text-[10px] font-bold text-gray-400 mb-2 tracking-wider uppercase">Gramos en Abiertas</label>
                <div class="pesos-container grid grid-cols-2 gap-3" id="pesos-${p.id_producto}">
                    <div class="relative flex items-center">
                        <input type="number" min="0" step="1" class="w-full bg-dark-bg border border-gray-700 rounded-lg pl-3 pr-8 py-2 text-white input-peso focus:border-neon-pink focus:outline-none focus:ring-1 focus:ring-neon-pink" placeholder="Ej: 950">
                        <button type="button" onclick="this.parentElement.remove()" class="absolute right-2 text-gray-500 hover:text-red-400">
                            <span class="material-symbols-outlined text-sm">close</span>
                        </button>
                    </div>
                </div>
                <button type="button" onclick="agregarInputPeso(${p.id_producto})" class="mt-3 text-xs text-neon-pink font-semibold flex items-center gap-1 hover:text-white transition-colors uppercase tracking-wider">
                    <span class="material-symbols-outlined text-sm">add_circle</span> Añadir Botella
                </button>
            </div>
            `;
        }

        div.innerHTML = html;
        listaProductos.appendChild(div);
    });
}

// Función global para que el botón HTML la pueda llamar
window.agregarInputPeso = function(idProducto) {
    const container = document.getElementById(`pesos-${idProducto}`);
    const inputWrapper = document.createElement('div');
    inputWrapper.className = "relative flex items-center";
    
    inputWrapper.innerHTML = `
        <input type="number" min="0" step="1" class="w-full bg-dark-bg border border-gray-700 rounded-lg pl-3 pr-8 py-2 text-white input-peso focus:border-neon-pink focus:outline-none focus:ring-1 focus:ring-neon-pink" placeholder="Ej: 950">
        <button type="button" onclick="this.parentElement.remove()" class="absolute right-2 text-gray-500 hover:text-red-400">
            <span class="material-symbols-outlined text-sm">close</span>
        </button>
    `;
    container.appendChild(inputWrapper);
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
            const inputsPeso = card.querySelectorAll('.input-peso');
            inputsPeso.forEach(inp => {
                const val = parseFloat(inp.value);
                if (!isNaN(val)) pesosAbiertas.push(val);
            });

            // VALIDACIÓN FAT FINGER: ¿Demasiadas botellas abiertas?
            if (pesosAbiertas.length > 3) {
                advertenciaFatFinger = true;
                mensajeFatFinger += `- Registraste ${pesosAbiertas.length} botellas abiertas de ${nombreProducto}.\n`;
            }
        }

        // VALIDACIÓN MATEMÁTICA: Números negativos (por si saltan el HTML)
        if (cerradas < 0 || pesosAbiertas.some(p => p < 0)) {
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