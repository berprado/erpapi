from sqlalchemy import Column, Integer, String, DateTime, Date
from database import Base

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

    