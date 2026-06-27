from sqlalchemy.orm import Session
from sqlalchemy import text, bindparam, func
from sqlalchemy.exc import IntegrityError
from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.responses import FileResponse, JSONResponse, Response
import hashlib
import json
from database import get_db
import models
import schemas
from typing import List, Optional
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from datetime import datetime, timedelta, timezone
import logging
from decimal import Decimal, ROUND_HALF_UP

logger = logging.getLogger(__name__)
from config import settings
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="API Inventario POS",
    description="Backend para control de pesaje y auditoría de barra",
    version="1.0.0"
)

# Habilita preflight OPTIONS y cabeceras CORS para clientes web (PWA/frontend).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuración de Seguridad
security = HTTPBearer()
SECRET_KEY = settings.SECRET_KEY  # Cargado desde .env


def _redondear_media_onza_half_up(valor: float) -> float:
    """Redondea a múltiplos de 0.5 usando HALF_UP para alinear backend y frontend."""
    redondeado = (Decimal(str(valor)) * Decimal("2")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return float(redondeado / Decimal("2"))


def _obtener_pesos_crudos_por_producto(db: Session, id_operacion: int) -> dict[int, list]:
    """Recupera la última captura cruda por producto para restaurar gramos reales en corrección."""
    registros = db.query(models.PaloteoRegistroCrudo).filter(
        models.PaloteoRegistroCrudo.id_operacion == id_operacion
    ).order_by(models.PaloteoRegistroCrudo.id.desc()).all()

    pesos_por_producto = {}
    for registro in registros:
        if registro.id_producto in pesos_por_producto:
            continue

        try:
            pesos = json.loads(registro.pesos_abiertas) if registro.pesos_abiertas else []
        except (TypeError, json.JSONDecodeError):
            pesos = []

        pesos_por_producto[registro.id_producto] = pesos if isinstance(pesos, list) else []

    return pesos_por_producto


def _obtener_tolerancia_operativa_oz(pesable: int | None, id_categoria: int | None) -> float:
    """Define la banda muerta operativa por producto pesable según su categoría."""
    if int(pesable or 0) != 1:
        return 0.0

    if int(id_categoria or 0) in {6, 22}:
        return 0.5

    return 0.25


def _cuantizar_delta_onzas_operativo(delta_exacto: float, tolerancia_oz: float) -> float:
    """Aplica banda muerta y cuantiza el delta en pasos de 0.5 oz."""
    if abs(delta_exacto) < tolerancia_oz:
        return 0.0
    return _redondear_media_onza_half_up(delta_exacto)


ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 600 # 10 horas de vigencia para cubrir toda la noche

# Función para extraer y validar el usuario real del token
def get_usuario_actual(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    token = credentials.credentials
    try:
        # Intentamos decodificar el token
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Token inválido")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="El token ha expirado. Inicie sesión nuevamente.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido o corrupto")

    # Verificamos que el usuario aún exista y esté habilitado en la BD
    usuario = db.query(models.Usuario).filter(models.Usuario.usuario == username).first()
    if usuario is None or usuario.estado != 'HAB' or usuario.habilitado != '1':
        raise HTTPException(status_code=401, detail="Usuario no encontrado o inactivo")
    
    return usuario


def _es_usuario_administrador(db: Session, id_usuario: int) -> bool:
    resultado = db.execute(
        text("""
            SELECT 1 FROM seg_permiso sp
            INNER JOIN seg_rol r ON r.id = sp.id_rol
            WHERE sp.id_usuario = :id_usuario
              AND sp.estado = 'HAB'
              AND r.estado = 'HAB'
              AND r.codigo = 'ROLE_ADMIN'
            LIMIT 1
        """),
        {"id_usuario": id_usuario}
    ).scalar()
    return resultado is not None


def get_usuario_administrador(
    current_user: models.Usuario = Depends(get_usuario_actual),
    db: Session = Depends(get_db)
):
    if not _es_usuario_administrador(db, current_user.id):
        raise HTTPException(status_code=403, detail="Acceso restringido a administradores.")
    return current_user

# --- FUNCIÓN DE ENCRIPTACIÓN ---
def hash_password(password: str) -> str:
    """Aplica SHA-256 puro para coincidir con el POS actual."""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def _validar_operacion_inicio_cierre(db: Session, id_operacion: int) -> models.Operacion:
    operacion = db.query(models.Operacion).filter(models.Operacion.id == id_operacion).first()
    if not operacion or operacion.estado_operacion != 24:
        raise HTTPException(status_code=400, detail="Operación inválida o barra no está en INICIO CIERRE.")
    return operacion


def _validar_operacion_cerrada(db: Session, id_operacion: int) -> models.Operacion:
    operacion = db.query(models.Operacion).filter(models.Operacion.id == id_operacion).first()
    if not operacion or operacion.estado_operacion != 23:
        raise HTTPException(status_code=400, detail="La consolidación de ajustes requiere operación en CERRADO (23).")
    return operacion


def _resolver_barra_operativa(request: Request) -> int:
    barra_por_defecto = settings.PALOTEO_DEFAULT_BARRA_ID
    barras_permitidas = settings.paloteo_allowed_barras

    if not settings.PALOTEO_SELECTOR_ENABLED:
        return barra_por_defecto

    barra_header = request.headers.get("X-Barra-Id")
    if not barra_header:
        return barra_por_defecto

    try:
        barra = int(barra_header)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="X-Barra-Id inválido.") from exc

    if barra not in barras_permitidas:
        raise HTTPException(status_code=400, detail="La barra solicitada no está habilitada para esta instancia.")

    return barra


def _obtener_onzas_por_botella_llena(db: Session, id_producto: int):
    resultado = db.execute(
        text("SELECT cantidad_detalle FROM alm_producto WHERE id = :id_producto LIMIT 1"),
        {"id_producto": id_producto}
    ).scalar()
    if resultado is None:
        return None
    return float(resultado)


def _procesar_items_paloteo(
    db: Session,
    payload: schemas.PaloteoRequest,
    id_inventario_pos: int,
    username_actual: str,
    fecha_actual: datetime,
    es_correccion: bool = False,
):
    resultados_procesados = []
    productos_omitidos = []
    productos_corregidos = []
    margen_error_balanza = 10.0
    onzas_max_por_producto = {}

    # En modo corrección, usamos actualización selectiva por producto para
    # conservar fecha_mod en los ítems no modificados.
    detalles_existentes_por_producto = {}
    if es_correccion:
        detalles_existentes = db.query(models.DetalleFisicoPOS).filter(
            models.DetalleFisicoPOS.id_inventario_fisico == id_inventario_pos,
            models.DetalleFisicoPOS.estado == 'HAB'
        ).all()
        detalles_existentes_por_producto = {
            detalle.id_producto: detalle for detalle in detalles_existentes
        }

    for item in payload.items:
        if item.id_producto not in onzas_max_por_producto:
            onzas_max_por_producto[item.id_producto] = _obtener_onzas_por_botella_llena(db, item.id_producto)

        onzas_max_producto = onzas_max_por_producto[item.id_producto]

        configs_producto = db.query(models.ProductoPesajeConfig).filter(
            models.ProductoPesajeConfig.id_producto_almacen == item.id_producto,
            models.ProductoPesajeConfig.estado == 'HAB'
        ).all()

        # Registrar productos sin configuración en la lista de omitidos.
        if not configs_producto:
            logger.warning("Producto id=%s omitido: sin configuración de pesaje en app_producto_pesaje_config_api", item.id_producto)
            productos_omitidos.append(item.id_producto)
            continue

        config_base = configs_producto[0]
        perfiles = sorted([cfg for cfg in configs_producto if cfg.pesable == 1], key=lambda cfg: cfg.id or 0)

        total_onzas = 0.0
        if config_base.pesable == 1 and perfiles:
            for abierta in item.pesos_abiertas:
                perfil = None

                if abierta.perfil_id is not None:
                    perfil = next((pf for pf in perfiles if pf.id == abierta.perfil_id), None)

                if perfil is None and abierta.perfil_index is not None:
                    perfil_index = abierta.perfil_index
                    if 0 <= perfil_index < len(perfiles):
                        perfil = perfiles[perfil_index]

                if perfil is None:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Perfil de botella inválido para producto {item.id_producto}."
                    )

                if any(
                    valor is None
                    for valor in (perfil.gramos_por_oz, perfil.tara, perfil.peso_bruto)
                ):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            f"Perfil de botella incompleto para producto {item.id_producto}. "
                            "Completa la configuración de pesaje antes de registrar el paloteo."
                        )
                    )

                gr_oz = float(perfil.gramos_por_oz)
                tara = float(perfil.tara)
                peso_bruto = float(perfil.peso_bruto)
                peso_medido = float(abierta.peso)

                if peso_bruto > 0 and peso_medido > peso_bruto:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            f"Peso inválido para producto {item.id_producto}. "
                            f"El peso medido ({peso_medido:.2f} g) supera el peso bruto del perfil "
                            f"({peso_bruto:.2f} g)."
                        )
                    )

                if peso_medido >= (tara - margen_error_balanza):
                    peso_liquido = max(0, peso_medido - tara)
                    onzas_abierta = (peso_liquido / gr_oz)

                    if onzas_max_producto is not None and onzas_max_producto > 0 and onzas_abierta > onzas_max_producto:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=(
                                f"Capacidad excedida para producto {item.id_producto}. "
                                f"La captura ({onzas_abierta:.2f} oz) supera la capacidad máxima "
                                f"({onzas_max_producto:.2f} oz)."
                            )
                        )

                    total_onzas += onzas_abierta

        onzas_redondeadas_pos = _redondear_media_onza_half_up(total_onzas)

        if es_correccion and item.id_producto in detalles_existentes_por_producto:
            detalle_existente = detalles_existentes_por_producto[item.id_producto]
            cantidad_unidad_actual = float(detalle_existente.cantidad_unidad or 0)
            cantidad_detalle_actual = float(detalle_existente.cantidad_detalle or 0)

            hubo_cambio = (
                cantidad_unidad_actual != float(item.botellas_cerradas)
                or cantidad_detalle_actual != float(onzas_redondeadas_pos)
            )

            if hubo_cambio:
                detalle_existente.cantidad_unidad = item.botellas_cerradas
                detalle_existente.cantidad_detalle = onzas_redondeadas_pos
                detalle_existente.usuario_reg = username_actual
                detalle_existente.fecha_mod = fecha_actual.date()
                productos_corregidos.append(item.id_producto)
        else:
            nuevo_detalle_pos = models.DetalleFisicoPOS(
                cantidad_unidad=item.botellas_cerradas,
                cantidad_detalle=onzas_redondeadas_pos,
                id_producto=item.id_producto,
                id_inventario_fisico=id_inventario_pos,
                usuario_reg=username_actual,
                fecha_reg=fecha_actual.date(),
                fecha_mod=fecha_actual.date() if es_correccion else None,
                estado='HAB'
            )
            db.add(nuevo_detalle_pos)
            if es_correccion:
                productos_corregidos.append(item.id_producto)

        registro_crudo = models.PaloteoRegistroCrudo(
            id_operacion=payload.id_operacion,
            id_producto=item.id_producto,
            botellas_cerradas=item.botellas_cerradas,
            pesos_abiertas=json.dumps([entrada.model_dump() for entrada in item.pesos_abiertas]),
            onzas_calculadas=total_onzas,
            usuario_reg=username_actual,
            fecha_reg=fecha_actual
        )
        db.add(registro_crudo)

        resultados_procesados.append({
            "id_producto": item.id_producto,
            "onzas_exactas": round(total_onzas, 2),
            "onzas_pos": onzas_redondeadas_pos
        })

    return resultados_procesados, productos_omitidos, productos_corregidos

