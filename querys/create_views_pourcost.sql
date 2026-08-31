-- Vistas del módulo POUR COST (2026-08-05).
--
-- Igual que los triggers de alm_producto (ver
-- querys/fix_trigger_alm_producto_after_*.sql), estas vistas viven en MySQL,
-- no en el ORM de este repo -- este script es la fuente de verdad versionada
-- para poder recrearlas en cualquier entorno. Reemplaza a
-- documentos/pour_cost/vistas_pourcost.sql, que es un dump de
-- information_schema.VIEWS (formato INSERT, generado por dbForge solo para
-- documentar) y por lo tanto NO es ejecutable: information_schema es de solo
-- lectura, un INSERT contra esa tabla falla en cualquier servidor real.
--
-- ADVERTENCIA -- prefijo de esquema hardcodeado a `adminerp`:
-- Las 6 vistas califican cada tabla con el prefijo `adminerp`.`tabla`
-- (esquema fijo, no relativo a la BD donde se ejecuta el CREATE VIEW). Eso
-- es correcto tal cual en los entornos remotos (test_pos, production), donde
-- el esquema real se llama `adminerp`. Pero el entorno local (WAMP,
-- APP_ENV=test) usa una copia llamada `adminerp_copy`
-- (ver documentos/estructura_tablas_modulo_ajuste.md, `USE adminerp_copy;`).
-- Si se ejecuta este script tal cual dentro de `adminerp_copy`, las vistas
-- quedarán creadas ahí pero seguirán leyendo de un esquema `adminerp`
-- separado en el mismo servidor MySQL -- que puede no existir, o existir
-- desactualizado. Antes de aplicar en local: (a) confirmar si hay un
-- esquema `adminerp` real y sincronizado en el WAMP local, o (b) generar una
-- variante de este script con `adminerp_copy` en vez de `adminerp` para uso
-- exclusivo en test. No asumir uno u otro sin verificar -- ver
-- documentos/pour_cost/pourcost.md sección "Riesgos y abiertos".
--
-- Ejecutar UNA VEZ por entorno (test / test_pos / production) antes de
-- activar los endpoints del módulo POUR COST.
--
-- Orden de dependencia (cada vista puede referenciar a la anterior):
--   1. v9_cache_wac_producto            (independiente)
--   2. v9_menubackstage                 (independiente)
--   3. vw_alm_producto_con_nombres      (independiente)
--   4. vw_cache_wac_producto_detalle    (independiente)
--   5. vw_combo_detalle_reload          (independiente)
--   6. vw_pourcost_receta               (depende de 4, 5 y 2)

-- ---------------------------------------------------------------------------
-- 1. v9_cache_wac_producto
--    WAC (costo promedio ponderado) actual por producto/almacén, ya unido a
--    nombre/categoría. Excluye productos deshabilitados y el producto
--    "COMODIN".
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v9_cache_wac_producto AS
select `c`.`id_almacen` AS `id_almacen`,`c`.`id_producto` AS `id_producto`,`p`.`codigo` AS `codigo_producto`,`p`.`nombre` AS `nombre_producto`,`p`.`descripcion` AS `descripcion_producto`,`p`.`id_categoria` AS `id_categoria`,`cat`.`nombre` AS `nombre_categoria`,`c`.`wac_actual` AS `wac_actual`,`c`.`wac_actual` AS `wac_unitario`,`c`.`fecha_actualizacion` AS `fecha_actualizacion` from ((`adminerp`.`cache_wac_producto` `c` join `adminerp`.`alm_producto` `p` on((`p`.`id` = `c`.`id_producto`))) left join `adminerp`.`alm_categoria` `cat` on((`cat`.`id` = `p`.`id_categoria`))) where ((`p`.`estado` = 'HAB') and (trim(coalesce(`p`.`descripcion`,'')) <> 'COMODIN'));

