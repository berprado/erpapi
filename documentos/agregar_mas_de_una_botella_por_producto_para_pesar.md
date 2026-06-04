Debemos considerar la posibilidad de que para un mismo producto pueda existir mas de un modelo de botella, eso significa el mismo producto con el mismo volumen pero con un peso bruto diferente y una tara diferente al registrado. 
En ese caso, nuestra aplicacion debera permitir el registro de botellas adicionales para poder convertir el peso en gramos a onzas.
Para eso hemos modificado la estructura de la tabla app_producto_pesaje_config_api y debemos realizar algunas modificaciones en el codigo segun los siguientes lineamientos

### Paso 1: Modificar el Backend (Python)

Como ahora la base de datos nos devolverá varias filas si un mismo producto tiene botellas distintas para un mismo volumen, tenemos que hacer que FastAPI las "agrupe" en una lista dentro del JSON.

**A. En el archivo `schemas.py`**, actualiza los modelos:
```python
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional

# --- NUEVO MODELO PARA LOS PERFILES ---
class PerfilPesaje(BaseModel):
    nombre_perfil: str
    peso_bruto: float
    tara: float
    gramos_por_oz: float
    tolerancia_oz: float

# --- ACTUALIZAMOS ProductoPendiente ---
class ProductoPendiente(BaseModel):
    id_producto: int
    codigo: str
    nombre: str
    categoria_nombre: Optional[str] = None
    ind_permite_comandar: int
    stock_ideal_unidades: float
    stock_ideal_onzas: float
    pesable: Optional[int] = None
    perfiles: List[PerfilPesaje] = [] # <-- REEMPLAZA A LOS CAMPOS SUELTOS DE TARA Y PESO
    onzas_por_botella_llena: float
```

**B. En el archivo `main.py`**, actualiza el endpoint `obtener_productos_pendientes` para que agrupe los resultados:
```python
@app.get("/api/inventario/pendientes", response_model=List[schemas.ProductoPendiente])
def obtener_productos_pendientes(
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_usuario_actual)
):
    query = text("""
        SELECT 
            a.id AS id_producto, a.codigo, a.nombre, a.ind_permite_comandar,
            i.cantidad_paq AS stock_ideal_unidades, i.cantidad_detalle AS stock_ideal_onzas,
            i.categoria_nombre,
            p.pesable, p.nombre_perfil, p.peso_bruto, p.tara, p.gramos_por_oz, p.tolerancia_oz,
            a.cantidad_detalle AS onzas_por_botella_llena
        FROM (
            SELECT DISTINCT d.id_producto_receta 
            FROM comandas_v9_detallada d
            INNER JOIN bar_comanda c ON d.id_comanda = c.id
            WHERE d.id_operacion = (SELECT MAX(id_operacion) FROM bar_comanda)
            AND c.estado_comanda = 26
        ) mov
        INNER JOIN alm_producto a ON mov.id_producto_receta = a.id
        INNER JOIN vista_inventario_barra_con_filtro i ON a.id = i.id_almacen 
        LEFT JOIN app_producto_pesaje_config_api p ON a.id = p.id_producto_almacen
        ORDER BY a.nombre ASC;
    """)
    
    rows = db.execute(query).mappings().all()
    
    # Lógica de Agrupación en Python
    productos_dict = {}
    for row in rows:
        prod_id = row['id_producto']
        if prod_id not in productos_dict:
            productos_dict[prod_id] = {
                "id_producto": prod_id,
                "codigo": row['codigo'],
                "nombre": row['nombre'],
                "categoria_nombre": row['categoria_nombre'],
                "ind_permite_comandar": row['ind_permite_comandar'],
                "stock_ideal_unidades": row['stock_ideal_unidades'],
                "stock_ideal_onzas": row['stock_ideal_onzas'],
                "pesable": row['pesable'],
                "onzas_por_botella_llena": row['onzas_por_botella_llena'],
                "perfiles": []
            }
        
        # Si es pesable y tiene un perfil configurado, lo añadimos a su lista
        if row['pesable'] == 1 and row['nombre_perfil']:
            productos_dict[prod_id]["perfiles"].append({
                "nombre_perfil": row['nombre_perfil'],
                "peso_bruto": float(row['peso_bruto']),
                "tara": float(row['tara']),
                "gramos_por_oz": float(row['gramos_por_oz']),
                "tolerancia_oz": float(row['tolerancia_oz'])
            })
            
    return list(productos_dict.values())
```

---

### Paso 2: Modificar el Frontend (JavaScript)

En `static/app.js`, debes inyectar toda la lista de perfiles en la tarjeta y generar el menú desplegable solo si hay más de una opción.

