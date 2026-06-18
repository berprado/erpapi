# 📋 Documentación: Proceso de Almacenamiento de Paloteo

**Versión:** 1.1  
**Fecha:** 11 de junio de 2026  
**Proyecto:** BackStage | Live Dashboard - Sistema de Inventario POS  
**Rama:** experiment/glitch-no-glow

---

## 📑 Tabla de Contenidos

1. [Introducción](#introducción)
2. [Flujo General del Proceso](#flujo-general-del-proceso)
3. [Arquitectura de Datos](#arquitectura-de-datos)
4. [Descripción de Tablas](#descripción-de-tablas)
5. [Flujo Detallado de Almacenamiento](#flujo-detallado-de-almacenamiento)
6. [Validaciones y Controles](#validaciones-y-controles)
7. [Ejemplos Prácticos](#ejemplos-prácticos)
8. [Seguridad y Auditoría](#seguridad-y-auditoría)
9. [Manejo de Errores](#manejo-de-errores)
10. [FAQ Técnico](#faq-técnico)

---

## Introducción

El sistema **BackStage** permite al personal de barra realizar inventarios físicos de productos pesables mediante:

- ✅ Ingreso de botellas cerradas (unidades enteras)
- ✅ Pesaje de botellas abiertas (onzas con precisión)
- ✅ Cálculo automático de diferencias vs. stock del sistema
- ✅ Almacenamiento en dos niveles: **datos procesados para el POS** y **auditoría cruda exacta**
- ✅ Observaciones opcionales del usuario

El propósito es mantener control riguroso del inventario y detectar discrepancias rápidamente.

---

## Flujo General del Proceso

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. USUARIO INICIA SESIÓN (Login)                                │
│    └─ Credenciales validadas contra seg_usuario                 │
│    └─ Token JWT generado (600 minutos de vigencia)              │
│    └─ Acceso registrado en seg_acceso                           │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. VERIFICACIÓN DE OPERACIÓN                                    │
│    └─ Se valida que exista operación activa (estado = 'HAB')    │
│    └─ Se verifica estado_operacion == 24 (INICIO CIERRE)        │
│    └─ Si está en 22 (vendiendo), se rechaza la operación        │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. CARGA DE PRODUCTOS PENDIENTES                                │
│    └─ Obtiene lista de productos con movimiento en la jornada   │
│    └─ Carga perfiles de pesaje desde app_producto_pesaje_config_api │
│    └─ Retorna stock ideal (sistema) para comparación            │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. INGRESO DE DATOS (Frontend)                                  │
│    └─ Usuario ingresa botellas cerradas por producto            │
│    └─ Usuario pesa botellas abiertas con balanza                │
│    └─ Se selecciona perfil de botella (si hay múltiples)        │
│    └─ Se calcula onzas en tiempo real                           │
│    └─ Se muestra diferencia vs. sistema                         │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 5. VALIDACIÓN PREVIA AL ENVÍO                                   │
│    └─ Valida que no haya números negativos                      │
│    └─ Valida peso por perfil (peso medido <= peso bruto)        │
│    └─ Valida capacidad por producto (onzas no excedan máximo)   │
│    └─ Si hay campos vacíos, solicita confirmación y rellena 0   │
│    └─ Abre diálogo para observaciones opcionales                │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 6. ENVÍO AL SERVIDOR (POST /api/inventario/paloteo)             │
│    └─ Se incluye token JWT en Authorization header              │
│    └─ Se envía payload con datos del inventario                 │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 7. PROCESAMIENTO EN BACKEND                                     │
│    └─ Backend valida operación nuevamente                       │
│    └─ Backend verifica que no exista inventario duplicado       │
│    └─ Calcula onzas exactas: (peso_medido - tara) / gramos_oz  │
│    └─ Redondea a media onza: round(onzas * 2) / 2              │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 8. ALMACENAMIENTO EN BASE DE DATOS                              │
│    ├─ Crea cabecera en bar_inventario_fisico (id_inventario)   │
│    ├─ Guarda detalles en bar_detalle_fisico (procesados/POS)   │
│    └─ Guarda auditoría en app_paloteo_registro_crudo (exacto)  │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 9. RESPUESTA AL CLIENTE                                         │
│    └─ Confirma éxito con ID del inventario guardado             │
│    └─ Mantiene datos en pantalla y habilita flujo de corrección │
└─────────────────────────────────────────────────────────────────┘
```

---

## Arquitectura de Datos

### Estructura de Capas

```
┌─────────────────────────────────────────────────────────┐
│         FRONTEND (PWA - HTML + Vanilla JS)              │
│  static/index.html + static/app.js                      │
└─────────────────────────────────┬───────────────────────┘
                                  │ HTTP/REST
                                  ↓
┌─────────────────────────────────────────────────────────┐
│      BACKEND (FastAPI - Python)                         │
│  main.py - Endpoints de validación y procesamiento      │
│  schemas.py - Modelos Pydantic de entrada/salida        │
│  models.py - Mapeos ORM de SQLAlchemy                   │
└─────────────────────────────────┬───────────────────────┘
                                  │ SQL
                                  ↓
┌─────────────────────────────────────────────────────────┐
│      BASE DE DATOS (MySQL)                              │
│  7 tablas: usuarios, operaciones, paloteo, auditoría    │
└─────────────────────────────────────────────────────────┘
```

### Relaciones entre Tablas

```
┌─────────────────────────────────────────────────────────────┐
│ seg_usuario (Autenticación)                                 │
│  ├─ PK: id                                                  │
│  └─ usuario (unique)                                        │
└────────────────────────┬────────────────────────────────────┘
                         │ ─── registra acceso
                         ↓
            ┌────────────────────────┐
            │ seg_acceso             │
            │ PK: id                 │
            │ FK: usuario            │
            └────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│ ope_operacion (Sesión de Barra)                            │
│  ├─ PK: id                                                 │
│  └─ estado_operacion (22=vendiendo, 24=cierre)             │
└────────────────────────┬─────────────────────────────────┘
                         │ ─── id_operacion
                         ├─────────────────┬─────────────────┐
                         ↓                 ↓                 ↓
    ┌────────────────────────────────────────────┐
    │ bar_inventario_fisico (Cabecera Inventario)│
    │  ├─ PK: id                                 │
    │  ├─ FK: id_operacion                       │
    │  └─ FK: id_barra                           │
    └─────────────────┬──────────────────────────┘
                      │ ─── id_inventario_fisico
                      ├──────────────────────────┬──────────────────────┐
                      ↓                          ↓                      ↓
        ┌──────────────────────────┐  ┌──────────────────────────────────┐
        │ bar_detalle_fisico       │  │ app_paloteo_registro_crudo       │
        │ (Datos Procesados/POS)   │  │ (Auditoría Exacta)               │
        │  ├─ PK: id               │  │  ├─ PK: id                       │
        │  ├─ FK: id_inventario    │  │  ├─ FK: id_operacion             │
        │  └─ FK: id_producto      │  │  └─ FK: id_producto              │
        │  └─ cantidad_detalle     │  │  └─ onzas_calculadas (exacto)    │
        │     (redondeado a 0.5)   │  │  └─ pesos_abiertas (JSON)        │
        └──────────────────────────┘  └──────────────────────────────────┘
              │                              │
              └──────────┬──────────────────┘
                         │ FK: id_producto
                         ↓
        ┌──────────────────────────────────────────┐
        │ app_producto_pesaje_config_api           │
        │ (Calibración de Balanzas)                │
        │  ├─ PK: id                               │
        │  ├─ FK: id_producto_almacen              │
        │  ├─ peso_bruto, tara                     │
        │  ├─ gramos_por_oz, tolerancia_oz         │
        │  └─ pesable (0=no pesable, 1=pesable)    │
        └──────────────────────────────────────────┘
```

---

## Descripción de Tablas

### 1. **seg_usuario** (Seguridad - Autenticación)

**Propósito:** Almacenar credenciales y datos del personal autorizado.

| Campo | Tipo | Nullable | Descripción |
|-------|------|----------|-------------|
| `id` | INT | NO | Identificador único del usuario |
| `paterno` | VARCHAR(255) | SÍ | Apellido paterno |
| `materno` | VARCHAR(255) | SÍ | Apellido materno |
| `nombres` | VARCHAR(255) | SÍ | Nombres del usuario |
| `usuario` | VARCHAR(255) | NO | **Nombre de usuario único** (ej: "bernardo.prado") |
| `contrasena` | VARCHAR(255) | NO | **Hash SHA-256 de la contraseña** |
| `habilitado` | CHAR(1) | SÍ | '1' = activo, '0' = inactivo |
| `estado` | VARCHAR(3) | SÍ | 'HAB' = habilitado, 'DES' = deshabilitado |

**Índices:**
- PK: `id`
- UNIQUE: `usuario`

**Ejemplo de dato:**
```json
{
  "id": 1,
  "usuario": "bernardo.prado",
  "nombres": "Bernardo",
  "paterno": "Prado",
  "materno": "López",
  "contrasena": "7c4a8d09ca3762af61e59520943dc26494f8941b",
  "habilitado": "1",
  "estado": "HAB"
}
```

---

### 2. **seg_acceso** (Seguridad - Auditoría de Accesos)

**Propósito:** Registrar todos los ingresos al sistema con fecha, hora e IP.

| Campo | Tipo | Nullable | Descripción |
|-------|------|----------|-------------|
| `id` | INT | NO | Identificador único |
| `usuario` | VARCHAR(255) | NO | Nombre de usuario que se conectó |
| `fecha` | DATETIME | SÍ | Timestamp de la conexión (UTC) |
| `ip` | VARCHAR(255) | SÍ | Dirección IP del cliente |

**Ejemplo de dato:**
```json
{
  "id": 1,
  "usuario": "bernardo.prado",
  "fecha": "2026-05-09T14:32:15Z",
  "ip": "192.168.1.100"
}
```

---

### 3. **ope_operacion** (Operaciones - Sesiones de Barra)

**Propósito:** Representar cada turno/sesión de barra con su estado (vendiendo vs. cierre).

| Campo | Tipo | Nullable | Descripción |
|-------|------|----------|-------------|
| `id` | INT | NO | ID único de la operación |
| `fecha` | DATE | SÍ | Fecha de la operación |
| `nombre_operacion` | VARCHAR(255) | SÍ | Descripción (ej: "Turno Tarde") |
| `estado_operacion` | INT | SÍ | **22** = Vendiendo, **24** = Inicio Cierre |
| `estado` | VARCHAR(3) | SÍ | 'HAB' = activo, 'DES' = inactivo |

**Estados válidos:**
- `22`: Estado **VENDIENDO** → No se permite paloteo (error 403)
- `24`: Estado **INICIO CIERRE** → Se permite paloteo ✅
- Otros: Estado inválido para paloteo

**Ejemplo de dato:**
```json
{
  "id": 42,
  "fecha": "2026-05-09",
  "nombre_operacion": "Operación Turno Noche",
  "estado_operacion": 24,
  "estado": "HAB"
}
```

---

### 4. **bar_inventario_fisico** (Cabecera del Inventario)

**Propósito:** Registrar cada cierre de inventario con metadatos.

| Campo | Tipo | Nullable | Descripción |
|-------|------|----------|-------------|
| `id` | INT | NO | **Identificador único del inventario** |
| `fecha` | DATE | SÍ | Fecha del inventario |
| `observaciones` | VARCHAR(255) | SÍ | Notas del bartender (ej: "Merma detectada en botellas Premium") |
| `procesado_por` | VARCHAR(255) | SÍ | Nombre completo formateado (ej: "PRADO, BERNARDO") |
| `estado_registro` | INT | SÍ | **62** = Pendiente, otros valores según negocio |
| `id_barra` | INT | SÍ | Referencia a la barra (FK) |
| `id_operacion` | INT | SÍ | **Referencia a la operación activa** (FK) |
| `usuario_reg` | VARCHAR(255) | SÍ | Usuario técnico que registró |
| `fecha_reg` | DATE | SÍ | Fecha técnica del registro |
| `estado` | VARCHAR(3) | SÍ | **'HAB'** = habilitado (activo) |

**Restricción de Integridad:**
- **ÚNICA POR OPERACIÓN:** Si ya existe un registro con `id_operacion` y `estado='HAB'`, se rechaza un segundo intento (error 409 Conflict).

**Ejemplo de dato:**
```json
{
  "id": 1,
  "fecha": "2026-05-09",
  "observaciones": "Verificado, faltó una botella de Vodka Premium",
  "procesado_por": "PRADO LÓPEZ, BERNARDO",
  "estado_registro": 62,
  "id_barra": 1,
  "id_operacion": 42,
  "usuario_reg": "bernardo.prado",
  "fecha_reg": "2026-05-09",
  "estado": "HAB"
}
```

---

### 5. **bar_detalle_fisico** (Detalles del Inventario - Datos Procesados para POS)

**Propósito:** Almacenar cada producto inventariado con valores **redondeados para el sistema POS**.

| Campo | Tipo | Nullable | Descripción |
|-------|------|----------|-------------|
| `id` | INT | NO | Identificador único |
| `cantidad_unidad` | DECIMAL(10,2) | SÍ | **Botellas cerradas** (enteras) |
| `cantidad_detalle` | DECIMAL(10,2) | SÍ | **Onzas redondeadas a media onza** (ej: 11.50, 12.00) |
| `id_producto` | INT | SÍ | ID del producto inventariado (FK) |
| `id_inventario_fisico` | INT | SÍ | **Referencia a cabecera** (FK) |
| `usuario_reg` | VARCHAR(255) | SÍ | Usuario que registró |
| `fecha_reg` | DATE | SÍ | Fecha del registro |
| `estado` | VARCHAR(3) | SÍ | **'HAB'** = habilitado |

**Cálculo de `cantidad_detalle`:**
```
Para cada botella abierta pesada:
  peso_liquido = peso_medido - tara
  onzas_exactas = peso_liquido / gramos_por_oz
  
Total = Σ(onzas_exactas)

REDONDEADO AL POS:
  cantidad_detalle = round(total * 2) / 2

Ejemplo:
  11.92 oz → 11.92 * 2 = 23.84 → round(23.84) = 24 → 24 / 2 = 12.00
  11.21 oz → 11.21 * 2 = 22.42 → round(22.42) = 22 → 22 / 2 = 11.00
  11.26 oz → 11.26 * 2 = 22.52 → round(22.52) = 23 → 23 / 2 = 11.50
```

**Ejemplo de dato:**
```json
{
  "id": 1,
  "id_producto": 456,
  "cantidad_unidad": 12,
  "cantidad_detalle": 11.50,
  "id_inventario_fisico": 1,
  "usuario_reg": "bernardo.prado",
  "fecha_reg": "2026-05-09",
  "estado": "HAB"
}
```

---

### 6. **app_paloteo_registro_crudo** (Auditoría Exacta - Datos Sin Procesar)

**Propósito:** Guardar el registro **exacto y completo** de cada medición para auditoría, análisis y debugging.

| Campo | Tipo | Nullable | Descripción |
|-------|------|----------|-------------|
| `id` | INT | NO | Identificador único |
| `id_operacion` | INT | SÍ | Operación a la que pertenece (FK) |
| `id_producto` | INT | SÍ | Producto medido (FK) |
| `botellas_cerradas` | INT | SÍ | Cantidad de botellas enteras |
| `pesos_abiertas` | TEXT (JSON) | SÍ | **Array JSON con cada peso individual** |
| `onzas_calculadas` | DECIMAL(10,2) | SÍ | **Onzas exactas SIN redondear** |
| `usuario_reg` | VARCHAR(255) | SÍ | Usuario que realizó el pesaje |
| `fecha_reg` | DATETIME | SÍ | Timestamp exacto (UTC) |

**Estructura de `pesos_abiertas` (JSON):**
```json
[
  {
    "peso": 950,
    "perfil_id": 1,
    "perfil_index": 0
  },
  {
    "peso": 945,
    "perfil_id": 1,
    "perfil_index": 0
  }
]
```

**Ejemplo de dato:**
```json
{
  "id": 1,
  "id_operacion": 42,
  "id_producto": 456,
  "botellas_cerradas": 12,
  "pesos_abiertas": [
    {"peso": 950, "perfil_id": 1, "perfil_index": 0},
    {"peso": 945, "perfil_id": 1, "perfil_index": 0}
  ],
  "onzas_calculadas": 11.92,
  "usuario_reg": "bernardo.prado",
  "fecha_reg": "2026-05-09T14:35:22Z"
}
```

---

### 7. **app_producto_pesaje_config_api** (Calibración de Balanzas)

**Propósito:** Definir parámetros de conversión peso → onzas para cada perfil de botella.

| Campo | Tipo | Nullable | Descripción |
|-------|------|----------|-------------|
| `id` | INT | NO | ID del perfil de botella |
| `id_producto_almacen` | INT | NO | **ID del producto** (puede haber múltiples perfiles por producto) |
| `nombre_perfil` | VARCHAR(100) | SÍ | Nombre descriptivo (ej: "Copa Estándar", "Botella Premium"). Default `'Estándar'` |
| `peso_bruto` | DECIMAL(10,2) | SÍ | Peso total cuando la botella está **llena** |
| `tara` | DECIMAL(10,2) | SÍ | Peso de la botella **vacía** |
| `gramos_por_oz` | DECIMAL(10,6) | SÍ | Factor de conversión gramos/oz. **Calculado por el backend**, no editable por el usuario: `(peso_bruto - tara) / volumen_estandar_oz`, donde `volumen_estandar_oz` es `alm_producto.cantidad_detalle` del mismo producto |
| `barcode` | VARCHAR(50) | SÍ | Código de barras del modelo de botella. Opcional; si no se especifica al crear, se copia el de otro perfil existente del mismo producto (si hay) |
| `tolerancia_oz` | DECIMAL(10,2) | SÍ | Columna heredada, default `1.50`. **No es configurable por el usuario** en el alta de un modelo: el valor operativo real siempre se calcula por categoría de producto vía `_obtener_tolerancia_operativa_oz` (0.5 oz para categorías 6/22, 0.25 oz para el resto), tanto al listar pendientes como al consolidar diferencias |
| `pesable` | INT (TINYINT) | SÍ | **0** = No pesable, **1** = Pesable |

**Clave única:** `(id_producto_almacen, nombre_perfil)` — evita duplicar el nombre de perfil dentro de un mismo producto, pero permite múltiples perfiles distintos por producto.

**Validaciones al crear un modelo (`POST /api/pesaje/perfiles`):**
- Nombre del modelo obligatorio (2-100 caracteres)
- `peso_bruto > tara` (obligatorio)
- El producto debe tener un volumen estándar válido en `alm_producto.cantidad_detalle` (de lo contrario no se puede calcular `gramos_por_oz`)
- El volumen del nuevo modelo es siempre el mismo que el del producto (no se permite definir un volumen distinto por perfil)

**Ejemplo de dato:**
```json
{
  "id": 1,
  "id_producto_almacen": 456,
  "nombre_perfil": "Botella Estándar",
  "peso_bruto": 1200,
  "tara": 250,
  "gramos_por_oz": 28.349523,
  "barcode": "7501234567890",
  "tolerancia_oz": 1.5,
  "pesable": 1
}
```

---

## Flujo Detallado de Almacenamiento

### Paso 1: Validación de Entrada

```python
# El cliente envía POST /api/inventario/paloteo con:
{
  "id_operacion": 42,
  "id_barra": 1,
  "observaciones": "Faltó reportar una botella de Vodka",
  "items": [
    {
      "id_producto": 456,
      "botellas_cerradas": 12,
      "pesos_abiertas": [
        {"peso": 950, "perfil_id": 1, "perfil_index": 0},
        {"peso": 945, "perfil_id": 1, "perfil_index": 0}
      ]
    }
  ]
}
```

**Backend Valida:**
1. ✅ Token JWT válido y no expirado
2. ✅ Usuario existe y está activo ('HAB')
3. ✅ Operación existe con `estado_operacion == 24`
4. ✅ No existe otro inventario para esta operación con `estado='HAB'`

---

### Paso 2: Creación de Cabecera

```python
# En bar_inventario_fisico:
nueva_cabecera = InventarioFisicoPOS(
    fecha=datetime.now().date(),  # 2026-05-09
    observaciones="Faltó reportar una botella de Vodka",
    procesado_por="PRADO LÓPEZ, BERNARDO",  # nombre formateado
    estado_registro=62,  # PENDIENTE
    id_barra=1,
    id_operacion=42,
    usuario_reg="bernardo.prado",
    fecha_reg=datetime.now().date(),
    estado='HAB'
)
db.add(nueva_cabecera)
db.flush()  # Genera el ID sin commitar
inventario_id = nueva_cabecera.id  # ej: 1
```

**Resultado en base de datos:**
```
INSERT INTO bar_inventario_fisico (...)
VALUES (id, 2026-05-09, "Faltó reportar...", "PRADO...", 62, 1, 42, 
        "bernardo.prado", 2026-05-09, 'HAB')
```

---

### Paso 3: Procesamiento de Productos

Para cada item en `items`:

```python
# 1. Obtener configuración de pesaje
configs = db.query(ProductoPesajeConfig).filter(
    ProductoPesajeConfig.id_producto_almacen == 456
).all()

config_base = configs[0]
perfiles = [cfg for cfg in configs if cfg.pesable == 1]

# 2. Calcular onzas
total_onzas = 0.0
margen_error = 10.0  # gramos

for abierta in pesos_abiertas:  # [950, 945]
    # Obtener perfil
    perfil = obtener_perfil(perfiles, abierta.perfil_id, abierta.perfil_index)
    
    # Validar peso
    tara = float(perfil.tara)  # 250
    gramos_oz = float(perfil.gramos_por_oz)  # 28.349523
    peso_medido = float(abierta.peso)  # 950
    
    if peso_medido >= (tara - margen_error):  # 950 >= 240
        peso_liquido = max(0, peso_medido - tara)  # 950 - 250 = 700
        onzas = peso_liquido / gramos_oz  # 700 / 28.349523 = 24.701...
        total_onzas += onzas

# Ejemplo con 2 botellas:
# Botella 1: (950 - 250) / 28.349523 = 24.701 oz
# Botella 2: (945 - 250) / 28.349523 = 24.556 oz
# Total: 49.257 oz

# 3. Redondear para POS
onzas_redondeadas = round(total_onzas * 2) / 2
# 49.257 * 2 = 98.514 → round(98.514) = 99 → 99 / 2 = 49.50
```

---

### Paso 4: Guardar Detalle (Datos Procesados para POS)

```python
nuevo_detalle = DetalleFisicoPOS(
    cantidad_unidad=12,  # botellas_cerradas
    cantidad_detalle=49.50,  # onzas redondeadas
    id_producto=456,
    id_inventario_fisico=1,  # FK a cabecera
    usuario_reg="bernardo.prado",
    fecha_reg=datetime.now().date(),
    estado='HAB'
)
db.add(nuevo_detalle)
```

**En base de datos:**
```
INSERT INTO bar_detalle_fisico (...)
VALUES (1, 12, 49.50, 456, 1, "bernardo.prado", 2026-05-09, 'HAB')
```

---

### Paso 5: Guardar Auditoría Cruda (Exacta)

```python
registro_crudo = PaloteoRegistroCrudo(
    id_operacion=42,
    id_producto=456,
    botellas_cerradas=12,
    pesos_abiertas=json.dumps([
        {"peso": 950, "perfil_id": 1, "perfil_index": 0},
        {"peso": 945, "perfil_id": 1, "perfil_index": 0}
    ]),
    onzas_calculadas=49.257,  # Exacto, NO redondeado
    usuario_reg="bernardo.prado",
    fecha_reg=datetime.now()  # DATETIME con minutos/segundos
)
db.add(registro_crudo)
```

**En base de datos:**
```
INSERT INTO app_paloteo_registro_crudo (...)
VALUES (1, 42, 456, 12, '[{"peso": 950, ...}]', 49.257, 
        "bernardo.prado", 2026-05-09 14:35:22)
```

---

### Paso 6: Commit a Base de Datos

```python
db.commit()  # Aplica todos los INSERT

# Respuesta exitosa al cliente:
{
  "status": "success",
  "id_inventario_pos": 1,
  "mensaje": "Se registraron 1 productos en el POS exitosamente.",
  "detalles": [
    {
      "id_producto": 456,
      "onzas_exactas": 49.26,
      "onzas_pos": 49.50
    }
  ]
}
```

---

## Validaciones y Controles

### 1. **Validaciones de Entrada (Pydantic - Frontend)**

```python
class PaloteoItem:
    id_producto: int  # > 0
    botellas_cerradas: int  # >= 0
    pesos_abiertas: List[PesoAbierta]  # min_length 0
    
    # Validación: no números negativos
    
class PesoAbierta:
    peso: float  # >= 0
    perfil_id: Optional[int]  # > 0 si presente
    perfil_index: Optional[int]  # >= 0 si presente
```

---

### 2. **Validaciones de Negocio (Backend)**

| Validación | Condición | Error (resumen) | HTTP |
|---|---|---|---|
| Operación inválida para registrar/corregir | No existe operación o `estado_operacion != 24` | "Operación inválida o barra no está en INICIO CIERRE" | 400 |
| Inventario duplicado (solo creación) | Ya existe con `id_operacion` y `estado='HAB'` | "Ya existe un inventario registrado" | 409 |
| Barra operativa no válida | `id_barra` no coincide con barra operativa o no habilitada | "La barra enviada... no coincide..." / "La barra solicitada no está habilitada" | 400 |
| Usuario activo | `usuario.estado != 'HAB' OR habilitado != '1'` | "Usuario no encontrado o inactivo" | 401 |
| Token expirado | `exp < now()` | "El token ha expirado" | 401 |
| Perfil inválido/incompleto | Perfil no encontrado o con datos incompletos | "Perfil de botella inválido/incompleto" | 400 |
| Peso inválido | `peso_medido > peso_bruto` | "Peso inválido... supera el peso bruto" | 400 |
| Capacidad excedida | `onzas_abierta > onzas_max_producto` | "Capacidad excedida" | 400 |

---

### 3. **Validaciones de Datos (Frontend)**

```javascript
// Prevención de errores por entrada accidental:

1. Números negativos: Se rechaza si cerradas < 0 o peso < 0
2. Peso inválido: Se bloquea si un peso supera el peso bruto del perfil
3. Capacidad excedida: Se bloquea si las onzas de una abierta superan la capacidad máxima
4. Campos vacíos: Se pide confirmación para registrar esos campos como 0
5. Diálogo de observaciones: Paso opcional antes del envío final
```

---

### 4. **Margen de Error en Balanza**

```python
margen_error_balanza = 10.0  # gramos

# Un peso se considera válido si:
if peso_medido >= (tara - margen_error):
    # Ejemplo: tara=250, margen=10
    # Válido si peso >= 240 (permite tolerancia de balanza)
```

---

## Ejemplos Prácticos

### Ejemplo 1: Cierre Simple (1 Producto, 2 Botellas Abiertas)

**Datos de entrada:**

```json
{
  "id_operacion": 42,
  "id_barra": 1,
  "observaciones": null,
  "items": [
    {
      "id_producto": 456,
      "botellas_cerradas": 12,
      "pesos_abiertas": [
        {"peso": 950, "perfil_id": 1, "perfil_index": 0},
        {"peso": 945, "perfil_id": 1, "perfil_index": 0}
      ]
    }
  ]
}
```

**Configuración de balanza (app_producto_pesaje_config_api):**
- `peso_bruto`: 1200
- `tara`: 250
- `gramos_por_oz`: 28.349523

**Cálculos:**

| Botella | Peso Medido | Tara | Peso Líquido | Onzas |
|---------|------------|------|--------------|-------|
| 1 | 950 | 250 | 700 | 24.701 |
| 2 | 945 | 250 | 695 | 24.532 |
| **TOTAL** | - | - | - | **49.233** |

**Redondeo para POS:**
```
49.233 * 2 = 98.466
round(98.466) = 98
98 / 2 = 49.00 oz
```

**Datos guardados:**

**bar_inventario_fisico:**
```
id: 1, id_operacion: 42, procesado_por: "PRADO LÓPEZ, BERNARDO",
estado_registro: 62, observaciones: "REGISTRADO VÍA API"
```

**bar_detalle_fisico:**
```
id: 1, id_producto: 456, cantidad_unidad: 12, cantidad_detalle: 49.00,
id_inventario_fisico: 1
```

**app_paloteo_registro_crudo:**
```
id: 1, id_operacion: 42, id_producto: 456, onzas_calculadas: 49.233,
pesos_abiertas: "[{peso: 950, ...}, {peso: 945, ...}]"
```

---

### Ejemplo 2: Cierre Con Observaciones

**Entrada:**

```json
{
  "id_operacion": 42,
  "id_barra": 1,
  "observaciones": "Detectada merma en botella Premium de Vodka",
  "items": [...]
}
```

**Resultado:**
```
bar_inventario_fisico.observaciones = "Detectada merma en botella Premium de Vodka"
```

---

### Ejemplo 3: Error - Inventario Duplicado

**Primer envío:** ✅ Exitoso, crea inventario

**Segundo envío:** ❌ Rechazado

```json
{
  "status": "error",
  "detail": "Ya existe un inventario registrado para esta operación (ID: 1). No se puede registrar dos veces.",
  "http_code": 409
}
```

---

## Seguridad y Auditoría

### 1. **Autenticación**

- **Método:** JWT (JSON Web Tokens)
- **Vigencia:** 600 minutos (10 horas)
- **Algoritmo:** HS256
- **Secret:** Cargado desde `.env`

```python
token_payload = {
    "sub": "bernardo.prado",  # Usuario
    "id": 1,                  # ID del usuario
    "exp": datetime.now() + timedelta(minutes=600)
}
token = jwt.encode(token_payload, SECRET_KEY, algorithm="HS256")
```

---

### 2. **Autorización**

- Cada endpoint verifica:
  1. ✅ Token presente en header `Authorization: Bearer {token}`
  2. ✅ Token válido y no expirado
  3. ✅ Usuario existe en `seg_usuario` con `estado='HAB'`

```python
@app.post("/api/inventario/paloteo")
def procesar_paloteo(
    payload: PaloteoRequest,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_usuario_actual)  # ← Validación
):
    # Aquí current_user ya está validado
```

---

### 3. **Auditoría de Accesos**

Cada login se registra en `seg_acceso`:

```
INSERT INTO seg_acceso (usuario, fecha, ip)
VALUES ('bernardo.prado', 2026-05-09 14:30:00, '192.168.1.100')
```

---

### 4. **Auditoría de Cambios**

**app_paloteo_registro_crudo** guarda:
- **Quién:** `usuario_reg` (quién hizo el pesaje)
- **Cuándo:** `fecha_reg` (timestamp UTC con precisión de segundos)
- **Qué:** Todos los pesos exactos sin redondear

Esto permite:
- Reproducir exactamente los cálculos
- Detectar fraudes o errores
- Analizar patrones de pesaje

---

### 5. **Validación de Integridad**

- **Constraint UNIQUE:** No puede haber dos inventarios con `id_operacion` y `estado='HAB'`
- **Foreign Keys:** Todas las referencias se validan
- **Tipos de datos:** MySQL rechaza datos fuera de rango

---

## Manejo de Errores

### Error 400: Bad Request (Datos Inválidos)

```
Causa: Operación inválida, estado no es 24, o datos malformados
Respuesta:
{
  "detail": "Operación inválida o barra no está en INICIO CIERRE."
}
```

---

### Error 401: Unauthorized (Autenticación)

```
Causa 1: Token no incluido
Respuesta: "Token inválido"

Causa 2: Token expirado
Respuesta: "El token ha expirado. Inicie sesión nuevamente."

Causa 3: Usuario inactivo
Respuesta: "Usuario no encontrado o inactivo"
```

---

### Error 403: Forbidden (No Autorizado)

```
Causa: Estado de operación es 22 (vendiendo), no 24 (cierre)
Respuesta:
{
  "detail": "Aún hay ventas activas. Cambie el estado de la operativa a INICIO CIERRE..."
}
```

---

### Error 404: Not Found (Recurso No Existe)

```
Causa: Operación activa no encontrada
Respuesta:
{
  "detail": "No se encontró ninguna operación activa en el sistema."
}
```

---

### Error 409: Conflict (Duplicado)

```
Causa: Ya existe un inventario para esta operación
Respuesta:
{
  "detail": "Ya existe un inventario registrado para esta operación (ID: 1). No se puede registrar dos veces."
}
```

---

### Error 500: Internal Server Error

```
Causa: Error en base de datos, cálculo, o lógica no prevista
Respuesta:
{
  "detail": "No se pudo procesar el paloteo. [mensaje técnico]"
}
```

**Acciones del backend:**
1. Log en `logging.exception()`
2. Rollback automático de transacción
3. Respuesta con error genérico

---

## FAQ Técnico

### P1: ¿Por qué se guardan dos tablas con datos de onzas (bar_detalle_fisico y app_paloteo_registro_crudo)?

**R:** Dos propósitos diferentes:

1. **bar_detalle_fisico:** Datos redondeados para **actualizar el POS**
   - El POS trabaja con media onza (11.50, 12.00, etc.)
   - Estos son los datos que se sincronizarán al sistema de inventario

2. **app_paloteo_registro_crudo:** Datos exactos para **auditoría y debugging**
   - Permite reproducir los cálculos exactamente
   - Útil para detectar discrepancias después del redondeo
   - Facilita análisis estadístico

---

### P2: ¿Qué pasa si la balanza falla durante el pesaje?

**R:** El sistema tiene tolerancia:

```python
margen_error = 10.0  # gramos

if peso_medido >= (tara - 10):
    # Se acepta (permite error de ±10g de la balanza)
else:
    # Se rechaza como inválido
```

El usuario recibe una advertencia visual en el frontend si el peso es sospechoso.

---

### P3: ¿Cómo se formatea el nombre del usuario en "procesado_por"?

**R:** Patrón: `"{PATERNO} {MATERNO}, {NOMBRES}"`

```python
nombre_formateado = f"{current_user.paterno} {current_user.materno}, {current_user.nombres}".upper()
# Ejemplo: "PRADO GARCÍA, BERNARDO"
```

Se convierte a mayúsculas para auditoría (estándar POS).

---

### P4: ¿Qué sucede si un producto tiene múltiples perfiles de botella?

**R:** El usuario elige el perfil al pesar:

**En el frontend:**
```html
<select class="select-perfil">
  <option value="1">Botella Estándar</option>
  <option value="2">Botella Premium</option>
</select>
```

**En la auditoría cruda:**
```json
{
  "peso": 950,
  "perfil_id": 2,  // Se guardó cuál se usó
  "perfil_index": 1
}
```

Esto permite:
- Trazabilidad de qué botella se pesó
- Auditoría de consistencia
- Mejora en precisión de cálculos futuros

---

### P5: ¿Se puede editar o eliminar un inventario ya guardado?

**R:** **Sí se puede corregir, con restricciones.**

- Existe endpoint de corrección: `PUT /api/inventario/paloteo/{id_inventario_pos}`.
- Solo permite correcciones mientras la operación siga en estado `24` (INICIO CIERRE).
- No existe endpoint `DELETE` para eliminar inventarios.

**Comportamiento de corrección:**
1. Se actualiza cabecera y detalles del inventario existente.
2. Solo se modifican productos con cambios efectivos (actualización selectiva).
3. Se sigue registrando auditoría cruda por cada envío de corrección.

---

### P6: ¿Cuál es el máximo número de botellas abiertas por producto?

**R:** No hay un límite duro en frontend/backend para la cantidad de botellas abiertas por producto.

El sistema actualmente no muestra advertencia específica por superar una cantidad de abiertas. Las protecciones activas son:

1. no negativos,
2. peso medido no mayor al peso bruto,
3. capacidad máxima por producto,
4. confirmación de campos vacíos.

---

### P7: ¿Qué hacer si el token JWT expira mientras estoy ingresando datos?

**R:** El token expira después de **600 minutos (10 horas)**.

Si expira:
- Frontend detecta el error 401
- Redirige a login
- Usuario vuelve a autenticarse
- Recupera su sesión de datos (PWA local storage)

---

### P8: ¿Los datos se sincronizan automáticamente al POS?

**R:** **NO** (Por diseño en fase actual)

**Flujo actual:**
1. Backend guarda en `bar_detalle_fisico`
2. `estado_registro = 62` (Pendiente)
3. Administrador ve "Nuevos Cierres Pendientes" en POS
4. Admin revisa y **aprueba manualmente**
5. Admin ejecuta sincronización
6. Datos se integran al inventario

**Futuro:**
- Automatizar sincronización en ciertos criterios
- Webhook para notificar cambios

---

### P9: ¿Cómo se recuperan los datos si falla la conexión?

**R:** 

**Antes del envío:**
- Datos en memoria del navegador
- PWA guarda estado en localStorage
- Usuario puede recuperar la sesión si actualiza

**Después del envío:**
- Datos ya en la BD (committed)
- Respuesta 200 OK confirma
- PWA limpia localStorage

---

### P10: ¿Hay límite de tamaño en el campo "observaciones"?

**R:** Sí, **VARCHAR(255)**

- Máximo 255 caracteres
- El límite duro está en base de datos
- Si se excede, el backend/BD rechazará el valor

**Recomendación:** Usar frases cortas y puntuales.

---

### P11: ¿Los datos del módulo REPORTE se almacenan de otra forma además del PDF?

**R:** El módulo REPORTE no persiste una tabla propia de "reportes".

1. Las filas del reporte se calculan en frontend desde la captura actual de Paloteo 3.
2. Los datos base sí se persisten cuando se guarda inventario (cabecera + detalle + auditoría cruda).
3. El endpoint `/api/paloteo3/exportar-pdf` genera y devuelve el PDF al cliente; no guarda el archivo en servidor.
4. Existe autosave local (localStorage) para borrador operativo, no como histórico oficial de reportes.

---

## Resumen de Flujo

```
LOGIN
  ↓
VERIFICAR OPERACIÓN (estado=24)
  ↓
CARGAR PRODUCTOS PENDIENTES
  ↓
USUARIO INGRESA DATOS
  ↓
VALIDAR DATOS (no negativos, peso/capacidad, vacíos)
  ↓
SOLICITAR OBSERVACIONES (opcional)
  ↓
ENVIAR POST /api/inventario/paloteo
  ↓
BACKEND VALIDA:
  ├─ Token JWT
  ├─ Operación activa
  ├─ No duplicado
  └─ Datos válidos
  ↓
CREAR CABECERA (bar_inventario_fisico)
  ↓
PARA CADA PRODUCTO:
  ├─ Calcular onzas exactas
  ├─ Redondear para POS
  ├─ Guardar en bar_detalle_fisico (redondeado)
  └─ Guardar en app_paloteo_registro_crudo (exacto)
  ↓
COMMIT A BASE DE DATOS
  ↓
RESPUESTA 200 SUCCESS
  ↓
FRONTEND MANTIENE DATOS Y PERMITE CORRECCIÓN
```

---

## Conclusión

Este sistema proporciona:

✅ **Precisión:** Dos niveles de almacenamiento (procesado + auditoría exacta)  
✅ **Seguridad:** Autenticación JWT, registro de accesos, validaciones de integridad  
✅ **Auditoría:** Quién, cuándo, qué (incluyendo pesos exactos)  
✅ **Prevención de errores:** validaciones de peso/capacidad, no negativos y confirmación de campos vacíos  
✅ **Integridad:** Prevención de inventarios duplicados, transacciones ACID  
✅ **Trazabilidad:** Perfiles de botellas seleccionados guardados en auditoría  

---

**Documentación preparada por:** Backend Architecture Team  
**Última actualización:** 11 de junio de 2026  
**Versión:** 1.1
