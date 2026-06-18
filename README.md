# BackStage - API de Inventario POS

Backend REST construido con FastAPI y frontend PWA integrado para control de inventario fisico y auditoria de barra del sistema POS BackStage.

---

## Descripcion General

El flujo operativo actual es:

1. El usuario inicia sesion en la PWA.
2. La API valida que la operativa este en estado INICIO CIERRE (`24`).
3. La app resuelve la barra operativa por entorno (con selector opcional controlado).
4. Se cargan productos pendientes para paloteo:
  - productos vendidos durante la operativa
  - productos traspasados de almacen a barra durante la operativa
5. Se registra inventario fisico desde PALOTEO 1/2/3 con un unico origen de datos. (estamos evaluando cual de las tres opciones de PALOTEO genera la menor friccion con el usuario al momento de ingresar los datos.
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
| `POST` | `/api/inventario/paloteo` | Registra inventario fisico completo |
| `GET` | `/api/inventario/paloteo/{id_operacion}` | Obtiene inventario registrado y si puede editarse |
| `PUT` | `/api/inventario/paloteo/{id_inventario_pos}` | Corrige inventario fisico existente |

Reglas de correccion actuales:

1. Solo se corrige si la operativa sigue en estado `24`.
2. `id_operacion` e `id_barra` del payload deben coincidir con la cabecera existente.
3. La correccion actualiza de forma selectiva los productos enviados; los no enviados se conservan.
4. Si la operativa cambia de estado, la API bloquea la correccion.

Reglas de barra operativa:

1. Si `PALOTEO_SELECTOR_ENABLED=false`, la barra se fija por `PALOTEO_DEFAULT_BARRA_ID`.
2. Si `PALOTEO_SELECTOR_ENABLED=true`, frontend puede enviar `X-Barra-Id` (solo valores de `PALOTEO_ALLOWED_BARRAS`).
3. En `POST/PUT /api/inventario/paloteo`, `payload.id_barra` debe coincidir con la barra operativa resuelta.

### Perfiles de Pesaje (requiere JWT + rol administrador)

| Metodo | Ruta | Descripcion |
|---|---|---|
| `POST` | `/api/pesaje/perfiles` | Crea (o reactiva si existe uno eliminado con el mismo nombre) un modelo de botella para producto pesable. Calcula `gramos_por_oz` en el backend a partir del volumen estandar del producto |
| `GET` | `/api/pesaje/categorias` | Lista de categorias habilitadas, para el filtro del modulo PESAJE |
| `GET` | `/api/pesaje/config` | Lista perfiles de pesaje (tabla `app_producto_pesaje_config_api`), con filtros opcionales `nombre`, `id_categoria`, `pesable` |
| `PUT` | `/api/pesaje/config/{id}` | Edita `peso_bruto`/`tara`/`barcode` de un perfil existente. En productos no pesables solo se permite editar `barcode` |
| `DELETE` | `/api/pesaje/config/{id}` | Elimina (soft-delete, `estado='DES'`) un perfil. Rechaza la eliminacion si es el ultimo perfil activo del producto |

Todos los endpoints de Pesaje requieren ademas que el usuario tenga el rol `ROLE_ADMINISTRADOR` (verificado contra `seg_permiso`/`seg_rol`), devolviendo `403` si no lo tiene.

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

---

## Validaciones Activas (Frontend + Backend)

En el flujo de inventario fisico/paloteo se aplican estas validaciones clave:

1. No se permiten valores negativos en unidades o pesos.
2. Se exige unicidad de `id_producto` en `items` del payload.
3. Para pesables, se bloquea cuando `peso_medido > peso_bruto` del perfil seleccionado.
4. Para pesables, se bloquea cuando las onzas calculadas exceden `onzas_por_botella_llena`.
5. Campos vacios se confirman explicitamente y, si el usuario acepta, se completan en `0`.

---

## REPORTE (Paloteo 3)

Funciones implementadas en la vista REPORTE:

1. Filtro por tipo de ajuste: `Todos`, `Ingreso (+)`, `Salida (-)`.
2. Ordenamiento por columnas: `ID`, `COD`, `PRODUCTO`.
3. Coloreo semantico de diferencias:
  - `0`: verde
  - negativo: rojo
  - positivo: amarillo
4. Exportacion PDF coherente con filtro activo:
  - `PALOTEO_<id>.pdf`
  - `PALOTEO_<id>_INGRESO.pdf`
  - `PALOTEO_<id>_SALIDA.pdf`
5. Generacion de PDF en memoria (sin escritura a disco) para evitar errores intermitentes en Windows.

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

---

## PWA Frontend

La PWA se sirve desde `/` y assets desde `/assets`.

Flujo actual de navegacion:

- PALOTEO 1
- PALOTEO 2
- PALOTEO 3 (captura ciega)
- REPORTE (diferencias y exportacion PDF)
- PESAJE (CRUD de modelos de botella y codigos de barra; solo visible/accesible para usuarios con rol `ROLE_ADMINISTRADOR`)

Sincronizacion entre modulos:

1. Cambios en PALOTEO 1, PALOTEO 2 y PALOTEO 3 se reflejan entre vistas.
2. El payload final se construye desde el inventario canonico.
3. Autosave guarda y recupera borradores locales por `operativa + barra + usuario`.

Service Worker:

- Cache First para assets estaticos.
- Network First para llamadas `/api/*`.

---

## Seguridad

- Verificacion de contrasena con SHA-256 (compatibilidad POS).
- JWT con expiracion de 10 horas.
- Endpoints de negocio protegidos con HTTPBearer.
- Control de acceso por rol (`ROLE_ADMINISTRADOR` via `seg_permiso`/`seg_rol`) para el modulo PESAJE. La respuesta de login incluye `is_admin` para que el frontend oculte la opcion de menu a usuarios sin ese rol.
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
