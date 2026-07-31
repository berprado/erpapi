-- Fix (2026-07-30): trg_alm_producto_after_update sincroniza `pesable` en
-- app_producto_pesaje_config / app_producto_pesaje_config_api cada vez que se
-- actualiza alm_producto.ind_permite_comandar, pero la version original
-- (existente solo en test_pos) ponia pesable=1 sin validar que el perfil ya
-- tuviera peso_bruto/gramos_por_oz reales cargados. Eso fue lo que dejo a
-- PATRON SILVER 750ML (id 31) y DUO TANNAT MERLOT 750ML (id 258) con un
-- perfil "pesable" pero con ceros/NULL, que rompia la captura de paloteo
-- (ZeroDivisionError) hasta el fix de la app v10.94.
--
-- Este script reemplaza el trigger para que:
--   - pesable=0 siempre se puede aplicar (deshabilitar nunca es riesgoso).
--   - pesable=1 solo se aplica si el perfil ya tiene peso_bruto y
--     gramos_por_oz > 0 (perfil realmente configurado).
--   - En cualquier otro caso, `pesable` queda como estaba: no se auto-habilita
--     con datos invalidos. La persona que complete el perfil real via el
--     modulo PESAJE de la app ya deja pesable=1 correctamente (esos
--     endpoints validan gt=0).
-- No corrige retroactivamente filas ya rotas (eso es un UPDATE de datos
-- aparte); solo evita que el mismo patron se repita para otros productos.
--
-- Fix adicional (mismo dia, tras probar en produccion): `ind_permite_comandar
-- = 71` por si solo NO significa "pesable" -- confirmado con el usuario que
-- CERVEZAS/AGUAS Y JUGOS (entre otras) tienen ese valor sin ser pesables.
-- v_pesable ahora excluye las mismas categorias que ya excluye la app
-- (CATEGORIAS_EXCLUIDAS_PESAJE en main.py: 10,11,13,14,15,17,18,19,20), para
-- no repetir el caso de AMSTEL/HUARI/-LIMONADA (aplicado y revertido en
-- producto el 2026-07-30 al ver que rompia la captura en vivo de la
-- operativa 1263).
--
-- Ejecutar UNA VEZ por entorno. Ver documentos/redondeo_y_tolerancia.md y
-- TODO.md ("conflictos excepcionales") para el contexto de negocio.

DROP TRIGGER IF EXISTS trg_alm_producto_after_update;

DELIMITER $$

CREATE DEFINER = 'root'@'localhost' TRIGGER trg_alm_producto_after_update
AFTER UPDATE ON alm_producto
FOR EACH ROW
BEGIN
    DECLARE v_pesable TINYINT(1);
    DECLARE v_estado VARCHAR(3);

    SET v_pesable = CASE
                        WHEN NEW.ind_permite_comandar = 71
                             AND (NEW.id_categoria IS NULL OR NEW.id_categoria NOT IN (10,11,13,14,15,17,18,19,20))
                            THEN 1
                        ELSE 0
                     END;
    SET v_estado = CASE WHEN NEW.estado = 'HAB' THEN 'HAB' ELSE 'DES' END;

    /*
      Sincroniza la fila legacy / AppSheet si existe.
    */
    INSERT IGNORE INTO app_producto_pesaje_config (
        id_producto_almacen,
        peso_bruto,
        tara,
        es_tara_provisional,
        gramos_por_oz,
        pesable,
        tolerancia_oz,
        usuario_reg,
        fecha_reg,
        fecha_mod
    ) VALUES (
        NEW.id,
        NULL,
        NULL,
        0,
        NULL,
        v_pesable,
        1.50,
        NEW.usuario_reg,
        NOW(),
        NOW()
    );

    UPDATE app_producto_pesaje_config
       SET pesable = CASE
                        WHEN v_pesable = 0 THEN 0
                        WHEN peso_bruto IS NOT NULL AND peso_bruto > 0
                             AND gramos_por_oz IS NOT NULL AND gramos_por_oz > 0
                            THEN 1
                        ELSE pesable
                     END,
           usuario_reg = NEW.usuario_reg,
           fecha_mod = NOW()
     WHERE id_producto_almacen = NEW.id;

    /*
      Sincroniza la capa API / PWA.
      nombre_perfil se mantiene como default 'Estándar'; no se sobreescriben
      pesos/barcode existentes; el estado sigue al producto.
    */
    INSERT IGNORE INTO app_producto_pesaje_config_api (
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
    ) VALUES (
        NEW.id,
        NULL,
        NULL,
        NULL,
        v_pesable,
        NULL,
        1.50,
        v_estado,
        NEW.usuario_reg,
        NOW(),
        NOW()
    );

    UPDATE app_producto_pesaje_config_api
       SET pesable = CASE
                        WHEN v_pesable = 0 THEN 0
                        WHEN peso_bruto IS NOT NULL AND peso_bruto > 0
                             AND gramos_por_oz IS NOT NULL AND gramos_por_oz > 0
                            THEN 1
                        ELSE pesable
                     END,
           estado = v_estado,
           usuario_reg = NEW.usuario_reg,
           fecha_mod = NOW()
     WHERE id_producto_almacen = NEW.id;
END$$

DELIMITER ;
