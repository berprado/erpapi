# BackStage - API de Inventario POS

Backend REST construido con FastAPI y frontend PWA integrado para control de inventario fisico y auditoria de barra del sistema POS BackStage.

---

## Descripcion General

El flujo operativo actual es:

1. El usuario inicia sesion en la PWA.
2. La API valida que la operativa este en estado INICIO CIERRE (`24`) para permitir registrar o corregir paloteo. Si la operativa esta en otro estado, los modulos PALOTEO 1/2/3 permanecen accesibles pero en modo solo lectura: se puede consultar el ultimo paloteo registrado, sin poder editarlo (inputs y botones de ajuste deshabilitados en el frontend; la API rechaza cualquier intento de registro/correccion mientras el estado no sea `24`).
3. La app resuelve la barra operativa por entorno (con selector opcional controlado).
4. Se cargan productos pendientes para paloteo:
  - productos vendidos durante la operativa
  - productos traspasados de almacen a barra durante la operativa
5. Se registra inventario fisico desde PALOTEO 1/2/3 con un unico origen de datos. (estamos evaluando cual de las tres opciones de PALOTEO genera la menor friccion con el usuario al momento de ingresar los datos.)
6. Se visualiza reporte de diferencias y se puede exportar a PDF.
7. Autosave local conserva borradores por operativa, barra y usuario.

Durante el registro, la API convierte gramos a onzas, conserva onzas exactas en auditoria cruda y guarda para POS las onzas redondeadas a media onza.

---

## Stack Tecnologico

| Capa | Tecnologia |
|---|---|
| Backend | Python 3.x, FastAPI, SQLAlchemy, PyMySQL |
| Autenticacion | JWT (PyJWT, HS256) |
| Base de datos | MySQL (WAMP local / produccion) |
| Frontend | HTML, Tailwind CSS, JavaScript Vanilla |
| PWA | Service Worker, Web App Manifest |
| PDF | fpdf2 |
| Configuracion | Pydantic Settings, `.env` |

---

## Estructura del Proyecto

```text
erpapi/
|- main.py
|- models.py
|- schemas.py
|- database.py
|- config.py
|- branding.py
|- static/
|  |- index.html          (plantilla: placeholders __BRAND_*__, ver "Marca")
|  |- app.js
|  |- sw.js
|  |- cellar-sync-tokens.css
|  |- brands/              (override de colores por marca, uno por BRAND_ID)
|  |- imgs/
|  |  |- brands/            (logos por marca)
|  |- icons/
|  |  |- brands/            (favicons/iconos por marca)
|  |- pdfs/
|- querys/
|- documentos/
|- TODO.md
```

`static/manifest.json` ya no existe como archivo: `/assets/manifest.json` lo genera `main.py` en runtime según la marca activa (ver "Marca (branding) por instancia").

---

## Configuracion del Entorno

### 1. Requisitos

- Python 3.10+
- WAMP/MySQL en ejecucion
- `pip`

### 2. Instalar dependencias

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Variables de entorno

Crear un archivo `.env` en la raiz:

```env
APP_ENV=test

# Marca visual de esta instancia (logo/paleta). Ver "Marca (branding) por
# instancia" mas abajo. Valores validos: los definidos en branding.py.
BRAND_ID=backstage

# JWT (minimo 32 caracteres)
SECRET_KEY=tu_clave_secreta_muy_larga_y_aleatoria

# Base de datos test
TEST_DB_HOST=localhost
TEST_DB_USER=root
TEST_DB_PASS=
TEST_DB_NAME=nombre_base_de_datos
TEST_DB_PORT=3306

# Base de datos produccion
PROD_DB_HOST=host_produccion
PROD_DB_USER=usuario_prod
PROD_DB_PASS=contrasena_prod
PROD_DB_NAME=nombre_bd_prod
PROD_DB_PORT=3306

# Paloteo: barra operativa
PALOTEO_DEFAULT_BARRA_ID=1
PALOTEO_SELECTOR_ENABLED=false
PALOTEO_ALLOWED_BARRAS=1
```

Generar una `SECRET_KEY` segura:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

### 4. Levantar el servidor

```powershell
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

App: `http://localhost:8000/`
Docs: `http://localhost:8000/docs`

---

## Endpoints de la API

### Autenticacion

| Metodo | Ruta | Descripcion |
|---|---|---|
| `GET` | `/api` | Estado de la API |
| `GET` | `/api/health` | Verifica conexion a BD |
| `POST` | `/api/auth/login` | Inicio de sesion, devuelve JWT. Responde `429` si el usuario o la IP acumulan demasiados intentos fallidos en la ventana configurada (`LOGIN_MAX_INTENTOS_*`, `LOGIN_VENTANA_MINUTOS`); un login exitoso resetea el contador. Todo intento (exitoso o fallido) queda registrado en `app_login_auditoria_api` |

### Operacion (requiere JWT)

| Metodo | Ruta | Descripcion |
|---|---|---|
| `GET` | `/api/operacion/activa` | Valida estado de operativa para paloteo |
| `GET` | `/api/config/public` | Configuracion publica para frontend (entorno y barra operativa) |

### Inventario / Paloteo (requiere JWT)

| Metodo | Ruta | Descripcion |
|---|---|---|
| `GET` | `/api/inventario/pendientes` | Lista productos vendidos + traspasados a barra con configuracion de pesaje |
| `GET` | `/api/inventario/catalogo/buscar` | Busca en el catalogo completo de la barra (sin filtrar por movimiento), para agregar manualmente al conteo productos que no tuvieron movimiento esta operativa. `?busqueda=` es opcional (si se omite o va vacio, min. 2 caracteres si se especifica), devuelve resultados con la misma forma que `/pendientes`. `?limite=` (1-500, default 15) ajusta el tope de resultados; con `busqueda` vacia y `limite` alto trae el catalogo completo, para el flujo de "paloteo completo" |
| `POST` | `/api/inventario/paloteo` | Registra inventario fisico completo |
| `GET` | `/api/inventario/paloteo/{id_operacion}` | Obtiene inventario registrado y si puede editarse |
| `PUT` | `/api/inventario/paloteo/{id_inventario_pos}` | Corrige inventario fisico existente |
| `DELETE` | `/api/inventario/paloteo/{id_inventario_pos}/producto/{id_producto}` | Da de baja (soft-delete) el detalle de un solo producto, para deshacer una alta manual por error. A diferencia de `PUT` (upsert-only, nunca borra), este endpoint si elimina una fila puntual. No afecta `app_paloteo_registro_crudo` |

