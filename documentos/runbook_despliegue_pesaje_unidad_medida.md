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
| `test_pos` | Túnel `servidor.localto.net:5277`, BD `adminerp` — entorno de validación E2E con POS real conectado, réplica exacta de producción Beer Garden | ✅ Aplicado y verificado 2026-09-10 (backfills + fix de esquema legacy + triggers, con sanity check real de INSERT/UPDATE) |
| `production` — casa matriz | Túnel `backapp.localto.net:1790`, BD `adminerp` | ⬜ BD aplicada y verificada 2026-09-10 (backfills + triggers, con sanity check real de INSERT/UPDATE; el paso 3.4 no aplicó — esquema legacy ya correcto, 296 filas con actividad real) — **falta el smoke test (5) en la PWA real**, no dar por cerrada esta fila hasta registrarlo. Auditoría: 63 productos sin config (INCOMPLETOS), 5 conflictos excepcionales incluyendo `HUARI 620ML`/`AMSTEL 620ML` — sin editar por SQL directo, pendiente completar vía PESAJE |
| `production` — Beer Garden | Túnel `gardentcp.localto.net:7755`, BD propia | ⬜ Pendiente — misma línea que `test_pos`, se espera el mismo esquema legacy desfasado (ver 3.4) |

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
| 5 | Cambio de criterio: `pesable` se deriva de `p_unidad_medida IN (11,61)` en vez de categoría — triggers, `_producto_deberia_ser_pesable()`, bloque INCOMPLETOS, frontend | PR #9 (mergeado a `main` 2026-09-10) + `querys/fix_trigger_alm_producto_after_insert.sql`/`after_update.sql` | `test` y `test_pos` (BD) |
| 6 | **Fix crítico (2026-09-10, no relacionado al criterio de pesable):** esquema desfasado de `app_producto_pesaje_config` (legacy, sistema propio de casa matriz) en la línea Beer Garden rompía **todo** INSERT/UPDATE de `alm_producto` al disparar el trigger (`ERROR 1054: Unknown column 'id_producto_almacen'`) — bug dormido desde 2026-07-30, encontrado recién al hacer un sanity check real en `test_pos` | `querys/fix_esquema_legacy_app_producto_pesaje_config.sql` | `test_pos` |

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

-- Trigger actual: que criterio esta corriendo hoy en esta base.
-- LOS DOS, no solo uno -- after_insert y after_update se instalan con
-- comandos separados en 3.5 (dos archivos .sql distintos): si uno de los
-- dos falla a mitad de camino (ej. un timeout de conexion entre el primer
-- mysql < ...sql y el segundo), quedan en versiones distintas. Mirar solo
-- after_insert y asumir que after_update esta igual puede hacer que se
-- salte 3.5 dejando after_update con el criterio viejo sin que nadie lo note.
SHOW CREATE TRIGGER trg_alm_producto_after_insert\G
SHOW CREATE TRIGGER trg_alm_producto_after_update\G

