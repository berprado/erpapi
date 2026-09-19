## Plan: Valoración Histórica de Varianzas

Implementar la valoración monetaria de las variaciones de inventario como un hecho histórico del ajuste aplicado, reutilizando el cálculo único de deltas, el control idempotente existente y el WAC vigente de la fuente semántica. No depender de los snapshots COGS actuales, ya que su proceso documentado usa un WAC histórico acumulado incompatible con el WAC móvil vigente.

**Hallazgos verificados**
- `_calcular_diferencias_paloteo()` en `main.py` es la fuente única de deltas; entrega paq, detalle exacto y detalle operativo.
- `aplicar_ajustes_inventario()` persiste cabeceras/detalles POS, iguala el stock y crea `app_paloteo_ajuste_control` con JSON e idempotencia por operativa/barra/inventario físico.
- `bar_paloteo_cierre`, escrito por POS, ya congela ideal, físico y diferencia por producto/operativa/barra; es la fuente indicada para posteriores PDFs históricos.
- `cache_wac_producto` conserva solo WAC vigente por `(id_almacen, id_producto)`; `v9_cache_wac_producto` es su interfaz semántica y no tiene historial.
- `analytics_cogs_historico` y `analytics_wac_operacion` pertenecen al motor financiero externo/documentado. El job existente de `analytics_cogs_historico` usa `vw_wac_producto_almacen` (promedio histórico), no `cache_wac_producto`; no reutilizarlo para esta funcionalidad sin su corrección integral.

**Decisión propuesta**
- Crear una tabla analítica nueva, normalizada y específica: `analytics_varianza_inventario` (nombre sujeto a convención POS), una fila por producto por aplicación de ajuste.
- Mantener `app_paloteo_ajuste_control.payload_json` como evidencia técnica de idempotencia y diagnóstico, pero no usar JSON como fuente para agregaciones semanales/mensuales: dificulta índices, filtros, auditoría y consultas MySQL 5.6.
- En la misma transacción de `aplicar_ajustes_inventario()`, leer y congelar WAC y capacidad de detalle; insertar las valoraciones junto al control. La clave única debe impedir reintentos: `(id_operacion, id_barra, id_inventario_fisico, id_producto)`.
- Si en el futuro queda disponible un snapshot oficial `analytics_wac_operacion` COMPLETADO para esa operativa/producto/almacén, priorizarlo; de lo contrario usar WAC vigente en el instante de aplicar y registrar el origen. Así el módulo no queda bloqueado y se preserva trazabilidad.

