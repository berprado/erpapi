# Análisis Técnico del Proyecto `erpapi` — BackStage Inventario
**Fecha:** 05/05/2026  
**Rama analizada:** `main`  
**Archivos revisados:** `main.py`, `schemas.py`, `models.py`, `database.py`, `config.py`, `static/app.js`, `static/index.html`

---

## 1. Resumen Ejecutivo

El proyecto es una API REST construida con **FastAPI + SQLAlchemy + PyMySQL**, que sirve también un frontend SPA en modo PWA. El código está generalmente bien estructurado para su tamaño, pero tiene varios puntos que representan riesgos de seguridad, inconsistencias lógicas y deuda técnica que conviene atender antes de salir a producción.

---

## 2. Hallazgos por Archivo

---

### 2.1 `main.py`

#### 🔴 Crítico

| # | Problema | Detalle |
|---|----------|---------|
| 1 | **Mezcla `datetime.now()` y `datetime.utcnow()`** | En el login se usa `datetime.utcnow()` para la expiración del JWT y `datetime.now()` para `fecha_reg`. Dependiendo de la zona horaria del servidor, el token puede expirar antes o después de lo esperado. En Python 3.12+ `utcnow()` está deprecado. |
| 2 | **`allow_origins=["*"]` con credenciales** | Si en algún momento se cambia `allow_credentials=True`, esta combinación es rechazada por los navegadores y puede causar que la app deje de funcionar silenciosamente. Mejor definir ya el origen real (`http://localhost:8000` para dev, dominio real para prod). |
| 3 | **`/api/health` expuesto sin autenticación** | Revela la versión exacta de MySQL al público. Un atacante puede usar esta información para buscar vulnerabilidades conocidas. Proteger con `Depends(get_usuario_actual)` o eliminarlo en producción. |

#### 🟡 Advertencia

| # | Problema | Detalle |
|---|----------|---------|
| 4 | **`/api/operacion/activa` sin autenticación** | El endpoint no tiene `Depends(get_usuario_actual)`. Cualquier cliente no autenticado puede consultar el estado de la caja (datos de negocio sensibles). |
| 5 | **`procesar_paloteo` no valida duplicados** | Si el mismo usuario llama al endpoint dos veces con el mismo `id_operacion`, se crean dos cabeceras (`bar_inventario_fisico`) distintas. No existe un `UNIQUE` lógico que prevenga inventarios dobles por operación. |
| 6 | **`if not config: continue` silencia productos** | Si un producto no tiene configuración de pesaje, simplemente se omite del resultado sin ningún aviso en la respuesta. El usuario no sabrá que un producto fue ignorado. |
| 7 | **SQL crudo con subquery de MAX anidado** | En `/api/inventario/pendientes`, la condición `WHERE d.id_operacion = (SELECT MAX(id_operacion) FROM bar_comanda)` no está ligada al `id_operacion` activo (`currentOperacionId`). Podría devolver productos de una operación distinta si hay inconsistencias entre tablas. |
| 8 | **`estado_registro=62` hardcodeado** | El valor `62` representa un estado de negocio. Si cambia en el POS, habrá que buscar y editar manualmente. Conviene una constante o enum con nombre descriptivo. |
| 9 | **`margen_error_balanza = 10.0` no configurable** | Es un parámetro de negocio crítico hardcodeado. Debería venir del `.env` o de la tabla de configuración de pesaje. |

#### 🔵 Mejora

| # | Sugerencia | Detalle |
|---|------------|---------|
| 10 | **`procesar_paloteo` sin `response_model`** | El endpoint `POST /api/inventario/paloteo` devuelve un dict sin schema Pydantic. Conviene añadir un `response_model` para documentación y validación de salida. |
| 11 | **Comentario `# <-- CANDADO AQUÍ`** | Artefacto de desarrollo, eliminar antes de producción. |

---

### 2.2 `schemas.py`

#### 🟡 Advertencia

| # | Problema | Detalle |
|---|----------|---------|
| 12 | **`ProductoPendiente` sin `model_config`** | Pydantic v2 requiere `model_config = ConfigDict(from_attributes=True)` para mapear objetos ORM. Aunque actualmente se usan `.mappings()` en la query (que devuelven dicts y funcionan), si en algún momento se cambia a ORM objects, fallará silenciosamente. |
| 13 | **Campos `Optional` sin valor por defecto en `ProductoPendiente`** | `pesable`, `peso_bruto`, `tara`, `gramos_por_oz` son `Optional[X]` pero sin `= None` explícito. Pydantic v2 requiere el `= None` para que el campo sea verdaderamente opcional en la deserialización. |

