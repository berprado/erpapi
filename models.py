from database import Base
from sqlalchemy import Column, Integer, String, DateTime, Date, Numeric, Text, Boolean, text

NOMBRE_PERFIL_PESAJE_DEFAULT = "Estándar"

class Usuario(Base):
    __tablename__ = "seg_usuario"

    id = Column(Integer, primary_key=True, index=True)
    paterno = Column(String(255))
    materno = Column(String(255))
    nombres = Column(String(255))
    usuario = Column(String(255), unique=True, index=True)
    contrasena = Column(String(255))
    habilitado = Column(String(1))
    estado = Column(String(3))
    
 # Nota: SQLAlchemy permite mapear solo las columnas que vas a usar. 
 # No es obligatorio poner las 19 columnas de la tabla si no las vas a leer en la API,
 # pero estas son las esenciales para el Login.

class LoginAuditoria(Base):
    __tablename__ = "app_login_auditoria_api"

    id = Column(Integer, primary_key=True, index=True)
    usuario = Column(String(255))
    exito = Column(Integer)  # 1 = login exitoso, 0 = intento fallido
    motivo = Column(String(50))  # 'CREDENCIALES' | 'DESHABILITADO' | NULL si éxito
    ip = Column(String(255))
    fecha = Column(DateTime)


class Acceso(Base):
    __tablename__ = "seg_acceso"
    
    id = Column(Integer, primary_key=True, index=True)
    usuario = Column(String(255))
    fecha = Column(DateTime)
    ip = Column(String(255))


class Operacion(Base):
    __tablename__ = "ope_operacion"
    
    id = Column(Integer, primary_key=True, index=True)
    fecha = Column(Date)
    nombre_operacion = Column(String(255))
    estado_operacion = Column(Integer) # Aquí guardamos el 22 o el 24
    estado = Column(String(3)) # Para saber si el registro está 'HAB' (Habilitado)



# Modelo para la configuración de pesaje de productos (tabla app_producto_pesaje_config_api)

class ProductoPesajeConfig(Base):
    __tablename__ = "app_producto_pesaje_config_api"
    
    id = Column(Integer, primary_key=True, index=True)
    id_producto_almacen = Column(Integer, index=True)
    nombre_perfil = Column(String(100), nullable=False, server_default=text("'Estándar'"))
    peso_bruto = Column(Numeric(10, 2))
    tara = Column(Numeric(10, 2))
    gramos_por_oz = Column(Numeric(10, 6))
    pesable = Column(Integer) # Usamos Integer para el TINYINT(1)
    barcode = Column(String(50))
    tolerancia_oz = Column(Numeric(10, 2))
    estado = Column(String(3))

class PaloteoRegistroCrudo(Base):
    __tablename__ = "app_paloteo_registro_crudo"
    
    id = Column(Integer, primary_key=True, index=True)
    id_operacion = Column(Integer)
    id_producto = Column(Integer)
    botellas_cerradas = Column(Integer)
    pesos_abiertas = Column(Text)
    onzas_calculadas = Column(Numeric(10, 2))
    usuario_reg = Column(String(255))
    fecha_reg = Column(DateTime)
    
# Mapeamos las tablas donde vive el inventario físico para luego guardar el resultado final del paloteo (no el registro crudo, sino el resultado ya procesado y validado)
class InventarioFisicoPOS(Base):
    __tablename__ = "bar_inventario_fisico"
    
    id = Column(Integer, primary_key=True, index=True)
    fecha = Column(Date)
    observaciones = Column(String(255))
    procesado_por = Column(String(255))
    estado_registro = Column(Integer, default=1) # Usualmente 1 para nuevo
    id_barra = Column(Integer)
    id_operacion = Column(Integer)
    usuario_reg = Column(String(255))
    fecha_reg = Column(Date)
    fecha_mod = Column(Date) # Fecha de última corrección
    estado = Column(String(3), default='HAB')

class DetalleFisicoPOS(Base):
    __tablename__ = "bar_detalle_fisico"

    id = Column(Integer, primary_key=True, index=True)
    cantidad_unidad = Column(Numeric(10, 2)) # Botellas cerradas
    cantidad_detalle = Column(Numeric(10, 2)) # Onzas calculadas
    id_producto = Column(Integer)
    id_inventario_fisico = Column(Integer)
    usuario_reg = Column(String(255))
    fecha_reg = Column(Date)
    fecha_mod = Column(Date) # Fecha de última corrección
    estado = Column(String(3), default='HAB')

