from pydantic import BaseModel, Field, field_validator
from typing import List

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
    mensaje: str

# Las reglas de validación para el paloteo

class PaloteoItem(BaseModel):
    id_producto: int = Field(..., gt=0, description="ID del producto de almacén")
    botellas_cerradas: int = Field(..., ge=0, description="Cantidad de botellas enteras (No puede ser negativo)")
    # Usamos List[float] para recibir el array. Si no hay, recibe una lista vacía []
    pesos_abiertas: List[float] = Field(default_factory=list, description="Pesos individuales de las botellas abiertas")

    @field_validator('pesos_abiertas')
    def validar_pesos_positivos(cls, pesos):
        """Asegura que ningún peso individual dentro del array sea negativo"""
        for peso in pesos:
            if peso < 0:
                raise ValueError("Ningún peso puede ser negativo.")
        return pesos

class PaloteoRequest(BaseModel):
    id_operacion: int = Field(..., gt=0)
    items: List[PaloteoItem] = Field(..., min_length=1, description="Debe enviar al menos un producto")

# en que barra se está haciendo el paloteo, para validaciones futuras de seguridad (no es un campo obligatorio para el proceso actual, pero lo dejamos preparado)
class PaloteoRequest(BaseModel):
    id_operacion: int = Field(..., gt=0)
    id_barra: int = Field(..., gt=0, description="ID de la barra donde se hace el físico")
    items: List[PaloteoItem] = Field(..., min_length=1)