**1. Actualiza `crearInputPeso`:**
```javascript
// Actualizamos para recibir los perfiles en formato JSON string
function crearInputPeso(perfilesJson) {
    const perfiles = JSON.parse(perfilesJson || '[]');
    let selectHTML = '';
    
    // Si hay más de un perfil, mostramos el combo desplegable
    if (perfiles.length > 1) {
        selectHTML = `<select class="bg-gray-800 text-[10px] text-neon-green border border-gray-700 rounded-lg px-2 py-2 focus:outline-none select-perfil mr-2 cursor-pointer">`;
        perfiles.forEach((pf, idx) => {
            selectHTML += `<option value="${idx}">${escapeHtml(pf.nombre_perfil)}</option>`;
        });
        selectHTML += `</select>`;
    }

    return `
        <div class="relative flex items-center item-peso-wrapper">
            ${selectHTML}
            <div class="relative flex-1">
                <input type="number" min="0" step="1" class="w-full bg-dark-bg border border-gray-700 rounded-lg pl-3 pr-8 py-2 text-white input-peso focus:border-neon-pink focus:outline-none focus:ring-1 focus:ring-neon-pink" placeholder="Ej: 950">
                <button type="button" onclick="this.parentElement.parentElement.remove()" class="absolute right-2 top-2 text-gray-500 hover:text-red-400">
                    <span class="material-symbols-outlined text-sm">close</span>
                </button>
            </div>
        </div>
    `;
}
```

**2. Actualiza `renderizarProductos`:**
Cambia cómo guardamos los datos en el `dataset` y la llamada a `crearInputPeso`:
```javascript
        // Reemplaza los datos individuales por el array completo de perfiles
        const perfilesJson = JSON.stringify(p.perfiles || []);
        div.dataset.perfiles = perfilesJson;
        
        // (Para la tolerancia general, usamos la del primer perfil o 0)
        div.dataset.tolerancia = p.perfiles && p.perfiles.length > 0 ? p.perfiles[0].tolerancia_oz : 0;
        
        // ... (el resto del html igual, pero actualiza la parte del pesaje):
        if (p.pesable === 1) {
            html += `
            <div class="mt-4 border-t border-gray-800 pt-4">
                <label class="block text-[10px] font-bold text-gray-400 mb-2 tracking-wider uppercase">Gramos en Abiertas</label>
                <div class="pesos-container grid grid-cols-1 sm:grid-cols-2 gap-3" id="pesos-${p.id_producto}">
                    ${crearInputPeso(perfilesJson)}
                </div>
                <button type="button" onclick="agregarInputPeso(${p.id_producto}, '${perfilesJson.replace(/'/g, "\\'")}')" class="mt-3 text-xs text-neon-pink font-semibold flex items-center gap-1 hover:text-white transition-colors uppercase tracking-wider">
                    <span class="material-symbols-outlined text-sm">add_circle</span> Añadir Botella
                </button>
            </div>
            `;
        }
```

**3. Actualiza `agregarInputPeso` y la lógica de cálculo (`recalcularTarjeta`):**
```javascript
window.agregarInputPeso = function(idProducto, perfilesJson) {
    const container = document.getElementById(`pesos-${idProducto}`);
    const inputWrapper = document.createElement('div');
    inputWrapper.innerHTML = crearInputPeso(perfilesJson);
    container.appendChild(inputWrapper.firstElementChild);
}

// Dentro de recalcularTarjeta(card) reemplaza la parte del pesaje por esto:
    if (pesable === 1) {
        const perfiles = JSON.parse(card.dataset.perfiles || '[]');
        const inputsPeso = card.querySelectorAll('.input-peso');
        const spanDet = document.getElementById(`val-det-${idProducto}`);
        const difDetSpan = document.getElementById(`dif-det-${idProducto}`);
        
        let detBarra = 0;
        const margenError = 10.0; 
        
        inputsPeso.forEach(inp => {
            const wrapper = inp.closest('.item-peso-wrapper');
            const select = wrapper.querySelector('.select-perfil');
            const perfilIndex = select ? select.value : 0;
            const perfil = perfiles[perfilIndex] || perfiles[0];
            
            if(!perfil) return;

            const tara = parseFloat(perfil.tara);
            const groz = parseFloat(perfil.gramos_por_oz);
            const pesoMedido = parseFloat(inp.value);
            
            if (!isNaN(pesoMedido) && pesoMedido >= (tara - margenError)) {
                const pesoLiquido = Math.max(0, pesoMedido - tara);
                detBarra += (pesoLiquido / groz);
            }
        });
        
        if (spanDet) spanDet.textContent = detBarra.toFixed(2);
        if (difDetSpan) difDetSpan.innerHTML = formatearDiferencia(detBarra - detSist, true, tolerancia);
    }
```