# --- ENDPOINTS ---
@app.get("/api")
def read_root():
    return {"mensaje": "API del Sistema POS en línea y funcionando"}

@app.get("/api/health")
def health_check(db: Session = Depends(get_db)):
    """Endpoint para verificar la conexión a la base de datos MySQL."""
    try:
        resultado = db.execute(text("SELECT VERSION()")).scalar()
        return {
            "status": "ok",
            "database": "conectada",
            "mysql_version": resultado
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error de conexión a la BD: {str(e)}")


@app.get("/api/config/public")
def obtener_configuracion_publica():
    return {
        "app_env": settings.APP_ENV,
        "paloteo": {
            "default_barra_id": settings.PALOTEO_DEFAULT_BARRA_ID,
            "selector_enabled": settings.PALOTEO_SELECTOR_ENABLED,
            "allowed_barras": settings.paloteo_allowed_barras,
        },
    }

@app.post("/api/auth/login", response_model=schemas.Token)
def login(login_data: schemas.UsuarioLogin, request: Request, db: Session = Depends(get_db)):
    # 1. Buscar al usuario en la base de datos
    usuario_db = db.query(models.Usuario).filter(models.Usuario.usuario == login_data.usuario).first()
    
    if not usuario_db:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Usuario o contraseña incorrectos"
        )
        
    # 2. Validar que el usuario esté activo y habilitado
    if usuario_db.estado != 'HAB' or usuario_db.habilitado != '1':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="El usuario no está activo o habilitado en el sistema"
        )

    # 3. Verificar contraseña comparando los Hashes SHA-256
    hash_calculado = hash_password(login_data.contrasena)
    if usuario_db.contrasena != hash_calculado:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Usuario o contraseña incorrectos"
        )

    # 4. Registrar el acceso en la tabla de auditoría (seg_acceso)
    client_ip = request.client.host
    nuevo_acceso = models.Acceso(
        usuario=usuario_db.usuario, 
        fecha=datetime.now(timezone.utc), 
        ip=client_ip
    )
    db.add(nuevo_acceso)
    db.commit()

    # 5. Generar y devolver el Token Real (JWT)
    expiracion = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    token_payload = {
        "sub": usuario_db.usuario, # Subject (El usuario)
        "id": usuario_db.id,
        "exp": expiracion # Fecha de caducidad
    }
    
    token_real = jwt.encode(token_payload, SECRET_KEY, algorithm=ALGORITHM)
    
    return {
        "access_token": token_real,
        "token_type": "Bearer",
        "usuario_id": usuario_db.id,
        "nombres": f"{usuario_db.paterno} {usuario_db.materno}, {usuario_db.nombres}",
        "is_admin": _es_usuario_administrador(db, usuario_db.id)
    }
    
@app.get("/api/operacion/activa", response_model=schemas.OperacionResponse)
def verificar_operacion_activa(
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_usuario_actual)
):
    """
    Verifica si la operación actual está en estado de 'INICIO CIERRE' (24)
    para permitir el inventario físico.
    """
    # 1. Buscamos la última operación activa ('HAB') ordenando por ID descendente
    operacion_actual = db.query(models.Operacion).filter(
        models.Operacion.estado == 'HAB'
    ).order_by(models.Operacion.id.desc()).first()

    # Si no hay operaciones en la tabla
    if not operacion_actual:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="No se encontró ninguna operación activa en el sistema."
        )

    # 2. Evaluamos la regla de negocio según el estado_operacion
    if operacion_actual.estado_operacion == 22:
        # Estado: EN PROCESO (vendiendo)
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "detail": {
                    "id_operacion": operacion_actual.id,
                    "estado_operacion": operacion_actual.estado_operacion,
                    "icon": "block",
                    "titulo": f"OPERATIVA {operacion_actual.id}: EN PROCESO",
                    "mensaje": "Inicia el cierre de la operativa para realizar el paloteo.",
                    "status_class": "status-warning-icon"
                }
            }
        )

    # 3. Estado CERRADO: Paloteo ya realizado
    if operacion_actual.estado_operacion == 23:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "detail": {
                    "id_operacion": operacion_actual.id,
                    "estado_operacion": operacion_actual.estado_operacion,
                    "icon": "lock",
                    "titulo": f"OPERATIVA {operacion_actual.id}: CERRADA",
                    "mensaje": "El paloteo de esta operativa ya fue realizado.",
                    "status_class": "status-info-icon"
                }
            }
        )

    # 4. Luz Verde: Estado INICIO CIERRE (24)
    if operacion_actual.estado_operacion == 24:
        return {
            "id_operacion": operacion_actual.id,
            "nombre": operacion_actual.nombre_operacion,
            "estado_operacion": operacion_actual.estado_operacion,
            "icon": "check_circle",
            "titulo": f"OPERATIVA {operacion_actual.id}: INICIO DE CIERRE",
            "mensaje": "Puedes realizar el paloteo de esta operativa.",
            "status_class": "success-check-icon"
        }

    # 5. Si tiene otro estado distinto
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "detail": {
                "id_operacion": operacion_actual.id,
                "estado_operacion": operacion_actual.estado_operacion,
                "icon": "warning",
                "titulo": f"OPERATIVA {operacion_actual.id}: ESTADO NO VÁLIDO",
                "mensaje": f"La operación no está en un estado válido para paloteo (Estado: {operacion_actual.estado_operacion}).",
                "status_class": "status-warning-icon"
            }
        }
    )
    
