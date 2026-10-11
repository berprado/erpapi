-- Control y auditoria de las operaciones del POS hechas desde la PWA
-- (documentos/operaciones_pos/). Tabla propia de la API: no altera tablas del POS.
--
-- Una fila por operacion confirmada (hoy solo tipo 'INGRESO_BARRA':
-- ingreso de proveedor -> traspaso -> recepcion en barra, v12.50). Se escribe
-- dentro de la misma transaccion que los movimientos del POS.
--
-- clave_idempotencia: la genera la PWA al abrir el formulario y la reenvia en
-- cada intento. Un segundo envio con la misma clave choca con el UNIQUE y la
-- API responde 409 con los documentos ya creados, en vez de duplicar el
-- ingreso (un ingreso con costo mueve el WAC: no debe repetirse por un doble
-- toque o un reintento de red).
--
-- Aplicar ANTES de desplegar v12.50 en cada entorno (test local, test_pos,
-- casa matriz, Beer Garden). Sin esta tabla el endpoint responde 500 y no
-- escribe nada (la transaccion se revierte entera).

CREATE TABLE IF NOT EXISTS app_operacion_pos_control (
    id INT(11) NOT NULL AUTO_INCREMENT,
    tipo VARCHAR(30) NOT NULL,
    clave_idempotencia VARCHAR(64) NOT NULL,
    id_operacion INT(11) NOT NULL,
    id_ingreso INT(11) DEFAULT NULL,
    id_salida_inventario INT(11) DEFAULT NULL,
    id_almacen INT(11) DEFAULT NULL,
    id_barra INT(11) DEFAULT NULL,
    estado VARCHAR(20) NOT NULL,
    payload_json TEXT NOT NULL,
    resultado_json TEXT,
    usuario_reg VARCHAR(255) NOT NULL,
    fecha_reg DATETIME NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_operacion_pos_clave (clave_idempotencia),
    KEY idx_operacion_pos_operacion (id_operacion),
    KEY idx_operacion_pos_ingreso (id_ingreso)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

-- Permisos del usuario de la API (querys/seguridad_usuario_api_tuneles.sql):
-- GRANT INSERT ON adminerp.app_operacion_pos_control TO 'api_paloteo'@'localhost', 'api_paloteo'@'127.0.0.1';