# Modelos del módulo de AJUSTES: cabeceras/detalles de ingreso y salida por ajuste,
# replicando el mismo flujo que usa el POS para igualar bar_inventario al físico.
# NOTA: el COMMENT real de bar_ajuste.ind_estado_ingreso dice "0: pendiente, 1: procesaro,
# 3: cancelado", pero está desactualizado: los valores reales son 16 (PENDIETE) y 20
# (PROCESADO), igual que bar_salida_inventario.ind_estado_salida (confirmado contra
# parameter_table y un trace SQL real de ejecución del POS).

class AjusteIngreso(Base):
    __tablename__ = "bar_ajuste"

    id = Column(Integer, primary_key=True, index=True)
    fecha = Column(Date)
    numero_documento = Column(String(255))
    observaciones = Column(String(255))
    recepcionado_por = Column(String(255))
    ind_estado_ingreso = Column(Integer)
    ind_tipo_movimiento = Column(Integer)
    id_operacion = Column(Integer)
    id_barra = Column(Integer)
    usuario_reg = Column(String(255))
    fecha_reg = Column(Date)
    fecha_mod = Column(Date)
    estado = Column(String(3), default='HAB')


class DetalleAjusteIngreso(Base):
    __tablename__ = "bar_detalle_ajuste"

    id = Column(Integer, primary_key=True, index=True)
    cantidad = Column(Numeric(10, 2))
    precio_costo = Column(Numeric(10, 2))
    precio_costo_real = Column(Numeric(10, 5))
    observaciones = Column(String(255))
    ind_paq_detalle = Column(String(1)) # '1': paq/display, '0': detalle/onzas
    id_ajuste = Column(Integer)
    id_producto = Column(Integer)
    usuario_reg = Column(String(255))
    fecha_reg = Column(Date)
    fecha_mod = Column(Date)
    estado = Column(String(3), default='HAB')


class AjusteSalida(Base):
    __tablename__ = "bar_salida_inventario"

    id = Column(Integer, primary_key=True, index=True)
    fecha_salida = Column(Date)
    correlativo = Column(Integer)
    responsable = Column(String(255))
    ind_estado_salida = Column(Integer)
    observaciones_salida = Column(String(255))
    fecha_recepcion = Column(Date)
    observaciones_recepcion = Column(String(255))
    responsable_recepcion = Column(String(255))
    id_almacen = Column(Integer)
    id_barra = Column(Integer)
    id_operacion = Column(Integer)
    ind_tipo_salida = Column(Integer)
    usuario_reg = Column(String(255))
    fecha_reg = Column(Date)
    fecha_mod = Column(Date)
    estado = Column(String(3), default='HAB')


class DetalleAjusteSalida(Base):
    __tablename__ = "bar_detalle_salida_inv"

    id = Column(Integer, primary_key=True, index=True)
    cantidad = Column(Numeric(10, 2))
    ind_paq_detalle = Column(String(1)) # '1': paq/display, '0': detalle/onzas
    id_salida_inventario = Column(Integer)
    id_producto = Column(Integer)
    usuario_reg = Column(String(255))
    fecha_reg = Column(Date)
    fecha_mod = Column(Date)
    estado = Column(String(3), default='HAB')


class InventarioBarra(Base):
    __tablename__ = "bar_inventario"

    id = Column(Integer, primary_key=True, index=True)
    cantidad_paq = Column(Numeric(10, 2))
    cantidad_detalle = Column(Numeric(10, 2))
    id_producto = Column(Integer)
    id_barra = Column(Integer)
    usuario_reg = Column(String(255))
    fecha_reg = Column(Date)
    fecha_mod = Column(DateTime)
    estado = Column(String(3), default='HAB')


class PaloteoAjusteControl(Base):
    __tablename__ = "app_paloteo_ajuste_control"

    id = Column(Integer, primary_key=True, index=True)
    id_operacion = Column(Integer)
    id_barra = Column(Integer)
    id_inventario_fisico = Column(Integer)
    id_ajuste = Column(Integer)
    id_salida_inventario = Column(Integer)
    estado = Column(String(20))
    payload_json = Column(Text)
    usuario_reg = Column(String(255))
    fecha_reg = Column(DateTime)
    fecha_mod = Column(DateTime)