#### 🔵 Mejora

| # | Sugerencia | Detalle |
|---|------------|---------|
| 14 | **No existe schema de respuesta para `paloteo`** | La respuesta del `POST /api/inventario/paloteo` es un dict libre. Crear `PaloteoResponse(BaseModel)` mejora la documentación en Swagger y la tipabilidad del frontend. |

---

### 2.3 `models.py`

#### 🟡 Advertencia

| # | Problema | Detalle |
|---|----------|---------|
| 15 | **`habilitado` mapeado como `String(1)` en lugar de `Boolean`** | La columna `habilitado` se compara con `'1'` (string). Si la BD guarda un `TINYINT`, la comparación `usuario.habilitado != '1'` puede fallar dependiendo del driver. Mejor usar `Boolean` o `Integer`. |
| 16 | **Sin `ForeignKey` ni `relationship` en ningún modelo** | Los modelos `DetalleFisicoPOS` e `InventarioFisicoPOS` tienen columnas como `id_inventario_fisico` e `id_operacion` que deberían ser `ForeignKey`. La integridad referencial solo existe en la BD, SQLAlchemy no la conoce, impidiendo hacer joins ORM o lazy loading. |
| 17 | **`PaloteoRegistroCrudo` guarda `fecha_reg` como `DateTime` pero `DetalleFisicoPOS` como `Date`** | Inconsistencia entre modelos para el mismo campo semántico. Afecta queries cruzadas o reportes futuros. |

#### 🔵 Mejora

| # | Sugerencia | Detalle |
|---|------------|---------|
| 18 | **Sin índices en columnas de búsqueda frecuente** | `PaloteoRegistroCrudo.id_operacion`, `DetalleFisicoPOS.id_inventario_fisico` y `InventarioFisicoPOS.id_operacion` se usan en queries pero no tienen `index=True`. |

---

### 2.4 `database.py`

#### 🟡 Advertencia

| # | Problema | Detalle |
|---|----------|---------|
| 19 | **Sin `pool_pre_ping=True`** | Si la conexión MySQL se interrumpe (timeout del servidor, reinicio de WAMP), SQLAlchemy reutilizará una conexión muerta del pool y lanzará un error 500. Añadir `pool_pre_ping=True` al `create_engine` previene esto. |

---

### 2.5 `config.py`

#### 🟡 Advertencia

| # | Problema | Detalle |
|---|----------|---------|
| 20 | **`print()` con emojis en `database_url`** | El `print("🚀 Conectando a PRODUCCIÓN...")` se ejecuta en cada arranque y en cada reload de uvicorn. En producción conviene usar `logging` correctamente configurado en lugar de `print`. |
| 21 | **`SECRET_KEY` sin longitud mínima validada** | Si alguien define una `SECRET_KEY` corta en `.env`, los tokens generados serán débiles. Añadir un `@field_validator` que rechace claves de menos de 32 caracteres. |

---

### 2.6 `static/app.js`

#### 🔴 Crítico

| # | Problema | Detalle |
|---|----------|---------|
| 22 | **`API_BASE = "http://localhost:8000/api"` hardcodeado** | En producción esta URL apuntará al servidor incorrecto. Cualquier usuario que instale la PWA fuera de localhost no podrá conectarse. Debe derivarse dinámicamente: `const API_BASE = \`\${window.location.origin}/api\`` |

#### 🟡 Advertencia

| # | Problema | Detalle |
|---|----------|---------|
| 23 | **Token JWT almacenado en `localStorage`** | `localStorage` es vulnerable a ataques XSS. Para una PWA sin backend de sesión, es aceptable, pero hay que asegurar que no haya inputs sin sanitizar en la UI (ver punto 24). |
| 24 | **`div.innerHTML = html` con datos directos de la API** | Los campos `p.nombre`, `p.codigo` y `p.categoria_nombre` se insertan directamente como HTML sin escapar. Si algún nombre de producto contiene `<script>` o `"`, se produce una vulnerabilidad XSS. Usar `textContent` o una función de escape para los valores dinámicos. |
| 25 | **`cargarProductos()` no maneja error 401** | A diferencia de `iniciarDashboard()`, si `/api/inventario/pendientes` devuelve 401, `cargarProductos()` no hace logout automático — simplemente muestra el mensaje de "no hay productos". |
| 26 | **`ID_BARRA_ACTUAL = 1` hardcodeado** | El comentario dice "lo hacemos dinámico después". Si esto llega a producción con múltiples barras, todos los inventarios se registrarán en la barra 1. |

