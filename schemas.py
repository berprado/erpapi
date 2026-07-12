from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Literal
from datetime import datetime

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
    is_admin: bool = False

# Esquema para la respuesta de la operación
class OperacionResponse(BaseModel):
    id_operacion: int
    nombre: str
    titulo: str
    mensaje: str
    estado_operacion: Optional[int] = None

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

    @field_validator('items')
    def validar_items_unicos(cls, items):
        ids = [item.id_producto for item in items]
        if len(ids) != len(set(ids)):
            raise ValueError("No se permiten productos duplicados en items.")
        return items

class PerfilPesaje(BaseModel):
    id: Optional[int] = None
    nombre_perfil: str
    peso_bruto: float
    tara: float
    gramos_por_oz: float
    tolerancia_oz: float
    barcode: Optional[str] = None

class CrearPerfilPesajeRequest(BaseModel):
    id_producto: int = Field(..., gt=0)
    nombre_perfil: str = Field(..., min_length=2, max_length=100)
    peso_bruto: float = Field(..., gt=0)
    tara: float = Field(..., ge=0)
    barcode: Optional[str] = Field(None, max_length=50)
    
class PesajeConfigItem(BaseModel):
    id: int
    id_producto: int
    nombre_producto: str
    codigo_producto: str
    id_categoria: Optional[int] = None
    nombre_categoria: Optional[str] = None
    volumen_oz: Optional[float] = None
    peso_bruto: Optional[float] = None
    tara: Optional[float] = None
    gramos_por_oz: Optional[float] = None
    pesable: int
    barcode: Optional[str] = None
    nombre_perfil: str
    medida: Optional[float] = None
    nombre_unidad_medida: Optional[str] = None
    nombre_unidad_medida_detalle: Optional[str] = None
    nombre_ind_permite_comandar: Optional[str] = None

class ActualizarPesajeConfigRequest(BaseModel):
    peso_bruto: Optional[float] = Field(None, gt=0)
    tara: Optional[float] = Field(None, ge=0)
    barcode: Optional[str] = Field(None, max_length=50)

class CategoriaItem(BaseModel):
    id_categoria: int
    nombre_categoria: str

class ProductoPendiente(BaseModel):
    id_producto: int
    id_categoria: Optional[int] = None
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
    pesos_abiertas: List[PesoAbierta] = Field(default_factory=list)


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


class EliminarProductoPaloteoResponse(BaseModel):
    status: Literal['success']
    id_inventario_pos: int
    id_producto: int
    existia: bool
    mensaje: str


class FilaDiferenciaPdf(BaseModel):
    idProducto: str
    codigo: str
    nombre: str
    paqPos: Optional[float] = None
    paqBar: Optional[float] = None
    detPos: Optional[float] = None
    detBar: Optional[float] = None
    difUnidades: Optional[float] = None
    difOnzas: Optional[float] = None
    difOnzasExactas: Optional[float] = None
    difOnzasPos: Optional[float] = None

class ExportarPdfRequest(BaseModel):
    id_operacion: int = Field(..., gt=0)
    id_barra: int = Field(..., gt=0)
    usuario: str
    tipo_reporte: Literal['general', 'ingreso', 'salida'] = 'general'
    filas: List[FilaDiferenciaPdf] = Field(..., min_length=1)


class ConsolidarAjustesRequest(BaseModel):
    id_operacion: int = Field(..., gt=0, description="ID de la operativa a consolidar")
    id_barra: int = Field(..., gt=0, description="ID de la barra asociada")
    observaciones: Optional[str] = Field(None, description="Observaciones opcionales")


class AjusteMovimientoPreview(BaseModel):
    id_producto: int
    cantidad: float
    ind_paq_detalle: Literal['0', '1']


class AjusteDeltaPreview(BaseModel):
    id_producto: int
    id_categoria: Optional[int] = None
    pesable: int
    tolerancia_oz: float
    delta_paq: float
    delta_det_exacto: float
    delta_det_operativo: float


class ConsolidarAjustesPreviewResponse(BaseModel):
    status: Literal['ok', 'skipped']
    id_operacion: int
    id_barra: int
    id_inventario_pos: int
    observaciones: Optional[str] = None
    ya_aplicado: bool = False
    aplicado_por: Optional[str] = None
    aplicado_en: Optional[datetime] = None
    resumen: dict
    sobrantes_paq: List[AjusteMovimientoPreview] = Field(default_factory=list)
    sobrantes_det: List[AjusteMovimientoPreview] = Field(default_factory=list)
    faltantes_paq: List[AjusteMovimientoPreview] = Field(default_factory=list)
    faltantes_det: List[AjusteMovimientoPreview] = Field(default_factory=list)
    deltas: List[AjusteDeltaPreview] = Field(default_factory=list)


class AplicarAjustesRequest(BaseModel):
    id_operacion: int = Field(..., gt=0)
    id_barra: int = Field(..., gt=0)
    observaciones: Optional[str] = None


class AplicarAjustesResponse(BaseModel):
    status: Literal['success', 'skipped']
    id_operacion: int
    id_barra: int
    id_inventario_pos: int
    id_ajuste: Optional[int] = None
    id_salida_inventario: Optional[int] = None
    productos_afectados: int
    igualacion_verificada: bool
    mensaje: str