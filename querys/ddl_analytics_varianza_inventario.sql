-- Snapshot histórico de valoración de variaciones detectadas por el módulo
-- AJUSTES. Es una tabla analítica propia de la PWA: no altera ni agrega
-- restricciones a tablas legacy del POS.
--
-- Una fila representa un producto incluido en una consolidación aplicada. Los
-- importes usan el delta operativo, que es el mismo que generó movimientos
-- POS; el delta exacto se conserva únicamente como evidencia de medición.

CREATE TABLE IF NOT EXISTS analytics_varianza_inventario (
    id INT(11) NOT NULL AUTO_INCREMENT,
    id_operacion INT(11) NOT NULL,
    id_barra INT(11) NOT NULL,
    id_inventario_fisico INT(11) NOT NULL,
    id_control_ajuste INT(11) NOT NULL,
    id_producto INT(11) NOT NULL,
    id_categoria INT(11) DEFAULT NULL,
    fecha_operacion DATE DEFAULT NULL,
    fecha_aplicacion DATETIME NOT NULL,
    id_almacen INT(11) NOT NULL,
    delta_paq DECIMAL(12,2) NOT NULL,
    delta_det_exacto DECIMAL(14,6) NOT NULL,
    delta_det_operativo DECIMAL(12,2) NOT NULL,
    rendimiento_por_envase DECIMAL(14,4) DEFAULT NULL,
    unidad_detalle VARCHAR(100) DEFAULT NULL,
    wac_snapshot DECIMAL(12,4) DEFAULT NULL,
    fecha_actualizacion_wac DATETIME DEFAULT NULL,
    origen_wac VARCHAR(50) NOT NULL,
    estado_valoracion VARCHAR(30) NOT NULL,
    valor_paq DECIMAL(14,4) DEFAULT NULL,
    valor_detalle_operativo DECIMAL(14,4) DEFAULT NULL,
    valor_neto DECIMAL(14,4) DEFAULT NULL,
    usuario_reg VARCHAR(255) NOT NULL,
    fecha_reg DATETIME NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_varianza_inventario_unica
        (id_operacion, id_barra, id_inventario_fisico, id_producto),
    KEY idx_varianza_fecha_barra (fecha_aplicacion, id_barra),
    KEY idx_varianza_producto_fecha (id_producto, fecha_aplicacion),
    KEY idx_varianza_categoria_fecha (id_categoria, fecha_aplicacion),
    KEY idx_varianza_control (id_control_ajuste)
) ENGINE=InnoDB DEFAULT CHARSET=latin1 COLLATE=latin1_swedish_ci;