Reglas de correccion actuales:

1. Solo se corrige si la operativa sigue en estado `24`.
2. `id_operacion` e `id_barra` del payload deben coincidir con la cabecera existente.
3. La correccion actualiza de forma selectiva los productos enviados; los no enviados se conservan (no se borran).
4. Si la operativa cambia de estado, la API bloquea la correccion.
5. Para eliminar un producto puntual (no solo dejarlo sin enviar), usar `DELETE /api/inventario/paloteo/{id_inventario_pos}/producto/{id_producto}`.

Reglas de barra operativa:

1. Si `PALOTEO_SELECTOR_ENABLED=false`, la barra se fija por `PALOTEO_DEFAULT_BARRA_ID`.
2. Si `PALOTEO_SELECTOR_ENABLED=true`, frontend puede enviar `X-Barra-Id` (solo valores de `PALOTEO_ALLOWED_BARRAS`).
3. En `POST/PUT /api/inventario/paloteo`, `payload.id_barra` debe coincidir con la barra operativa resuelta.

### Perfiles de Pesaje (requiere JWT + rol administrador)

| Metodo | Ruta | Descripcion |
|---|---|---|
| `POST` | `/api/pesaje/perfiles` | Crea (o reactiva si existe uno eliminado con el mismo nombre) un modelo de botella para producto pesable. Regla general: calcula `gramos_por_oz` en el backend a partir del volumen estandar del producto. Excepción categoria VINOS (`id_categoria=6`): no se calcula por volumen; se fuerza `tara=0` y `gramos_por_oz=1`, y `peso_bruto` representa copas disponibles. El primer modelo activo de un producto se registra siempre como `Estándar`, alineado con el default de `app_producto_pesaje_config_api.nombre_perfil`; los modelos adicionales pueden tener nombre libre |
| `GET` | `/api/pesaje/categorias` | Lista de categorias habilitadas, para el filtro del modulo PESAJE |
| `GET` | `/api/pesaje/config` | Lista perfiles de pesaje (tabla `app_producto_pesaje_config_api`), con filtros opcionales `nombre`, `id_categoria`, `pesable`. Excluye siempre las categorias 10, 11, 13, 14, 15, 17, 18, 19 y 20. Para `pesable=1`, además de los perfiles existentes, incluye productos pesables habilitados (`alm_producto.ind_permite_comandar=71`) que todavía no tienen ninguna configuración activa, para que aparezcan en INCOMPLETOS. Ademas de los campos propios del perfil, hace `LEFT JOIN` a `vw_alm_producto_con_nombres` (por `id_producto`) para sumar `medida`, `nombre_unidad_medida`, `nombre_unidad_medida_detalle` y `nombre_ind_permite_comandar` — datos del producto que no dependen de la barra (a diferencia de existencias/cantidades, el peso bruto/tara/codigo de barras es el mismo sin importar donde este el producto), por eso no se usa `nombre_barra` de esa vista |
| `PUT` | `/api/pesaje/config/{id}` | Edita `peso_bruto`/`tara`/`barcode` de un perfil existente. `peso_bruto` y `tara` ya no son obligatorios juntos: alcanza con `peso_bruto` (la tara recien se conoce cuando se termina el contenido de la botella) y se puede completar despues con una segunda edicion. "Promover": si el perfil esta en `pesable=0` pero el catalogo dice que deberia ser pesable (`ind_permite_comandar=71` y categoria fuera de `CATEGORIAS_EXCLUIDAS_PESAJE`), cargar `peso_bruto` lo pasa a `pesable=1` directo desde aca — ya no hace falta editar la BD a mano para destrabar una fila fantasma (ver "Triggers de base de datos"). Si el catalogo no lo marca pesable, se sigue rechazando cualquier intento de tocar `peso_bruto`/`tara` (solo se permite `barcode`). En categoria VINOS (`id_categoria=6`) se valida y fuerza `tara=0` y `gramos_por_oz=1` (consistencia operativa por copas) — con `peso_bruto` alcanza para completarlo en un solo paso |
| `DELETE` | `/api/pesaje/config/{id}` | Elimina (soft-delete, `estado='DES'`) un perfil. Rechaza la eliminacion si es el ultimo perfil activo del producto |

Todos los endpoints de Pesaje requieren ademas que el usuario tenga el rol `ROLE_ADMIN` (verificado contra `seg_permiso`/`seg_rol`), devolviendo `403` si no lo tiene.

#### Consultas SQL de auditoría (PESAJE)

Universo objetivo del módulo (habilitados, pesables por catálogo y fuera de categorías excluidas):

```sql
SELECT COUNT(*) AS total_objetivo
FROM alm_producto a
WHERE a.estado = 'HAB'
  AND a.ind_permite_comandar = 71
  AND (a.id_categoria IS NULL OR a.id_categoria NOT IN (10,11,13,14,15,17,18,19,20));
```

Productos que deberían verse en INCOMPLETOS por no tener configuración activa:

```sql
SELECT a.id, a.codigo, a.nombre, a.id_categoria, c.nombre AS categoria, a.cantidad_detalle AS volumen_objetivo_oz
FROM alm_producto a
LEFT JOIN alm_categoria c ON c.id = a.id_categoria
WHERE a.estado = 'HAB'
  AND a.ind_permite_comandar = 71
  AND (a.id_categoria IS NULL OR a.id_categoria NOT IN (10,11,13,14,15,17,18,19,20))
  AND NOT EXISTS (
    SELECT 1
    FROM app_producto_pesaje_config_api p
    WHERE p.id_producto_almacen = a.id
      AND p.estado = 'HAB'
  )
ORDER BY a.nombre ASC;
```

