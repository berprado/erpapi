# BackStage — API de Inventario POS

Backend REST construido con **FastAPI** y frontend **PWA** integrado para el control de inventario físico y auditoría de barra del sistema POS BackStage.

---

## Descripción General

El sistema permite a los bartenders registrar el inventario físico al cierre de cada operativa nocturna. El flujo principal es:

1. El usuario inicia sesión desde la PWA.
2. La API verifica que la operativa esté en estado **INICIO CIERRE** (estado `24`).
3. El bartender registra botellas cerradas y pesos de botellas abiertas por producto ("paloteo").
4. La API convierte los gramos medidos a onzas (redondeadas a la media onza más cercana) y guarda el resultado tanto en las tablas del POS como en una tabla de auditoría cruda.

---

## Stack Tecnológico

| Capa | Tecnología |
|---|---|
| Backend | Python 3.x · FastAPI · SQLAlchemy · PyMySQL |
| Autenticación | JWT (PyJWT · HS256) |
| Base de datos | MySQL (WAMP local / producción) |
| Frontend | HTML · Tailwind CSS · JavaScript Vanilla |
| PWA | Service Worker · Web App Manifest |
| Configuración | Pydantic Settings · `.env` |

---

## Estructura del Proyecto

```
erpapi/
├── main.py          # Endpoints FastAPI (rutas, lógica de negocio)
├── models.py        # Modelos SQLAlchemy (tablas de la BD)
├── schemas.py       # Esquemas Pydantic (validación de entrada/salida)
├── database.py      # Motor y sesión de SQLAlchemy
├── config.py        # Configuración por entorno (test / producción)
├── static/
│   ├── index.html   # PWA — Shell principal (BackStage Live Dashboard)
│   ├── app.js       # Lógica del frontend
│   ├── sw.js        # Service Worker (Cache First / Network First)
│   ├── manifest.json
│   └── cellar-sync-tokens.css  # Design tokens CSS
├── querys/          # Queries SQL de referencia
├── documentos/      # Documentación técnica y análisis
└── TODO.md          # Backlog de tareas pendientes
```

---

## Configuración del Entorno

### 1. Requisitos

- Python 3.10+
- WAMP / MySQL corriendo localmente (para desarrollo)
- `pip`

### 2. Instalar dependencias

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Variables de entorno

Crea un archivo `.env` en la raíz del proyecto con el siguiente formato:

```env
APP_ENV=test

# Clave JWT (mínimo 32 caracteres)
SECRET_KEY=tu_clave_secreta_muy_larga_y_aleatoria

# Base de datos de pruebas (WAMP local)
TEST_DB_HOST=localhost
TEST_DB_USER=root
TEST_DB_PASS=
TEST_DB_NAME=nombre_base_de_datos
TEST_DB_PORT=3306

# Base de datos de producción
PROD_DB_HOST=host_produccion
PROD_DB_USER=usuario_prod
PROD_DB_PASS=contrasena_prod
PROD_DB_NAME=nombre_bd_prod
PROD_DB_PORT=3306
```

> **Nota:** Para generar una `SECRET_KEY` segura:
> ```powershell
> python -c "import secrets; print(secrets.token_hex(32))"
> ```
> Cambia `APP_ENV=production` para conectar a la BD de producción.

### 4. Levantar el servidor

```powershell
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

La PWA estará disponible en `http://localhost:8000/` y la documentación interactiva en `http://localhost:8000/docs`.

---

## Endpoints de la API

### Autenticación

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api` | Estado de la API |
| `GET` | `/api/health` | Verifica la conexión a la BD |
| `POST` | `/api/auth/login` | Inicio de sesión, devuelve JWT |

**Body de login:**
```json
{
  "usuario": "jperez",
  "contrasena": "mi_password"
}
```

**Respuesta exitosa:**
```json
{
  "access_token": "eyJ...",
  "token_type": "Bearer",
  "usuario_id": 5,
  "nombres": "PÉREZ MAMANI, JUAN"
}
```

---

### Operación (requiere JWT)

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/operacion/activa` | Verifica si la operativa está en INICIO CIERRE |

---

### Inventario / Paloteo (requiere JWT)

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/inventario/pendientes` | Lista de productos con movimiento en la operativa activa |
| `POST` | `/api/inventario/paloteo` | Registra el inventario físico completo |

**Body de paloteo (ejemplo):**
```json
{
  "id_operacion": 42,
  "id_barra": 1,
  "observaciones": "Conteo realizado a las 03:00 AM",
  "items": [
    {
      "id_producto": 101,
      "botellas_cerradas": 2,
      "pesos_abiertas": [
        { "peso": 650.5, "perfil_id": 3 }
      ]
    }
  ]
}
```

---

### Perfiles de Pesaje (requiere JWT)

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/api/pesaje/perfiles` | Crea un nuevo modelo de botella para un producto |

---

## Lógica de Conversión de Pesos

Para cada botella abierta registrada:

1. Se verifica que el `peso_medido >= (tara - margen_error_balanza)` (margen: 10g).
2. Se calcula el peso del líquido: `peso_liquido = max(0, peso_medido - tara)`.
3. Se convierte a onzas: `onzas = peso_liquido / gramos_por_oz`.
4. El total se guarda **exacto** en la tabla de auditoría cruda.
5. Se redondea a la **media onza más cercana** para el POS:
   ```python
   onzas_pos = round(total_onzas * 2) / 2
   ```

---

## Modelos de Base de Datos

| Tabla | Descripción |
|---|---|
| `seg_usuario` | Usuarios del sistema |
| `seg_acceso` | Auditoría de accesos (login) |
| `ope_operacion` | Operativas de la barra |
| `app_producto_pesaje_config` | Perfiles de botella por producto |
| `bar_inventario_fisico` | Cabecera del inventario físico (POS) |
| `bar_detalle_fisico` | Detalle por producto del inventario (POS) |
| `app_paloteo_registro_crudo` | Auditoría cruda con pesos exactos |

---

## PWA Frontend

La aplicación web progresiva **BackStage** se sirve directamente desde `/` y usa un design system "Electric Industrial" con los siguientes tokens de diseño:

- **Primary:** Electric Cyan (`#00dbe9`)
- **Background:** Dark Surface (`#0d1515`)
- **Tipografía:** Space Grotesk
- **Iconos:** Google Material Symbols Outlined

El Service Worker implementa:
- **Cache First** para todos los assets estáticos.
- **Network First** para las llamadas a la API (`/api/*`).

---

## Seguridad

- Las contraseñas se verifican comparando hashes **SHA-256** (compatible con el POS existente).
- Los tokens JWT tienen vigencia de **10 horas** (`HS256`).
- Todos los endpoints de negocio están protegidos con `HTTPBearer` y validan que el usuario esté activo en BD.
- Se valida longitud mínima de `SECRET_KEY` (32 caracteres) al arrancar la aplicación.
- CORS habilitado para clientes web (configurable en `main.py`).

---

## Entornos

| `APP_ENV` | Base de datos usada |
|---|---|
| `test` (default) | WAMP local (`TEST_DB_*`) |
| `production` | Servidor remoto (`PROD_DB_*`) |

---

## Pendientes Principales

Ver [TODO.md](TODO.md) para el backlog completo. Los más relevantes:

- Separar endpoints en routers por módulo (`APIRouter`).
- Implementar refresh token.
- Agregar tests automatizados (login, paloteo válido/inválido).
- Implementar manejo de errores global con `exception_handler`.
