# BackStage - API de Inventario POS

Backend REST construido con FastAPI y frontend PWA integrado para control de inventario fisico y auditoria de barra del sistema POS BackStage.

---

## Descripcion General

El flujo operativo actual es:

1. El usuario inicia sesion en la PWA.
2. La API valida que la operativa este en estado INICIO CIERRE (`24`).
3. Se registra inventario fisico (paloteo 1 y paloteo 2) por producto.
4. Se captura paloteo 3 (captura ciega) para contraste.
5. Se visualiza reporte de diferencias y se puede exportar a PDF.

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

### Inventario / Paloteo (requiere JWT)

| Metodo | Ruta | Descripcion |
|---|---|---|
| `GET` | `/api/inventario/pendientes` | Lista productos con movimiento y configuracion de pesaje |
| `POST` | `/api/inventario/paloteo` | Registra inventario fisico completo |
| `GET` | `/api/inventario/paloteo/{id_operacion}` | Obtiene inventario registrado y si puede editarse |
| `PUT` | `/api/inventario/paloteo/{id_inventario_pos}` | Corrige inventario fisico existente |

Reglas de correccion actuales:

1. Solo se corrige si la operativa sigue en estado `24`.
2. `id_operacion` e `id_barra` del payload deben coincidir con la cabecera existente.
3. La correccion actualiza de forma selectiva los productos enviados; los no enviados se conservan.
4. Si la operativa cambia de estado, la API bloquea la correccion.

### Perfiles de Pesaje (requiere JWT)

| Metodo | Ruta | Descripcion |
|---|---|---|
| `POST` | `/api/pesaje/perfiles` | Crea un modelo de botella para producto pesable |

### Reporte Paloteo 3 (requiere JWT)

| Metodo | Ruta | Descripcion |
|---|---|---|
| `POST` | `/api/paloteo3/exportar-pdf` | Genera y descarga PDF del reporte de diferencias |

Body ejemplo de exportacion:

```json
{
  "id_operacion": 42,
  "id_barra": 1,
  "usuario": "PEREZ MAMANI, JUAN",
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
| `ope_operacion` | Operativas |
| `app_producto_pesaje_config` | Configuracion/perfiles de pesaje |
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

Service Worker:

- Cache First para assets estaticos.
- Network First para llamadas `/api/*`.

---

## Seguridad

- Verificacion de contrasena con SHA-256 (compatibilidad POS).
- JWT con expiracion de 10 horas.
- Endpoints de negocio protegidos con HTTPBearer.
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