-- OBLIGATORIO -- esquema de la tabla legacy que el trigger tambien escribe
-- (ver 3.4 antes de re-aplicar el trigger, sin importar el resultado de
-- los SHOW CREATE TRIGGER de arriba)
SHOW CREATE TABLE app_producto_pesaje_config\G
SELECT COUNT(*) FROM app_producto_pesaje_config;
```

En la salida de CADA `SHOW CREATE TRIGGER`, mirar la condición de
`v_pesable`: si dice `ind_permite_comandar = 71 AND ... NOT IN (10,11,...)`
es la versión vieja (2026-07-30); si dice `p_unidad_medida IN (11, 61)` ya
es la nueva. **Solo saltar el paso 3.5 si LOS DOS triggers ya muestran la
versión nueva** — si uno quedó viejo y el otro nuevo, correr 3.5 igual (el
`DROP TRIGGER IF EXISTS` + `CREATE TRIGGER` de cada script es idempotente,
no hay problema en reaplicar el que ya estaba bien).

En la salida del `SHOW CREATE TABLE app_producto_pesaje_config`, confirmar
si tiene columnas `id_producto_almacen`/`gramos_por_oz`/`pesable` (esquema
"nuevo", el que asume el trigger) o `id_producto` sin esas columnas (esquema
"viejo", el de la línea Beer Garden antes de este fix) — ver 3.4.

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

### 3.4 ⚠️ Corregir esquema legacy — obligatorio en la línea Beer Garden antes de re-aplicar el trigger

**Hallazgo crítico (2026-09-10):** `trg_alm_producto_after_insert`/`after_update`
siempre asumieron el esquema "nuevo" de `app_producto_pesaje_config` (tabla
legacy de un sistema propio de casa matriz, independiente de este repo —
`id_producto_almacen`, `gramos_por_oz`, `pesable`). En la línea Beer Garden
(`test_pos`, y se espera lo mismo en su producción) esa tabla nunca se
migró a ese esquema porque el sistema que la usa no está implementado ahí
— quedó con un esquema viejo (`id_producto`, sin esas columnas) y sin
ninguna fila. Mientras la tabla tenga ese esquema viejo, **el trigger falla
con `ERROR 1054: Unknown column 'id_producto_almacen' in 'field list'` en
CUALQUIER INSERT o UPDATE sobre `alm_producto`** — no solo altas de
producto, cualquier edición del catálogo (precio, categoría,
habilitar/deshabilitar) rompe. Confirmado con un sanity check real en
`test_pos` el 2026-09-10; el error no aparece con `SHOW CREATE TRIGGER`
(el trigger se instala bien), solo se ve al ejecutar un `INSERT`/`UPDATE`
real.

**Si el pre-chequeo (3.1) mostró el esquema viejo** (`id_producto`, sin
`gramos_por_oz`/`pesable`) **y la tabla tiene 0 filas** (confirmar con el
`SELECT COUNT(*)` del pre-chequeo):

```powershell
mysql -h <HOST> -P <PUERTO> -u <USUARIO> -p <BASE> < querys\fix_esquema_legacy_app_producto_pesaje_config.sql
```

El script termina con un `SHOW CREATE TABLE` — comparar contra el esquema
de casa matriz (arriba, en el hallazgo) para confirmar que coincide.

**Si la tabla ya tiene filas** (no se espera en la línea Beer Garden, pero
si aparece): DETENERSE, no correr el script — fue escrito para migrar una
tabla vacía, no para preservar datos existentes. Revisar a mano antes de
seguir.

**Si el pre-chequeo mostró el esquema nuevo** (como en casa matriz): saltar
este paso, no aplica.

### 3.5 Re-aplicar los triggers con el criterio nuevo

Solo si el pre-chequeo (3.1) mostró que **alguno de los dos** triggers de
esta base todavía tiene la versión 2026-07-30 (correr ambos comandos
siempre que uno lo necesite — son idempotentes, no pasa nada si el otro ya
estaba en la versión nueva):

```powershell
mysql -h <HOST> -P <PUERTO> -u <USUARIO> -p <BASE> < querys\fix_trigger_alm_producto_after_insert.sql
mysql -h <HOST> -P <PUERTO> -u <USUARIO> -p <BASE> < querys\fix_trigger_alm_producto_after_update.sql
```

Verificar **los dos**, no solo uno — cada `mysql < archivo.sql` es un
proceso separado y puede fallar independientemente (conexión cortada,
permisos, etc.) sin que el otro se entere:

```sql
SHOW CREATE TRIGGER trg_alm_producto_after_insert\G
SHOW CREATE TRIGGER trg_alm_producto_after_update\G
```

Confirmar que la condición de `v_pesable` dice `p_unidad_medida IN (11, 61)`
en ambas salidas antes de seguir al sanity check.

**Sanity check OBLIGATORIO, no opcional** (esto fue justo lo que encontró el
bug de 3.4 — `SHOW CREATE TRIGGER` solo confirma que el trigger se instaló,
no que funcione de punta a punta): insertar un producto de prueba real,
confirmar que ambas tablas quedan bien, probar también el `UPDATE`, y
limpiar todo. Validado tal cual en `test_pos` el 2026-09-10:

```sql
-- 1) INSERT -- si esto tira ERROR 1054, volver a 3.4, algo quedo mal
INSERT INTO alm_producto (nombre, correlativo, id_categoria, medida, p_unidad_medida, cantidad_detalle, ind_permite_comandar, codigo, usuario_reg, estado)
VALUES ('SANITY CHECK PESABLE', 0, 1, 750, 11, 25.5, 71, 'SANITY-PESABLE', 'sanity', 'HAB');

