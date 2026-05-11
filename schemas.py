from pydantic import BaseModel, Field, field_validator
from typing import List, Optional

# Esquema para lo que la API va a RECIBIR del cliente
class UsuarioLogin(BaseModel):
    usuario: str
    contrasena: str

# Esquema para lo que la API va a RESPONDER si el login es exitoso
class Token(BaseModel):
    access_token: str
    token_type: str
    usuario_id: int
    nombres: str

# Esquema para la respuesta de la operación
class OperacionResponse(BaseModel):
    id_operacion: int
    nombre: str
    titulo: str
    mensaje: str

# Las reglas de validación para el paloteo

class PesoAbierta(BaseModel):
    peso: float = Field(..., ge=0, description="Peso medido en gramos")
    perfil_id: Optional[int] = Field(None, gt=0, description="ID del perfil de botella seleccionado")
    perfil_index: Optional[int] = Field(None, ge=0, description="Indice de respaldo del perfil de botella")

class PaloteoItem(BaseModel):
    id_producto: int = Field(..., gt=0, description="ID del producto de almacén")
    botellas_cerradas: int = Field(..., ge=0, description="Cantidad de botellas enteras (No puede ser negativo)")
    # Cada registro abierta incluye el peso y el perfil seleccionado.
    pesos_abiertas: List[PesoAbierta] = Field(default_factory=list, description="Pesos de abiertas con el perfil de botella usado")

    @field_validator('pesos_abiertas')
    def validar_pesos_positivos(cls, pesos_abiertas):
        """Asegura que ningún peso individual dentro del array sea negativo"""
        for entrada in pesos_abiertas:
            if entrada.peso < 0:
                raise ValueError("Ningún peso puede ser negativo.")
        return pesos_abiertas

class PaloteoRequest(BaseModel):
    id_operacion: int = Field(..., gt=0)
    id_barra: int = Field(..., gt=0, description="ID de la barra donde se hace el físico")
    observaciones: Optional[str] = Field(None, description="Nota opcional del bartender") # NUEVO
    items: List[PaloteoItem] = Field(..., min_length=1)

class PerfilPesaje(BaseModel):
    id: Optional[int] = None
    nombre_perfil: str
    peso_bruto: float
    tara: float
    gramos_por_oz: float
    tolerancia_oz: float

class CrearPerfilPesajeRequest(BaseModel):
    id_producto: int = Field(..., gt=0)
    nombre_perfil: str = Field(..., min_length=2, max_length=100)
    peso_bruto: float = Field(..., gt=0)
    tara: float = Field(..., ge=0)
    gramos_por_oz: float = Field(..., gt=0)
    tolerancia_oz: float = Field(0, ge=0)
    
class ProductoPendiente(BaseModel):
    id_producto: int
    codigo: str
    nombre: str
    categoria_nombre: Optional[str] = None
    ind_permite_comandar: int
    stock_ideal_unidades: float
    stock_ideal_onzas: float
    pesable: Optional[int] = None
    perfiles: List[PerfilPesaje] = Field(default_factory=list)
    onzas_por_botella_llena: float


class InventarioDetalleRegistrado(BaseModel):
    id_producto: int
    botellas_cerradas: float
    onzas_pos: float


class InventarioRegistradoResponse(BaseModel):
    id_inventario_pos: int
    id_operacion: int
    id_barra: int
    observaciones: Optional[str] = None
    puede_editar: bool
    detalles: List[InventarioDetalleRegistrado]


class PaloteoOperacionResponse(BaseModel):
    status: str
    id_inventario_pos: int
    mensaje: str
    detalles: List[dict]
    productos_omitidos: List[int]