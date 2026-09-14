# Validaciones de Datos en los Módulos de Paloteo, Pesaje y Pour Cost

Este documento describe de manera exhaustiva todas las validaciones de datos aplicadas en la aplicación (tanto en el **Frontend PWA / Vanilla JS** como en el **Backend FastAPI / Python / Pydantic**) para los módulos de **Paloteo**, **Pesaje** y **Pour Cost**.

---

## 1. Módulo de Paloteo (PALOTEO 1, 2, 3 y Ajustes)

El módulo de paloteo permite el registro y corrección del inventario físico en barra. Para garantizar la integridad de las mediciones y evitar datos inconsistentes, se aplican validaciones en multinivel:

### 1.1. Validaciones en el Frontend (PWA / Vanilla JS)

1. **Teclado Adaptativo y Restricción de Tipo:**
   - Todos los campos de entradas de unidades cerradas y pesos utilizan atributos HTML5 `inputmode="numeric"` o `inputmode="decimal"` y `min="0"`, forzando el teclado numérico en dispositivos móviles y previniendo el ingreso de caracteres no numéricos.
2. **Validación de Peso Bruto (Bloqueo Duro):**
   - Antes de enviar el paloteo, el cliente compara el peso ingresado contra el `peso_bruto` del perfil seleccionado.
   - Si $\text{peso\_ingresado} > \text{peso\_bruto}$, se muestra una ventana modal de error notificando la botella y el valor excedido. **Se bloquea el envío hasta corregir.** *(Excepto en categoría VINOS).*
3. **Validación de Capacidad Máxima de Envase (Bloqueo Duro):**
   - Para botellas pesables, calcula las onzas equivalentes:
     $$\text{onzas} = \frac{\max(0, \text{peso\_ingresado} - \text{tara})}{\text{gramos\_por\_oz}}$$
   - Si $\text{onzas} > \text{onzas\_por\_botella\_llena}$, la PWA despliega una alerta indicando la capacidad máxima excedida. **Se bloquea el envío.**
4. **Detección y Confirmación de Campos Vacíos (Advertencia Confirmable):**
   - Si un producto de la lista tiene campos de unidades o pesos vacíos, la PWA muestra un diálogo de confirmación listing los productos omitidos:
     > *"Los siguientes campos están vacíos y se registrarán como 0. ¿Confirmas que representan cero?"*
   - Si el usuario acepta, la PWA completa automáticamente los campos vacíos con `'0'` antes de enviar el payload. Si cancela, vuelve a la vista de edición.
5. **Autosave Local:**
   - La PWA guarda borradores locales aislados por `operativa + barra + usuario`, evitando pérdidas de datos por desconexión o navegación accidental.

### 1.2. Validaciones en el Backend (FastAPI / Pydantic)

1. **Esquema Pydantic (`schemas.PaloteoRequest`):**
   - `id_operacion` y `id_barra`: enteros estrictamente mayores a cero (`gt=0`).
   - `botellas_cerradas`: entero no negativo (`ge=0`).
   - `pesos_abiertas`: lista de objetos `PesoAbierta`, donde cada peso individual valida `ge=0` (`validar_pesos_positivos`).
   - `items`: exige al menos un elemento (`min_length=1`) e impone **unicidad de `id_producto`** mediante el validador `@field_validator('items')`. Si se envía un `id_producto` duplicado, retorna `422 Unprocessable Entity` o `400 Bad Request`.
2. **Máquina de Estado de Operativa:**
   - Solamente se permite `POST` (registro) o `PUT` (corrección) si la operativa en `ope_operacion` está en estado **`24` (INICIO CIERRE)**. Si está en otro estado, la API responde `400 Bad Request` y el frontend se conmuta automáticamente a modo *solo lectura*.
3. **Validación de Barra Operativa:**
   - El `id_barra` enviado en el JSON debe coincidir exactamente con la barra operativa resuelta por la sesión (`_resolver_barra_operativa`). De lo contrario, rechaza con `400 Bad Request`.