@app.post("/api/inventario/paloteo", response_model=schemas.PaloteoOperacionResponse)
def procesar_paloteo(
    payload: schemas.PaloteoRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_usuario_actual) # <-- CANDADO AQUÍ
):
    # Extraemos los datos del usuario autenticado directamente del token validado
    username_actual = current_user.usuario
    nombre_formateado = f"{current_user.paterno} {current_user.materno}, {current_user.nombres}".upper()
    fecha_actual = datetime.now(timezone.utc)

    # --- NUEVO: Lógica de Observaciones ---
    obs_final = payload.observaciones if payload.observaciones else "REGISTRADO VÍA API"

    # 1. Validar Operación
    _validar_operacion_inicio_cierre(db, payload.id_operacion)

    barra_operativa = _resolver_barra_operativa(request)
    if payload.id_barra != barra_operativa:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"La barra enviada ({payload.id_barra}) no coincide con la barra operativa configurada ({barra_operativa})."
        )

    # Fix #5: Prevenir inventario duplicado por operación.
    # Si ya existe una cabecera HAB para este id_operacion, rechazamos el registro.
    inventario_existente = db.query(models.InventarioFisicoPOS).filter(
        models.InventarioFisicoPOS.id_operacion == payload.id_operacion,
        models.InventarioFisicoPOS.estado == 'HAB'
    ).first()
    if inventario_existente:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un inventario registrado para esta operación (ID: {inventario_existente.id}). No se puede registrar dos veces."
        )

    # 2. CREAR CABECERA EN EL POS (Con estado 62 y nombre formateado)
    nueva_cabecera_pos = models.InventarioFisicoPOS(
        fecha=fecha_actual.date(),
        observaciones=obs_final,
        procesado_por=nombre_formateado,
        estado_registro=62, # NUEVO ESTADO PENDIENTE
        id_barra=payload.id_barra,
        id_operacion=payload.id_operacion,
        usuario_reg=username_actual,
        fecha_reg=fecha_actual.date(),
        estado='HAB'
    )
    db.add(nueva_cabecera_pos)
    db.flush()

    resultados_procesados, productos_omitidos, _ = _procesar_items_paloteo(
        db=db,
        payload=payload,
        id_inventario_pos=nueva_cabecera_pos.id,
        username_actual=username_actual,
        fecha_actual=fecha_actual,
        es_correccion=False,
    )

    db.commit()

    return {
        "status": "success",
        "id_inventario_pos": nueva_cabecera_pos.id,
        "mensaje": f"Se registraron {len(resultados_procesados)} productos en el POS exitosamente.",
        "detalles": resultados_procesados,
        "productos_omitidos": productos_omitidos
    }


@app.get("/api/inventario/paloteo/{id_operacion}", response_model=schemas.InventarioRegistradoResponse)
def obtener_inventario_registrado(
    id_operacion: int,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_usuario_actual)
):
    inventario = db.query(models.InventarioFisicoPOS).filter(
        models.InventarioFisicoPOS.id_operacion == id_operacion,
        models.InventarioFisicoPOS.estado == 'HAB'
    ).first()

    if not inventario:
        raise HTTPException(status_code=404, detail="No existe inventario físico registrado para esta operación.")

    operacion = db.query(models.Operacion).filter(models.Operacion.id == id_operacion).first()
    puede_editar = bool(operacion and operacion.estado_operacion == 24)

    detalles_db = db.query(models.DetalleFisicoPOS).filter(
        models.DetalleFisicoPOS.id_inventario_fisico == inventario.id,
        models.DetalleFisicoPOS.estado == 'HAB'
    ).all()
    pesos_crudos_por_producto = _obtener_pesos_crudos_por_producto(db, inventario.id_operacion)

    detalles = [
        {
            "id_producto": detalle.id_producto,
            "botellas_cerradas": float(detalle.cantidad_unidad or 0),
            "onzas_pos": float(detalle.cantidad_detalle or 0),
            "pesos_abiertas": pesos_crudos_por_producto.get(detalle.id_producto, []),
        }
        for detalle in detalles_db
    ]

    return {
        "id_inventario_pos": inventario.id,
        "id_operacion": inventario.id_operacion,
        "id_barra": inventario.id_barra,
        "observaciones": inventario.observaciones,
        "puede_editar": puede_editar,
        "detalles": detalles,
    }


@app.put("/api/inventario/paloteo/{id_inventario_pos}", response_model=schemas.PaloteoOperacionResponse)
def corregir_paloteo(
    id_inventario_pos: int,
    payload: schemas.PaloteoRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_usuario_actual)
):
    username_actual = current_user.usuario
    nombre_formateado = f"{current_user.paterno} {current_user.materno}, {current_user.nombres}".upper()
    fecha_actual = datetime.now(timezone.utc)

    inventario = db.query(models.InventarioFisicoPOS).filter(
        models.InventarioFisicoPOS.id == id_inventario_pos,
        models.InventarioFisicoPOS.estado == 'HAB'
    ).first()
    if not inventario:
        raise HTTPException(status_code=404, detail="Inventario físico no encontrado o inactivo.")

    if payload.id_operacion != inventario.id_operacion:
        raise HTTPException(
            status_code=400,
            detail="El id_operacion del payload no coincide con el inventario físico a corregir."
        )

    if payload.id_barra != inventario.id_barra:
        raise HTTPException(
            status_code=400,
            detail="El id_barra del payload no coincide con el inventario físico a corregir."
        )

    # La corrección solo se permite mientras la operación siga en INICIO CIERRE (24).
    _validar_operacion_inicio_cierre(db, inventario.id_operacion)

    barra_operativa = _resolver_barra_operativa(request)
    if payload.id_barra != barra_operativa:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"La barra enviada ({payload.id_barra}) no coincide con la barra operativa configurada ({barra_operativa})."
        )

    inventario.observaciones = payload.observaciones if payload.observaciones else inventario.observaciones
    inventario.procesado_por = nombre_formateado
    inventario.usuario_reg = username_actual
    inventario.fecha_reg = fecha_actual.date()

    resultados_procesados, productos_omitidos, productos_corregidos = _procesar_items_paloteo(
        db=db,
        payload=payload,
        id_inventario_pos=inventario.id,
        username_actual=username_actual,
        fecha_actual=fecha_actual,
        es_correccion=True,
    )

    # La cabecera se marca como modificada solo si hubo al menos un detalle corregido.
    if productos_corregidos:
        inventario.fecha_mod = fecha_actual.date()

    db.commit()

    return {
        "status": "success",
        "id_inventario_pos": inventario.id,
        "mensaje": f"Inventario físico corregido. Se registraron {len(resultados_procesados)} productos en el POS.",
        "detalles": resultados_procesados,
        "productos_omitidos": productos_omitidos,
    }