Conflictos excepcionales (catálogo pesable vs configuración activa `pesable=0`):

```sql
SELECT DISTINCT a.id AS id_producto, a.codigo, a.nombre, a.id_categoria, c.nombre AS categoria,
       a.ind_permite_comandar, p.id AS id_pesaje_config, p.nombre_perfil, p.pesable, p.estado
FROM alm_producto a
INNER JOIN app_producto_pesaje_config_api p
  ON p.id_producto_almacen = a.id
 AND p.estado = 'HAB'
 AND p.pesable = 0
LEFT JOIN alm_categoria c ON c.id = a.id_categoria
WHERE a.estado = 'HAB'
  AND a.ind_permite_comandar = 71
  AND (a.id_categoria IS NULL OR a.id_categoria NOT IN (10,11,13,14,15,17,18,19,20))
ORDER BY a.nombre ASC;
```

Productos cuyo primer perfil activo no es `Estándar`:

```sql
SELECT
    p1.id_producto_almacen AS id_producto,
    a.codigo,
    a.nombre,
    p1.id AS id_primer_perfil_activo,
    p1.nombre_perfil AS nombre_primer_perfil
FROM app_producto_pesaje_config_api p1
INNER JOIN (
    SELECT id_producto_almacen, MIN(id) AS min_id_activo
    FROM app_producto_pesaje_config_api
    WHERE estado = 'HAB'
    GROUP BY id_producto_almacen
) x
    ON x.id_producto_almacen = p1.id_producto_almacen
   AND x.min_id_activo = p1.id
INNER JOIN alm_producto a
    ON a.id = p1.id_producto_almacen
WHERE p1.estado = 'HAB'
  AND p1.nombre_perfil <> 'Estándar'
ORDER BY a.nombre;
```

Nota operativa: el valor `Estándar` se usa de forma intencional y centralizada en backend/frontend para coincidir con el default de la columna `app_producto_pesaje_config_api.nombre_perfil` y evitar variantes como `ESTÁNDAR`.

### Triggers de base de datos: sincronizacion catalogo -> pesaje

Esta API no tiene ningun hook sobre altas/bajas de `alm_producto` (lo gestiona el ERP/POS), asi que dos triggers de MySQL sobre esa tabla mantienen `app_producto_pesaje_config_api` (y la tabla legacy `app_producto_pesaje_config`, no usada por esta API) sincronizada con el catalogo. **Viven en la base de datos de cada entorno, fuera de este repo** — no hay migraciones versionadas de DB; la definicion actual se guarda en `querys/` como fuente de verdad y hay que re-aplicarla manualmente si algun entorno se recrea:

- **`trg_alm_producto_after_insert`** (AFTER INSERT en `alm_producto`): al crear un producto, inserta una fila base en `app_producto_pesaje_config_api` con `pesable` derivado de `ind_permite_comandar=71` **y** de que la categoria no este en `CATEGORIAS_EXCLUIDAS_PESAJE` (la misma constante que usa `main.py`), `nombre_perfil='Estándar'` (default de columna) y `peso_bruto`/`tara`/`gramos_por_oz` en `NULL`. Un producto pesable nuevo cae asi directo en la pestaña INCOMPLETOS, visible y editable desde el primer momento.
- **`trg_alm_producto_after_update`** (AFTER UPDATE en `alm_producto`): sincroniza `estado` (HAB/DES) y re-evalua `pesable` con el mismo criterio cada vez que cambia el catalogo (ej. se habilita/deshabilita un producto, o cambia `ind_permite_comandar`). Solo promueve `pesable` de `0` a `1` si el perfil ya tiene `peso_bruto` y `gramos_por_oz > 0` reales cargados; en cualquier otro caso deja `pesable` como estaba — nunca auto-habilita un perfil con datos invalidos.

Definicion actual, aplicada y verificada (`SHOW CREATE TRIGGER`) en `test_pos` y produccion el 2026-07-30:
[querys/fix_trigger_alm_producto_after_insert.sql](querys/fix_trigger_alm_producto_after_insert.sql),
[querys/fix_trigger_alm_producto_after_update.sql](querys/fix_trigger_alm_producto_after_update.sql).

**Antecedente (por que la validacion de `pesable=1` importa):** antes de este fix, versiones anteriores de estos triggers podian dejar una fila "fantasma" en `pesable=0` con `nombre_perfil='Estándar'` para un producto que el catalogo si marca pesable. Como `app_producto_pesaje_config_api` tiene una clave unica real (`uk_producto_perfil` sobre `id_producto_almacen, nombre_perfil`), esa fila fantasma bloqueaba cualquier arreglo desde la app (`POST /perfiles` respondia 409 porque `'Estándar'` ya existia; `DELETE` respondia 400 por ser el ultimo perfil activo; `PUT` con `pesable=0` solo permitia editar `barcode`) — la unica salida era editar la BD directo, que es como se origino el bug de `PATRON SILVER 750ML` corregido en v10.94 (ver CHANGELOG). La limpieza puntual de los productos afectados en produccion quedo en `querys/fix_12_productos_atascados_produccion.sql`. **Desde v10.98, `PUT /api/pesaje/config/{id}` ya permite "promover" una fila fantasma directo desde la app** (ver la fila de esa ruta en la seccion de endpoints, mas arriba) — ya no hace falta SQL directo para este caso. Historial completo en `TODO.md` ("conflictos excepcionales de pesable").

### Reporte Paloteo 3 (requiere JWT)

| Metodo | Ruta | Descripcion |
|---|---|---|
| `POST` | `/api/paloteo3/exportar-pdf` | Genera y descarga PDF del reporte (general, ingreso o salida) |

Body ejemplo de exportacion:

