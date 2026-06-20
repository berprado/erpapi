# TODO — API Inventario POS

## 🔴 Alta Prioridad

- [ ] **Reemplazar SECRET_KEY en `.env` por una clave real y aleatoria antes de pasar a producción**
  - `.env` sigue usando el placeholder `cambia_esto_por_una_clave_larga_y_aleatoria_en_produccion` (pasa la validación de longitud ≥32, pero no es aleatorio).
  - Generar con: `python -c "import secrets; print(secrets.token_hex(32))"`

- [x] **Reemplazar el token simulado de autenticación por JWT real en el endpoint `/api/auth/login`**
  - Confirmado: `login()` genera JWT real (`jwt.encode` con `SECRET_KEY`/`ALGORITHM`), valida usuario/contraseña/estado y registra acceso en `seg_acceso`.

- [x] **Extraer el usuario logueado desde el token en todos los endpoints protegidos**
  - Todos los endpoints que registran `usuario_reg` usan `current_user` desde `Depends(get_usuario_actual)` (paloteo, ajustes, perfiles de pesaje, etc.).

## 🟡 Media Prioridad

- [x] **Manejar productos sin configuración de pesaje en `procesar_paloteo`**
  - Implementado: `_procesar_items_paloteo` devuelve `productos_omitidos` y se incluye en la respuesta de los endpoints de paloteo (no se omiten en silencio).

- [x] **Proteger el endpoint `/api/operacion/activa` con autenticación JWT**
  - Ya usa `Depends(get_usuario_actual)` (`main.py:437`).

- [ ] **Implementar refresh token**
  - El token actual expira en 10 horas (`ACCESS_TOKEN_EXPIRE_MINUTES = 600`).
  - Evaluar si se necesita un mecanismo de renovación automática.

## 🟢 Baja Prioridad / Mejoras Futuras

- [ ] **Separar los endpoints en routers por módulo (FastAPI `APIRouter`)**
  - `auth.py`, `inventario.py`, `operacion.py` — para mantener `main.py` limpio a medida que crece.

- [x] **Agregar logging estructurado**
  - `config.py` ya usa `logging.getLogger(__name__)` en lugar de `print()` (Fix #20). Pendiente evaluar si se extiende a `main.py`.

- [ ] **Agregar manejo de errores global**
  - Implementar un `exception_handler` en FastAPI para respuestas de error consistentes.

- [ ] **Tests automatizados**
  - Cubrir al menos: login correcto, login fallido, paloteo válido, paloteo con operación inválida.

- [ ] **Revisar si `engine` se necesita en algún módulo futuro**
  - Actualmente fue removido de `main.py` por no usarse.

## 📌 Pendiente de Validaciones de Cantidades y Pesos (Paloteo 1, 2 y 3)

- [x] **Alinear validaciones Frontend/Backend para pesos fisicos maximos**
  - Implementado: bloqueo duro en backend y frontend para `peso > peso_bruto` por perfil.

- [x] **Definir y aplicar regla de sobrecapacidad de onzas por botella en backend**
  - Implementado: sobrecapacidad de onzas se trata como error bloqueante en backend y frontend.

- [x] **Validar unicidad de `id_producto` en `items` del payload de paloteo**
  - Implementado en schema de request para evitar duplicados en creacion/correccion.

- [x] **Revisar consistencia funcional de PALOTEO 3 vs PALOTEO 1/2**
  - Resuelto: PALOTEO 3 reutiliza `leerValoresCard`/`aplicarValoresCard` (igual que el modo captura 1x1), soporta multi-botella y multi-perfil, y corrige el step de los botones +/- de peso para que sea proporcional a `gramos_por_oz`.

- [ ] **Mejorar precarga de corrección para múltiples botellas abiertas**
  - Actualmente se repone solo el primer peso/perfil; evaluar restauración completa de todas las entradas capturadas.
