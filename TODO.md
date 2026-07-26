# TODO — API Inventario POS

## 🔴 Alta Prioridad

- [ ] **Implementar actualización de precisión ML→OZ en PRODUCCIÓN (cuando test_pos sea estable)**
  - **Status:** ✓ COMPLETADO EN test_pos, PENDIENTE PRODUCCIÓN
  - **Cambios:** 306 productos con redondeo HALF_UP a 0.5 oz + 149 perfiles de pesaje recalculados
  - **Ambientes:**
    - ✓ test_pos (remoto POS real): ACTUALIZADO Y VALIDADO (operativa 1249 completó ciclo completo)
    - ⏳ Producción (localhost): SIN CAMBIOS, en standby
  - **Próximos pasos cuando test_pos sea confirmado estable:**
    1. Backup completo de BD producción
    2. Ejecutar `TEST_POS_UPDATE_1_alm_producto.sql` (306 updates)
    3. Ejecutar `TEST_POS_UPDATE_2_gramos_por_oz.sql` (149 updates)
    4. Validar integridad post-actualización
    5. Monitorear primera operativa de producción
    6. Comunicar cambios a equipo operativo
  - **Documentación:** Ver `scratchpad/TRABAJO_FINALIZADO_PRECISION_ML_OZ.md`
  - **Validación en test_pos:** Paloteos precisos a 0.5 oz, falsos positivos eliminados, diferencias reales visibles ✓

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

- [ ] **Resolver los 4 conflictos excepcionales de pesable en PESAJE**
  - Contexto (detectado en `adminerp_copy`, `APP_ENV=test`): hay 4 productos habilitados y pesables por catálogo (`alm_producto.estado='HAB'`, `ind_permite_comandar=71`, fuera de categorías excluidas) que tienen configuración activa con `pesable=0` en `app_producto_pesaje_config_api`.
  - Productos identificados: `ALMA TANNAT ROSADO 750ML` (id 296), `DUO TANNAT MERLOT 750ML` (id 258), `MOSCOW MULE LATA` (id 478), `PATRON SILVER 750ML` (id 31).
  - Decisión actual: mantenerlos como **casos excepcionales** (sin corrección inmediata).
  - Pendiente: definir criterio de negocio y resolver su situación (homologar catálogo/configuración o documentar excepción permanente).

- [ ] **Identificar focos de recetas mal configuradas en `bar_detalle_combo_bar`**
  - Motivacion: todas las recetas vigentes (828 filas activas con `ind_paq_detalle='0'`) usan cantidades multiplo de 0.5 oz, pero se encontraron 5 ventas historicas (2025-08-02 a 2025-09-14, `bar_detalle_sal_combo_coctel`) que descontaron 0.07 oz de Coca Cola via el combo "V BUHO NEGRO" (id 392) — un valor que no coincide con la receta actual de ese combo (4.00 oz). La receta ya fue corregida, pero el residuo ya aplicado a `bar_inventario` en su momento nunca se corrigio retroactivamente y se arrastra entre operativas via `bar_inventario_cierre`.
  - Revisar si existen otros combos con historial de cantidades atipicas (no multiplo de 0.5) en `bar_detalle_sal_combo_coctel`, mas alla de este caso ya cerrado.

- [x] **Revisar el redondeo del monto documentado en `bar_detalle_ajuste`/`bar_detalle_salida_inv` para categorias con tolerancia 0.25 oz**
  - Resuelto (v10.39): se unifico la tolerancia operativa a **0.5 oz para todos los productos pesables**, eliminando la distincion por categoria (antes: 0.5 para VINOS/MEZCLADORES, 0.25 para el resto). La decision se tomo tras verificar en BD que todos los valores de `bar_inventario.cantidad_detalle` para productos pesables son multiplos de 0.5, por lo que `delta_det_exacto` siempre cae en multiplo de 0.5 y la cuantizacion a la grilla 0.5 nunca introduce distorsion ni residuo. Ver `documentos/redondeo_y_tolerancia.md` para el analisis completo.

