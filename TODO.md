# TODO — API Inventario POS

## 🔴 Alta Prioridad

- [ ] **Reemplazar SECRET_KEY en `.env` por una clave real y aleatoria antes de pasar a producción**
  - Generar con: `python -c "import secrets; print(secrets.token_hex(32))"`

- [ ] **Reemplazar el token simulado de autenticación por JWT real en el endpoint `/api/auth/login`**
  - Ya está implementado el sistema JWT, verificar que funcione end-to-end con el cliente móvil.

- [ ] **Extraer el usuario logueado desde el token en todos los endpoints protegidos**
  - `procesar_paloteo` ya fue corregido.
  - Revisar cualquier endpoint futuro que registre `usuario_reg`.

## 🟡 Media Prioridad

- [ ] **Manejar productos sin configuración de pesaje en `procesar_paloteo`**
  - Actualmente se omiten en silencio (`if not config: continue`).
  - Decidir si se debe retornar un `400` o incluir una lista de `omitidos` en la respuesta.

- [ ] **Proteger el endpoint `/api/operacion/activa` con autenticación JWT**
  - Actualmente es público. Agregar `Depends(get_usuario_actual)` si se requiere.

- [ ] **Implementar refresh token**
  - El token actual expira en 10 horas (`ACCESS_TOKEN_EXPIRE_MINUTES = 600`).
  - Evaluar si se necesita un mecanismo de renovación automática.

## 🟢 Baja Prioridad / Mejoras Futuras

- [ ] **Separar los endpoints en routers por módulo (FastAPI `APIRouter`)**
  - `auth.py`, `inventario.py`, `operacion.py` — para mantener `main.py` limpio a medida que crece.

- [ ] **Agregar logging estructurado**
  - Reemplazar los `print()` de `config.py` por un logger real (`logging` o `loguru`).

- [ ] **Agregar manejo de errores global**
  - Implementar un `exception_handler` en FastAPI para respuestas de error consistentes.

- [ ] **Tests automatizados**
  - Cubrir al menos: login correcto, login fallido, paloteo válido, paloteo con operación inválida.

- [ ] **Revisar si `engine` se necesita en algún módulo futuro**
  - Actualmente fue removido de `main.py` por no usarse.

## 📌 Pendiente de Validaciones de Cantidades y Pesos (Paloteo 1, 2 y 3)

- [ ] **Alinear validaciones Frontend/Backend para pesos físicos máximos**
  - Implementar en backend la misma regla de bloqueo duro que ya existe en frontend para `peso > peso_bruto` por perfil.

- [ ] **Definir y aplicar regla de sobrecapacidad de onzas por botella en backend**
  - Actualmente en frontend es advertencia confirmable; falta una regla explícita del lado servidor para mantener consistencia.

- [ ] **Validar unicidad de `id_producto` en `items` del payload de paloteo**
  - Evitar duplicados en creación/corrección que puedan producir resultados no deterministas.

- [ ] **Revisar consistencia funcional de PALOTEO 3 vs PALOTEO 1/2**
  - PALOTEO 3 captura un solo peso por producto, mientras PALOTEO 1/2 soportan múltiples abiertas y perfiles.
  - Definir si es decisión funcional o si debe unificarse el modelo de captura.

- [ ] **Mejorar precarga de corrección para múltiples botellas abiertas**
  - Actualmente se repone solo el primer peso/perfil; evaluar restauración completa de todas las entradas capturadas.