@app.post("/api/pesaje/perfiles", response_model=schemas.PerfilPesaje)
def crear_perfil_pesaje(
    payload: schemas.CrearPerfilPesajeRequest,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_usuario_administrador)
):
    """Crea un nuevo modelo de botella para un producto pesable."""
    if payload.tara >= payload.peso_bruto:
        raise HTTPException(status_code=400, detail="La tara no puede ser mayor o igual al peso bruto.")

    volumen_oz = _obtener_onzas_por_botella_llena(db, payload.id_producto)
    if not volumen_oz:
        raise HTTPException(
            status_code=400,
            detail="No se pudo determinar el volumen estándar del producto."
        )

    gramos_por_oz = (payload.peso_bruto - payload.tara) / volumen_oz

    nombre_perfil = payload.nombre_perfil.strip()
    barcode = payload.barcode.strip() if payload.barcode else None
    if not barcode:
        barcode = db.execute(
            text("""
                SELECT barcode FROM app_producto_pesaje_config_api
                WHERE id_producto_almacen = :id_producto AND barcode IS NOT NULL AND estado = 'HAB'
                LIMIT 1
            """),
            {"id_producto": payload.id_producto}
        ).scalar()

    # Un perfil eliminado (DES) con el mismo nombre sigue ocupando la clave única
    # (id_producto_almacen, nombre_perfil). En vez de fallar con 409, lo reactivamos
    # con los nuevos datos en lugar de crear una fila nueva.
    perfil_des = db.query(models.ProductoPesajeConfig).filter(
        models.ProductoPesajeConfig.id_producto_almacen == payload.id_producto,
        models.ProductoPesajeConfig.nombre_perfil == nombre_perfil,
        models.ProductoPesajeConfig.estado == 'DES'
    ).first()

    try:
        if perfil_des:
            perfil_des.peso_bruto = payload.peso_bruto
            perfil_des.tara = payload.tara
            perfil_des.gramos_por_oz = gramos_por_oz
            perfil_des.barcode = barcode
            perfil_des.pesable = 1
            perfil_des.estado = 'HAB'
            perfil_des.usuario_reg = current_user.usuario
            db.commit()
            perfil_id = perfil_des.id
        else:
            insert_sql = text("""
                INSERT INTO app_producto_pesaje_config_api
                (id_producto_almacen, nombre_perfil, peso_bruto, tara, gramos_por_oz, barcode, pesable, usuario_reg)
                VALUES
                (:id_producto, :nombre_perfil, :peso_bruto, :tara, :gramos_por_oz, :barcode, 1, :usuario_reg)
            """)
            result = db.execute(insert_sql, {
                "id_producto": payload.id_producto,
                "nombre_perfil": nombre_perfil,
                "peso_bruto": payload.peso_bruto,
                "tara": payload.tara,
                "gramos_por_oz": gramos_por_oz,
                "barcode": barcode,
                "usuario_reg": current_user.usuario,
            })
            db.commit()
            perfil_id = result.lastrowid
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un perfil '{nombre_perfil}' para este producto."
        ) from exc
    except Exception as exc:
        db.rollback()
        logger.exception("Error creando perfil de pesaje para producto %s", payload.id_producto)
        raise HTTPException(status_code=500, detail="No se pudo crear el modelo de botella.") from exc

    return schemas.PerfilPesaje(
        id=perfil_id,
        nombre_perfil=nombre_perfil,
        peso_bruto=float(payload.peso_bruto),
        tara=float(payload.tara),
        gramos_por_oz=gramos_por_oz,
        tolerancia_oz=_obtener_tolerancia_operativa_oz(1, None),
        barcode=barcode,
    )


CATEGORIAS_EXCLUIDAS_PESAJE = (15, 18, 19, 20)


@app.get("/api/pesaje/categorias", response_model=List[schemas.CategoriaItem])
def listar_categorias_pesaje(
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_usuario_administrador)
):
    """Lista de categorías habilitadas, para el filtro del módulo PESAJE."""
    rows = db.execute(
        text("""
            SELECT id, nombre FROM alm_categoria
            WHERE estado = 'HAB' AND id NOT IN :excluidas
            ORDER BY nombre
        """).bindparams(bindparam("excluidas", expanding=True)),
        {"excluidas": CATEGORIAS_EXCLUIDAS_PESAJE}
    ).mappings().all()
    return [
        schemas.CategoriaItem(id_categoria=row["id"], nombre_categoria=row["nombre"])
        for row in rows
    ]


@app.get("/api/pesaje/config", response_model=List[schemas.PesajeConfigItem])
def listar_pesaje_config(
    nombre: Optional[str] = None,
    id_categoria: Optional[int] = None,
    pesable: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_usuario_administrador)
):
    """Listado de perfiles de pesaje (tabla app_producto_pesaje_config_api vía v9_pesaje_config_api), para el módulo PESAJE."""
    condiciones = ["(id_categoria IS NULL OR id_categoria NOT IN :excluidas)"]
    parametros = {"excluidas": CATEGORIAS_EXCLUIDAS_PESAJE}

    if nombre:
        condiciones.append("nombre_producto LIKE :nombre")
        parametros["nombre"] = f"%{nombre}%"
    if id_categoria is not None:
        condiciones.append("id_categoria = :id_categoria")
        parametros["id_categoria"] = id_categoria
    if pesable is not None:
        condiciones.append("pesable = :pesable")
        parametros["pesable"] = pesable

    where_sql = f"WHERE {' AND '.join(condiciones)}"

    query = text(f"""
        SELECT id_pesaje_config, id_producto, nombre_producto, codigo_producto,
               id_categoria, nombre_categoria, cantidad_detalle, peso_bruto, tara,
               gramos_por_oz, pesable, barcode, nombre_perfil
        FROM v9_pesaje_config_api
        {where_sql}
        ORDER BY nombre_producto ASC, nombre_perfil ASC
    """).bindparams(bindparam("excluidas", expanding=True))

    rows = db.execute(query, parametros).mappings().all()
    return [
        schemas.PesajeConfigItem(
            id=row["id_pesaje_config"],
            id_producto=row["id_producto"],
            nombre_producto=row["nombre_producto"],
            codigo_producto=row["codigo_producto"],
            id_categoria=row["id_categoria"],
            nombre_categoria=row["nombre_categoria"],
            volumen_oz=float(row["cantidad_detalle"]) if row["cantidad_detalle"] is not None else None,
            peso_bruto=float(row["peso_bruto"]) if row["peso_bruto"] is not None else None,
            tara=float(row["tara"]) if row["tara"] is not None else None,
            gramos_por_oz=float(row["gramos_por_oz"]) if row["gramos_por_oz"] is not None else None,
            pesable=row["pesable"],
            barcode=row["barcode"],
            nombre_perfil=row["nombre_perfil"],
        )
        for row in rows
    ]


@app.put("/api/pesaje/config/{id_pesaje_config}", response_model=schemas.PesajeConfigItem)
def actualizar_pesaje_config(
    id_pesaje_config: int,
    payload: schemas.ActualizarPesajeConfigRequest,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_usuario_administrador)
):
    """Edita peso_bruto/tara/barcode de un perfil de pesaje existente."""
    perfil = db.query(models.ProductoPesajeConfig).filter(
        models.ProductoPesajeConfig.id == id_pesaje_config,
        models.ProductoPesajeConfig.estado == 'HAB'
    ).first()
    if not perfil:
        raise HTTPException(status_code=404, detail="Perfil de pesaje no encontrado.")

    if perfil.pesable == 1:
        if payload.peso_bruto is None or payload.tara is None:
            raise HTTPException(status_code=400, detail="peso_bruto y tara son obligatorios para un producto pesable.")
        if payload.tara >= payload.peso_bruto:
            raise HTTPException(status_code=400, detail="La tara no puede ser mayor o igual al peso bruto.")

        volumen_oz = _obtener_onzas_por_botella_llena(db, perfil.id_producto_almacen)
        if not volumen_oz:
            raise HTTPException(status_code=400, detail="No se pudo determinar el volumen estándar del producto.")

        perfil.peso_bruto = payload.peso_bruto
        perfil.tara = payload.tara
        perfil.gramos_por_oz = (payload.peso_bruto - payload.tara) / volumen_oz
    else:
        if payload.peso_bruto is not None or payload.tara is not None:
            raise HTTPException(
                status_code=400,
                detail="Solo se puede editar el código de barras en productos no pesables."
            )

    if payload.barcode is not None:
        perfil.barcode = payload.barcode.strip() or None

    db.commit()

    row = db.execute(
        text("""
            SELECT id_pesaje_config, id_producto, nombre_producto, codigo_producto,
                   id_categoria, nombre_categoria, cantidad_detalle, peso_bruto, tara,
                   gramos_por_oz, pesable, barcode, nombre_perfil
            FROM v9_pesaje_config_api
            WHERE id_pesaje_config = :id
        """),
        {"id": id_pesaje_config}
    ).mappings().first()

    return schemas.PesajeConfigItem(
        id=row["id_pesaje_config"],
        id_producto=row["id_producto"],
        nombre_producto=row["nombre_producto"],
        codigo_producto=row["codigo_producto"],
        id_categoria=row["id_categoria"],
        nombre_categoria=row["nombre_categoria"],
        volumen_oz=float(row["cantidad_detalle"]) if row["cantidad_detalle"] is not None else None,
        peso_bruto=float(row["peso_bruto"]) if row["peso_bruto"] is not None else None,
        tara=float(row["tara"]) if row["tara"] is not None else None,
        gramos_por_oz=float(row["gramos_por_oz"]) if row["gramos_por_oz"] is not None else None,
        pesable=row["pesable"],
        barcode=row["barcode"],
        nombre_perfil=row["nombre_perfil"],
    )


