-- Auditoría de intentos de login de la PWA (exitosos y fallidos).
-- Soporta el freno de fuerza bruta de /api/auth/login (429).
-- Ejecutar UNA VEZ por entorno (test / producción); la API no crea tablas sola.
CREATE TABLE IF NOT EXISTS app_login_auditoria_api (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    usuario VARCHAR(255) NOT NULL,
    exito TINYINT(1) NOT NULL,
    motivo VARCHAR(50) NULL COMMENT 'CREDENCIALES | DESHABILITADO | NULL si exito',
    ip VARCHAR(255) NULL,
    fecha DATETIME NOT NULL COMMENT 'UTC, igual que seg_acceso via API',
    PRIMARY KEY (id),
    KEY idx_login_aud_usuario_fecha (usuario, fecha),
    KEY idx_login_aud_ip_fecha (ip, fecha)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Auditoria de login PWA BackStage API';