-- ---------------------------------------------------------------------------
-- 2. v9_menubackstage
--    Menú activo: combos (bar_combo_coctel) UNION ALL productos sueltos
--    comandables (alm_producto con ind_permite_comandar = 70), cada uno con
--    su precio_venta vigente por id_dia (se queda con la fila HAB más
--    reciente de ope_precio_venta vía NOT EXISTS de una posterior).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v9_menubackstage AS
select `c`.`codigo` AS `codigo`,`c`.`nombre` AS `nombre`,`pv`.`precio_venta` AS `precio_venta`,`c`.`descripcion` AS `descripcion`,`c`.`id_categoria` AS `id_categoria`,`cat`.`nombre` AS `nombre_categoria`,'combo' AS `tipo`,`c`.`id` AS `id_origen`,`pv`.`id_dia` AS `id_dia`,`pv`.`fecha_mod` AS `fecha_precio` from ((`adminerp`.`ope_precio_venta` `pv` join `adminerp`.`bar_combo_coctel` `c` on((`pv`.`id_combo_coctel` = `c`.`id`))) join `adminerp`.`alm_categoria` `cat` on((`cat`.`id` = `c`.`id_categoria`))) where ((`c`.`estado` = 'HAB') and (`pv`.`estado` = 'HAB') and (`cat`.`estado` = 'HAB') and (not(exists(select 1 from `adminerp`.`ope_precio_venta` `pv2` where ((`pv2`.`estado` = 'HAB') and (`pv2`.`id_combo_coctel` = `pv`.`id_combo_coctel`) and (`pv2`.`id_dia` = `pv`.`id_dia`) and (coalesce(`pv2`.`fecha_mod`,`pv2`.`fecha_reg`) > coalesce(`pv`.`fecha_mod`,`pv`.`fecha_reg`))))))) union all select `p`.`codigo` AS `codigo`,`p`.`nombre` AS `nombre`,`pv`.`precio_venta` AS `precio_venta`,`p`.`descripcion` AS `descripcion`,`p`.`id_categoria` AS `id_categoria`,`cat`.`nombre` AS `nombre_categoria`,'producto' AS `tipo`,`p`.`id` AS `id_origen`,`pv`.`id_dia` AS `id_dia`,`pv`.`fecha_mod` AS `fecha_precio` from ((`adminerp`.`ope_precio_venta` `pv` join `adminerp`.`alm_producto` `p` on((`pv`.`id_producto` = `p`.`id`))) join `adminerp`.`alm_categoria` `cat` on((`cat`.`id` = `p`.`id_categoria`))) where ((`p`.`estado` = 'HAB') and (`p`.`ind_permite_comandar` = 70) and (`pv`.`estado` = 'HAB') and (`cat`.`estado` = 'HAB') and (not(exists(select 1 from `adminerp`.`ope_precio_venta` `pv2` where ((`pv2`.`estado` = 'HAB') and (`pv2`.`id_producto` = `pv`.`id_producto`) and (`pv2`.`id_dia` = `pv`.`id_dia`) and (coalesce(`pv2`.`fecha_mod`,`pv2`.`fecha_reg`) > coalesce(`pv`.`fecha_mod`,`pv`.`fecha_reg`)))))));

-- ---------------------------------------------------------------------------
-- 3. vw_alm_producto_con_nombres
--    Catálogo completo de productos con nombres resueltos (categoría,
--    proveedor, barra, unidades de medida). Fuente del "catálogo de
--    insumos" para simulación de recetas.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_alm_producto_con_nombres AS
select `p`.`id` AS `id`,`p`.`nombre` AS `nombre`,`p`.`descripcion` AS `descripcion`,`p`.`codigo` AS `codigo`,`p`.`correlativo` AS `correlativo`,`cat`.`nombre` AS `categoria`,`prov`.`nombre` AS `proveedor`,`barra`.`nombre` AS `nombre_barra`,`p`.`medida` AS `medida`,`p`.`p_unidad_medida` AS `p_unidad_medida`,`um`.`nombre` AS `nombre_unidad_medida`,`p`.`cantidad_detalle` AS `cantidad_detalle`,`p`.`p_unidad_medida_detalle` AS `p_unidad_medida_detalle`,`umd`.`nombre` AS `nombre_unidad_medida_detalle`,`p`.`minimo_stock` AS `minimo_stock`,`p`.`maximo_stock` AS `maximo_stock`,`p`.`minimo_stock_barra` AS `minimo_stock_barra`,`p`.`maximo_stock_barra` AS `maximo_stock_barra`,`p`.`ind_permite_comandar` AS `ind_permite_comandar`,`ipc`.`nombre` AS `nombre_ind_permite_comandar`,`p`.`estado` AS `estado`,`p`.`usuario_reg` AS `usuario_reg`,`p`.`fecha_reg` AS `fecha_reg`,`p`.`fecha_mod` AS `fecha_mod` from ((((((`adminerp`.`alm_producto` `p` left join `adminerp`.`alm_categoria` `cat` on(((`p`.`id_categoria` = `cat`.`id`) and (`cat`.`estado` = 'HAB')))) left join `adminerp`.`alm_proveedor` `prov` on(((`p`.`id_proveedor` = `prov`.`id`) and (`prov`.`estado` = 'HAB')))) left join `adminerp`.`bar_barra` `barra` on(((`p`.`id_barra` = `barra`.`id`) and (`barra`.`estado` = 'HAB')))) left join `adminerp`.`parameter_table` `um` on(((`p`.`p_unidad_medida` = `um`.`id`) and (`um`.`id_master` = 3) and (`um`.`estado` = 'HAB')))) left join `adminerp`.`parameter_table` `umd` on(((`p`.`p_unidad_medida_detalle` = `umd`.`id`) and (`umd`.`id_master` = 4) and (`umd`.`estado` = 'HAB')))) left join `adminerp`.`parameter_table` `ipc` on(((`p`.`ind_permite_comandar` = `ipc`.`id`) and (`ipc`.`id_master` = 20) and (`ipc`.`estado` = 'HAB')))) where (`p`.`estado` = 'HAB');