@app.delete("/api/pesaje/config/{id_pesaje_config}")
def eliminar_pesaje_config(
    id_pesaje_config: int,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_usuario_administrador)
):
    """Elimina (soft-delete) un perfil de pesaje, siempre que el producto conserve al menos uno activo."""
    perfil = db.query(models.ProductoPesajeConfig).filter(
        models.ProductoPesajeConfig.id == id_pesaje_config,
        models.ProductoPesajeConfig.estado == 'HAB'
    ).first()
    if not perfil:
        raise HTTPException(status_code=404, detail="Perfil de pesaje no encontrado.")

    otros_activos = db.query(models.ProductoPesajeConfig).filter(
        models.ProductoPesajeConfig.id_producto_almacen == perfil.id_producto_almacen,
        models.ProductoPesajeConfig.estado == 'HAB',
        models.ProductoPesajeConfig.id != perfil.id
    ).count()

    if otros_activos == 0:
        raise HTTPException(status_code=400, detail="No se puede eliminar el último modelo del producto.")

    perfil.estado = 'DES'
    db.commit()
    return {"status": "success", "mensaje": "Modelo de pesaje eliminado."}


# OBTENEMOS LOS PRODUCTOS PARA EL PALOTEO

@app.get("/api/inventario/pendientes", response_model=List[schemas.ProductoPendiente])
def obtener_productos_pendientes(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_usuario_actual) # <-- CANDADO AQUÍ
    ):
    """
    Devuelve la lista de productos que tuvieron movimiento en la operación activa,
    junto con su stock ideal y parámetros de pesaje.
    """
    id_barra_operativa = _resolver_barra_operativa(request)

    query = text("""
        SELECT 
            a.id AS id_producto, a.codigo, a.nombre, a.ind_permite_comandar,
            i.cantidad_paq AS stock_ideal_unidades, i.cantidad_detalle AS stock_ideal_onzas,
            i.id_categoria, i.categoria_nombre,
            p.id AS perfil_id, p.pesable, p.nombre_perfil, p.peso_bruto, p.tara, p.gramos_por_oz, p.tolerancia_oz, p.barcode,
            a.cantidad_detalle AS onzas_por_botella_llena
        FROM (
            SELECT DISTINCT d.id_producto_receta AS id_producto
            FROM comandas_v9_detallada d
            INNER JOIN bar_comanda c ON d.id_comanda = c.id
            WHERE d.id_operacion = (SELECT MAX(id_operacion) FROM bar_comanda)
            AND c.estado_comanda = 26
            AND d.id_producto_receta IS NOT NULL

            UNION

            SELECT DISTINCT dsi.id_producto AS id_producto
            FROM alm_salida_inventario asi
            INNER JOIN alm_detalle_salida_inv dsi ON dsi.id_salida_inventario = asi.id
            WHERE asi.id_operacion = (SELECT MAX(id_operacion) FROM bar_comanda)
            AND asi.estado = 'HAB'
            AND dsi.estado = 'HAB'
            AND asi.id_barra = :id_barra
            AND asi.ind_tipo_movimiento = 83
            AND asi.ind_tipo_salida = 34
            AND asi.ind_estado_salida = 21
        ) mov
        INNER JOIN alm_producto a ON mov.id_producto = a.id
        INNER JOIN vista_inventario_barra_con_filtro i ON a.id = i.id_almacen 
        LEFT JOIN app_producto_pesaje_config_api p ON a.id = p.id_producto_almacen AND p.estado = 'HAB'
        ORDER BY a.nombre ASC, p.id ASC;
 
          """)

    rows = db.execute(query, {"id_barra": id_barra_operativa}).mappings().all()

    # Agrupamos perfiles de pesaje por producto porque ahora puede haber
    # múltiples modelos de botella para el mismo id_producto.
    productos_dict = {}
    for row in rows:
        prod_id = row["id_producto"]
        if prod_id not in productos_dict:
            productos_dict[prod_id] = {
                "id_producto": prod_id,
                "id_categoria": row["id_categoria"],
                "codigo": row["codigo"],
                "nombre": row["nombre"],
                "categoria_nombre": row["categoria_nombre"],
                "ind_permite_comandar": row["ind_permite_comandar"],
                "stock_ideal_unidades": row["stock_ideal_unidades"],
                "stock_ideal_onzas": row["stock_ideal_onzas"],
                "pesable": row["pesable"],
                "onzas_por_botella_llena": row["onzas_por_botella_llena"],
                "perfiles": []
            }

        if row["pesable"] == 1 and row["nombre_perfil"]:
            # Si el perfil viene incompleto desde BD, se omite para no romper
            # la serialización del endpoint con valores None en campos float.
            if any(
                row[campo] is None
                for campo in ("peso_bruto", "tara", "gramos_por_oz", "tolerancia_oz")
            ):
                logger.warning(
                    "Perfil de pesaje incompleto omitido. producto=%s perfil_id=%s",
                    prod_id,
                    row["perfil_id"],
                )
                continue

            productos_dict[prod_id]["perfiles"].append({
                "id": row["perfil_id"],
                "nombre_perfil": row["nombre_perfil"],
                "peso_bruto": float(row["peso_bruto"]),
                "tara": float(row["tara"]),
                "gramos_por_oz": float(row["gramos_por_oz"]),
                "tolerancia_oz": _obtener_tolerancia_operativa_oz(row["pesable"], row["id_categoria"]),
                "barcode": row["barcode"]
            })

    return list(productos_dict.values())


# CATALOGO PARA EL MODULO CONVERSOR (calculadora de peso -> onzas, sin estado de operativa)

@app.get("/api/conversor/productos", response_model=List[schemas.ProductoConversorItem])
def obtener_productos_conversor(
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_usuario_actual)
):
    """
    Catálogo completo de productos pesables, sin filtrar por movimiento en la
    operación activa ni por barra. Alimenta el módulo CONVERSOR, disponible
    siempre sin importar el estado de la operativa.
    """
    query = text("""
        SELECT id_pesaje_config, id_producto, nombre_producto, codigo_producto,
               id_categoria, nombre_categoria, peso_bruto, tara,
               gramos_por_oz, pesable, barcode, nombre_perfil
        FROM v9_pesaje_config_api
        WHERE pesable = 1
        AND (id_categoria IS NULL OR id_categoria NOT IN :excluidas)
        ORDER BY nombre_producto ASC, nombre_perfil ASC
    """).bindparams(bindparam("excluidas", expanding=True))

    rows = db.execute(query, {"excluidas": CATEGORIAS_EXCLUIDAS_PESAJE}).mappings().all()

    productos_dict = {}
    for row in rows:
        prod_id = row["id_producto"]
        if prod_id not in productos_dict:
            productos_dict[prod_id] = {
                "id_producto": prod_id,
                "codigo": row["codigo_producto"],
                "nombre": row["nombre_producto"],
                "id_categoria": row["id_categoria"],
                "nombre_categoria": row["nombre_categoria"],
                "perfiles": []
            }

        if any(
            row[campo] is None
            for campo in ("peso_bruto", "tara", "gramos_por_oz")
        ):
            logger.warning(
                "Perfil de pesaje incompleto omitido en conversor. producto=%s perfil_id=%s",
                prod_id,
                row["id_pesaje_config"],
            )
            continue

        productos_dict[prod_id]["perfiles"].append({
            "id": row["id_pesaje_config"],
            "nombre_perfil": row["nombre_perfil"],
            "peso_bruto": float(row["peso_bruto"]),
            "tara": float(row["tara"]),
            "gramos_por_oz": float(row["gramos_por_oz"]),
            "tolerancia_oz": _obtener_tolerancia_operativa_oz(row["pesable"], row["id_categoria"]),
            "barcode": row["barcode"]
        })

    return [p for p in productos_dict.values() if p["perfiles"]]