#### 🔵 Mejora

| # | Sugerencia | Detalle |
|---|------------|---------|
| 27 | **Doble registro del HTML del input-peso** | El HTML del input de peso está duplicado: una vez en `renderizarProductos` (campo por defecto) y otra en `window.agregarInputPeso`. Extraer como función `crearInputPeso()` reutilizable. |
| 28 | **`estadoIcon.classList` no se limpia entre navegaciones** | Si el usuario navega a la app con estado verde, luego el estado cambia a rojo y vuelve a llamar a `iniciarDashboard()`, las clases de color previas pueden acumularse. Conviene hacer `estadoIcon.className = "..."` con el estado base antes de cada verificación. |

---

### 2.7 `static/index.html`

#### 🔵 Mejora

| # | Sugerencia | Detalle |
|---|------------|---------|
| 29 | **Tailwind via CDN en producción** | El CDN de Tailwind descarga el compilador JS completo (~350KB) y genera clases en runtime. Para producción conviene un build con Tailwind CLI o PostCSS que genere un CSS minificado de solo las clases usadas (~5-15KB). |
| 30 | **Sin `<meta name="description">`** | Afecta SEO y la vista previa cuando se comparte el link de la app. |

---

## 3. Vulnerabilidades OWASP Identificadas

| OWASP | Categoría | Hallazgo en el proyecto |
|-------|-----------|------------------------|
| A03:2021 | Injection | `innerHTML` con datos de API sin escapar (XSS) — punto #24 |
| A02:2021 | Cryptographic Failures | SHA-256 sin salt para contraseñas — heredado del POS, pero documentado |
| A07:2021 | Identification and Auth Failures | `/api/operacion/activa` sin autenticación (#4), `/api/health` expone versión MySQL (#3) |
| A05:2021 | Security Misconfiguration | `allow_origins=["*"]` — aceptable en dev, no en prod (#2) |

---

## 4. Tabla de Prioridades

| Prioridad | # | Acción |
|-----------|---|--------|
| 🔴 **Inmediata** | 22 | Cambiar `API_BASE` a URL dinámica antes de cualquier deploy |
| 🔴 **Inmediata** | 24 | Escapar valores de la API antes de inyectar en `innerHTML` |
| 🔴 **Inmediata** | 1  | Unificar `datetime.now(timezone.utc)` en todo el proyecto |
| 🟡 **Corto plazo** | 4  | Proteger `/api/operacion/activa` con autenticación |
| 🟡 **Corto plazo** | 5  | Validar inventario duplicado por operación |
| 🟡 **Corto plazo** | 13 | Añadir `= None` a campos Optional en `ProductoPendiente` |
| 🟡 **Corto plazo** | 19 | Añadir `pool_pre_ping=True` en `create_engine` |
| 🟡 **Corto plazo** | 25 | Manejar 401 en `cargarProductos()` |
| 🔵 **Cuando sea posible** | 26 | Hacer `ID_BARRA_ACTUAL` dinámico (desde API o selector) |
| 🔵 **Cuando sea posible** | 27 | Refactorizar HTML del input-peso a función reutilizable |
| 🔵 **Cuando sea posible** | 29 | Migrar Tailwind a build estático para producción |

---

## 5. Deuda Técnica Estructural (Largo Plazo)

1. **Separar `main.py` en routers** — FastAPI soporta `APIRouter`. Conviene tener `routers/auth.py`, `routers/inventario.py`, `routers/operacion.py`.
2. **Agregar capa de servicios** — La lógica de negocio (cálculo de onzas, validación de operación) vive dentro de los endpoints. Extraerla a `services/inventario.py` mejora la testabilidad.
3. **Tests automatizados** — No existe ningún test. Con `pytest` + `httpx` se pueden cubrir los casos críticos (login fallido, token expirado, inventario duplicado) en pocas horas.
4. **Logging estructurado** — Reemplazar `print()` por `logging.getLogger()` con niveles (`INFO`, `WARNING`, `ERROR`) y formato JSON para producción.
5. **Refresh token** — El token actual dura 10 horas y no se puede revocar. Un mecanismo de refresh + blacklist permite cerrar sesiones remotamente.

---

*Documento generado por análisis estático del código fuente. Última versión analizada: commit local sin push (post `d2e8b6c`).*
