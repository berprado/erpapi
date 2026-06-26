--
-- Set default database
--
USE adminerp_copy;

--
-- Create table `bar_salida_inventario`
--
CREATE TABLE bar_salida_inventario
  (
    id                      INT(11)      NOT NULL AUTO_INCREMENT,
    fecha_salida            DATE         NOT NULL,
    correlativo             INT(11)      DEFAULT NULL,
    responsable             VARCHAR(255) NOT NULL,
    ind_estado_salida       INT(11)      NOT NULL,
    observaciones_salida    VARCHAR(255) DEFAULT NULL,
    fecha_recepcion         DATE         DEFAULT NULL,
    observaciones_recepcion VARCHAR(255) DEFAULT NULL,
    responsable_recepcion   VARCHAR(255) DEFAULT NULL,
    id_almacen              INT(11)      DEFAULT NULL,
    id_barra                INT(11)      DEFAULT NULL,
    id_operacion            INT(11)      DEFAULT NULL,
    ind_tipo_salida         INT(11)      DEFAULT NULL,
    usuario_reg             VARCHAR(255) NOT NULL,
    fecha_reg               DATE         DEFAULT NULL,
    fecha_mod               DATE         DEFAULT NULL,
    estado                  VARCHAR(3)   NOT NULL,
    PRIMARY KEY (id)
  )
ENGINE = INNODB,
AUTO_INCREMENT = 717,
AVG_ROW_LENGTH = 171,
CHARACTER SET latin1,
COLLATE latin1_swedish_ci,
ROW_FORMAT = COMPACT;

--
-- Create index `bar_salida_inventario_ibfk_1` on table `bar_salida_inventario`
--
ALTER TABLE bar_salida_inventario
ADD INDEX bar_salida_inventario_ibfk_1 (id_operacion);

--
-- Create index `fk_bar_salida_inventario_alm_almacen1` on table `bar_salida_inventario`
--
ALTER TABLE bar_salida_inventario
ADD INDEX fk_bar_salida_inventario_alm_almacen1 (id_almacen);

--
-- Create index `fk_bar_salida_inventario_bar_barra1` on table `bar_salida_inventario`
--
ALTER TABLE bar_salida_inventario
ADD INDEX fk_bar_salida_inventario_bar_barra1 (id_barra);

--
-- Create table `bar_detalle_salida_inv`
--
CREATE TABLE bar_detalle_salida_inv
  (
    id                   INT(11)        NOT NULL AUTO_INCREMENT,
    cantidad             DECIMAL(10, 2) DEFAULT NULL,
    ind_paq_detalle      VARCHAR(1)     DEFAULT NULL,
    id_salida_inventario INT(11)        NOT NULL,
    id_producto          INT(11)        NOT NULL,
    usuario_reg          VARCHAR(255)   NOT NULL,
    fecha_reg            DATE           DEFAULT NULL,
    fecha_mod            DATE           DEFAULT NULL,
    estado               VARCHAR(3)     NOT NULL,
    PRIMARY KEY (id)
  )
ENGINE = INNODB,
AUTO_INCREMENT = 5394,
AVG_ROW_LENGTH = 66,
CHARACTER SET latin1,
COLLATE latin1_swedish_ci,
ROW_FORMAT = COMPACT;

--
-- Create index `fk_bar_detalle_salida_inv_alm_producto1` on table `bar_detalle_salida_inv`
--
ALTER TABLE bar_detalle_salida_inv
ADD INDEX fk_bar_detalle_salida_inv_alm_producto1 (id_producto);

--
-- Create index `fk_bar_detalle_salida_inv_bar_salida_inventario1` on table `bar_detalle_salida_inv`
--
ALTER TABLE bar_detalle_salida_inv
ADD INDEX fk_bar_detalle_salida_inv_bar_salida_inventario1 (id_salida_inventario);

--
-- Create table `bar_detalle_ajuste`
--
CREATE TABLE bar_detalle_ajuste
  (
    id                INT(11)        NOT NULL AUTO_INCREMENT,
    cantidad          DECIMAL(10, 2) NOT NULL,
    precio_costo      DECIMAL(10, 2) NOT NULL,
    precio_costo_real DECIMAL(10, 5) DEFAULT NULL,
    observaciones     VARCHAR(255)   DEFAULT NULL,
    ind_paq_detalle   VARCHAR(1)     DEFAULT NULL COMMENT '1: display 0:detalle',
    id_ajuste         INT(11)        NOT NULL,
    id_producto       INT(11)        NOT NULL,
    usuario_reg       VARCHAR(255)   NOT NULL,
    fecha_reg         DATE           DEFAULT NULL,
    fecha_mod         DATE           DEFAULT NULL,
    estado            VARCHAR(3)     NOT NULL,
    PRIMARY KEY (id)
  )
ENGINE = INNODB,
AUTO_INCREMENT = 4818,
AVG_ROW_LENGTH = 68,
CHARACTER SET latin1,
COLLATE latin1_swedish_ci,
ROW_FORMAT = COMPACT;

--
-- Create index `fk_bar_detalle_ajuste_alm_producto_idx` on table `bar_detalle_ajuste`
--
ALTER TABLE bar_detalle_ajuste
ADD INDEX fk_bar_detalle_ajuste_alm_producto_idx (id_producto);

--
-- Create index `fk_bar_detalle_ajuste_bar_ajuste_idx` on table `bar_detalle_ajuste`
--
ALTER TABLE bar_detalle_ajuste
ADD INDEX fk_bar_detalle_ajuste_bar_ajuste_idx (id_ajuste);

--
-- Create table `bar_ajuste`
--
CREATE TABLE bar_ajuste
  (
    id                  INT(11)      NOT NULL AUTO_INCREMENT,
    fecha               DATE         DEFAULT NULL,
    numero_documento    VARCHAR(255) DEFAULT NULL,
    observaciones       VARCHAR(255) DEFAULT NULL,
    recepcionado_por    VARCHAR(255) DEFAULT NULL,
    ind_estado_ingreso  INT(11)      NOT NULL COMMENT '0: pendiente, 1: procesaro, 3: cancelado',
    ind_tipo_movimiento INT(11)      DEFAULT NULL,
    id_operacion        INT(11)      DEFAULT NULL,
    id_barra            INT(11)      DEFAULT NULL,
    usuario_reg         VARCHAR(255) NOT NULL,
    fecha_reg           DATE         DEFAULT NULL,
    fecha_mod           DATE         DEFAULT NULL,
    estado              VARCHAR(3)   NOT NULL,
    PRIMARY KEY (id)
  )
ENGINE = INNODB,
AUTO_INCREMENT = 662,
AVG_ROW_LENGTH = 183,
CHARACTER SET latin1,
COLLATE latin1_swedish_ci,
COMMENT = 'Ajustes de inventario en el bar, incluyendo pérdidas y modificaciones de stock.',
ROW_FORMAT = COMPACT;

--
-- Create index `bar_ajuste_ibfk_1` on table `bar_ajuste`
--
ALTER TABLE bar_ajuste
ADD INDEX bar_ajuste_ibfk_1 (id_operacion);

--
-- Create index `bar_ajuste_ibfk_2` on table `bar_ajuste`
--
ALTER TABLE bar_ajuste
ADD INDEX bar_ajuste_ibfk_2 (id_barra);