4. **Prevención de Registros Duplicados:**
   - En `POST /api/inventario/paloteo`, la API verifica que no exista previamente una cabecera habilitada (`estado='HAB'`) para ese `id_operacion`. Si ya existe, responde `409 Conflict`.
5. **Validaciones de Balanza y Margen de Error por Botella:**
   - **Tolerancia de Balanza:** Se valida que $\text{peso\_medido} \ge (\text{tara} - 10\text{g})$. Si es menor a la tara menos $10\text{g}$, la diferencia líquida se calcula como $0$.
   - **Verificación de Incompletos:** Si un producto pesable tiene un perfil incompleto (`tara IS NULL`, `peso_bruto <= 0` o `gramos_por_oz <= 0`), la API rechaza el registro con `400 Bad Request`.
   - **Exceso de Peso y Capacidad:** Backend vuelve a validar de forma independiente que ningún peso medido supere el peso bruto del perfil ni que las onzas calculadas superen la capacidad de la botella. Si ocurre, retorna `400 Bad Request`.

---

## 2. Módulo de Pesaje (Gestión de Perfiles y Modelos de Botella)

El módulo de Pesaje gestiona la configuración de pesabilidad, tara, peso bruto y códigos de barra de las botellas.

### 2.1. Validaciones en el Frontend (PWA / Vanilla JS)

1. **Restricción de Acceso por Rol:**
   - Solamente accesible si el usuario autenticado tiene `is_admin = True`. La interfaz oculta las pestañas y botones de edición a usuarios estándar.
2. **Validación de Datos en Formulario Modal (`#pesaje-modal`):**
   - **Peso Bruto:** Debe ser un número estrictamente mayor a $0$.
   - **Tara:** Debe ser un número mayor o igual a $0$.
   - **Relación Bruto vs Tara:** La PWA impide enviar si $\text{tara} \ge \text{peso\_bruto}$, mostrando un diálogo de error explicativo.
3. **Caso Especial VINOS (`id_categoria = 6`):**
   - La etiqueta del campo cambia visualmente a *"Copas por botella"*.
   - El campo tara se oculta o deshabilita forzando automáticamente su valor a $0$.
4. **Preservación de Scroll e Interacción Modal:**
   - Al guardar, agregar o eliminar modelos dentro del modal, la vista se refresca sin cerrar la ventana emergente, manteniendo la posición de scroll.
5. **Protección de Deshabilitación de Eliminar:**
   - El botón *Eliminar modelo* se deshabilita con aviso si el producto tiene un único modelo activo, evitando intentos fallidos hacia la API.

### 2.2. Validaciones en el Backend (FastAPI / Pydantic)

1. **Protección de Ruta:**
   - Todos los endpoints (`/api/pesaje/*`) exigen rol de administrador (`_es_usuario_administrador`). Si no lo posee, retorna `403 Forbidden`.
2. **Creación de Perfil (`POST /api/pesaje/perfiles`):**
   - `id_producto`: entero positivo (`gt=0`).
   - `nombre_perfil`: cadena de $2$ a $100$ caracteres.
   - `peso_bruto`: flotante strictly mayor a cero (`gt=0`).
   - `tara`: flotante no negativo (`ge=0`).
   - **Regla Tara < Bruto:** Retorna `400 Bad Request` si $\text{tara} \ge \text{peso\_bruto}$ (para productos no vinos).
   - **Unicidad de Perfil:** Verifica la clave única `(id_producto_almacen, nombre_perfil)`. Si ya existe activo, retorna `409 Conflict`. Si existía pero estaba eliminado (`estado='DES'`), la API lo reactiva automáticamente con los nuevos datos.
   - **Regla VINOS (`id_categoria = 6`):** Fuerza $\text{tara} = 0.0$ y $\text{gramos\_por\_oz} = 1.0$. Si el cliente envía tara distinta de $0$, retorna `400 Bad Request`.