def _calcular_diferencias_paloteo(db: Session, id_barra: int, id_inventario_fisico: int) -> list[dict]:
    """Calcula delta_paq/delta_det por producto entre el físico (paloteo) y el ideal (POS).

    Es la fuente de verdad única usada tanto por el preview de consolidación como por
    el endpoint que aplica los ajustes definitivos, para garantizar que ambos vean
    exactamente las mismas diferencias.
    """
    query_diferencias = text("""
        SELECT
            df.id_producto,
            v.id_categoria,
            CASE
                WHEN EXISTS (
                    SELECT 1
                    FROM app_producto_pesaje_config_api p
                    WHERE p.id_producto_almacen = df.id_producto
                      AND p.pesable = 1
                ) THEN 1 ELSE 0
            END AS pesable,
            COALESCE(df.cantidad_unidad, 0) AS real_paq,
            COALESCE(df.cantidad_detalle, 0) AS real_det,
            COALESCE(v.cantidad_paq, 0) AS ideal_paq,
            COALESCE(v.cantidad_detalle, 0) AS ideal_det
        FROM bar_detalle_fisico df
        LEFT JOIN vista_inventario_barra_con_filtro v
               ON v.id_almacen = df.id_producto
              AND v.nro_barra = :id_barra
        WHERE df.id_inventario_fisico = :id_fisico
          AND df.estado = 'HAB'
          AND NOT EXISTS (
              SELECT 1
              FROM bar_inventario bi
              INNER JOIN inventario_excluido ie ON ie.id = bi.id
              WHERE bi.id_producto = df.id_producto
                AND bi.id_barra = :id_barra
                AND bi.estado = 'HAB'
          )
    """)

    filas_dif = db.execute(query_diferencias, {
        "id_fisico": id_inventario_fisico,
        "id_barra": id_barra,
    }).mappings().all()

    deltas = []
    for fila in filas_dif:
        real_paq = float(fila["real_paq"] or 0)
        real_det = float(fila["real_det"] or 0)
        delta_paq = real_paq - float(fila["ideal_paq"] or 0)
        delta_det_exacto = real_det - float(fila["ideal_det"] or 0)

        pesable = int(fila["pesable"] or 0)
        id_categoria = int(fila["id_categoria"]) if fila["id_categoria"] is not None else None
        tolerancia_oz = _obtener_tolerancia_operativa_oz(pesable, id_categoria)
        delta_det_operativo = _cuantizar_delta_onzas_operativo(delta_det_exacto, tolerancia_oz)

        deltas.append({
            "id_producto": fila["id_producto"],
            "id_categoria": id_categoria,
            "pesable": pesable,
            "tolerancia_oz": tolerancia_oz,
            "real_paq": real_paq,
            "real_det": real_det,
            "delta_paq": float(delta_paq),
            "delta_det_exacto": float(delta_det_exacto),
            "delta_det_operativo": float(delta_det_operativo),
        })

    return deltas


def _obtener_control_aplicado(db: Session, id_operacion: int, id_barra: int, id_inventario_fisico: int) -> models.PaloteoAjusteControl | None:
    return db.query(models.PaloteoAjusteControl).filter(
        models.PaloteoAjusteControl.id_operacion == id_operacion,
        models.PaloteoAjusteControl.id_barra == id_barra,
        models.PaloteoAjusteControl.id_inventario_fisico == id_inventario_fisico,
        models.PaloteoAjusteControl.estado == 'APLICADO'
    ).first()


def _validar_cardinalidad_bar_inventario(db: Session, id_barra: int, ids_producto: list[int]) -> None:
    """Exige exactamente una fila HAB en bar_inventario por producto/barra.

    bar_inventario no tiene UNIQUE(id_barra, id_producto) a nivel de BD. Se valida
    aqui mismo (compartido por preview y aplicar) para que el admin vea el problema
    de datos en el preview, en vez de descubrirlo solo al confirmar el ajuste.
    """
    if not ids_producto:
        return

    filas = db.query(
        models.InventarioBarra.id_producto,
        func.count(models.InventarioBarra.id)
    ).filter(
        models.InventarioBarra.id_barra == id_barra,
        models.InventarioBarra.id_producto.in_(ids_producto),
        models.InventarioBarra.estado == 'HAB'
    ).group_by(models.InventarioBarra.id_producto).all()

    conteo_por_producto = {id_producto: cantidad for id_producto, cantidad in filas}

    sin_registro = [p for p in ids_producto if conteo_por_producto.get(p, 0) == 0]
    duplicados = [p for p in ids_producto if conteo_por_producto.get(p, 0) > 1]

    if sin_registro or duplicados:
        partes = []
        if sin_registro:
            partes.append(f"sin registro en bar_inventario: {sin_registro}")
        if duplicados:
            partes.append(f"con filas HAB duplicadas en bar_inventario: {duplicados}")
        raise HTTPException(
            status_code=500,
            detail=f"Estado de datos inconsistente en bar_inventario para barra {id_barra} — productos " + "; ".join(partes) + "."
        )


def _resolver_inventario_fisico(db: Session, request: Request, id_operacion: int, id_barra: int) -> models.InventarioFisicoPOS:
    """Valida que id_barra coincida con la barra operativa y devuelve la cabecera HAB
    de InventarioFisicoPOS para operacion/barra, o lanza 400/404. Compartido por preview
    y aplicar para que ambos vean exactamente la misma validacion.
    """
    barra_operativa = _resolver_barra_operativa(request)
    if id_barra != barra_operativa:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"La barra enviada ({id_barra}) no coincide con la barra operativa configurada ({barra_operativa})."
        )

    inv_fisico_cabecera = db.query(models.InventarioFisicoPOS).filter(
        models.InventarioFisicoPOS.id_operacion == id_operacion,
        models.InventarioFisicoPOS.id_barra == id_barra,
        models.InventarioFisicoPOS.estado == 'HAB'
    ).first()

    if not inv_fisico_cabecera:
        raise HTTPException(
            status_code=404,
            detail="No se encontró inventario físico registrado para la operativa/barra solicitadas."
        )

    return inv_fisico_cabecera


