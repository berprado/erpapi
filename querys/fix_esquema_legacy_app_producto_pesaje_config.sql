-- Fix (2026-09-10): esquema desfasado de app_producto_pesaje_config (legacy,
-- sistema de casa matriz -- backstage -- independiente de este repo) en la
-- linea Beer Garden (test_pos y su produccion).
--
-- Contexto: trg_alm_producto_after_insert/after_update siempre asumieron el
-- esquema "nuevo" de esta tabla (id_producto_almacen, gramos_por_oz,
-- pesable) porque asi la tiene casa matriz en produccion (296 filas,
-- actividad real hoy -- verificado 2026-09-10, sistema vivo y en uso). En la
-- linea Beer Garden (test_pos, y presumiblemente su produccion por ser
-- replica exacta) esta tabla nunca se migro a ese esquema porque el sistema
-- de casa matriz que la usa no esta implementado ahi -- quedo con el
-- esquema viejo (id_producto, sin gramos_por_oz/pesable) y 0 filas, sin
-- consumidor real en esa linea.
--
-- Efecto del desfasaje (encontrado 2026-09-10 con un INSERT de sanity check
-- real en test_pos, no solo SHOW CREATE TRIGGER): CUALQUIER INSERT o UPDATE
-- sobre alm_producto fallaba con
-- "ERROR 1054: Unknown column 'id_producto_almacen' in 'field list'" al
-- disparar el trigger, porque este intenta escribir en columnas que no
-- existen en esta version de la tabla. Bug dormido desde que el trigger
-- unificado se aplico (2026-07-30) -- nadie lo noto porque nadie habia
-- insertado/actualizado un producto real en esa base desde entonces.
--
-- Este script lleva el esquema de la tabla, en la linea Beer Garden, al
-- mismo que ya usa casa matriz -- MISMO nombre de tabla y de trigger en
-- ambas lineas, solo se corrige el esquema para que un unico script de
-- trigger (querys/fix_trigger_alm_producto_after_insert.sql /
-- after_update.sql) funcione en las dos sin bifurcar logica.
--
-- Seguro de ejecutar: la tabla esta vacia (0 filas) en la linea Beer Garden,
-- verificado antes de escribir este script. Si por algun motivo la tabla
-- destino ya tuviera filas reales al momento de ejecutar esto, DETENERSE y
-- revisar -- este script no esta pensado para migrar datos existentes.
--
-- Ejecutar UNA VEZ por entorno de la linea Beer Garden (test_pos, luego su
-- produccion) ANTES de re-aplicar los triggers ahi.

-- PASO MANUAL OBLIGATORIO ANTES DE SEGUIR: correr esto solo y confirmar que
-- da 0. Si da distinto de 0, DETENERSE ACA -- este script no esta pensado
-- para migrar datos existentes, solo para corregir una tabla vacia.
--
--   SELECT COUNT(*) FROM app_producto_pesaje_config;
--
-- No se automatiza el chequeo (MySQL no tiene una forma limpia de abortar
-- un script .sql a mitad de camino desde fuera de una rutina) -- queda a
-- criterio de quien ejecuta, a proposito, para que se detenga y piense si
-- ve un numero inesperado.

ALTER TABLE app_producto_pesaje_config
    CHANGE COLUMN id_producto id_producto_almacen INT(11) NOT NULL,
    MODIFY COLUMN peso_bruto DECIMAL(10,2) DEFAULT NULL,
    MODIFY COLUMN tara DECIMAL(10,2) DEFAULT NULL,
    ADD COLUMN gramos_por_oz DECIMAL(10,6) DEFAULT NULL AFTER es_tara_provisional,
    ADD COLUMN pesable TINYINT(1) DEFAULT '1' AFTER gramos_por_oz,
    MODIFY COLUMN barcode VARCHAR(50) DEFAULT NULL,
    MODIFY COLUMN tolerancia_oz DECIMAL(10,2) DEFAULT '1.50',
    MODIFY COLUMN usuario_reg VARCHAR(255) NOT NULL,
    MODIFY COLUMN fecha_mod TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;

-- Reemplaza la unique key vieja (sobre id_producto) por la de casa matriz
-- (mismo nombre, sobre la columna ya renombrada).
ALTER TABLE app_producto_pesaje_config DROP INDEX id_producto;
ALTER TABLE app_producto_pesaje_config ADD UNIQUE KEY uk_app_pesaje_producto_almacen (id_producto_almacen);

-- Charset/collation al mismo que casa matriz (la tabla esta vacia, sin
-- riesgo de mojibake en datos existentes).
ALTER TABLE app_producto_pesaje_config CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Verificacion: comparar contra el esquema real de casa matriz antes de dar
-- por buena la migracion.
SHOW CREATE TABLE app_producto_pesaje_config;
