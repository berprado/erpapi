-- EJECUTADO en produccion el 2026-07-30. Aplicado a 8 de los 12 (7 VINOS +
-- PATRON SILVER). Los otros 4 (HUARI 620ML, AMSTEL 620ML, AMSTEL LATA 473ML,
-- -LIMONADA) se aplicaron y se REVIRTIERON el mismo dia: son categorias
-- CERVEZAS/AGUAS Y JUGOS, excluidas a proposito del modulo PESAJE
-- (CATEGORIAS_EXCLUIDAS_PESAJE). AMSTEL LATA 473ML tenia movimiento en la
-- operativa activa (1263) y paso a pedir peso en vivo en vez de unidades --
-- se detecto y revirtio de inmediato. Pendiente decision de negocio: ver
-- TODO.md antes de reintentar el pesable=1 para esos 4.
--
-- Destrabar en produccion los 12 productos cuyo catalogo dice pesable
-- (alm_producto.ind_permite_comandar=71) pero cuya unica fila activa en
-- app_producto_pesaje_config_api quedo con pesable=0 (fila fantasma creada
-- por trg_alm_producto_after_insert). Hoy son infixables desde la app:
-- POST /perfiles choca 409 (nombre 'Estandar' ya ocupado), DELETE rechaza
-- 400 (unico perfil activo), PUT con pesable=0 solo permite editar barcode.
-- Ver TODO.md ("conflictos excepcionales de pesable") para el contexto
-- completo. Ejecutar UNA VEZ en produccion.
--
-- 7 productos son VINOS y ya tienen valor real validado en test_pos (mismo
-- producto fisico) -- se copia ese peso_bruto directo, con tara=0 y
-- gramos_por_oz=1 por la excepcion VINOS (id_categoria=6).
UPDATE app_producto_pesaje_config_api
   SET pesable = 1, peso_bruto = 5.00, tara = 0.00, gramos_por_oz = 1.000000
 WHERE id_producto_almacen = 258 AND estado = 'HAB'; -- DUO TANNAT MERLOT 750ML

UPDATE app_producto_pesaje_config_api
   SET pesable = 1, peso_bruto = 5.00, tara = 0.00, gramos_por_oz = 1.000000
 WHERE id_producto_almacen = 324 AND estado = 'HAB'; -- NAVARRO CORREAS EXTRA BRUT 750ML

UPDATE app_producto_pesaje_config_api
   SET pesable = 1, peso_bruto = 5.00, tara = 0.00, gramos_por_oz = 1.000000
 WHERE id_producto_almacen = 363 AND estado = 'HAB'; -- PIONERO 750ML

UPDATE app_producto_pesaje_config_api
   SET pesable = 1, peso_bruto = 5.00, tara = 0.00, gramos_por_oz = 1.000000
 WHERE id_producto_almacen = 386 AND estado = 'HAB'; -- CHANDON DEMI SEC 750ML

UPDATE app_producto_pesaje_config_api
   SET pesable = 1, peso_bruto = 5.00, tara = 0.00, gramos_por_oz = 1.000000
 WHERE id_producto_almacen = 392 AND estado = 'HAB'; -- JUAN CRUZ 750ML

UPDATE app_producto_pesaje_config_api
   SET pesable = 1, peso_bruto = 5.00, tara = 0.00, gramos_por_oz = 1.000000
 WHERE id_producto_almacen = 452 AND estado = 'HAB'; -- KOHLBERG BICENTENARIO 750ML

UPDATE app_producto_pesaje_config_api
   SET pesable = 1, peso_bruto = 5.00, tara = 0.00, gramos_por_oz = 1.000000
 WHERE id_producto_almacen = 472 AND estado = 'HAB'; -- CODORNIU CLASICO 750ML

-- 5 productos no son VINOS y no hay peso bruto real en ningun entorno todavia.
-- Solo se destraban a NULL (pesable segun catalogo, sin datos). Quedan en
-- INCOMPLETOS, editables normalmente desde PESAJE cuando se puedan pesar.
UPDATE app_producto_pesaje_config_api
   SET pesable = 1, peso_bruto = NULL, tara = NULL, gramos_por_oz = NULL
 WHERE id_producto_almacen = 31 AND estado = 'HAB'; -- PATRON SILVER 750ML

UPDATE app_producto_pesaje_config_api
   SET pesable = 1, peso_bruto = NULL, tara = NULL, gramos_por_oz = NULL
 WHERE id_producto_almacen = 138 AND estado = 'HAB'; -- HUARI 620ML

UPDATE app_producto_pesaje_config_api
   SET pesable = 1, peso_bruto = NULL, tara = NULL, gramos_por_oz = NULL
 WHERE id_producto_almacen = 358 AND estado = 'HAB'; -- -LIMONADA

UPDATE app_producto_pesaje_config_api
   SET pesable = 1, peso_bruto = NULL, tara = NULL, gramos_por_oz = NULL
 WHERE id_producto_almacen = 466 AND estado = 'HAB'; -- AMSTEL 620ML

UPDATE app_producto_pesaje_config_api
   SET pesable = 1, peso_bruto = NULL, tara = NULL, gramos_por_oz = NULL
 WHERE id_producto_almacen = 492 AND estado = 'HAB'; -- AMSTEL LATA 473ML
