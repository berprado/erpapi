-- Usuario de base de datos propio para la API (acceso via tunel LocalToNet).
-- TODO.md: "Cambiar usuarios y contraseñas de BD de produccion".
--
-- OBJETIVO: que la API deje de entrar como root. Se crea un usuario solo para
-- la API, con lectura sobre adminerp y escritura SOLO en las tablas que la API
-- escribe. El usuario que usa el POS localmente (root) NO se toca en este paso.
--
-- ESTE ARCHIVO NO TIENE CONTRASEÑAS. Reemplazar <CONTRASENA_API> por una
-- contraseña fuerte y DISTINTA por servidor (casa matriz, Beer Garden,
-- test_pos), p. ej.:  python -c "import secrets; print(secrets.token_urlsafe(24))"
-- No guardar la contraseña en el repo; va solo en el .env local y en las
-- variables de entorno de Seenode, marcada como secreto.
--
-- Hechos verificados el 2026-10-04 (solo lectura, test_pos y Beer Garden):
--  * MySQL 5.6.12. La API entra hoy como root@localhost con ALL PRIVILEGES.
--  * Por el tunel, el servidor ve la conexion como LOCAL (USER() = root@localhost):
--    el cliente de LocalToNet corre en la misma maquina que MySQL. Por eso el
--    usuario se crea para 'localhost' y '127.0.0.1'; no se puede restringir por
--    la IP de origen real (Seenode) desde MySQL.
--  * Existe un usuario anonimo ''@'localhost'. Con el usuario anonimo presente,
--    un 'api_paloteo'@'%' NO funcionaria (MySQL elige primero la fila con host
--    mas especifico, ''@'localhost', y el login falla): por eso se crea con host
--    explicito. Ver tambien el paso 6.
--
-- ORDEN: aplicar primero en test_pos, apuntar la API local a test_pos con el
-- usuario nuevo y recorrer login, PALOTEO (alta y correccion), AJUSTES (preview
-- y aplicar), PESAJE (editar perfil) y POUR COST. Recien despues, Beer Garden y
-- casa matriz, actualizando PROD_DB_USER / PROD_DB_PASS en Seenode.

-- ---------------------------------------------------------------------------
-- 0. Verificacion previa (solo lectura)
-- ---------------------------------------------------------------------------
SELECT user, host FROM mysql.user ORDER BY user, host;
SHOW GRANTS FOR ''@'localhost';   -- que puede hacer hoy el usuario anonimo

-- ---------------------------------------------------------------------------
-- 1. Usuario de la API
-- ---------------------------------------------------------------------------
CREATE USER 'api_paloteo'@'localhost' IDENTIFIED BY '<CONTRASENA_API>';
CREATE USER 'api_paloteo'@'127.0.0.1' IDENTIFIED BY '<CONTRASENA_API>';

-- ---------------------------------------------------------------------------
-- 2. Lectura: todo el esquema adminerp
-- ---------------------------------------------------------------------------
-- La API lee unas 40 tablas y vistas (catalogo, comandas, traspasos, vistas
-- v9_*/vw_*/vista_*, seg_*, parameter_table...). SELECT sobre el esquema evita
-- que una vista o tabla nueva rompa la API en produccion. Alternativa mas
-- estricta: GRANT SELECT tabla por tabla (mas fragil al agregar consultas).
GRANT SELECT ON adminerp.* TO 'api_paloteo'@'localhost';
GRANT SELECT ON adminerp.* TO 'api_paloteo'@'127.0.0.1';

-- ---------------------------------------------------------------------------
-- 3. Escritura: solo las tablas que la API escribe (extraido de main.py/models.py)
-- ---------------------------------------------------------------------------
-- Sin DELETE: la API no borra filas (soft delete con estado = 'DES').
-- Sin DDL (CREATE/ALTER/DROP), TRIGGER, GRANT ni privilegios globales: los DDL
-- de querys/ se siguen aplicando con un usuario administrador.

-- Inventario fisico (PALOTEO: alta y correccion)
GRANT INSERT, UPDATE ON adminerp.bar_inventario_fisico      TO 'api_paloteo'@'localhost', 'api_paloteo'@'127.0.0.1';
GRANT INSERT, UPDATE ON adminerp.bar_detalle_fisico         TO 'api_paloteo'@'localhost', 'api_paloteo'@'127.0.0.1';
GRANT INSERT         ON adminerp.app_paloteo_registro_crudo TO 'api_paloteo'@'localhost', 'api_paloteo'@'127.0.0.1';

