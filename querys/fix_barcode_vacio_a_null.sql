-- Corrige 5 filas legacy en app_producto_pesaje_config_api con barcode=''
-- en vez de NULL (mismos id_config en test_pos y produccion -- misma fila
-- de origen, no un problema por entorno). No las genera el trigger actual
-- (inserta NULL literal) ni el flujo normal de guardado, una vez corregido
-- el bug de v10.97 en PUT /api/pesaje/config/{id} (el chequeo
-- `payload.barcode is not None` nunca aplicaba el guardado cuando el
-- frontend mandaba `barcode: null` para vaciar el campo).
--
-- Ejecutado en test_pos y produccion el 2026-07-31.
UPDATE app_producto_pesaje_config_api SET barcode = NULL WHERE id = 190 AND barcode = ''; -- WINSTON YELLOW P
UPDATE app_producto_pesaje_config_api SET barcode = NULL WHERE id = 281 AND barcode = ''; -- POMELO NEUS 3LT
UPDATE app_producto_pesaje_config_api SET barcode = NULL WHERE id = 266 AND barcode = ''; -- PUERTO DE INDIAS MORA 750ML
UPDATE app_producto_pesaje_config_api SET barcode = NULL WHERE id = 264 AND barcode = ''; -- HIRAM WALKER 1LT
UPDATE app_producto_pesaje_config_api SET barcode = NULL WHERE id = 261 AND barcode = ''; -- VILLA CARDEA 1LT
