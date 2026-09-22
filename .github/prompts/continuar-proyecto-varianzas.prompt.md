# Continuar proyecto: valoración y reportes de varianzas

Actúa como agente de desarrollo senior en el repositorio `c:\wamp\www\erpapi`. Responde siempre en español y usa PowerShell. No reviertas cambios del usuario ni trabajes directamente sobre tablas legacy del POS.

## Estado actual

La fase de valoración económica de varianzas de inventario está terminada y mergeada en `main`.

- Rama principal: `main`.
- Último merge funcional: `b4292a4 merge: valoracion historica de varianzas`.
- La rama de trabajo original fue `feature/valoracion-varianzas-inventario`.
- El DDL `querys/ddl_analytics_varianza_inventario.sql` ya fue aplicado en producción según confirmación del usuario.
- El entorno local canónico es `adminerp` para `APP_ENV=test`.
- `adminerp_garden` se conserva como entorno local de validación de Garden.
- No usar `adminerp_copy` como base canónica.
- La suite completa quedó validada con `103 passed`.
- El cache-busting vigente documentado es `12.30`.
- `.playwright-mcp/` es salida temporal y no debe incluirse en commits.

Antes de editar, comprobar siempre:

```powershell
git status --short
git branch --show-current
git log -3 --oneline --decorate
```

## Qué quedó implementado

### Persistencia analítica

Existe `analytics_varianza_inventario`, tabla propia de la PWA, sin modificar tablas legacy del POS. Se crea mediante:

```text
querys/ddl_analytics_varianza_inventario.sql
```

La tabla conserva una fila por producto y aplicación de ajuste con:

- operativa, barra, inventario físico y control de ajuste;
- producto y categoría;
- delta de paquetes, delta exacto y delta operativo;
- rendimiento y unidad de detalle;
- `id_almacen`, WAC congelado, fecha/origen del WAC;
- estado de valoración;
- valor de paquetes, valor de detalle y valor neto.

La inserción se realiza dentro de la misma transacción de `aplicar_ajustes_inventario()`.

### Fuente de cálculo

La fuente única de diferencias es:

```text
_calcular_diferencias_paloteo()
```

La fórmula es:

```text
valor_paq = delta_paq × wac_snapshot
valor_detalle = (delta_det_operativo / rendimiento_por_envase) × wac_snapshot
valor_neto = valor_paq + valor_detalle
```

El signo es `real - ideal`:

- negativo: faltante;
- positivo: sobrante.

Los productos sin WAC o con rendimiento inválido no se convierten silenciosamente en Bs 0. Se identifican mediante `SIN_WAC`, `WAC_INVALIDO` o `RENDIMIENTO_INVALIDO`.

La fuente actual de WAC es `cache_wac_producto` con `id_almacen = 1`. Esta decisión está documentada en:

```text
documentos/wac_multialmacen_varianzas.md
```

El WAC se maneja conceptualmente por `id_almacen + id_producto`. No mezclar costos entre almacenes.

### AJUSTES y PDF

Antes de aplicar:

- el preview consulta diferencias contra el inventario ideal;
- la tabla AJUSTES muestra diferencias y montos;
- el PDF usa la valoración calculada por backend;
- el diálogo de confirmación recuerda revisar/exportar el PDF antes de aplicar.

Después de aplicar:

- `bar_inventario` queda igualado al físico;
- el preview detecta `ya_aplicado`;
- la tabla recupera deltas y montos desde `analytics_varianza_inventario`, no desde el stock ya igualado;
- las filas muestran `AJUSTE REGISTRADO`;
- el PDF recupera snapshots históricos y no muestra ceros por la igualación;
- los iconos de columnas son:
  - `mobiledata_arrows` para PAQ;
  - `contrast_square` para DET;
  - `price_change` para MONTO.

### Reporte histórico económico

Está implementado:

```text
GET /api/ajustes/varianzas
```

Parámetros:

- `fecha_inicio`;
- `fecha_fin`;
- `agrupacion=dia|semana|mes`;
- filtros opcionales `id_barra`, `id_producto`, `id_categoria`.

La respuesta separa:

- faltantes;
- sobrantes;
- neto;
- productos sin valoración;
- periodos agregados.

La PWA tiene controles administrativos para consultar el histórico desde AJUSTES.

## Archivos principales

