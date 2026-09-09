-- Backfill (2026-09-08): unico producto con p_unidad_medida = 61 (BARRIL
-- PACEÑA 50L, id 155) sin fila en app_producto_pesaje_config_api.
--
-- Complemento de backfill_productos_no_pesables_pesaje_config_api.sql: aquella
-- corrida cubrio todo HAB con p_unidad_medida NOT IN (11, 61) como pesable=0.
-- La unidad 61 quedo fuera de ese filtro a proposito porque, a diferencia de
-- las demas unidades no-11, SI corresponde a un producto pesable (un barril
-- se pesa/palotea igual que una botella) -- solo que aun no tenia perfil
-- cargado. Se agrega aqui con pesable=1 y el resto de los valores por defecto
-- de la tabla (sin peso_bruto/tara/gramos_por_oz: cae en INCOMPLETOS, editable
-- desde el modulo PESAJE).
--
-- NOT EXISTS lo hace idempotente igual que el script hermano.
-- Ejecutar UNA VEZ por entorno (test / test_pos / production).
--
-- nombre_perfil se omite adrede para que tome el DEFAULT 'Estándar' de la
-- columna en vez de un literal en este script -- ver la nota de encoding en
-- backfill_productos_no_pesables_pesaje_config_api.sql.

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
    1,
    NULL,
    1.50,
    'HAB',
    'BERNARDO',
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
FROM alm_producto ap
WHERE ap.estado = 'HAB'
  AND ap.p_unidad_medida = 61
  AND NOT EXISTS (
      SELECT 1
      FROM app_producto_pesaje_config_api pc
      WHERE pc.id_producto_almacen = ap.id
  );