-- 2) Verificar las DOS tablas que toca el trigger
SELECT id_producto_almacen, pesable FROM app_producto_pesaje_config
WHERE id_producto_almacen = (SELECT id FROM alm_producto WHERE codigo='SANITY-PESABLE');
SELECT id_producto_almacen, nombre_perfil, pesable FROM app_producto_pesaje_config_api
WHERE id_producto_almacen = (SELECT id FROM alm_producto WHERE codigo='SANITY-PESABLE');
-- pesable debe ser 1 en ambas

-- 3) Probar tambien el trigger de UPDATE (no solo el de INSERT)
UPDATE alm_producto SET medida = 750 WHERE codigo='SANITY-PESABLE';
-- no deberia tirar error

-- 4) Limpieza (no hace falta copiar el id a mano)
DELETE FROM app_producto_pesaje_config_api WHERE id_producto_almacen = (SELECT id FROM alm_producto WHERE codigo='SANITY-PESABLE');
DELETE FROM app_producto_pesaje_config WHERE id_producto_almacen = (SELECT id FROM alm_producto WHERE codigo='SANITY-PESABLE');
DELETE FROM alm_producto WHERE codigo = 'SANITY-PESABLE';
```

### 3.6 Verificación de auditoría

Usar las 3 consultas de `README.md` sección "Consultas SQL de auditoría
(PESAJE)" (ya actualizadas al criterio `p_unidad_medida IN (11,61)`) para
confirmar que el universo objetivo, los productos en INCOMPLETOS y los
conflictos excepcionales tienen sentido para el catálogo real de esta base.

### 3.7 Paso de negocio: productos tipo HUARI/AMSTEL 620ML

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
- **Fix de esquema legacy (3.4)**: solo aplica en la línea Beer Garden y
  solo se corre sobre una tabla vacía — no hay datos que revertir. Si hiciera
  falta deshacer el cambio de esquema en sí (no debería, es estrictamente
  más completo que el anterior), la definición vieja de la tabla está en el
  historial de git de este runbook (versión previa a este commit) y en
  `SHOW CREATE TABLE` de `test_pos` antes del 2026-09-10.
- **Código**: revertir el merge de PR #9 en GitHub y dejar que Seenode
  redeploye el commit anterior.

---

## 7. Checklist final (una fila por base de datos)

- [x] `test_pos`: 3.1 → 3.2 → 3.3 → 3.4 → 3.5 → 3.6 → 3.7 → smoke test (5) — completado 2026-09-10
- [ ] `production` casa matriz: 3.1 → 3.2 → 3.3 → **3.4 no aplicó** (esquema ya era el nuevo) → 3.5 → 3.6 → 3.7 completados 2026-09-10 → **smoke test (5) pendiente** (requiere login real en la PWA de Seenode, no ejecutable por este medio) — no marcar esta fila como terminada hasta registrarlo
- [ ] `production` Beer Garden: 3.1 → 3.2 → 3.3 → 3.4 → 3.5 → 3.6 → 3.7 → smoke test (5)
- [x] PR #9 mergeado (2026-09-10) — deploy de código a confirmar en ambas instancias de Seenode
- [ ] Tabla "Instancias desplegadas actualmente" de `despliegue_seenode.md` (6.3.2) sigue reflejando la realidad — actualizarla si algo cambió

---

## 8. Objetos verificados sin acción necesaria

- **Procedimiento `obtener_inventario_barra`** (MySQL, externo a este repo,
  igual en las 3 bases verificadas — casa matriz creado 2025-06-28, `test`/
  `test_pos` son copias más recientes de la misma definición): recibe
  `p_id_barra` y sí filtra correctamente por barra (`WHERE bi.id_barra =
  p_id_barra`), a diferencia de `vista_inventario_barra_con_filtro` que
  necesita el filtro agregado a mano en la consulta que la usa (ver
  CHANGELOG 12.5). Nombra `bi.id AS id_barra` (en realidad el id de la fila
  de `bar_inventario`, no el número de barra) y `bi.id_barra AS nro_barra`
  (el número de barra real) — nombres invertidos respecto a como los llama
  hoy la vista de este repo, pero es una convención propia de este
  procedimiento, consistente en las 3 bases, no algo que haya quedado
  desincronizado. **No lo usa esta API** (sin referencias en el código) —
  no requiere ninguna acción para este despliegue.