@app.post("/api/inventario/consolidar/preview", response_model=schemas.ConsolidarAjustesPreviewResponse)
def previsualizar_consolidacion_ajustes(
    payload: schemas.ConsolidarAjustesRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_usuario_actual)
):
    _validar_operacion_cerrada(db, payload.id_operacion)

    inv_fisico_cabecera = _resolver_inventario_fisico(db, request, payload.id_operacion, payload.id_barra)

    control_aplicado = _obtener_control_aplicado(db, payload.id_operacion, payload.id_barra, inv_fisico_cabecera.id)
    info_control = {
        "ya_aplicado": control_aplicado is not None,
        "aplicado_por": control_aplicado.usuario_reg if control_aplicado else None,
        "aplicado_en": control_aplicado.fecha_reg if control_aplicado else None,
    }

    deltas = _calcular_diferencias_paloteo(db, payload.id_barra, inv_fisico_cabecera.id)

    ids_con_diferencia = [d["id_producto"] for d in deltas if abs(d["delta_paq"]) > 0 or abs(d["delta_det_operativo"]) > 0]
    _validar_cardinalidad_bar_inventario(db, payload.id_barra, ids_con_diferencia)

    if not deltas:
        return {
            "status": "skipped",
            "id_operacion": payload.id_operacion,
            "id_barra": payload.id_barra,
            "id_inventario_pos": inv_fisico_cabecera.id,
            "observaciones": payload.observaciones,
            **info_control,
            "resumen": {
                "productos_evaluados": 0,
                "productos_con_diferencia": 0,
                "movimientos_generados": 0,
            },
            "sobrantes_paq": [],
            "sobrantes_det": [],
            "faltantes_paq": [],
            "faltantes_det": [],
            "deltas": [],
        }

    sobrantes_paq = []
    sobrantes_det = []
    faltantes_paq = []
    faltantes_det = []

    for d in deltas:
        if d["delta_paq"] > 0:
            sobrantes_paq.append({
                "id_producto": d["id_producto"],
                "cantidad": d["delta_paq"],
                "ind_paq_detalle": '1',
            })
        elif d["delta_paq"] < 0:
            faltantes_paq.append({
                "id_producto": d["id_producto"],
                "cantidad": abs(d["delta_paq"]),
                "ind_paq_detalle": '1',
            })

        if d["delta_det_operativo"] > 0:
            sobrantes_det.append({
                "id_producto": d["id_producto"],
                "cantidad": d["delta_det_operativo"],
                "ind_paq_detalle": '0',
            })
        elif d["delta_det_operativo"] < 0:
            faltantes_det.append({
                "id_producto": d["id_producto"],
                "cantidad": abs(d["delta_det_operativo"]),
                "ind_paq_detalle": '0',
            })

    movimientos_generados = len(sobrantes_paq) + len(sobrantes_det) + len(faltantes_paq) + len(faltantes_det)
    productos_con_diferencia = len(ids_con_diferencia)
    status_preview = "ok" if movimientos_generados > 0 else "skipped"

    return {
        "status": status_preview,
        "id_operacion": payload.id_operacion,
        "id_barra": payload.id_barra,
        "id_inventario_pos": inv_fisico_cabecera.id,
        "observaciones": payload.observaciones,
        **info_control,
        "resumen": {
            "productos_evaluados": len(deltas),
            "productos_con_diferencia": productos_con_diferencia,
            "movimientos_generados": movimientos_generados,
        },
        "sobrantes_paq": sobrantes_paq,
        "sobrantes_det": sobrantes_det,
        "faltantes_paq": faltantes_paq,
        "faltantes_det": faltantes_det,
        "deltas": deltas,
    }


def _decimal2(valor: float) -> Decimal:
    """Convierte a Decimal con 2 decimales para persistir cantidades (nunca float)."""
    return Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@app.post("/api/inventario/ajustes/aplicar", response_model=schemas.AplicarAjustesResponse)
def aplicar_ajustes_inventario(
    payload: schemas.AplicarAjustesRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_usuario_administrador)
):
    """Aplica de forma definitiva las diferencias paloteo-vs-POS: genera bar_ajuste /
    bar_salida_inventario (y sus detalles) y actualiza bar_inventario para que el stock
    vivo quede igual al físico contado. Solo administrador, requiere operación CERRADA (23).
    """
    _validar_operacion_cerrada(db, payload.id_operacion)

    inv_fisico_cabecera = _resolver_inventario_fisico(db, request, payload.id_operacion, payload.id_barra)

    control_existente = _obtener_control_aplicado(db, payload.id_operacion, payload.id_barra, inv_fisico_cabecera.id)
    if control_existente:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Los ajustes para esta operativa/barra ya fueron aplicados anteriormente."
        )

    deltas = _calcular_diferencias_paloteo(db, payload.id_barra, inv_fisico_cabecera.id)
    deltas_con_diferencia = [
        d for d in deltas if abs(d["delta_paq"]) > 0 or abs(d["delta_det_operativo"]) > 0
    ]
    _validar_cardinalidad_bar_inventario(db, payload.id_barra, [d["id_producto"] for d in deltas_con_diferencia])

    if not deltas_con_diferencia:
        return {
            "status": "skipped",
            "id_operacion": payload.id_operacion,
            "id_barra": payload.id_barra,
            "id_inventario_pos": inv_fisico_cabecera.id,
            "id_ajuste": None,
            "id_salida_inventario": None,
            "productos_afectados": 0,
            "mensaje": "No hay diferencias entre el inventario físico y el ideal; no se generaron movimientos.",
        }

    username_actual = current_user.usuario
    fecha_actual = datetime.now(timezone.utc)
    fecha_hoy = fecha_actual.date()
    obs_final = payload.observaciones if payload.observaciones else "AJUSTE GENERADO VÍA API"

    try:
        ajuste_header = None
        salida_header = None

        tiene_sobrante = any(d["delta_paq"] > 0 or d["delta_det_operativo"] > 0 for d in deltas_con_diferencia)
        tiene_faltante = any(d["delta_paq"] < 0 or d["delta_det_operativo"] < 0 for d in deltas_con_diferencia)

        if tiene_sobrante:
            ajuste_header = models.AjusteIngreso(
                fecha=fecha_hoy,
                numero_documento=None,
                observaciones=obs_final,
                recepcionado_por=username_actual,
                ind_estado_ingreso=16,
                ind_tipo_movimiento=84,
                id_operacion=None,
                id_barra=payload.id_barra,
                usuario_reg=username_actual,
                fecha_reg=fecha_hoy,
                estado='HAB',
            )
            db.add(ajuste_header)
            db.flush()

        if tiene_faltante:
            salida_header = models.AjusteSalida(
                fecha_salida=fecha_hoy,
                correlativo=None,
                responsable=username_actual,
                ind_estado_salida=16,
                observaciones_salida=obs_final,
                id_almacen=None,
                id_barra=payload.id_barra,
                id_operacion=None,
                ind_tipo_salida=77,
                usuario_reg=username_actual,
                fecha_reg=fecha_hoy,
                estado='HAB',
            )
            db.add(salida_header)
            db.flush()

        for d in deltas_con_diferencia:
            id_producto = d["id_producto"]

            if d["delta_paq"] > 0:
                db.add(models.DetalleAjusteIngreso(
                    cantidad=_decimal2(abs(d["delta_paq"])),
                    precio_costo=Decimal("0"),
                    ind_paq_detalle='1',
                    id_ajuste=ajuste_header.id,
                    id_producto=id_producto,
                    usuario_reg=username_actual,
                    fecha_reg=fecha_hoy,
                    estado='HAB',
                ))
            elif d["delta_paq"] < 0:
                db.add(models.DetalleAjusteSalida(
                    cantidad=_decimal2(abs(d["delta_paq"])),
                    ind_paq_detalle='1',
                    id_salida_inventario=salida_header.id,
                    id_producto=id_producto,
                    usuario_reg=username_actual,
                    fecha_reg=fecha_hoy,
                    estado='HAB',
                ))

            if d["delta_det_operativo"] > 0:
                db.add(models.DetalleAjusteIngreso(
                    cantidad=_decimal2(abs(d["delta_det_operativo"])),
                    precio_costo=Decimal("0"),
                    ind_paq_detalle='0',
                    id_ajuste=ajuste_header.id,
                    id_producto=id_producto,
                    usuario_reg=username_actual,
                    fecha_reg=fecha_hoy,
                    estado='HAB',
                ))
            elif d["delta_det_operativo"] < 0:
                db.add(models.DetalleAjusteSalida(
                    cantidad=_decimal2(abs(d["delta_det_operativo"])),
                    ind_paq_detalle='0',
                    id_salida_inventario=salida_header.id,
                    id_producto=id_producto,
                    usuario_reg=username_actual,
                    fecha_reg=fecha_hoy,
                    estado='HAB',
                ))

            # Cardinalidad ya validada por _validar_cardinalidad_bar_inventario antes
            # de iniciar la transaccion; aqui solo se obtiene la fila para mutarla.
            # with_for_update(): bloquea la fila por el resto de la transaccion para
            # evitar perder una escritura concurrente sobre el mismo bar_inventario.
            fila_inventario = db.query(models.InventarioBarra).filter(
                models.InventarioBarra.id_barra == payload.id_barra,
                models.InventarioBarra.id_producto == id_producto,
                models.InventarioBarra.estado == 'HAB'
            ).with_for_update().first()
            fila_inventario.cantidad_paq = _decimal2(d["real_paq"])
            fila_inventario.cantidad_detalle = _decimal2(d["real_det"])
            fila_inventario.usuario_reg = username_actual
            fila_inventario.fecha_mod = fecha_actual

        if ajuste_header:
            ajuste_header.ind_estado_ingreso = 20
        if salida_header:
            salida_header.ind_estado_salida = 20

        control = models.PaloteoAjusteControl(
            id_operacion=payload.id_operacion,
            id_barra=payload.id_barra,
            id_inventario_fisico=inv_fisico_cabecera.id,
            id_ajuste=ajuste_header.id if ajuste_header else None,
            id_salida_inventario=salida_header.id if salida_header else None,
            estado='APLICADO',
            payload_json=json.dumps({
                "deltas": deltas_con_diferencia,
                "observaciones": obs_final,
            }, default=str),
            usuario_reg=username_actual,
            fecha_reg=fecha_actual,
        )
        db.add(control)

        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.exception(
            "Error aplicando ajustes de inventario para operación %s / barra %s",
            payload.id_operacion, payload.id_barra,
        )
        raise HTTPException(status_code=500, detail="No se pudo aplicar el ajuste de inventario.") from exc

    return {
        "status": "success",
        "id_operacion": payload.id_operacion,
        "id_barra": payload.id_barra,
        "id_inventario_pos": inv_fisico_cabecera.id,
        "id_ajuste": ajuste_header.id if ajuste_header else None,
        "id_salida_inventario": salida_header.id if salida_header else None,
        "productos_afectados": len(deltas_con_diferencia),
        "mensaje": f"Ajuste aplicado correctamente sobre {len(deltas_con_diferencia)} producto(s).",
    }

