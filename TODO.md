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

- [ ] **Identificar focos de recetas mal configuradas en `bar_detalle_combo_bar`**
  - Motivacion: todas las recetas vigentes (828 filas activas con `ind_paq_detalle='0'`) usan cantidades multiplo de 0.5 oz, pero se encontraron 5 ventas historicas (2025-08-02 a 2025-09-14, `bar_detalle_sal_combo_coctel`) que descontaron 0.07 oz de Coca Cola via el combo "V BUHO NEGRO" (id 392) — un valor que no coincide con la receta actual de ese combo (4.00 oz). La receta ya fue corregida, pero el residuo ya aplicado a `bar_inventario` en su momento nunca se corrigio retroactivamente y se arrastra entre operativas via `bar_inventario_cierre`.
  - Revisar si existen otros combos con historial de cantidades atipicas (no multiplo de 0.5) en `bar_detalle_sal_combo_coctel`, mas alla de este caso ya cerrado.

- [ ] **Revisar el redondeo del monto documentado en `bar_detalle_ajuste`/`bar_detalle_salida_inv` para categorias con tolerancia 0.25 oz**
  - Motivacion: probando casos limite contra la BD de test (operativa sintetica 1239), un producto de categoria con tolerancia 0.25 (JARANA SILVER 1LT, id 297) con diferencia exacta de 0.25 oz genero un movimiento documentado de **0.50 oz** (no 0.25), porque `_redondear_media_onza_half_up` redondea el delta operativo a multiplos de 0.5 antes de guardarlo. `bar_inventario` igual queda igualado correctamente al fisico (26.50, verificado), pero el comprobante de auditoria sobre-reporta la magnitud del ajuste en estos casos. No afecta a categorias con tolerancia 0.5 (ahi 0.5 ya es el paso minimo, no hay distorsion).
  - Evaluar si el monto documentado deberia reflejar el delta exacto (sin redondear a 0.5) cuando la categoria usa tolerancia 0.25, para que el comprobante coincida con la causa real del ajuste.

- [ ] **Tests automatizados para el modulo AJUSTES (`/api/inventario/consolidar/preview` y `/api/inventario/ajustes/aplicar`)**
  - Motivacion: en la rama `claude/adjustments-module-guide-xp8pt8` un bug de SQL (join roto contra `inventario_excluido`/`vista_inventario_barra_con_filtro`) dejo `_calcular_diferencias_paloteo` siempre vacio en silencio; solo se detecto con pruebas manuales end-to-end armando data de prueba en BD. Un test automatizado lo habria detectado en el primer commit.
  - Cubrir al menos: `_calcular_diferencias_paloteo` con diferencias reales (sobrante/faltante en paq y det), idempotencia (`409` en segundo intento de aplicar), validacion de cardinalidad de `bar_inventario` (`_validar_cardinalidad_bar_inventario`, producto sin fila vs duplicada), gating de admin (`403` sin `ROLE_ADMIN`), y operativa no en estado `23` (`400`).
  - Requiere antes un setup minimo de pytest + fixtures de BD de test (hoy no existe ningun test en el repo).
  - Una vez exista el setup, ampliar tambien a login correcto/fallido y paloteo valido/con operacion invalida.

- [ ] **Bloquear la busqueda-en-catalogo (agregar producto sin movimiento) en modo solo-lectura**
  - Motivacion: el flujo de "agregar producto sin movimiento" (v10.37) no verifica `operativaPermitePaloteo` antes de mostrar resultados del catalogo y permitir agregarlos. La card/fila resultante sí queda con sus inputs deshabilitados (igual que el resto en modo solo-lectura), asi que no hay impacto funcional ni de seguridad, pero la busqueda deja agregar una card "muerta" que no se puede llenar. Evaluar ocultar el resultado de catalogo (o el boton "+ Agregar") cuando `!operativaPermitePaloteo`.

## 🟢 Baja Prioridad / Mejoras Futuras

- [ ] **Separar los endpoints en routers por módulo (FastAPI `APIRouter`)**
  - `auth.py`, `inventario.py`, `operacion.py` — para mantener `main.py` limpio a medida que crece.

- [x] **Agregar logging estructurado**
  - `config.py` ya usa `logging.getLogger(__name__)` en lugar de `print()` (Fix #20). Pendiente evaluar si se extiende a `main.py`.

- [ ] **Agregar manejo de errores global**
  - Implementar un `exception_handler` en FastAPI para respuestas de error consistentes.

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

- [ ] **Verificar las validaciones implementadas en Paloteo 1, 2 y 3**
  - Repasar end-to-end (frontend y backend) las validaciones ya marcadas como resueltas en esta sección (pesos máximos, sobrecapacidad de onzas, unicidad de `id_producto`) y confirmar que se comportan igual en los tres módulos tras los cambios recientes de consistencia funcional y foco.

- [ ] **Restringir a administradores los botones de ajuste (+/-) en PALOTEO 1 y PALOTEO 2**
  - Ya implementado en PALOTEO 3 (`esUsuarioAdministrador()` oculta `stock-btn-dec-unid`/`inc-unid` y `stock-btn-dec-peso`/`inc-peso`).
  - Aplicar el mismo criterio a los botones equivalentes de PALOTEO 1 y 2 (decisión explícita de dejarlos para después, ver `CHANGELOG.md` v10.22).
  - Evaluar si conviene además una validación server-side, dado que hoy es una restricción solo de frontend.