```json
{
  "id_operacion": 42,
  "id_barra": 1,
  "usuario": "PEREZ MAMANI, JUAN",
  "tipo_reporte": "general",
  "filas": [
    {
      "idProducto": "101",
      "codigo": "LIC-001",
      "nombre": "WHISKY 750 ML",
      "difUnidades": 1,
      "difOnzas": -3.5
    }
  ]
}
```

`tipo_reporte` admite: `general`, `ingreso`, `salida`.

### Ajustes de Inventario (requiere JWT; aplicar requiere rol administrador)

| Metodo | Ruta | Descripcion |
|---|---|---|
| `POST` | `/api/inventario/consolidar/preview` | Calcula (desde BD, sin escribir nada) las diferencias paloteo-vs-POS para una operativa/barra: cuantos productos tienen diferencia, sobrantes/faltantes por paquete y por detalle (oz), y si ya existe un ajuste `APLICADO` para esa combinacion (`ya_aplicado`, `aplicado_por`, `aplicado_en`) |
| `POST` | `/api/inventario/ajustes/aplicar` | Aplica de forma definitiva las diferencias: crea `bar_ajuste`/`bar_salida_inventario` (con sus detalles) y actualiza `bar_inventario` para igualar el stock vivo al fisico contado. Solo administrador. Requiere operativa en estado `23` (CERRADA) e inventario fisico ya registrado |

Reglas:

1. Ambos endpoints exigen `_validar_operacion_cerrada` (operativa en estado `23`) y que `id_barra` coincida con la barra operativa resuelta (`_resolver_barra_operativa`).
2. `_calcular_diferencias_paloteo` es la unica fuente de verdad para las diferencias, compartida entre preview y aplicar: solo evalua productos que tienen fila en `bar_detalle_fisico` para ese inventario fisico (productos no contados no generan ajuste, aunque el modulo AJUSTES de la PWA -que itera sobre todo el catalogo de la barra- pueda mostrarlos como diferencia si su input quedo vacio en pantalla).
3. Si no hay diferencias, `aplicar` responde `status: "skipped"` sin crear nada.
4. Idempotencia: la tabla `app_paloteo_ajuste_control` registra cada aplicacion con `UNIQUE KEY (id_operacion, id_barra, id_inventario_fisico)`. Un segundo intento sobre la misma combinacion responde `409`.
5. Las cantidades se persisten con `Decimal`/`ROUND_HALF_UP` (nunca `float`), igual que el resto del modulo de pesaje.

---

### POUR COST (requiere JWT + rol administrador)

Modulo de solo lectura: calcula el costo de receta (WAC) y el pour cost % de combos/cocteles y productos sueltos comandables desde el POS. No escribe nada en `adminerp`; la simulacion (cambiar precio objetivo, WAC o receta) vive en el frontend, en memoria. Diseño completo en `documentos/pour_cost/pourcost.md`.

| Metodo | Ruta | Descripcion |
|---|---|---|
| `GET` | `/api/pourcost/menu?id_dia=1` | Menu activo (combos + productos sueltos) con su `precio_venta` para el `id_dia` pedido |
| `GET` | `/api/pourcost/recetas?id_dia=1` | Combos agregados desde `vw_pourcost_receta`: costo total de receta, `precio_venta` del `id_dia` pedido, pour cost % y la lista de ingredientes con su `cogs_ingrediente` |
| `GET` | `/api/pourcost/productos?id_dia=1` | Productos sueltos comandables (sin receta): costo = su WAC directo (`v9_cache_wac_producto`), sin agregacion de lineas |
| `GET` | `/api/pourcost/insumos` | Catalogo completo de insumos (`vw_alm_producto_con_nombres` + WAC) para la simulacion "agregar ingrediente" del frontend |

Reglas:

1. `id_dia` es un "horario de precio" (ej. jueves-sabado vs. domingo-lunes con tarifa distinta), no un dia calendario 1:1 — se selecciona manualmente en la UI, default `1`. Las vistas fuente traen su propio `precio_venta` fijo a `id_dia=1`; los endpoints lo ignoran y resuelven el precio aparte contra `v9_menubackstage` filtrando por el `id_dia` recibido.
2. `sin_wac`/`costo_incompleto` marcan ingredientes sin WAC cacheado (`cache_wac_producto` vacio) — no se ocultan ni se tratan como costo cero silencioso.
3. Las vistas fuente (`v9_menubackstage`, `vw_pourcost_receta`, `vw_alm_producto_con_nombres`, `v9_cache_wac_producto`) viven en MySQL, no en el ORM de este repo — mismo patron que los triggers de `alm_producto`. DDL versionado en `querys/create_views_pourcost.sql`; ya existen en `test_pos`, que es el entorno de desarrollo/validacion de este modulo (ver `documentos/pour_cost/pourcost.md`, seccion 2).
4. Sin `Aplicar Precio` (escritura en `ope_precio_venta`) todavia — explicitamente fuera de alcance de esta fase.

---

## Validaciones Activas (Frontend + Backend)

En el flujo de inventario fisico/paloteo se aplican estas validaciones clave:

1. No se permiten valores negativos en unidades o pesos.
2. Se exige unicidad de `id_producto` en `items` del payload.
3. Para pesables, se bloquea cuando `peso_medido > peso_bruto` del perfil seleccionado.
4. Para pesables, se bloquea cuando las onzas calculadas exceden `onzas_por_botella_llena`.
5. Campos vacios se confirman explicitamente y, si el usuario acepta, se completan en `0`.

---

## AJUSTES (Paloteo 3)

Vista renombrada de "REPORTE" a "AJUSTES" (mismo panel `#panel-scan`, mismos datos de diferencias). Funciones:

1. Filtro por tipo de ajuste: `Todos`, `Ingreso (+)`, `Salida (-)`.
2. Ordenamiento por columnas: `ID`, `COD`, `PRODUCTO`.
3. Coloreo semantico de diferencias:
  - `0`: verde
  - negativo: rojo
  - positivo: amarillo