-- ---------------------------------------------------------------------------
-- 4. vw_cache_wac_producto_detalle
--    Variante de v9_cache_wac_producto orientada a join (sin filtrar estado
--    de producto ni excluir COMODIN). vw_pourcost_receta la usa para traer
--    el WAC de cada ingrediente de receta.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_cache_wac_producto_detalle AS
select `w`.`id_almacen` AS `id_almacen`,`w`.`id_producto` AS `id_producto`,`p`.`nombre` AS `nombre_producto`,`c`.`nombre` AS `nombre_categoria`,`w`.`wac_actual` AS `wac_actual`,`w`.`fecha_actualizacion` AS `fecha_actualizacion` from ((`adminerp`.`cache_wac_producto` `w` join `adminerp`.`alm_producto` `p` on((`p`.`id` = `w`.`id_producto`))) left join `adminerp`.`alm_categoria` `c` on((`c`.`id` = `p`.`id_categoria`))) order by `p`.`nombre`;

-- ---------------------------------------------------------------------------
-- 5. vw_combo_detalle_reload
--    Receta de cada combo/cóctel: una fila por ingrediente
--    (bar_detalle_combo_bar), con unidades de medida resueltas y el tipo de
--    cantidad (Unidad = botella completa, Detalle = fracción/oz).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_combo_detalle_reload AS
select `det`.`id_combo_coctel` AS `id_combo_coctel`,`combo`.`codigo` AS `codigo_combo`,`combo`.`nombre` AS `nombre_combo`,`combo`.`descripcion` AS `descripcion_combo`,`cat_combo`.`nombre` AS `nombre_categoria_combo`,`pro`.`id` AS `id_producto`,`pro`.`codigo` AS `codigo_producto`,`pro`.`nombre` AS `nombre_producto`,`cat_prod`.`nombre` AS `nombre_categoria_producto`,`pro`.`medida` AS `medida`,`pro`.`p_unidad_medida` AS `p_unidad_medida`,`pt1`.`nombre` AS `nombre_unidad_medida`,`pro`.`cantidad_detalle` AS `cantidad_detalle`,`pro`.`p_unidad_medida_detalle` AS `p_unidad_medida_detalle`,`pt2`.`nombre` AS `nombre_unidad_medida_detalle`,`det`.`cantidad` AS `cantidad_combo`,(case when (`det`.`ind_paq_detalle` = '1') then 'Unidad' else 'Detalle' end) AS `tipo_cantidad_combo`,`det`.`ind_tipo_producto` AS `ind_tipo_producto`,`pt3`.`nombre` AS `tipo_parte_combo`,`pro`.`ind_permite_comandar` AS `ind_permite_comandar_producto`,`pt_ind`.`nombre` AS `tipo_comandable_producto` from ((((((((`adminerp`.`bar_detalle_combo_bar` `det` join `adminerp`.`alm_producto` `pro` on((`pro`.`id` = `det`.`id_producto`))) join `adminerp`.`bar_combo_coctel` `combo` on((`combo`.`id` = `det`.`id_combo_coctel`))) left join `adminerp`.`alm_categoria` `cat_combo` on(((`cat_combo`.`id` = `combo`.`id_categoria`) and (`cat_combo`.`estado` = 'HAB')))) left join `adminerp`.`alm_categoria` `cat_prod` on(((`cat_prod`.`id` = `pro`.`id_categoria`) and (`cat_prod`.`estado` = 'HAB')))) left join `adminerp`.`parameter_table` `pt1` on(((`pt1`.`id` = `pro`.`p_unidad_medida`) and (`pt1`.`id_master` = 3) and (`pt1`.`estado` = 'HAB')))) left join `adminerp`.`parameter_table` `pt2` on(((`pt2`.`id` = `pro`.`p_unidad_medida_detalle`) and (`pt2`.`id_master` = 4) and (`pt2`.`estado` = 'HAB')))) left join `adminerp`.`parameter_table` `pt3` on(((`pt3`.`id` = `det`.`ind_tipo_producto`) and (`pt3`.`id_master` = 12) and (`pt3`.`estado` = 'HAB')))) left join `adminerp`.`parameter_table` `pt_ind` on(((`pt_ind`.`id` = `pro`.`ind_permite_comandar`) and (`pt_ind`.`id_master` = 20) and (`pt_ind`.`estado` = 'HAB')))) where ((`det`.`estado` = 'HAB') and (`combo`.`estado` = 'HAB') and (`pro`.`estado` = 'HAB'));