- [x] **Igualar `bar_inventario` al fisico de forma incondicional en `/api/inventario/ajustes/aplicar`**
  - Resuelto (v10.77): la igualacion se separo del filtro de tolerancia — el loop itera `deltas_a_igualar` (todo producto con `fisico != ideal`, tolerados incluidos) mientras `deltas_con_diferencia` sigue generando solo los movimientos documentales. La validacion de cardinalidad se amplio al mismo conjunto en preview y aplicar (la advertencia original sobre `_validar_cardinalidad_bar_inventario` quedo cubierta). Las igualaciones sin movimiento se auditan en `app_paloteo_ajuste_control.payload_json` (`igualaciones_sin_movimiento`) y se informan en el mensaje de exito.
  - Limite documentado: si ningun producto genera movimientos, aplicar responde `skipped` sin escribir nada (no hay consolidacion; coherente con el preview y con la PWA, que no ofrece el boton). Detalle completo en `documentos/redondeo_y_tolerancia.md` seccion 5.
  - Cobertura: `tests/test_integracion_ajustes.py` (tolerado igualado, asimetria con `delta_paq`, todo-tolerado skipped, cardinalidad ampliada). Verificado ademas que `adminerp_copy` no tiene filas HAB duplicadas por barra/producto en `bar_inventario`.

- [x] **Validar end-to-end en test_pos la igualacion incondicional (v10.77) antes de produccion**
  - Validada el 2026-07-18 sobre la operativa 1254 (VIERNES) con el ciclo POS completo, via el deploy publico de seenode (erpapi.seenode.app -> BD test_pos): paloteo por API de 6 productos (inventario fisico 606, conversiones peso->onzas exactas, crudo con exactos y POS con redondeados), cierre desde el POS (snapshot `bar_paloteo_cierre` limpio y consistente), y consolidacion: preview 6/4/5, aplicar exitoso (ajuste 684 con estados 20/mov 84, salida 738 con 20/tipo 77, 5 movimientos exactos), `bar_inventario` igualado en los 6 productos, idempotencia 409 y `ya_aplicado` en preview.
  - El camino nuevo de v10.77 se ejercito con un escenario controlado: fisico de BEEFEATER (223) editado a 11.8 oz (ideal 11.5, delta +0.3 dentro de la banda) despues del cierre — quedo igualado a (0, 11.8) SIN generar movimiento, auditado en `payload_json.igualaciones_sin_movimiento` y avisado en el mensaje. 18 verificaciones automatizadas, cero fallas.
  - Prechequeo de datos en test_pos: sin duplicados HAB en `bar_inventario`; `app_paloteo_ajuste_control` y `app_login_auditoria_api` presentes (esta ultima creada el 2026-07-17; rate limit activo, verificado en vivo). **Al replicar a produccion**: repetir el chequeo de duplicados HAB y ejecutar el DDL de `app_login_auditoria_api` (sigue pendiente alli).

- [x] **Tests automatizados para el modulo AJUSTES (`/api/inventario/consolidar/preview` y `/api/inventario/ajustes/aplicar`)**
  - Resuelto (v10.76): `tests/test_integracion_ajustes.py` (15 tests) cubre todo lo pedido — deltas reales (sobrante/faltante en paq y det, banda de tolerancia y limite estricto 0.5), idempotencia (`409`), cardinalidad de `bar_inventario` (sin fila y duplicada, en preview y aplicar), gating de admin (`403`), operativa fuera de estado `23` (`400`) — mas la exclusion via `inventario_excluido` (la regresion exacta del join roto que motivo este pendiente).
  - Infraestructura en `tests/conftest.py`: transaccion externa + savepoints (los `commit()` de los endpoints no persisten; la BD queda intacta), guarda dura si `APP_ENV != test` o host no local, skip limpio si la BD no responde, fabrica de usuarios con JWT real y constructor de escenarios (`EscenarioAjustes`). `httpx` agregado a `requirements-dev.txt` para el `TestClient`.