4. Exportacion PDF coherente con filtro activo (columnas `DIF PAQ` y `DIF DET POS` unicamente; ya no incluye el valor exacto pre-redondeo):
  - `PALOTEO_<id>.pdf`
  - `PALOTEO_<id>_INGRESO.pdf`
  - `PALOTEO_<id>_SALIDA.pdf`
5. Generacion de PDF en memoria (sin escritura a disco) para evitar errores intermitentes en Windows.

### Bloque "Aplicar Ajustes" (solo administradores)

A diferencia de la tabla/PDF anteriores (calculados en cliente desde el catalogo completo de la barra, con `0` para productos sin valor capturado), el boton "Aplicar Ajustes" usa la fuente autoritativa de BD (`POST /api/inventario/consolidar/preview`), que solo considera productos con fila real en `bar_detalle_fisico`. Esto evita generar ajustes sobre productos que nunca se contaron.

Logica en `app.js` (`actualizarPanelAjustes()` / `aplicarAjustesInventario()`):

1. Bloque oculto por completo si el usuario no es administrador.
2. Si la operativa no esta en estado `23`, o no hay diferencias (`status: "skipped"`), se muestra un mensaje informativo en vez del boton.
3. Si ya existe un ajuste `APLICADO` para esa operativa/barra (`ya_aplicado` del preview), se muestra un badge "Ajustes aplicados por X el Y" en vez del boton.
4. Si hay diferencias sin aplicar, el boton queda habilitado; al hacer clic pide confirmacion con el resumen (productos/movimientos) antes de llamar a `POST /api/inventario/ajustes/aplicar`.
5. Maneja exito, `skipped`, `409` (ya aplicado por otra sesion) y errores de red/servidor con los dialogos `mostrarDialogoResultado`/`mostrarDialogoConfirmacion` existentes.

---

## Logica de Conversion de Pesos

Para cada botella abierta:

1. Se valida `peso_medido >= (tara - 10g)`.
2. Se calcula `peso_liquido = max(0, peso_medido - tara)`.
3. Se convierte a onzas: `onzas = peso_liquido / gramos_por_oz`.
4. Se guarda el total exacto en `app_paloteo_registro_crudo`.
5. Se redondea para POS: `onzas_pos = round(total_onzas * 2) / 2`.

Excepción operativa en VINOS (`id_categoria=6`):

1. Se conserva la misma fórmula para mantener consistencia técnica.
2. Se usa `peso` como copas disponibles (entrada visual del encargado).
3. Se fuerza `tara = 0` (constante).
4. Se fuerza `gramos_por_oz = 1` (constante).
5. El resultado operativo queda `contenido = (copas - 0) / 1 = copas`.

---

## Modelos de Base de Datos (mapeados en API)

| Tabla | Descripcion |
|---|---|
| `seg_usuario` | Usuarios |
| `seg_acceso` | Auditoria de accesos exitosos (compatibilidad POS) |
| `app_login_auditoria_api` | Auditoria de intentos de login de la PWA (exito/fallo, motivo, IP); soporta el rate limit del login. DDL en [querys/ddl_app_login_auditoria_api.sql](querys/ddl_app_login_auditoria_api.sql) |
| `seg_rol` | Catalogo de roles (ej. `ROLE_ADMIN`) |
| `seg_permiso` | Asignacion de roles por usuario (tabla puente N:M) |
| `ope_operacion` | Operativas |
| `app_producto_pesaje_config_api` | Configuracion/perfiles de pesaje (incluye `estado` para soft-delete y `barcode`); sincronizada desde `alm_producto` por triggers de BD externos al repo, ver "Triggers de base de datos" en la seccion de PESAJE |
| `bar_inventario_fisico` | Cabecera inventario fisico POS |
| `bar_detalle_fisico` | Detalle inventario fisico POS |
| `app_paloteo_registro_crudo` | Auditoria cruda de pesajes |
| `bar_inventario` | Stock vivo por barra/producto (actualizado por `POST /api/inventario/ajustes/aplicar`) |
| `bar_ajuste` / `bar_detalle_ajuste` | Cabecera/detalle de ingresos por ajuste generados al aplicar diferencias |
| `bar_salida_inventario` / `bar_detalle_salida_inv` | Cabecera/detalle de salidas por ajuste generadas al aplicar diferencias |
| `app_paloteo_ajuste_control` | Control de idempotencia: una fila `APLICADO` por `(id_operacion, id_barra, id_inventario_fisico)`. DDL en [documentos/DOCUMENTACION_INGRESOS_SALIDAS_AJUSTE_PWA.md](documentos/DOCUMENTACION_INGRESOS_SALIDAS_AJUSTE_PWA.md) |

---

## PWA Frontend

La PWA se sirve desde `/` y assets desde `/assets`.

### Marca (branding) por instancia

Cada instancia desplegada (casa matriz, cada sucursal) corre el mismo
código — mismo repo, misma rama `main` — y elige su piel visual (logo,
paleta, título, favicons) con una sola variable de entorno, `BRAND_ID`,
igual que `APP_ENV` elige la base de datos. No se crean ramas ni copias del
repo por marca; ver `documentos/despliegue_seenode.md`.

- `branding.py` define el diccionario `BRANDS`: por marca, título, nombre
  de app, `theme_color`, carpeta de íconos, rutas de logo (login/navbar
  completo/navbar colapsado) y si el efecto glitch del login está activo.
- Los **colores** no viven en `branding.py` sino como CSS custom
  properties: `static/cellar-sync-tokens.css` define los valores por
  defecto (marca `backstage`) y `static/brands/<BRAND_ID>.css` los
  sobreescribe por cascada (el `<link>` de la marca se carga después). El
  `tailwind.config` embebido en `index.html` lee esas mismas variables
  (`var(--primary-container)`, etc.) en vez de hex propios, para que no
  existan dos paletas hardcodeadas por separado.
