-- Backfill (2026-09-08): productos NO pesables preexistentes sin fila en
-- app_producto_pesaje_config_api.
--
-- Contexto: los triggers trg_alm_producto_after_insert / trg_alm_producto_after_update
-- (ver fix_trigger_alm_producto_after_insert.sql / fix_trigger_alm_producto_after_update.sql)
-- solo mantienen sincronizada la tabla hacia adelante (altas/bajas/cambios en
-- alm_producto a partir de su instalacion, 2026-07-30). Los productos que ya
-- existian en alm_producto antes de esta app -- y que nunca fueron pesables --
-- jamas dispararon un INSERT en app_producto_pesaje_config_api, asi que hoy
-- esa tabla solo contiene perfiles de productos pesables (verificado en test:
-- 120/120 filas con pesable=1, cero filas con pesable=0).
--
-- Este script agrega la fila base "Estandar" (pesable=0, sin pesos) para todo
-- producto HAB de alm_producto cuya unidad de medida (p_unidad_medida) no sea
-- 11 ni 61 -- las dos unidades usadas exclusivamente por productos pesables --
-- y que aun no tenga ninguna fila en app_producto_pesaje_config_api.
--
-- NOT EXISTS evita pisar productos que ya tienen perfil (evita violar
-- uk_producto_perfil (id_producto_almacen, nombre_perfil) y evita tocar datos
-- de pesaje ya cargados). Verificado en test: 57 candidatos, 0 con fila previa
-- -> las 57 se insertan limpio.
--
-- Ejecutar UNA VEZ por entorno (test / test_pos / production). Idempotente:
-- una segunda corrida no inserta nada nuevo porque el NOT EXISTS ya encuentra
-- la fila recien creada.
--
-- nombre_perfil se omite adrede (igual que en los triggers de
-- fix_trigger_alm_producto_after_insert/update.sql) para que tome el DEFAULT
-- 'Estándar' de la columna en vez de un literal en este script: un literal
-- con tilde llego corrupto a la fila (mojibake) la primera vez que se corrio
-- este script con el charset de cliente del mysql.exe local en cp850 en vez
-- de utf8mb4. El DEFAULT de columna no pasa por el charset de la conexion.

INSERT INTO app_producto_pesaje_config_api (
    id_producto_almacen,
    peso_bruto,
    tara,
    gramos_por_oz,
    pesable,
    barcode,
    tolerancia_oz,
    estado,
    usuario_reg,
    fecha_reg,
    fecha_mod
)
SELECT
    ap.id,
    NULL,
    NULL,
    NULL,
    0,
    NULL,
    1.50,
    'HAB',
    'BERNARDO',
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
FROM alm_producto ap
WHERE ap.estado = 'HAB'
  AND ap.p_unidad_medida NOT IN (11, 61)
  AND NOT EXISTS (
      SELECT 1
      FROM app_producto_pesaje_config_api pc
      WHERE pc.id_producto_almacen = ap.id
  );