- `main.py`: cálculo de deltas, valoración, preview, aplicación, PDF y reporte histórico.
- `models.py`: modelo `VarianzaInventario`.
- `schemas.py`: contratos de preview y reporte histórico.
- `static/app.js`: tabla AJUSTES, snapshots aplicados, PDF e histórico.
- `static/index.html`: columnas, iconos y controles históricos.
- `querys/ddl_analytics_varianza_inventario.sql`: DDL analítico nuevo.
- `tests/test_calculos_varianza_inventario.py`: pruebas unitarias de fórmula.
- `tests/test_integracion_ajustes.py`: preview, aplicación, snapshots, PDF antes/después e histórico.
- `README.md` y `documentos/DOCUMENTACION_INGRESOS_SALIDAS_AJUSTE_PWA.md`: documentación funcional.
- `documentos/wac_multialmacen_varianzas.md`: política de WAC multialmacén.
- `TODO.md`: pendientes futuros.

## Pendientes reales para la siguiente fase

No reabrir la fase económica ya terminada. Los pendientes son independientes:

### 1. Reporte histórico completo de paloteos

El reporte económico de varianzas ya existe. Falta un reporte histórico completo de paloteos cerrados que pueda regenerar las cantidades y pesos originales aunque el navegador ya no esté abierto.

Fuentes documentadas:

- `bar_paloteo_cierre`: ideal, físico y diferencia por operativa/barra/producto.
- `app_paloteo_registro_crudo`: pesos y onzas exactas capturadas.
- `analytics_varianza_inventario`: valoración histórica si el ajuste fue aplicado.

Requisitos para esa fase:

- endpoint backend que arme filas desde BD, no desde payload del navegador;
- filtro por operativa/barra;
- reutilizar el renderer PDF existente;
- no reconvertir pesos con perfiles actuales: usar `onzas_calculadas` históricas;
- distinguir diferencia exacta y diferencia operativa;
- permitir regenerar el PDF de una operativa cerrada;
- agregar pruebas de operativa con y sin ajuste aplicado.

### 2. Bloquear búsqueda de catálogo en solo lectura

Cuando `operativaPermitePaloteo` sea falso, ocultar o deshabilitar el flujo de agregar productos desde catálogo para evitar tarjetas que no pueden editarse. Es una mejora UX de baja prioridad y no debe mezclarse con el reporte histórico.

## Reglas de implementación

- No alterar `bar_inventario`, `bar_ajuste`, `bar_detalle_ajuste`, `bar_salida_inventario`, `bar_detalle_salida_inv`, `bar_paloteo_cierre` ni otras tablas legacy para agregar analítica.
- Las tablas analíticas nuevas deben tener DDL versionado en `querys/`.
- Antes de aplicar DDL, confirmar explícitamente `SELECT DATABASE()` y el entorno.
- Para desarrollo canónico usar `adminerp` local.
- Validar Garden por separado con `adminerp_garden` cuando el cambio dependa de catálogo o esquema.
- No usar WAC vigente para reinterpretar históricos ya congelados.
- Mantener `Decimal` en cálculos monetarios y redondear únicamente al presentar.
- Actualizar `CHANGELOG.md`, documentación y cache-busting en cada modificación.
- Mantener el número de versión de `CACHE_NAME` y las queries `?v=` sincronizado.
- No hacer commit automático salvo que el usuario lo solicite.

## Flujo recomendado al iniciar una nueva sesión

1. Leer este prompt y `CLAUDE.md`.
2. Consultar `git status`, rama y último commit.
3. Leer el apartado correspondiente de `TODO.md`.
4. Formular una hipótesis local y un chequeo discriminante antes del primer cambio.
5. Inspeccionar solo los archivos directamente relacionados con el pendiente elegido.
6. Editar de forma incremental.
7. Ejecutar primero la prueba focalizada y luego la suite completa.
8. Actualizar documentación y cache-busting.
9. Informar archivos modificados, pruebas y cualquier limitación.

## Objetivo sugerido de continuación

Comenzar por el reporte histórico completo de paloteos cerrados. Antes de editar, revisar el contrato actual de `FilaDiferenciaPdf`, la función `exportar_pdf_paloteo3`, las columnas reales de `bar_paloteo_cierre` y la regla de última captura de `app_paloteo_registro_crudo`. Diseñar primero un endpoint de lectura y una prueba integrada; no modificar tablas legacy.