- `index.html` es una plantilla con placeholders `__BRAND_TITLE__`,
  `__BRAND_APP_NAME__`, `__BRAND_THEME_COLOR__`, `__BRAND_ICON_DIR__`,
  `__BRAND_CSS_HREF__`, `__BRAND_LOGO_LOGIN__`,
  `__BRAND_LOGO_NAVBAR_FULL__`, `__BRAND_LOGO_NAVBAR_ISOTIPO__` y
  `__BRAND_GLITCH_ENABLED__`, que `GET /` (`main.py`) completa con la marca
  activa antes de responder. `GET /assets/manifest.json` se genera igual
  en runtime (`branding.build_manifest`) en vez de ser un archivo estático.
- Colores funcionales (error/warning/info/success) **no** varían por
  marca a propósito: son lenguaje semántico de UI, no identidad visual.
- El PDF de exportación de PALOTEO 3 (`exportar_pdf_paloteo3`) también es
  consciente de la marca: `_LOGO_PATH` toma `logo_navbar_full` de la marca
  activa en vez de un archivo fijo.

Para dar de alta una marca nueva: agregar sus assets en
`static/imgs/brands/<id>/` y `static/icons/brands/<id>/`, crear
`static/brands/<id>.css` con el override de colores, agregar la entrada en
`branding.py` y setear `BRAND_ID=<id>` en las env vars de esa instancia de
Seenode.

**Instancias en producción hoy** (ver "Instancias desplegadas actualmente"
en `documentos/despliegue_seenode.md` para la tabla completa y mantenida):
casa matriz en https://erpapi.seenode.app/ (`BRAND_ID=backstage`, default) y
la sucursal Beer Garden en https://erpapi-2.seenode.app/
(`BRAND_ID=beer_garden`) — mismo repo y rama `main`, cada una con su propia
base de datos vía un túnel LocalToNet distinto.

Flujo actual de navegacion:

- PALOTEO 1
- PALOTEO 2
- PALOTEO 3 (captura ciega)
- AJUSTES (diferencias, exportacion PDF y, solo administradores, aplicar el ajuste definitivo contra `bar_inventario`)
- PESAJE (CRUD de modelos de botella y codigos de barra; solo visible/accesible para usuarios con rol `ROLE_ADMIN`). Cada tarjeta de producto pesable ofrece dos acciones: EDITAR (modal de modelos/codigos de barra) y CALCULAR (calculadora de peso a onzas integrada; ex-modulo CONVERSOR). CALCULAR solo aparece en productos pesables con todos sus perfiles completos.
- POUR COST (solo lectura + simulacion; solo visible/accesible para `ROLE_ADMIN`). Costo de receta/WAC y pour cost % de cocteles y productos sueltos, con un sandbox de simulacion en memoria (precio objetivo, WAC/cantidad) que nunca escribe en el backend.

Sincronizacion entre modulos:

1. Cambios en PALOTEO 1, PALOTEO 2 y PALOTEO 3 se reflejan entre vistas.
2. El payload final se construye desde el inventario canonico.
3. Autosave guarda y recupera borradores locales por `operativa + barra + usuario`.

### Agregar productos sin movimiento (paloteo completo)

El buscador unico del navbar (compartido por PALOTEO 1/2/3) permite agregar al
conteo activo productos que no tuvieron movimiento esta operativa, sin
necesidad de recargar la pagina:

- Al tipear (2+ caracteres) y no haber coincidencias locales, se ofrece
  buscar en el catalogo completo de la barra (`GET /api/inventario/catalogo/buscar`)
  y agregar un resultado puntual al conteo.
- El boton "Ver catalogo completo" (icono junto al buscador) trae de una vez
  el catalogo entero de la barra, con y sin movimiento, para el caso de un
  **paloteo completo** (recontar todo el inventario, no solo lo que tuvo
  movimiento).
- El boton "Agregar todos (N)" en el panel de resultados agrega en bloque
  todo lo listado en ese momento (sea el catalogo completo o el resultado de
  una busqueda puntual, ej. una categoria), pidiendo confirmacion antes por
  el volumen que puede implicar.
- Los productos agregados asi quedan marcados visualmente en las tres vistas
  (PALOTEO 1, PALOTEO 2 y PALOTEO 3): borde/glow distintivo (`card-agregado-manual`)
  y badge "Sin movimiento" junto al ID/Codigo. La marca se decide en runtime
  a partir de `producto._agregadoManual` dentro de `crearTarjetaProductoElement`/
  `crearFilaPaloteo3` (no se aplica una sola vez desde afuera), para que
  sobreviva a cualquier re-render — `refrescarPaloteo3DesdeInventario()` se
  dispara en cada tecla escrita en PALOTEO 1, y `renderTarjetaCaptura()`
  reconstruye la tarjeta de PALOTEO 2 en cada navegacion.
- Se pueden quitar individualmente desde cualquiera de las tres vistas (boton
  "x", oculto en modo solo lectura) (`DELETE
  /api/inventario/paloteo/{id}/producto/{id_producto}` si el paloteo ya se
  guardo). Pasan por las mismas validaciones que cualquier otro producto del
  conteo (ver "Validaciones Activas"): si sus campos quedan vacios, se
  ofrece confirmarlos como `0` antes de enviar, exactamente igual que un
  producto con movimiento.

### PALOTEO 3: captura ciega y botones de ajuste

El paloteo compara el inventario ideal (segun el POS) contra el inventario
real (conteo fisico de cerradas + peso de abiertas convertido a onzas); la
diferencia es lo que el modulo AJUSTES materializa como ingreso/salida
(ver "Ajustes de Inventario" mas arriba). Por eso PALOTEO 3 es "captura ciega": a diferencia de
PALOTEO 1/2, no muestra el ideal del sistema ni el delta en tiempo real,
para que quien cuenta fisicamente no pueda ajustar su conteo para disimular
faltantes.