-- Ajustes (AJUSTES: aplicar)
GRANT INSERT, UPDATE ON adminerp.bar_ajuste                 TO 'api_paloteo'@'localhost', 'api_paloteo'@'127.0.0.1';
GRANT INSERT, UPDATE ON adminerp.bar_detalle_ajuste         TO 'api_paloteo'@'localhost', 'api_paloteo'@'127.0.0.1';
GRANT INSERT, UPDATE ON adminerp.bar_salida_inventario      TO 'api_paloteo'@'localhost', 'api_paloteo'@'127.0.0.1';
GRANT INSERT, UPDATE ON adminerp.bar_detalle_salida_inv     TO 'api_paloteo'@'localhost', 'api_paloteo'@'127.0.0.1';
GRANT        UPDATE  ON adminerp.bar_inventario             TO 'api_paloteo'@'localhost', 'api_paloteo'@'127.0.0.1';
GRANT INSERT, UPDATE ON adminerp.app_paloteo_ajuste_control TO 'api_paloteo'@'localhost', 'api_paloteo'@'127.0.0.1';
GRANT INSERT         ON adminerp.analytics_varianza_inventario TO 'api_paloteo'@'localhost', 'api_paloteo'@'127.0.0.1';

-- PESAJE (perfiles: alta, edicion, baja logica)
GRANT INSERT, UPDATE ON adminerp.app_producto_pesaje_config_api TO 'api_paloteo'@'localhost', 'api_paloteo'@'127.0.0.1';

-- Login (rastro de accesos y auditoria)
GRANT INSERT         ON adminerp.seg_acceso                 TO 'api_paloteo'@'localhost', 'api_paloteo'@'127.0.0.1';
GRANT INSERT         ON adminerp.app_login_auditoria_api    TO 'api_paloteo'@'localhost', 'api_paloteo'@'127.0.0.1';

-- Nota MySQL 8.0.22+: SELECT ... FOR UPDATE pasa a exigir UPDATE (o DELETE /
-- LOCK TABLES) sobre la tabla. La API bloquea ope_operacion,
-- bar_inventario_fisico y bar_inventario. Hoy (5.6) basta con SELECT; si algun
-- dia se migra a 8.0, agregar LOCK TABLES ON adminerp.* o UPDATE en ope_operacion.

FLUSH PRIVILEGES;

-- ---------------------------------------------------------------------------
-- 4. Verificacion posterior
-- ---------------------------------------------------------------------------
SHOW GRANTS FOR 'api_paloteo'@'localhost';
SHOW GRANTS FOR 'api_paloteo'@'127.0.0.1';
-- Probar conectado como api_paloteo (deben fallar con "command denied"):
--   DELETE FROM adminerp.bar_inventario WHERE 1 = 0;
--   CREATE TABLE adminerp.prueba_permiso (id INT);

-- ---------------------------------------------------------------------------
-- 5. Cambiar la API al usuario nuevo
-- ---------------------------------------------------------------------------
-- .env local / Seenode (variables marcadas como secreto):
--   PROD_DB_USER=api_paloteo
--   PROD_DB_PASS=<CONTRASENA_API de ESA sucursal>
-- Redesplegar (Seenode reinicia al guardar variables) y repetir el smoke test.

-- ---------------------------------------------------------------------------
-- 6. Despues, con la API ya funcionando con su usuario (pasos aparte)
-- ---------------------------------------------------------------------------
-- a) Usuario anonimo: si el paso 0 muestra que no lo usa nadie, eliminarlo
--    (es parte de la instalacion por defecto de MySQL, no del POS):
--      DROP USER ''@'localhost';
-- b) root: hoy cualquiera que llegue al puerto del tunel puede intentar
--    contraseñas de root. Cambiar su contraseña SOLO coordinando con la
--    configuracion del POS local (que hoy probablemente usa root). Tener en
--    cuenta que root existe en 'localhost', '127.0.0.1' y '::1': son tres
--    cuentas y hay que cambiar las tres.
-- c) Idealmente, que el tunel no exponga MySQL a internet (o lo restrinja por
--    IP en LocalToNet, si el plan lo permite).

-- ---------------------------------------------------------------------------
-- Rollback (la API vuelve a root cambiando PROD_DB_USER/PROD_DB_PASS)
-- ---------------------------------------------------------------------------
-- DROP USER 'api_paloteo'@'localhost';
-- DROP USER 'api_paloteo'@'127.0.0.1';