- [x] **Ampliar la suite de integracion a login y paloteo**
  - Resuelto (v10.78): `tests/test_integracion_login.py` (login correcto con JWT usable y rastro en `seg_acceso`/auditoria, 401 generico, 403 deshabilitado, `is_admin`, rate limit 429 por usuario) y `tests/test_integracion_paloteo.py` (captura valida con perfil real, redondeo de la suma, omitidos/no pesables, 400 por estado/barra/peso bruto/sobrecapacidad, 409 duplicado). Los modulos de PESAJE (perfiles/config) siguen sin cobertura automatizada.

- [ ] **Modulo de reportes historicos de paloteos ya registrados (operativas cerradas)**
  - Motivacion: hoy el PDF de diferencias (REPORTE, `/api/paloteo3/exportar-pdf`) solo puede generarse durante la sesion viva del paloteo, porque las filas se arman en el navegador desde las tarjetas de PALOTEO 1/2. Una vez cerrada la operativa (o cerrado el navegador) ya no se puede regenerar el reporte.
  - Los datos necesarios ya se persisten; el reporte historico se arma cruzando dos fuentes por `(id_operacion, id_barra, id_producto)`:
    - `bar_paloteo_cierre` (escrita por el POS al cerrar cada operativa, una fila por producto del catalogo y por barra): `actual_paq`/`actual_detalle` = inventario ideal congelado al iniciar el cierre (PAQ POS/DET POS), `fisico_paq`/`fisico_detalle` = fisico registrado (PAQ BAR/DET BAR, ya redondeado a 0.5 oz), `diferencia_paq`/`diferencia_detalle` = fisico − actual sin banda de tolerancia (NULL si no hubo fisico). Verificado en `adminerp_copy` con operativa 1248 (producto 12, barra 1).
    - `app_paloteo_registro_crudo` (append-only): ultima fila por producto gana (misma regla que `_obtener_pesos_crudos_por_producto`). De ahi salen PESO (suma del JSON `pesos_abiertas`) y DIF REAL exacta (`onzas_calculadas − actual_detalle`).
  - Cuidados de implementacion:
    - Usar `onzas_calculadas` tal como quedo guardada; NUNCA reconvertir peso con el perfil vigente (los `gramos_por_oz` cambiaron con la actualizacion de precision ML→OZ y los perfiles son mutables).
    - Cruzar contra `bar_detalle_fisico` con `estado='HAB'` para excluir productos eliminados del paloteo despues de registrarse (el crudo conserva sus filas por ser log de auditoria).
    - Para reproducir el DIF OP mostrado esa noche, aplicar la banda de tolerancia operativa (0.5 oz pesables) sobre `diferencia_detalle`; decidir si el reporte historico muestra ademas la diferencia cruda.
    - Solo aplica a operativas cerradas: la operativa en curso no tiene filas en `bar_paloteo_cierre`.
  - Alcance sugerido: endpoint backend que arme las filas desde BD (a diferencia del actual, que las recibe del frontend) reutilizando el renderer PDF existente de `exportar_pdf_paloteo3`, mas un selector de operativas cerradas en la PWA.

- [ ] **Bloquear la busqueda-en-catalogo (agregar producto sin movimiento) en modo solo-lectura**
  - Motivacion: el flujo de "agregar producto sin movimiento" (v10.37) no verifica `operativaPermitePaloteo` antes de mostrar resultados del catalogo y permitir agregarlos. La card/fila resultante sí queda con sus inputs deshabilitados (igual que el resto en modo solo-lectura), asi que no hay impacto funcional ni de seguridad, pero la busqueda deja agregar una card "muerta" que no se puede llenar. Evaluar ocultar el resultado de catalogo (o el boton "+ Agregar") cuando `!operativaPermitePaloteo`.

