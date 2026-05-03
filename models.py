from database import Base
from sqlalchemy import Column, Integer, String, DateTime, Date, Numeric, Text, Boolean
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



# Modelo para la configuración de pesaje de productos (tabla app_producto_pesaje_config)

class ProductoPesajeConfig(Base):
    __tablename__ = "app_producto_pesaje_config"
    
    id = Column(Integer, primary_key=True, index=True)
    id_producto_almacen = Column(Integer, unique=True, index=True)
    peso_bruto = Column(Numeric(10, 2))
    tara = Column(Numeric(10, 2))
    gramos_por_oz = Column(Numeric(10, 6))
    pesable = Column(Integer) # Usamos Integer para el TINYINT(1)
    tolerancia_oz = Column(Numeric(10, 2))

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
    estado = Column(String(3), default='HAB')