3. **Edición / Promoción de Perfil (`PUT /api/pesaje/config/{id}`):**
   - Soporta ediciones parciales (ejemplo: guardar solo `peso_bruto` o solo `barcode`).
   - **Regla de Promoción (*Promover* `pesable=0` $\rightarrow$ `1`):** Si un producto tiene `pesable=0`, solo se permite asignarle `peso_bruto`/`tara` si el catálogo indica que debe ser pesable (`_producto_deberia_ser_pesable`, evaluando `p_unidad_medida IN (11, 61)`). De lo contrario, rechaza con `400 Bad Request`.
4. **Eliminación Segura (`DELETE /api/pesaje/config/{id}`):**
   - Aplica *soft-delete* (`estado = 'DES'`).
   - **Protección de Último Modelo:** Consulta cuántos perfiles activos le quedan al producto. Si se intenta eliminar el último modelo activo, responde `400 Bad Request` con el mensaje: *"No se puede eliminar el último modelo del producto."*

---

## 3. Módulo de Pour Cost (Costo de Receta y Sandbox de Simulación)

El módulo de Pour Cost calcula los costos de receta (WAC) y porcentajes de pour cost de cócteles y productos sueltos.

### 3.1. Validaciones en el Frontend (PWA / Sandbox)

1. **Entorno de Simulación en Memoria:**
   - Ninguna acción del módulo de Pour Cost escribe o persiste datos en la base de datos. Todos los ajustes son locales y temporales.
2. **Edición de Cantidades por Ingrediente:**
   - Controles `[-] [cantidad] [+]` con paso de $0,5$ unidades.
   - La cantidad mínima permitida es $0$.
   - Normalización de entradas manuales: Acepta comas (`,`) o puntos (`.`) decimales, convirtiéndolos a un valor numérico estable (`1`, `1.0`, `1,5` $\rightarrow$ `1.5`).
   - Rechazo de entradas no numéricas, vacías o negativas.
3. **Selección de Ingredientes Opcionales:**
   - Los ingredientes con `tipo_parte_combo = 'OPCIONAL'` cuentan con un checkbox independiente.
   - Si no está seleccionado, sus cambios de cantidad o WAC no afectan el costo total de la simulación.
   - Los ingredientes principales no se pueden desmarcar ni excluir del cálculo.
4. **Cálculo de Porcentaje Objetivo y Precio Sugerido:**
   - Permite ingresar un **% Pour Cost Objetivo**. Si el valor ingresado es un número válido y mayor a $0$, calcula reactivamente el **Precio Sugerido**:
     $$\text{Precio Sugerido Exacto} = \frac{\text{Costo Total Simulado}}{\text{Pour Cost Objetivo \%} / 100}$$
   - Muestra tanto el valor exacto como el redondeado a número entero superior/estándar mediante redondeo `HALF_UP`.
5. **Reinicio de Simulación:**
   - Al pulsar *"Reiniciar simulación"*, se descartan los cambios en memoria re-clonando el estado original entregado por la API.

### 3.2. Validaciones en el Backend (FastAPI)

1. **Restricción de Acceso:**
   - Endpoints `/api/pourcost/*` restringidos a usuarios con `is_admin = True` (`403 Forbidden`).
2. **Validación de Grupos de Precio (`id_dia`):**
   - Valida el parámetro `id_dia` contra los grupos de precio activos configurados en `POURCOST_DIAS_PRECIO_ACTIVOS` (`config.py`).
3. **Tratamiento de WAC Faltante (Sin WAC):**
   - Si un ingrediente no cuenta con costo en el caché WAC (`v9_cache_wac_producto`), la API no lo asume como $0$ ni lo oculta silenciosamente; marca los flags `sin_wac = True` y `costo_incompleto = True` en la respuesta para que la PWA alerte al usuario sobre un costo de receta parcial.

---

## 4. Validaciones Transversales de Seguridad y Consolidación

### 4.1. Autenticación y Control de Intentos (Login)

1. **Anti-Enumeración de Usuarios:**
   - Tanto si el usuario no existe como si la contraseña es incorrecta, la API retorna el mismo mensaje genérico `401 Unauthorized` (*"Usuario o contraseña incorrectos"*).