- [ ] **`vista_inventario_barra_con_filtro` y `vista_inventario_barra` tienen `bi.id_barra = 1` hardcodeado**
  - Motivacion: ambas vistas (que alimentan `/api/inventario/pendientes` y `/api/inventario/catalogo/buscar`) tienen `WHERE ... AND bi.id_barra = 1` fijo en su definicion SQL, a pesar de que el nombre ("con_filtro") sugiere que deberian parametrizarse por barra. La relacion real producto↔barra vive en `bar_inventario` (id_producto + id_barra: 295 filas para barra 1, 44 para barra 2, 0 para barra 3) — `alm_producto.id_barra` es vestigial (solo 2/503 filas lo tienen seteado, sin relacion con el flujo real) y no debe usarse para esto.
  - Hoy no rompe nada porque la config activa (`PALOTEO_SELECTOR_ENABLED=false`, `PALOTEO_ALLOWED_BARRAS=1`) solo opera barra 1. Si en el futuro se habilita el selector para barra 2 o 3, el catalogo/pendientes seguiria devolviendo el stock de barra 1 sin importar la barra operativa resuelta (`X-Barra-Id`), de forma silenciosa (sin error, solo datos incorrectos).
  - Antes de habilitar `PALOTEO_SELECTOR_ENABLED` para mas de una barra: parametrizar ambas vistas (o reemplazar por una consulta directa a `bar_inventario` con `id_barra` como bind param) y verificar que no haya otros consumidores de estas vistas que dependan del hardcodeo actual.

## 🟢 Baja Prioridad / Mejoras Futuras

- [ ] **Separar los endpoints en routers por módulo (FastAPI `APIRouter`)**
  - `auth.py`, `inventario.py`, `operacion.py` — para mantener `main.py` limpio a medida que crece.

- [x] **Agregar logging estructurado**
  - `config.py` ya usa `logging.getLogger(__name__)` en lugar de `print()` (Fix #20). Pendiente evaluar si se extiende a `main.py`.

- [ ] **Agregar manejo de errores global**
  - Implementar un `exception_handler` en FastAPI para respuestas de error consistentes.

- [ ] **Revisar si `engine` se necesita en algún módulo futuro**
  - Actualmente fue removido de `main.py` por no usarse.

- [ ] **Evaluar si se reconstruye el hueco del CHANGELOG (10.52 a 10.70) a partir del `git log`**
  - Situacion: el CHANGELOG salta de `## 10.51` directo a `## 10.71`. Son **19 versiones sin entrada**, correspondientes a commits del 2026-07-09 al 2026-07-13, pese a que la regla de `.github/instructions/cache-busting-obligatorio.instructions.md` pide una entrada por cada bump. El hueco no es de contenido menor: incluye el endurecimiento de login (rate limit, auditoria de accesos, CORS/CSP), el cambio de rol `ROLE_ADMINISTRADOR` a `ROLE_ADMIN` en PESAJE, y varios cambios de los PDF de AJUSTES/paloteo.
  - **Decidir primero si conviene hacerlo**, no darlo por hecho. Existe precedente explicito de aceptar huecos: la cabecera del propio CHANGELOG ya declara que "las versiones anteriores a 10.13 no se reconstruyeron retroactivamente; ver `git log` para historial completo". Una opcion valida y mas barata es extender esa misma nota al rango 10.52-10.70 y cerrar el tema.
  - Argumento a favor de reconstruir: el CHANGELOG es hoy la unica vista legible de la evolucion del proyecto para quien no lee `git log`, y un hueco de 19 versiones justo en el tramo de seguridad del login es el peor lugar posible para tenerlo.
  - Argumento en contra: es documentacion retroactiva escrita por inferencia, no por quien hizo el cambio. `git log` sigue siendo la fuente de verdad y no se pierde nada; el esfuerzo puede rendir mas invertido en no volver a abrir el hueco.
  - Si se decide reconstruir — los 19 commits se listan con:
    `git log --format='%h|%ad|%s' --date=short -G"backstage-v10\.(5[2-9]|6[0-9]|70)" -- static/sw.js`
  - Ojo al reconstruir: **no alcanza con el mensaje del commit** para mapear commit a version. Varios mensajes no citan el numero (ej. `26c3522` dice solo "actualiza la version del service worker") y algunos commits bumpean mas de una version. Hay que leer el diff de `static/sw.js` de cada commit para leer el `CACHE_NAME` resultante. Ademas el mensaje describe la intencion, no siempre el alcance real del diff.
  - Lo mas valioso puede ser la prevencion, no el backfill: entender por que la regla se salteo 19 veces seguidas (¿trabajo en rafaga? ¿regla percibida como ruido en cambios chicos?) y, si corresponde, automatizar la verificacion en vez de confiar en la disciplina manual.

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