En la misma linea, los botones +/- de ajuste rapido (unidades y peso) en
PALOTEO 3 solo son visibles para usuarios con `is_admin` (helper
`esUsuarioAdministrador()` en `app.js`), ya que facilitan "redondear" un
valor sin haber contado/pesado con precision. El boton "+ Botella" (agregar
una entrada de peso) y el de eliminar una entrada agregada por error siguen
disponibles para todos los usuarios, porque solo gestionan la estructura de
inputs, no el valor capturado. Es una restriccion de frontend (oculta el
boton, no protege un endpoint) — pendiente aplicar el mismo criterio en
PALOTEO 1 y 2.

PALOTEO 1 y PALOTEO 3 muestran una barra "Capturados: X / Y (Z%)" que
cuenta cuantos productos ya tienen unidades/peso ingresados
(`tarjetaCompleta()` + `actualizarResumenProgreso*()` en `app.js`). No
revela el inventario ideal, solo el avance de la captura, y se mantiene
sincronizada entre ambos modulos porque comparten el mismo origen de datos.

### Modulo PESAJE: detalles de UI

- **Grid responsivo de tarjetas resumen** (`#pesaje-list`, `grid-template-columns: repeat(auto-fill, minmax(240px, 1fr))`): la cantidad de tarjetas por fila se adapta sola al ancho del dispositivo, sin breakpoints manuales. Cada tarjeta muestra categoria, nombre, ID/codigo, `medida`+`nombre_unidad_medida` (ej. "750 ML"), `cantidad_detalle`+`nombre_unidad_medida_detalle` (ej. "25 Oz." — la unidad varia por producto, no siempre es onzas), badge "Comanda: Si/No" y, si tiene mas de un perfil, un badge con la cantidad de modelos.
- **Tres pestañas de filtro**: PESABLES, INCOMPLETOS y NO PESABLES. Las dos primeras piden el mismo `GET /api/pesaje/config?pesable=1` y se separan en cliente (`pesajeProductoTieneIncompleto()`: algun perfil sin `peso_bruto`/`tara`, con `peso_bruto<=0`, con `gramos_por_oz<=0`, o sin modelos activos); NO PESABLES pide `pesable=0`. Un producto que completa su ultimo perfil incompleto pasa solo de INCOMPLETOS a PESABLES en el siguiente refresco, sin accion manual. `tara=0` sigue siendo valido (no cuenta como incompleto), ya que el schema lo permite explicitamente; el umbral `<=0` aplica solo a `peso_bruto` y `gramos_por_oz`, que la API siempre calcula/valida como positivos cuando el perfil se crea o edita correctamente — un valor en `0` ahi solo puede venir de datos historicos escritos fuera de la API (ver v10.94 en el changelog).
- **NO PESABLES ya no es un callejon sin salida (desde v10.98, "promover")**: dentro de esa pestaña, una tarjeta con `pesable=0` muestra los campos de peso (ademas de `barcode`) si el catalogo dice que el producto deberia ser pesable (`nombre_ind_permite_comandar` = "Si" — el listado ya garantiza que si el producto llego hasta el frontend, su categoria no esta excluida). Cargar `peso_bruto` la promueve a `pesable=1` sin editar la BD a mano. Si el catalogo no lo marca pesable (`nombre_ind_permite_comandar` = "No"), la tarjeta se comporta igual que siempre: solo `barcode` editable.
- **Dos acciones por tarjeta**: cada tarjeta tiene en su parte inferior los botones EDITAR y, solo en pesables completos, CALCULAR. EDITAR abre el modal de edicion (`#pesaje-modal`); CALCULAR abre la calculadora (`#conversor-modal`, ver "Calculadora peso -> onzas") reutilizando los perfiles ya cargados del producto (sin fetch adicional). En NO PESABLES e INCOMPLETOS la tarjeta solo muestra EDITAR.
- **Modal de edicion** (`#pesaje-modal`, mismo patron que `#conversor-modal`): se abre con EDITAR y muestra exactamente lo que antes se veia inline por perfil (`peso_bruto`, `tara`, `g/oz` recalculado en vivo, `barcode`, botones Guardar/Eliminar) mas el boton "Agregar modelo". Los campos de modelo de botella (`peso_bruto`/`tara`/`g/oz`) se muestran si el perfil ya es `pesable=1` **o** si el catalogo dice que deberia serlo (`nombre_ind_permite_comandar`="Si", habilita "promover" — ver v10.98); solo en un producto genuinamente no pesable por catalogo el modal muestra unicamente el codigo de barras. Los perfiles con `peso_bruto`/`tara` nulos o con `peso_bruto`/`gramos_por_oz` en `0` se siguen marcando con borde de advertencia + icono "Incompleto" dentro del modal (por perfil, relevante si un producto tiene varios modelos y solo uno esta incompleto).
- Al crear el primer modelo de un producto sin perfiles activos, el nombre se fija en `Estándar` por defecto; a partir del segundo modelo, el nombre vuelve a ser editable.
- Si el modal esta abierto cuando se guarda/agrega/elimina un perfil, su contenido se refresca en el lugar con los datos nuevos (`renderizarModalPesaje()`) en vez de cerrarse — incluso si el producto "cambio de pestaña" (ej. paso de INCOMPLETOS a PESABLES al completarse). Se cierra solo si el producto deja de existir en la respuesta.
- Excluye productos de las categorias 10, 11, 13, 14, 15, 17, 18, 19 y 20 (tanto en el listado como en el filtro de categorias).

### Calculadora peso -> onzas (integrada en PESAJE, ex-modulo CONVERSOR)