# --- EXPORTACIÓN PDF PALOTEO 3 ---

import os
from fpdf import FPDF

_LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "imgs", "backstage_horizontal_banner.png")

def _color_diferencia(valor: float):
    if valor > 0:
        return (245, 158, 11)   # ámbar (#F59E0B)
    if valor < 0:
        return (239, 68, 68)    # rojo  (#EF4444)
    return (72, 232, 152)       # verde (#48E898)

@app.post("/api/paloteo3/exportar-pdf")
def exportar_pdf_paloteo3(
    payload: schemas.ExportarPdfRequest,
    current_user: models.Usuario = Depends(get_usuario_actual),
):
    tipo_reporte = payload.tipo_reporte
    if tipo_reporte == 'ingreso':
        sufijo_archivo = '_INGRESO'
        titulo_reporte = 'INGRESO POR AJUSTE'
        subtitulo_reporte = 'Ajuste Ingreso'
    elif tipo_reporte == 'salida':
        sufijo_archivo = '_SALIDA'
        titulo_reporte = 'SALIDA POR AJUSTE'
        subtitulo_reporte = 'Ajuste Salida'
    else:
        sufijo_archivo = ''
        titulo_reporte = 'REPORTE DE DIFERENCIAS'
        subtitulo_reporte = 'Paloteo 3'

    nombre_archivo = f"PALOTEO_{payload.id_operacion}{sufijo_archivo}.pdf"

    ahora = datetime.now()
    fecha_hora = ahora.strftime("%d/%m/%Y %H:%M:%S")

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_margins(20, 15, 20)

    # — Encabezado: logo + título —
    if os.path.exists(_LOGO_PATH):
        pdf.image(_LOGO_PATH, x=20, y=12, h=14)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(51, 51, 51)
    pdf.set_xy(20, 13)
    pdf.cell(0, 5, titulo_reporte, align="R")
    pdf.set_xy(20, 18)
    pdf.cell(0, 5, subtitulo_reporte, align="R")

    # línea divisoria
    pdf.set_draw_color(200, 200, 200)
    pdf.line(20, 28, 190, 28)
    pdf.ln(20)

    # — Metadata —
    pdf.set_text_color(34, 34, 34)
    meta = [
        ("Generado:", fecha_hora),
        ("Usuario:", payload.usuario),
        ("Operativa:", str(payload.id_operacion)),
        ("Barra:", str(payload.id_barra)),
    ]
    label_w, value_w, row_h = 24, 61, 6
    meta_y0 = pdf.get_y()
    for i, (etiqueta, valor) in enumerate(meta):
        x = 20 + (label_w + value_w) * (i % 2)
        y = meta_y0 + (i // 2) * row_h
        pdf.set_xy(x, y)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(label_w, row_h, etiqueta)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(value_w, row_h, valor)
    pdf.set_y(meta_y0 + (len(meta) // 2) * row_h + 4)
    pdf.ln(6)

    # — Tabla —
    col_widths = [12, 20, 86, 18, 34]   # ID | Codigo | Producto | Dif.Paq | Dif.Det POS
    headers   = ["ID", "CODIGO", "PRODUCTO", "DIF PAQ", "DIF DET POS"]
    aligns    = ["R", "L", "L", "R", "R"]
    row_h = 7

    # cabecera de tabla
    pdf.set_fill_color(242, 242, 242)
    pdf.set_draw_color(204, 204, 204)
    pdf.set_text_color(17, 17, 17)
    pdf.set_font("Helvetica", "B", 8)
    for w, h, a in zip(col_widths, headers, aligns):
        pdf.cell(w, row_h, h, border=1, align=a, fill=True)
    pdf.ln()

    # filas de datos
    pdf.set_font("Helvetica", "", 8)
    for idx, fila in enumerate(payload.filas):
        texto_unid = ""
        texto_oz_pos = ""
        color_unid = None
        color_oz_pos = None

        if fila.difUnidades is not None:
            texto_unid = f"{'+' if fila.difUnidades > 0 else ''}{round(fila.difUnidades)}"
            color_unid = _color_diferencia(fila.difUnidades)

        dif_oz_exacta = fila.difOnzasExactas if fila.difOnzasExactas is not None else fila.difOnzas
        dif_oz_pos = fila.difOnzasPos
        if dif_oz_pos is None and dif_oz_exacta is not None:
            # Unificamos granularidad con POS: incrementos de 0.5 oz.
            dif_oz_pos = round(dif_oz_exacta * 2.0) * 0.5

        if dif_oz_pos is not None:
            texto_oz_pos = f"{'+' if dif_oz_pos > 0 else ''}{dif_oz_pos:.2f} oz"
            color_oz_pos = _color_diferencia(dif_oz_pos)

        fondo = (245, 245, 245) if idx % 2 == 1 else (255, 255, 255)
        pdf.set_fill_color(*fondo)

        valores = [fila.idProducto, fila.codigo, fila.nombre, texto_unid, texto_oz_pos]
        colores = [None, None, None, color_unid, color_oz_pos]
        # Jerarquía visual: ID y CODIGO con menor peso visual que PRODUCTO
        jerarquias = ["muted", "muted", "primary", "valor", "valor"]

        for w, val, align, color, jerarquia in zip(col_widths, valores, aligns, colores, jerarquias):
            if color:
                pdf.set_text_color(*color)
                pdf.set_font("Helvetica", "B", 8)
            elif jerarquia == "muted":
                pdf.set_text_color(150, 150, 150)
                pdf.set_font("Helvetica", "", 7)
            elif jerarquia == "primary":
                pdf.set_text_color(17, 17, 17)
                pdf.set_font("Helvetica", "B", 8)
            else:
                pdf.set_text_color(17, 17, 17)
                pdf.set_font("Helvetica", "", 8)
            pdf.cell(w, row_h, str(val), border=1, align=align, fill=True)
        pdf.ln()

    pdf_bytes = bytes(pdf.output())

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'},
    )


# --- SERVIDOR DE ARCHIVOS ESTÁTICOS (FRONTEND) ---
# Montamos una carpeta llamada 'static' donde vivirá el HTML, CSS y JS
app.mount("/assets", StaticFiles(directory="static"), name="assets")

# Favicon canónico: se sirve desde static/icons sin duplicar archivos en la raíz
@app.get("/favicon.ico", include_in_schema=False)
def serve_favicon():
    return FileResponse("static/icons/favicon.ico")

# Ruta principal que devuelve la página web
@app.get("/")
def serve_frontend():
    return FileResponse("static/index.html")