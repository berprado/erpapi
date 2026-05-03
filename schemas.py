from pydantic import BaseModel

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