2. **Rate Limiting (Control de Fuerza Bruta):**
   - Basado en auditoría real en `app_login_auditoria_api`:
     - Máximo $5$ intentos fallidos por usuario (`LOGIN_MAX_INTENTOS_USUARIO`).
     - Máximo $20$ intentos fallidos por IP (`LOGIN_MAX_INTENTOS_IP`).
     - Ventana de tiempo: $5$ minutos (`LOGIN_VENTANA_MINUTOS`).
   - Al superar el límite, la API responde `429 Too Many Requests`. Un login exitoso resetea el contador.

### 4.2. Consolidación de Ajustes de Inventario

1. **Estado de Operativa:**
   - `POST /api/inventario/ajustes/aplicar` exige que la operativa esté en estado **`23` (CERRADA)**.
2. **Control de Idempotencia:**
   - Registrado en la tabla `app_paloteo_ajuste_control` con clave única `(id_operacion, id_barra, id_inventario_fisico)`.
   - Si se intenta aplicar nuevamente un ajuste ya consolidado, responde `409 Conflict`.
3. **Validación de Inexistencia de Movimientos (`skipped`):**
   - Si el cálculo de diferencias no genera ninguna diferencia física fuera de la banda de tolerancia, responde `status: "skipped"` sin crear documentos de movimiento ni alterar `bar_inventario`.

---

## 5. Cuadro Resumen de Validaciones por Módulo

| Módulo | Campo / Acción | Regla de Validación | Capa | Resultado ante Fallo |
|---|---|---|---|---|
| **Paloteo** | Cantidad Cerradas | Entero $\ge 0$ | PWA / Pydantic | Bloqueo HTML5 / `422 Unprocessable` |
| **Paloteo** | Peso Abiertas | Flotante $\ge 0$ | PWA / Pydantic | Bloqueo HTML5 / `422 Unprocessable` |
| **Paloteo** | Unicidad Productos | Sin `id_producto` duplicado | Pydantic | `422 Unprocessable` |
| **Paloteo** | Peso vs Peso Bruto | $\text{peso} \le \text{peso\_bruto}$ | PWA / Backend | Bloqueo Modal PWA / `400 Bad Request` |
| **Paloteo** | Onzas vs Capacidad | $\text{onzas} \le \text{capacidad\_máxima}$ | PWA / Backend | Bloqueo Modal PWA / `400 Bad Request` |
| **Paloteo** | Estado Operativa | Estado `= 24` (Inicio Cierre) | Backend | `400 Bad Request` / PWA Solo Lectura |
| **Paloteo** | Barra Operativa | Coincidir con barra activa | Backend | `400 Bad Request` |
| **Pesaje** | Rol de Usuario | Requiere `is_admin = True` | Backend | `403 Forbidden` |
| **Pesaje** | Nombre de Perfil | Longitud 2 a 100 caracteres | Pydantic | `422 Unprocessable` |
| **Pesaje** | Tara vs Bruto | $\text{tara} < \text{peso\_bruto}$ | PWA / Backend | Bloqueo Modal PWA / `400 Bad Request` |
| **Pesaje** | Vinos (Categoría 6) | $\text{tara} = 0$, $\text{g/oz} = 1$ | Backend | `400 Bad Request` (si tara $\neq 0$) |
| **Pesaje** | Promover Pesable | `p_unidad_medida IN (11, 61)` | Backend | `400 Bad Request` |
| **Pesaje** | Eliminar Perfil | Prohibido borrar el último | Backend | `400 Bad Request` |
| **Pour Cost** | Modificación Receta | Sandbox en memoria local | PWA | No altera base de datos |
| **Pour Cost** | Cantidad Receta | Decimal $\ge 0$, paso $0.5$ | PWA | Rechazo de valores negativos/inválidos |
| **Ajustes** | Consolidación | Estado `= 23` (Cerrada) + Rol Admin | Backend | `400 Bad Request` / `403 Forbidden` |
| **Ajustes** | Re-aplicación | Clave única en `app_paloteo_ajuste_control` | Backend | `409 Conflict` |
| **Login** | Intentos Fallidos | Max 5 por usuario / 20 por IP | Backend | `429 Too Many Requests` |