-- ---------------------------------------------------------------------------
-- 6. vw_pourcost_receta
--    Vista maestra del módulo: una fila por línea de receta, con
--    cantidad_unidad_base normalizada y cogs_ingrediente ya calculado
--    (cantidad x WAC, con la conversión Unidad/Detalle resuelta). Nota:
--    fija id_dia = 1 al unir con v9_menubackstage -- ver
--    documentos/pour_cost/pourcost.md sección "Riesgos y abiertos" sobre
--    qué día representa y si el módulo necesita exponer otros.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_pourcost_receta AS
select `det`.`id_combo_coctel` AS `id_combo_coctel`,`det`.`codigo_combo` AS `codigo_combo`,`det`.`nombre_combo` AS `nombre_combo`,`det`.`descripcion_combo` AS `descripcion_combo`,`det`.`nombre_categoria_combo` AS `nombre_categoria_combo`,`menu`.`precio_venta` AS `precio_venta`,`det`.`id_producto` AS `id_producto`,`det`.`codigo_producto` AS `codigo_producto`,`det`.`nombre_producto` AS `nombre_producto`,`det`.`nombre_categoria_producto` AS `nombre_categoria_producto`,`det`.`cantidad_combo` AS `cantidad_receta`,`det`.`tipo_cantidad_combo` AS `tipo_cantidad_combo`,`det`.`tipo_parte_combo` AS `tipo_parte_combo`,`det`.`nombre_unidad_medida` AS `unidad_base`,`det`.`medida` AS `medida_unidad_base`,`det`.`cantidad_detalle` AS `unidades_detalle_por_base`,`det`.`nombre_unidad_medida_detalle` AS `unidad_detalle`,coalesce(`wac`.`wac_actual`,0) AS `wac_actual`,(case when isnull(`wac`.`wac_actual`) then 1 else 0 end) AS `sin_wac`,(case when (`det`.`tipo_cantidad_combo` = 'Unidad') then `det`.`cantidad_combo` else (`det`.`cantidad_combo` / `det`.`cantidad_detalle`) end) AS `cantidad_unidad_base`,(case when (`det`.`tipo_cantidad_combo` = 'Unidad') then (`det`.`cantidad_combo` * coalesce(`wac`.`wac_actual`,0)) else ((`det`.`cantidad_combo` / `det`.`cantidad_detalle`) * coalesce(`wac`.`wac_actual`,0)) end) AS `cogs_ingrediente` from ((`adminerp`.`vw_combo_detalle_reload` `det` left join `adminerp`.`vw_cache_wac_producto_detalle` `wac` on(((`wac`.`id_producto` = `det`.`id_producto`) and (`wac`.`id_almacen` = 1)))) left join `adminerp`.`v9_menubackstage` `menu` on(((`menu`.`id_origen` = `det`.`id_combo_coctel`) and (`menu`.`tipo` = 'combo') and (`menu`.`id_dia` = 1))));
