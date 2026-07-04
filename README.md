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
|- static/
|  |- index.html
|  |- app.js
|  |- sw.js
|  |- manifest.json
|  |- cellar-sync-tokens.css
|  |- imgs/
|  |- icons/
|  |- pdfs/
|- querys/
|- documentos/
|- TODO.md
```

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
| `POST` | `/api/auth/login` | Inicio de sesion, devuelve JWT |

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
| `POST` | `/api/pesaje/perfiles` | Crea (o reactiva si existe uno eliminado con el mismo nombre) un modelo de botella para producto pesable. Calcula `gramos_por_oz` en el backend a partir del volumen estandar del producto |
| `GET` | `/api/pesaje/categorias` | Lista de categorias habilitadas, para el filtro del modulo PESAJE |
| `GET` | `/api/pesaje/config` | Lista perfiles de pesaje (tabla `app_producto_pesaje_config_api`), con filtros opcionales `nombre`, `id_categoria`, `pesable`. Excluye siempre las categorias 15, 18, 19 y 20 |
| `PUT` | `/api/pesaje/config/{id}` | Edita `peso_bruto`/`tara`/`barcode` de un perfil existente. En productos no pesables solo se permite editar `barcode` |
| `DELETE` | `/api/pesaje/config/{id}` | Elimina (soft-delete, `estado='DES'`) un perfil. Rechaza la eliminacion si es el ultimo perfil activo del producto |

Todos los endpoints de Pesaje requieren ademas que el usuario tenga el rol `ROLE_ADMINISTRADOR` (verificado contra `seg_permiso`/`seg_rol`), devolviendo `403` si no lo tiene.

### Conversor (requiere JWT)

| Metodo | Ruta | Descripcion |
|---|---|---|
| `GET` | `/api/conversor/productos` | Catalogo completo de productos pesables (`pesable=1`, excluye categorias 15, 18, 19 y 20), agrupados con sus perfiles. No filtra por operativa, barra ni movimiento reciente |

A diferencia de `/api/inventario/pendientes`, este endpoint no requiere rol administrador (cualquier usuario autenticado puede usarlo) y no depende del estado de la operativa: alimenta el modulo CONVERSOR, una calculadora de peso a onzas sin persistencia (ver seccion "Modulo CONVERSOR" mas abajo).

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

---

## Modelos de Base de Datos (mapeados en API)

| Tabla | Descripcion |
|---|---|
| `seg_usuario` | Usuarios |
| `seg_acceso` | Auditoria de accesos |
| `seg_rol` | Catalogo de roles (ej. `ROLE_ADMINISTRADOR`) |
| `seg_permiso` | Asignacion de roles por usuario (tabla puente N:M) |
| `ope_operacion` | Operativas |
| `app_producto_pesaje_config_api` | Configuracion/perfiles de pesaje (incluye `estado` para soft-delete y `barcode`) |
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

Flujo actual de navegacion:

- PALOTEO 1
- PALOTEO 2
- PALOTEO 3 (captura ciega)
- AJUSTES (diferencias, exportacion PDF y, solo administradores, aplicar el ajuste definitivo contra `bar_inventario`)
- PESAJE (CRUD de modelos de botella y codigos de barra; solo visible/accesible para usuarios con rol `ROLE_ADMINISTRADOR`)
- CONVERSOR (calculadora de peso a onzas, siempre disponible sin importar el estado de la operativa)

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
- Los productos agregados asi quedan marcados (`card-agregado-manual` en el
  DOM) y se pueden quitar individualmente (`DELETE
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

- Cada perfil pesable muestra `peso_bruto`, `tara`, `g/oz` (solo lectura, recalculado en vivo al editar peso/tara) y `barcode`.
- Los perfiles pesables con `peso_bruto` o `tara` nulos se marcan visualmente (borde de advertencia + icono + texto "Datos incompletos").
- Excluye productos de las categorias 15, 18, 19 y 20 (tanto en el listado como en el filtro de categorias).

### Modulo CONVERSOR: detalles de UI

- Calculadora de peso a onzas para cualquier producto pesable, sin escribir nada en BD y sin las restricciones de los demas modulos: siempre visible en el menu, no depende del estado de la operativa (`24`) ni de `is_admin`.
- Catalogo (`GET /api/conversor/productos`) se carga una sola vez por sesion (`conversorProductosCache` en `app.js`) y la busqueda/filtro corre en cliente; no hay roundtrip por cada tecla ni por cada peso ingresado.
- Al seleccionar un producto en los resultados se abre una ventana modal (`#conversor-modal`) con el mismo patron visual y de cierre (overlay, boton X, tecla Esc) que los modales "Guia Operativa" y "Boletin" (`#dummy-content-dialog`).
- Dentro de la modal se pueden agregar varias "botellas" (una fila por cada una), cada una con su propio selector de modelo si el producto tiene mas de un perfil (`resolverPerfilSeleccionado()`, reutilizado de PALOTEO). El calculo (`peso_liquido = max(0, peso - tara)`, `onzas = peso_liquido / gramos_por_oz`, redondeo HALF_UP con `redondearOnzasOperativas()`) se ejecuta en cliente y muestra tanto el total exacto como el redondeado POS.
- Cerrar la modal reinicia el estado (no hay boton "Limpiar" separado), ya que el modulo no persiste nada entre aperturas.

### FAB "volver al inicio"

Boton flotante reutilizable (clase `fab-scroll-top` + funcion `inicializarFabScrollTop(fabId, panelId)` en `app.js`) presente en PALOTEO 1, PALOTEO 3, AJUSTES, PESAJE y CONVERSOR. Aparece al hacer scroll mas alla de un umbral y solo si su panel esta activo; al hacer click hace scroll suave al inicio de la pagina. Para agregarlo a un nuevo modulo: insertar un boton con esa clase dentro del panel y llamar a la funcion con sus ids.

Service Worker:

- Cache First para assets estaticos.
- Network First para llamadas `/api/*`.

---

## Seguridad

- Verificacion de contrasena con SHA-256 (compatibilidad POS).
- JWT con expiracion de 10 horas.
- Endpoints de negocio protegidos con HTTPBearer.
- Control de acceso por rol (`ROLE_ADMINISTRADOR` via `seg_permiso`/`seg_rol`) para el modulo PESAJE y para `POST /api/inventario/ajustes/aplicar`. La respuesta de login incluye `is_admin` para que el frontend oculte la opcion de menu/boton a usuarios sin ese rol.
- Validacion de longitud minima de `SECRET_KEY` en configuracion.
- CORS habilitado para clientes web.

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
