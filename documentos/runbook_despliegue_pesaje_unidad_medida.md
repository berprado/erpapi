# Runbook: aplicar en `test_pos`/producción los cambios de PESAJE de esta tanda

**Origen:** sesión de trabajo 2026-09-08/10 (PRs #7, #8, #9). Cubre todo lo
que quedó pendiente de "aplicar en los demás entornos" a lo largo de esa
sesión — no repite la mecánica genérica de Seenode (build/start/env vars),
para eso ver `documentos/despliegue_seenode.md`.

**Cómo usar este documento:** es un checklist ejecutable. Cada bloque de SQL
está pensado para copiar/pegar tal cual contra la base de datos indicada.
Ninguno de los pasos de este runbook requiere tocar el dashboard de Seenode
salvo la sección 4 (deploy de código) — todo lo demás es una conexión MySQL
directa a cada base.

---

## 0. Alcance real: cuántas bases de datos hay que tocar

Este es el punto que más conviene confirmar antes de empezar, porque **no
es una sola base "production"**. Según `documentos/multisucursal_branding_deploy.md`
(memoria del proyecto) y `documentos/despliegue_seenode.md` (6.3.1/6.3.2),
casa matriz y la sucursal Beer Garden corren el mismo código pero cada una
tiene su **propia base de datos independiente** (catálogo, IDs y `alm_producto`
propios, no compartidos):

| Entorno | Base de datos | Estado tras esta sesión |
|---|---|---|
| `test` (WAMP local) | `adminerp_garden` — copia local, funciona como entorno de desarrollo de la sucursal Beer Garden | ✅ Ya tiene todo aplicado y verificado (backfills + triggers 2026-09-09) |
| `test_pos` | Túnel `servidor.localto.net:5277`, BD `adminerp` — entorno de validación E2E con POS real conectado | ⬜ Pendiente — **confirmar si sigue siendo el mismo catálogo que casa matriz o si ya está desactualizado como referencia** |
| `production` — casa matriz | Túnel `backapp.localto.net:1790`, BD `adminerp` | ⬜ Pendiente |
| `production` — Beer Garden | Túnel `gardentcp.localto.net:7755`, BD propia | ⬜ Pendiente |

**Antes de arrancar, confirmar con quien tenga acceso:**
1. ¿`test_pos` sigue vivo y es representativo de casa matriz, o quedó desactualizado desde que Beer Garden se desplegó por separado (2026-09-02)?
2. ¿Hay alguna otra sucursal desplegada además de estas dos a la fecha en que se ejecute este runbook? (revisar la tabla 6.3.2 de `despliegue_seenode.md`, que se supone se mantiene al día).

Si la respuesta agrega o quita bases de la lista de arriba, la sección 3 de
este runbook se repite igual, una vez por cada base real.

---

## 1. Qué se está aplicando (resumen de la sesión)

| # | Qué | Dónde vive | Ya aplicado en |
|---|---|---|---|
| 1 | Backfill: fila `pesable=0` para todo `alm_producto` HAB con `p_unidad_medida NOT IN (11,61)` sin fila previa | `querys/backfill_productos_no_pesables_pesaje_config_api.sql` | `test` |
| 2 | Backfill: único producto con `p_unidad_medida=61` como `pesable=1` | `querys/backfill_producto_barril_pesable_pesaje_config_api.sql` | `test` |
| 3 | Fix de código: `GET /api/pesaje/config`/`categorias` ya no excluyen categorías del listado | PR #7 (mergeado a `main`) | Todo lo que corra el código de `main` |
| 4 | Fix de código: `POST /api/inventario/paloteo` no ignora perfiles pesables cuando el producto tiene más de una fila de config | PR #8 (mergeado a `main`) | Todo lo que corra el código de `main` |
| 5 | Cambio de criterio: `pesable` se deriva de `p_unidad_medida IN (11,61)` en vez de categoría — triggers, `_producto_deberia_ser_pesable()`, bloque INCOMPLETOS, frontend | PR #9 (⬜ pendiente de mergear) + `querys/fix_trigger_alm_producto_after_insert.sql`/`after_update.sql` | `test` (BD) — el código llega solo con el merge de #9 |

**Importante — separar "deploy de código" de "aplicar SQL a mano":** los
puntos 3, 4 y 5 (parte de código) llegan automáticamente a casa matriz y
Beer Garden en cuanto se mergea el PR correspondiente a `main` (Seenode
redeploya solo, ver sección 4). Los puntos 1, 2 y la parte de BD del punto 5
**no** — son scripts en `querys/` que hay que correr a mano contra cada base,
nadie los ejecuta automáticamente.

---

## 2. Orden recomendado

1. Terminar de revisar y mergear PR #9 (código).
2. Aplicar la sección 3 de este runbook contra `test_pos`.
3. Smoke test funcional contra `test_pos` (sección 5) antes de tocar producción.
4. Aplicar la sección 3 contra `production` — casa matriz.
5. Aplicar la sección 3 contra `production` — Beer Garden.
6. Smoke test funcional contra ambas instancias de Seenode (sección 5).

No hay una razón técnica fuerte para bloquear el deploy de código (paso 1)
hasta terminar 2-5: los fixes de PR #7/#8 ya están en `main` desde antes de
esta sesión y son seguros standalone (ver sus PRs). El único riesgo real de
desordenar esto es que un entorno reciba el código de PR #9 antes que su
propio backfill/trigger — no rompe nada (el criterio nuevo simplemente no
tiene efecto hasta que el trigger de ese entorno se actualice), pero el
listado de PESAJE de ese entorno seguirá mostrando el estado viejo hasta que
se complete la sección 3.

---

## 3. Procedimiento por base de datos (repetir para `test_pos`, `production` casa matriz, `production` Beer Garden)

### 3.1 Pre-chequeo: entender qué se va a tocar

Antes de correr nada, tener una foto del estado actual:

```sql
-- Cuantos productos HAB hay por p_unidad_medida (sirve para estimar el
-- tamano del backfill antes de correrlo)
SELECT p_unidad_medida, COUNT(*) FROM alm_producto WHERE estado='HAB' GROUP BY p_unidad_medida;

-- Cuantos ya tienen fila de pesaje, por pesable
SELECT pesable, COUNT(*) FROM app_producto_pesaje_config_api WHERE estado='HAB' GROUP BY pesable;

-- Trigger actual: que criterio esta corriendo hoy en esta base
SHOW CREATE TRIGGER trg_alm_producto_after_insert\G
```

En la salida del último `SHOW CREATE TRIGGER`, mirar la condición de
`v_pesable`: si dice `ind_permite_comandar = 71 AND ... NOT IN (10,11,...)`
es la versión vieja (2026-07-30); si dice `p_unidad_medida IN (11, 61)` ya
es la nueva y **se puede saltar el paso 3.4** de esta base (ya está).

### 3.2 Backfill: productos no pesables preexistentes

```powershell
mysql -h <HOST> -P <PUERTO> -u <USUARIO> -p <BASE> < querys\backfill_productos_no_pesables_pesaje_config_api.sql
```

Es idempotente (`NOT EXISTS` en el `INSERT`) — correrlo dos veces no duplica
nada. Verificar después:

```sql
SELECT pesable, COUNT(*) FROM app_producto_pesaje_config_api WHERE estado='HAB' GROUP BY pesable;
```

El número de `pesable=0` debería subir; `pesable=1` no debería cambiar en
este paso.

### 3.3 Backfill: excepción pesable dentro de una categoría no-pesable

**Antes de correr este script, verificar cuántos productos con
`p_unidad_medida=61` existen en esta base** — el script fue escrito para
el caso real de Beer Garden (un único producto, BARRIL PACEÑA 50L), pero es
genérico en SQL (no hardcodea el `id` del producto, filtra por
`p_unidad_medida = 61`):

```sql
SELECT id, nombre, estado FROM alm_producto WHERE p_unidad_medida = 61;
```

- Si aparece 1+ producto HAB sin fila de pesaje: correr el script normal.
- Si no aparece ninguno: el script no va a insertar nada (0 filas afectadas)
  — no es un error, simplemente esta base no tiene ningún producto con esa
  unidad de medida todavía. No forzar nada a mano solo para "que aparezca
  algo".

```powershell
mysql -h <HOST> -P <PUERTO> -u <USUARIO> -p <BASE> < querys\backfill_producto_barril_pesable_pesaje_config_api.sql
```

### 3.4 Re-aplicar los triggers con el criterio nuevo

Solo si el pre-chequeo (3.1) mostró que esta base todavía tiene la versión
2026-07-30:

```powershell
mysql -h <HOST> -P <PUERTO> -u <USUARIO> -p <BASE> < querys\fix_trigger_alm_producto_after_insert.sql
mysql -h <HOST> -P <PUERTO> -u <USUARIO> -p <BASE> < querys\fix_trigger_alm_producto_after_update.sql
```

Verificar con `SHOW CREATE TRIGGER trg_alm_producto_after_insert\G` que la
condición de `v_pesable` ahora dice `p_unidad_medida IN (11, 61)`.

**Sanity check recomendado (opcional pero barato)** — insertar un producto
de prueba y confirmar que el trigger deriva `pesable` correctamente, después
borrarlo (mismo patrón usado para verificar esto en `test`):

```sql
INSERT INTO alm_producto (nombre, correlativo, id_categoria, medida, p_unidad_medida, cantidad_detalle, ind_permite_comandar, codigo, usuario_reg, estado)
VALUES ('SANITY CHECK PESABLE', 0, 1, 750, 11, 25.5, 71, 'SANITY-PESABLE', 'sanity', 'HAB');

SELECT p.id, p.nombre, pc.pesable
FROM alm_producto p
JOIN app_producto_pesaje_config_api pc ON pc.id_producto_almacen = p.id
WHERE p.codigo = 'SANITY-PESABLE';
-- pesable debe ser 1

-- Limpieza: usar el id devuelto arriba en vez de <ID>
DELETE FROM app_producto_pesaje_config_api WHERE id_producto_almacen = <ID>;
DELETE FROM app_producto_pesaje_config WHERE id_producto_almacen = <ID>;
DELETE FROM alm_producto WHERE codigo = 'SANITY-PESABLE';
```

### 3.5 Verificación de auditoría

Usar las 3 consultas de `README.md` sección "Consultas SQL de auditoría
(PESAJE)" (ya actualizadas al criterio `p_unidad_medida IN (11,61)`) para
confirmar que el universo objetivo, los productos en INCOMPLETOS y los
conflictos excepcionales tienen sentido para el catálogo real de esta base.

### 3.6 Paso de negocio: productos tipo HUARI/AMSTEL 620ML

Ver `TODO.md` ("conflictos excepcionales de pesable") y CHANGELOG v12.9/12.10
para el contexto completo. Decisión ya tomada: estos productos **sí son
pesables de verdad** y se aceptan sin excepción de código — pero cada
sucursal tiene su propio catálogo con IDs (y posiblemente nombres) propios,
así que hay que ubicarlos de nuevo en cada base, no asumir el mismo `id`
que en `test`:

```sql
-- Buscar equivalentes en esta base (ajustar el LIKE si los nombres varian)
SELECT id, nombre, p_unidad_medida, estado
FROM alm_producto
WHERE (nombre LIKE '%AMSTEL%' OR nombre LIKE '%HUARI%' OR nombre LIKE '%LIMONADA%')
  AND p_unidad_medida IN (11, 61);
```

Para cada producto que aparezca: **antes de que caiga en una operativa
real**, completar su perfil de pesaje real (`peso_bruto`/`tara` reales,
vía el módulo PESAJE de la app, tab INCOMPLETOS) para que el primer
paloteo que lo toque no le pegue con el `400` de "perfil incompleto"
en medio de una jornada.

---

## 4. Deploy de código

1. Mergear PR #9 a `main` (si no se hizo ya).
2. Un push a `main` dispara el auto-deploy de Seenode en **ambos** Web
   Services (casa matriz y Beer Garden) — no hace falta ningún paso manual
   en el dashboard salvo que algo falle (ver `despliegue_seenode.md` sección
   9, troubleshooting).
3. Revisar build/runtime logs de cada instancia en el dashboard de Seenode
   (`despliegue_seenode.md` sección 10, pasos 5-6).
4. `test_pos` no tiene (a la fecha de este runbook) un Web Service de
   Seenode propio confirmado — si se valida corriendo la app localmente
   contra ese túnel (`APP_ENV=test_pos` en `.env`), no hace falta ningún
   paso de deploy: el código ya está en `main`, solo hay que tener esa rama
   checked out localmente.

---

## 5. Verificación funcional post-deploy (por instancia)

Smoke test mínimo en la PWA del módulo PESAJE, para cada instancia (casa
matriz, Beer Garden, y `test_pos` si aplica):

1. Login como admin.
2. Entrar a PESAJE → tab **"No pesables"**: confirmar que aparecen productos
   de categorías antes ocultas (ej. bebidas/cigarrillos/comida, lo que
   corresponda al catálogo real de esa base) — antes de PR #7 esta tab
   podía estar vacía o incompleta para esas categorías.
3. Tab **"Pesables"**: si esa base tiene algún producto con
   `p_unidad_medida=61` (ver 3.3), confirmar que aparece ahí.
4. Selector de categoría: confirmar que ofrece categorías que antes no
   aparecían (ej. CERVEZAS).
5. Abrir un perfil `pesable=0` de un producto con unidad pesable (si existe
   alguno de los identificados en 3.6) y confirmar que el modal muestra los
   campos de peso habilitados (columna `catalogo_permite_pesar=true`) en vez
   de solo `barcode`.

Si algo de esto no se ve como se espera, revisar primero si el trigger de
esa base realmente quedó en la versión nueva (3.1) antes de sospechar del
código.

---

## 6. Rollback / contingencia

- **Triggers**: la definición anterior (2026-07-30) está en el historial de
  git de `querys/fix_trigger_alm_producto_after_insert.sql`/`after_update.sql`
  (`git log -p -- querys/fix_trigger_alm_producto_after_insert.sql`). Para
  revertir, recuperar esa versión del archivo y volver a correr el
  `DROP TRIGGER IF EXISTS` + `CREATE TRIGGER` que contiene.
- **Backfills**: son aditivos (solo `INSERT`, nunca tocan filas existentes).
  No hay "deshacer" automático — si hiciera falta revertir, es un `UPDATE
  app_producto_pesaje_config_api SET estado='DES' WHERE usuario_reg='...'`
  apuntado a las filas insertadas por el backfill (identificables por rango
  de `id` o por `usuario_reg`, según lo que se haya usado al correrlo en esa
  base).
- **Código**: revertir el merge de PR #9 en GitHub y dejar que Seenode
  redeploye el commit anterior.

---

## 7. Checklist final (una fila por base de datos)

- [ ] `test_pos`: 3.1 → 3.2 → 3.3 → 3.4 → 3.5 → 3.6 → smoke test (5)
- [ ] `production` casa matriz: 3.1 → 3.2 → 3.3 → 3.4 → 3.5 → 3.6 → smoke test (5)
- [ ] `production` Beer Garden: 3.1 → 3.2 → 3.3 → 3.4 → 3.5 → 3.6 → smoke test (5)
- [ ] PR #9 mergeado y deploy de código confirmado en ambas instancias de Seenode
- [ ] Tabla "Instancias desplegadas actualmente" de `despliegue_seenode.md` (6.3.2) sigue reflejando la realidad — actualizarla si algo cambió