- Antes era un modulo independiente con su propio tab y endpoint (`/api/conversor/productos`); se consolido dentro de PESAJE como el boton CALCULAR de cada tarjeta de producto pesable completo. Al ser parte de PESAJE, hereda su acceso solo-administrador. El tab y el endpoint fueron eliminados.
- No escribe nada en BD ni depende del estado de la operativa. `abrirCalculadoraDesdePesaje()` adapta el producto ya cargado en la tarjeta (perfiles con `tara`/`gramos_por_oz`, descartando incompletos) a la forma que espera la modal, sin fetch adicional.
- Abre una ventana modal (`#conversor-modal`) con el mismo patron visual y de cierre (overlay, boton X, tecla Esc) que los modales "Guia Operativa" y "Boletin" (`#dummy-content-dialog`).
- Dentro de la modal se pueden agregar varias "botellas" (una fila por cada una), cada una con su propio selector de modelo si el producto tiene mas de un perfil (`resolverPerfilSeleccionado()`, reutilizado de PALOTEO). El calculo (`peso_liquido = max(0, peso - tara)`, `onzas = peso_liquido / gramos_por_oz`, redondeo HALF_UP con `redondearOnzasOperativas()`) se ejecuta en cliente y muestra tanto el total exacto como el redondeado POS.
- Cerrar la modal reinicia el estado (no hay boton "Limpiar" separado), ya que no persiste nada entre aperturas.

### Modulo POUR COST: detalles de UI

- Mismo patron visual/estructural que PESAJE (tarjetas + modal de detalle), pero de solo lectura + simulacion: no hay accion "Guardar" en ningun lado del modulo. Solo visible/accesible para `ROLE_ADMIN`, igual criterio que PESAJE.
- Toggle **Cocteles / Productos sueltos** (`pourCostEstado.tipo`) determina que endpoint se consulta (`/api/pourcost/recetas` o `/api/pourcost/productos`) — son datasets y formas de tarjeta distintas, no un filtro sobre los mismos datos.
- Selector **Precios A / Precios B** (`pourCostEstado.idDia`, query param `id_dia`) es una eleccion manual del usuario, no se infiere de la operativa activa (decision de diseno, ver `documentos/pour_cost/pourcost.md` seccion 8.2) — cambiarlo vuelve a pedir datos al backend porque el precio depende del horario elegido.
- El filtro de categoria se llena en cliente a partir del dataset ya cargado (no hay endpoint `/api/pourcost/categorias`); cambia junto con el toggle de tipo.
- Cada tarjeta muestra el pour cost % en un badge coloreado: verde (`badge-ok`, <=28%), ambar (`badge-caution`, 28-35%) o rojo (`badge-danger`, >35%) — cortes definidos por el negocio, no un estandar generico. `badge-caution` es una clase nueva porque `badge-warning` ya estaba tomada por el rojo de diferencias de PALOTEO/AJUSTES.
- Al hacer click en una tarjeta se abre `#pourcost-modal` con el desglose real (receta con `cogs_ingrediente` por linea, o WAC directo en productos sueltos) y el sandbox de simulacion: cantidad/WAC editables por ingrediente y un campo de % objetivo que calcula el precio sugerido (exacto + redondeado a unidad entera) y su diferencia contra el precio actual. Todo el calculo (`pourCostCalcularPct`, `pourCostCalcularPrecioSugerido`, `pourCostRedondearHalfUp`) es JS puro que espeja exactamente las funciones de `main.py` (mismo HALF_UP manual que `redondearOnzasOperativas`, no `Math.round`) — nunca se envia nada al backend, "Reiniciar simulacion" descarta los cambios volviendo a clonar el item original.

### FAB "volver al inicio"

Boton flotante reutilizable (clase `fab-scroll-top` + funcion `inicializarFabScrollTop(fabId, panelId)` en `app.js`) presente en PALOTEO 1, PALOTEO 3, AJUSTES, PESAJE y POUR COST. Aparece al hacer scroll mas alla de un umbral y solo si su panel esta activo; al hacer click hace scroll suave al inicio de la pagina. Para agregarlo a un nuevo modulo: insertar un boton con esa clase dentro del panel y llamar a la funcion con sus ids.

Service Worker:

- Cache First para assets estaticos.
- Network First para llamadas `/api/*`.

---

## Seguridad

- Verificacion de contrasena con SHA-256 (compatibilidad POS).
- JWT con expiracion de 10 horas.
- Endpoints de negocio protegidos con HTTPBearer.
- Control de acceso por rol (`ROLE_ADMIN` via `seg_permiso`/`seg_rol`) para el modulo PESAJE y para `POST /api/inventario/ajustes/aplicar`. La respuesta de login incluye `is_admin` para que el frontend oculte la opcion de menu/boton a usuarios sin ese rol.
- Validacion de longitud minima de `SECRET_KEY` en configuracion.
- Anti-enumeracion en login: la contrasena se valida antes que el estado de la cuenta y usuario inexistente/contrasena incorrecta comparten el mismo `401` generico.
- Rate limit de login respaldado en `app_login_auditoria_api`: maximo `LOGIN_MAX_INTENTOS_USUARIO` (default 5) fallos por usuario y `LOGIN_MAX_INTENTOS_IP` (default 20) por IP dentro de `LOGIN_VENTANA_MINUTOS` (default 5); al superarlo responde `429`. La IP se resuelve priorizando `X-Forwarded-For` (reverse proxy). Fail-open: si la tabla no existe aun en el entorno, el login sigue funcionando y el freno queda inactivo (warning en logs).
- CORS deshabilitado por defecto (la PWA se sirve desde el mismo origen que la API). Para permitir clientes externos, definir `CORS_ALLOWED_ORIGINS` en `.env` (origenes separados por coma).
- Cabeceras de seguridad en toda respuesta: `Content-Security-Policy` (permite solo Tailwind CDN, Google Fonts e inline propio; `connect-src 'self'` bloquea exfiltracion del token), `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`. `/docs` y `/redoc` quedan exentos de CSP porque Swagger UI usa cdn.jsdelivr.net.

---

## Entornos

| APP_ENV | Base de datos |
|---|---|
| `test` | WAMP local (`TEST_DB_*`) |
| `production` | Servidor remoto (`PROD_DB_*`) |

---

## Pendientes

Ver `TODO.md` para el backlog actualizado.

## Documentacion Adicional

- [Proceso de Almacenamiento de Paloteo](documentos/DOCUMENTACION_ALMACENAMIENTO_PALOTEO.md)
