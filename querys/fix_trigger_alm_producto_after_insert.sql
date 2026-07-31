-- Unifica trg_alm_producto_after_insert entre entornos (2026-07-30).
--
-- Produccion tenia la version legacy: siempre pesable=0 y ceros (0.00 /
-- 0.000000) en vez de NULL para productos nuevos, sin mirar el catalogo.
-- test_pos tenia una version mas nueva (deriva pesable de
-- ind_permite_comandar, usa NULL) pero sin excluir categorias -- el mismo
-- gap que trg_alm_producto_after_update, confirmado el mismo dia al probar
-- con AMSTEL/HUARI/-LIMONADA (CERVEZAS/AGUAS Y JUGOS con
-- ind_permite_comandar=71 que NO son pesables).
--
-- Esta version:
--   - Deriva pesable de ind_permite_comandar=71 Y de que la categoria no
--     este en CATEGORIAS_EXCLUIDAS_PESAJE (main.py: 10,11,13,14,15,17,18,19,20).
--   - Usa NULL (no 0) en peso_bruto/tara/gramos_por_oz -- un producto nuevo
--     autentico pesable cae directo en INCOMPLETOS, visible y editable,
--     nunca en la fila fantasma pesable=0 que dejaba atascados a los 12
--     productos de TODO.md ("conflictos excepcionales").
--   - Sincroniza barcode=NULL y estado segun el producto, igual que
--     trg_alm_producto_after_update.
--
-- Ejecutar UNA VEZ por entorno.

DROP TRIGGER IF EXISTS trg_alm_producto_after_insert;

DELIMITER $$

CREATE DEFINER = 'root'@'localhost' TRIGGER trg_alm_producto_after_insert
AFTER INSERT ON alm_producto
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
      Configuracion legacy / AppSheet.
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

    /*
      Configuracion API / PWA.
      nombre_perfil se omite para usar el DEFAULT 'Estándar'.
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
END$$

DELIMITER ;
