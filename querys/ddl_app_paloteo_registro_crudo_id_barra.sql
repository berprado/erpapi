-- app_paloteo_registro_crudo: agregar id_barra (paloteo multi-barra, ver TODO.md
-- "Agregar id_barra a app_paloteo_registro_crudo" y CHANGELOG 12.45).
--
-- Por que: la tabla no guardaba la barra. Con dos barras en la misma operativa
-- (Beer Garden), la precarga de correccion y las columnas PESO / DIF REAL del
-- PDF de Ajustes y del Historico elegian la captura cruda "que explica el
-- conteo", y un producto con el MISMO conteo en ambas barras podia tomar el
-- pesaje de la otra. Con id_barra cada barra lee solo sus capturas.
--
-- Nullable a proposito: las filas historicas quedan en NULL (no hay forma
-- confiable de reconstruir su barra) y el codigo las sigue leyendo con la regla
-- anterior como respaldo.
--
-- ORDEN DE DESPLIEGUE: aplicar este DDL en TODAS las bases (test -> test_pos ->
-- produccion casa matriz y Beer Garden) ANTES de desplegar el codigo v12.45:
-- el codigo nuevo escribe y filtra por esta columna y fallaria sin ella.
-- El codigo anterior ignora la columna, asi que aplicar el DDL antes es seguro.
-- Hacerlo en una ventana sin cierres en ninguna sucursal.
--
-- MySQL 5.6 no tiene ADD COLUMN IF NOT EXISTS: correr primero la verificacion
-- y aplicar el ALTER solo si la columna no existe.

-- 1. Verificacion previa (esperado antes de aplicar: 0 filas).
SELECT COLUMN_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'app_paloteo_registro_crudo'
  AND COLUMN_NAME = 'id_barra';

-- 2. Cambio.
ALTER TABLE app_paloteo_registro_crudo
    ADD COLUMN id_barra INT(11) NULL DEFAULT NULL AFTER id_operacion,
    ADD INDEX idx_crudo_operacion_barra_producto (id_operacion, id_barra, id_producto);

-- 3. Verificacion posterior (esperado: la columna id_barra INT NULL despues de
--    id_operacion, el indice idx_crudo_operacion_barra_producto, y todas las
--    filas existentes con id_barra NULL).
SHOW CREATE TABLE app_paloteo_registro_crudo;
SELECT COUNT(*) AS filas, SUM(id_barra IS NULL) AS filas_sin_barra
FROM app_paloteo_registro_crudo;

-- Rollback (solo si hiciera falta volver al codigo anterior; el codigo v12.45
-- no funciona sin la columna):
-- ALTER TABLE app_paloteo_registro_crudo
--     DROP INDEX idx_crudo_operacion_barra_producto,
--     DROP COLUMN id_barra;