**Pasos**
1. Confirmar en BD de los entornos objetivo la estructura real y significado de `bar_paloteo_cierre`, `cache_wac_producto`, posibles `analytics_*`, y cuál `id_almacen` es el costo oficial de la barra. Revisar además si los procesos POS asignan `precio_costo_real` después de la aplicación. Esto bloquea las decisiones de DDL.
2. Diseñar y versionar el DDL de `analytics_varianza_inventario`: identificadores de operativa/barra/inventario físico/control/producto; fecha operativa y fecha de aplicación; `delta_paq`, `delta_det_exacto`, `delta_det_operativo`; rendimiento/unidad de detalle; WAC congelado, origen/fecha del WAC, estado de valoración y valores monetarios; índices por fecha/barra/producto/categoría y clave única idempotente.
3. Extraer un helper puro de valoración que reciba los deltas y el snapshot de costo/unidad, use `Decimal`, y calcule por separado valor de paq, valor de detalle operativo y neto. Mantener el signo `real - ideal`: negativo es faltante y positivo es sobrante. Casos sin WAC o rendimiento inválido quedan `SIN_WAC`/`RENDIMIENTO_INVALIDO`, sin tratarse silenciosamente como Bs 0.
4. Extender el query de `_calcular_diferencias_paloteo()` o un query acotado compartido para traer capacidad/rendimiento del producto y WAC. Reutilizar `v9_cache_wac_producto` para WAC cuando las reglas de negocio permitan el almacén fijado; no usar vistas de recetas POUR COST.
5. En `aplicar_ajustes_inventario()`, obtener snapshots antes de mutar `bar_inventario`, insertar registros analíticos para todos los productos de `deltas_a_igualar`, incluidos los tolerados cuando se produzca una consolidación; asociar los IDs de ajuste/salida/control disponibles. Dejar sin fila los casos globales `skipped`, pues no hubo aplicación.
6. Exponer en el preview el valor por línea y totales separados: faltantes, sobrantes, neto, cantidad sin WAC y cantidad con rendimiento inválido. El frontend debe renderizar estos valores devueltos por el backend, sin recalcular WAC ni importes.
7. Ajustar el PDF de sesión para que el backend arme o valide la valoración desde BD, no acepte WAC/montos del navegador. En paralelo, implementar el reporte histórico reutilizando `bar_paloteo_cierre`, `app_paloteo_registro_crudo` y la nueva tabla; evitar duplicar el renderer del PDF.
8. Añadir endpoint de reportes por rango de fecha con filtros de barra, producto/categoría y agrupación diaria/semanal/mensual. Devolver faltantes, sobrantes, neto y no valorizados como métricas separadas; la UI debe destacar ambos brutos para que el neto no los oculte.
9. Cubrir con pruebas unitarias las fórmulas y casos límite, y con integración la atomicidad/idempotencia de la aplicación, snapshots, productos sin WAC, diferencias mixtas paq/det y agregación por periodos. Actualizar documentación, cache busting y changelog según la regla del repositorio.

**Fórmula**
- `valor_paq = delta_paq × wac_snapshot`
- `valor_detalle = (delta_det_operativo / rendimiento_por_envase) × wac_snapshot`
- `valor_neto = valor_paq + valor_detalle`
- El valor exacto, si se requiere solo analítica de precisión de conteo, debe persistirse en un campo separado y nunca sustituir el valor operativo que explica los movimientos POS.

**Archivos relevantes**
- `main.py`: `_calcular_diferencias_paloteo`, `previsualizar_consolidacion_ajustes`, `aplicar_ajustes_inventario`, exportación PDF.
- `models.py` y `schemas.py`: control de ajuste y contratos de preview/reporte.
- `static/app.js`: panel AJUSTES y construcción actual del PDF.
- `tests/test_integracion_ajustes.py`: patrón de escenarios transaccionales existente.
- `querys/create_views_pourcost.sql`: referencia WAC semántica; no modificar para esta necesidad salvo que la verificación de BD confirme que requiere una vista reusable.
- `documentos/DOCUMENTACION_INGRESOS_SALIDAS_AJUSTE_PWA.md`, `documentos/redondeo_y_tolerancia.md`, `documentos/pour_cost/GUIA_DECISION_SNAPSHOT_WAC_CIERRE_OPERATIVA.md` y `TODO.md`: decisiones, límites y reporte histórico pendiente.

**Verificación**
1. Ejecutar DDL en base `test` y verificar claves, índices y FKs reales.
2. Ejecutar `python -m pytest tests/test_calculos_pesaje.py tests/test_integracion_ajustes.py` con `APP_ENV=test`.
3. Validar manualmente en `test_pos` que el WAC/almacén seleccionado coincide con el criterio financiero y que los totales del preview, PDF y registros persistidos son iguales.
4. Probar filtro semanal/mensual con una operativa de faltante, sobrante, diferencia mixta y producto sin WAC.

**Límites de alcance**
- Incluye valoración y reportes de variaciones del inventario de barra.
- Excluye corregir o activar `analytics_cogs_historico`, snapshots de ventas/comandas y auditoría histórica de recetas: son iniciativas del motor financiero más amplio y tienen inconsistencias documentadas que deben resolverse por separado.
- No escribir WAC en tablas POS de ajuste (`precio_costo`/`precio_costo_real`) sin validar su semántica y efectos en procesos legacy.
