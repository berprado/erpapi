from sqlalchemy.orm import Session
from sqlalchemy import text, bindparam, func
from sqlalchemy.exc import IntegrityError
from fastapi import FastAPI, Depends, HTTPException, status, Request, Query
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

# CORS solo si se configuran orígenes externos explícitos (CORS_ALLOWED_ORIGINS).
# La PWA integrada se sirve desde el mismo origen que la API y no necesita CORS.
if settings.cors_allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# CSP mínima que la PWA necesita hoy: Tailwind por CDN (requiere unsafe-eval),
# Google Fonts, e inline scripts/styles propios de index.html. connect-src 'self'
# impide exfiltrar el token hacia otros hosts aunque se inyecte un script.
_CSP_PWA = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data: blob:; "
    "connect-src 'self'; "
    "worker-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)

# Swagger UI carga sus assets desde cdn.jsdelivr.net: /docs queda exento de CSP.
_RUTAS_SIN_CSP = ("/docs", "/redoc", "/openapi.json")


@app.middleware("http")
async def agregar_cabeceras_seguridad(request: Request, call_next):
    response = await call_next(request)
    if not request.url.path.startswith(_RUTAS_SIN_CSP):
        response.headers.setdefault("Content-Security-Policy", _CSP_PWA)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    return response

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


def _obtener_tolerancia_operativa_oz(pesable: int | None) -> float:
    """Banda muerta operativa uniforme: 0.5 oz para todos los productos pesables.

    0.5 oz coincide con el paso mínimo del POS (grilla de redondeo), por lo que
    cualquier delta que supere la banda ya cae en un múltiplo de 0.5 sin distorsión
    al cuantizarse. Ver documentos/redondeo_y_tolerancia.md para el análisis completo.
    """
    if int(pesable or 0) != 1:
        return 0.0
    return 0.5


ID_CATEGORIA_VINOS = 6
TARA_VINOS = 0.0
GRAMOS_POR_OZ_VINOS = 1.0


def _es_producto_vino(db: Session, id_producto: int) -> bool:
    id_categoria = db.execute(
        text("SELECT id_categoria FROM alm_producto WHERE id = :id_producto LIMIT 1"),
        {"id_producto": id_producto}
    ).scalar()
    return int(id_categoria or 0) == ID_CATEGORIA_VINOS


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


def _formatear_nombre_usuario(usuario: models.Usuario) -> str:
    """Arma 'Paterno Materno, Nombres' omitiendo apellidos NULL o vacíos del POS."""
    apellidos = " ".join(
        parte.strip() for parte in [usuario.paterno, usuario.materno] if parte and parte.strip()
    )
    nombres = (usuario.nombres or "").strip()
    if apellidos and nombres:
        return f"{apellidos}, {nombres}"
    return apellidos or nombres or usuario.usuario


def _obtener_ip_cliente(request: Request) -> str:
    """IP real del cliente. Detrás de un reverse proxy request.client.host es la
    IP del proxy, por eso se prioriza X-Forwarded-For (primera IP de la cadena)."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(',')[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "desconocida"


def _registrar_intento_login(db: Session, usuario: str, ip: str, exito: bool, motivo: str = None) -> None:
    """Deja rastro de todo intento de login (exitoso o no) en app_login_auditoria_api.
    Fail-open: si la tabla no existe aún en el entorno, el login no debe caerse;
    se registra un warning y se continúa (el rate limit queda inactivo)."""
    try:
        db.add(models.LoginAuditoria(
            usuario=usuario,
            exito=1 if exito else 0,
            motivo=motivo,
            ip=ip,
            fecha=datetime.now(timezone.utc),
        ))
        db.commit()
    except Exception:
        db.rollback()
        logger.warning(
            "No se pudo registrar el intento de login (¿falta app_login_auditoria_api? "
            "Ver querys/ddl_app_login_auditoria_api.sql).", exc_info=True
        )


def _contar_fallos_login(db: Session, campo: str, valor: str, desde: datetime) -> int:
    """Fallos de login desde `desde`, ignorando los anteriores al último éxito
    (un login correcto resetea el contador de ese usuario/IP)."""
    if campo not in ("usuario", "ip"):
        raise ValueError(f"Campo de rate limit no soportado: {campo}")
    ultimo_exito = db.execute(
        text(f"SELECT MAX(fecha) FROM app_login_auditoria_api WHERE {campo} = :valor AND exito = 1"),
        {"valor": valor}
    ).scalar()
    if ultimo_exito and ultimo_exito > desde:
        desde = ultimo_exito
    total = db.execute(
        text(f"SELECT COUNT(*) FROM app_login_auditoria_api WHERE {campo} = :valor AND exito = 0 AND fecha > :desde"),
        {"valor": valor, "desde": desde}
    ).scalar()
    return int(total or 0)


def _verificar_rate_limit_login(db: Session, usuario: str, ip: str) -> None:
    """Freno de fuerza bruta: 429 si el usuario o la IP acumulan demasiados
    fallos dentro de la ventana. Se evalúa ANTES de tocar credenciales para no
    dar señal alguna sobre la cuenta."""
    # Fechas naive en UTC para comparar contra los DATETIME que devuelve MySQL.
    inicio_ventana = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        minutes=settings.LOGIN_VENTANA_MINUTOS
    )
    fallos_usuario = _contar_fallos_login(db, "usuario", usuario, inicio_ventana)
    fallos_ip = _contar_fallos_login(db, "ip", ip, inicio_ventana)
    if (fallos_usuario >= settings.LOGIN_MAX_INTENTOS_USUARIO
            or fallos_ip >= settings.LOGIN_MAX_INTENTOS_IP):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Demasiados intentos fallidos. Intente nuevamente en {settings.LOGIN_VENTANA_MINUTOS} minutos."
        )


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
    es_vino_por_producto = {}

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

        if item.id_producto not in es_vino_por_producto:
            es_vino_por_producto[item.id_producto] = _es_producto_vino(db, item.id_producto)

        onzas_max_producto = onzas_max_por_producto[item.id_producto]
        es_vino = es_vino_por_producto[item.id_producto]

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

                if (not es_vino) and (
                    perfil.tara is None
                    or perfil.peso_bruto is None or perfil.peso_bruto <= 0
                    or perfil.gramos_por_oz is None or perfil.gramos_por_oz <= 0
                ):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            f"Perfil de botella incompleto para producto {item.id_producto}. "
                            "Completa la configuración de pesaje antes de registrar el paloteo."
                        )
                    )

                gr_oz = GRAMOS_POR_OZ_VINOS if es_vino else float(perfil.gramos_por_oz)
                tara = TARA_VINOS if es_vino else float(perfil.tara)
                peso_bruto = float(perfil.peso_bruto or 0)
                peso_medido = float(abierta.peso)

                if (not es_vino) and peso_bruto > 0 and peso_medido > peso_bruto:
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
    usuario_solicitado = login_data.usuario.strip()
    ip_cliente = _obtener_ip_cliente(request)

    # 0. Freno de fuerza bruta: corta con 429 antes de evaluar credenciales.
    # Fail-open si la tabla de auditoría no existe aún en este entorno.
    try:
        _verificar_rate_limit_login(db, usuario_solicitado, ip_cliente)
    except HTTPException:
        raise
    except Exception:
        logger.warning(
            "Rate limit de login no disponible (¿falta app_login_auditoria_api?); se permite el intento.",
            exc_info=True
        )

    # 1. Buscar al usuario y verificar credenciales (hash SHA-256).
    # La contraseña se valida ANTES que el estado de la cuenta para que un
    # tercero sin credenciales no pueda descubrir si un usuario existe o está
    # deshabilitado (misma respuesta 401 genérica en ambos casos).
    usuario_db = db.query(models.Usuario).filter(models.Usuario.usuario == usuario_solicitado).first()
    hash_calculado = hash_password(login_data.contrasena)

    if not usuario_db or usuario_db.contrasena != hash_calculado:
        _registrar_intento_login(db, usuario_solicitado, ip_cliente, exito=False, motivo='CREDENCIALES')
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos"
        )

    # 2. Con credenciales válidas, validar que el usuario esté activo y habilitado
    if usuario_db.estado != 'HAB' or usuario_db.habilitado != '1':
        _registrar_intento_login(db, usuario_solicitado, ip_cliente, exito=False, motivo='DESHABILITADO')
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El usuario no está activo o habilitado en el sistema"
        )

    # 4. Registrar el acceso: seg_acceso (compatibilidad POS) + auditoría propia
    # (resetea el contador de fallos del rate limit para este usuario/IP).
    _registrar_intento_login(db, usuario_db.usuario, ip_cliente, exito=True)
    nuevo_acceso = models.Acceso(
        usuario=usuario_db.usuario,
        fecha=datetime.now(timezone.utc),
        ip=ip_cliente
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
        "nombres": _formatear_nombre_usuario(usuario_db),
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
    nombre_formateado = _formatear_nombre_usuario(current_user).upper()
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
    nombre_formateado = _formatear_nombre_usuario(current_user).upper()
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


@app.delete("/api/inventario/paloteo/{id_inventario_pos}/producto/{id_producto}", response_model=schemas.EliminarProductoPaloteoResponse)
def eliminar_producto_paloteo(
    id_inventario_pos: int,
    id_producto: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_usuario_actual)
):
    """
    Da de baja (soft-delete) el detalle de un solo producto dentro de un inventario
    físico ya registrado. Pensado para deshacer un producto agregado manualmente
    por error (ver /api/inventario/catalogo/buscar): a diferencia de PUT, que es
    upsert-only y nunca borra filas omitidas del payload, este endpoint sí elimina
    explícitamente una fila puntual.

    No toca app_paloteo_registro_crudo: es un log de auditoría append-only, la
    captura original (incluso si luego se quita) debe seguir siendo rastreable.
    """
    inventario = db.query(models.InventarioFisicoPOS).filter(
        models.InventarioFisicoPOS.id == id_inventario_pos,
        models.InventarioFisicoPOS.estado == 'HAB'
    ).first()
    if not inventario:
        raise HTTPException(status_code=404, detail="Inventario físico no encontrado o inactivo.")

    _validar_operacion_inicio_cierre(db, inventario.id_operacion)

    barra_operativa = _resolver_barra_operativa(request)
    if inventario.id_barra != barra_operativa:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"La barra operativa configurada ({barra_operativa}) no coincide con la del inventario físico ({inventario.id_barra})."
        )

    detalle = db.query(models.DetalleFisicoPOS).filter(
        models.DetalleFisicoPOS.id_inventario_fisico == id_inventario_pos,
        models.DetalleFisicoPOS.id_producto == id_producto,
        models.DetalleFisicoPOS.estado == 'HAB'
    ).first()

    existia = detalle is not None
    if detalle:
        fecha_actual = datetime.now(timezone.utc).date()
        detalle.estado = 'DES'
        detalle.fecha_mod = fecha_actual
        inventario.fecha_mod = fecha_actual
        db.commit()

    return {
        "status": "success",
        "id_inventario_pos": id_inventario_pos,
        "id_producto": id_producto,
        "existia": existia,
        "mensaje": "Producto quitado del inventario físico." if existia else "El producto no estaba guardado; no había nada que quitar.",
    }


@app.post("/api/pesaje/perfiles", response_model=schemas.PerfilPesaje)
def crear_perfil_pesaje(
    payload: schemas.CrearPerfilPesajeRequest,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_usuario_administrador)
):
    """Crea un nuevo modelo de botella para un producto pesable."""
    es_vino = _es_producto_vino(db, payload.id_producto)

    if es_vino:
        if abs(float(payload.tara) - TARA_VINOS) > 1e-9:
            raise HTTPException(status_code=400, detail="En categoría VINOS la tara debe ser 0.")
        tara = TARA_VINOS
        gramos_por_oz = GRAMOS_POR_OZ_VINOS
    else:
        if payload.tara >= payload.peso_bruto:
            raise HTTPException(status_code=400, detail="La tara no puede ser mayor o igual al peso bruto.")

        volumen_oz = _obtener_onzas_por_botella_llena(db, payload.id_producto)
        if not volumen_oz:
            raise HTTPException(
                status_code=400,
                detail="No se pudo determinar el volumen estándar del producto."
            )

        tara = float(payload.tara)
        gramos_por_oz = (payload.peso_bruto - tara) / volumen_oz

    tiene_perfil_activo = db.query(models.ProductoPesajeConfig.id).filter(
        models.ProductoPesajeConfig.id_producto_almacen == payload.id_producto,
        models.ProductoPesajeConfig.estado == 'HAB'
    ).first() is not None

    # Regla operativa: el primer modelo activo de cada producto debe usar el
    # mismo valor por defecto definido en la tabla. Los modelos adicionales
    # pueden tener nombre libre.
    nombre_perfil = (
        payload.nombre_perfil.strip()
        if tiene_perfil_activo
        else models.NOMBRE_PERFIL_PESAJE_DEFAULT
    )
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
            perfil_des.tara = tara
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
                "tara": tara,
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
        tara=tara,
        gramos_por_oz=gramos_por_oz,
        tolerancia_oz=_obtener_tolerancia_operativa_oz(1),
        barcode=barcode,
    )


CATEGORIAS_EXCLUIDAS_PESAJE = (10, 11, 13, 14, 15, 17, 18, 19, 20)


def _producto_deberia_ser_pesable(db: Session, id_producto: int) -> bool:
    """Mismo criterio que usan trg_alm_producto_after_insert/after_update para
    derivar `pesable` desde el catalogo: ind_permite_comandar=71 y categoria
    fuera de CATEGORIAS_EXCLUIDAS_PESAJE. Se usa para permitir "promover" un
    perfil pesable=0 sin depender de que el listado ya lo haya filtrado antes."""
    row = db.execute(
        text("SELECT ind_permite_comandar, id_categoria FROM alm_producto WHERE id = :id_producto LIMIT 1"),
        {"id_producto": id_producto}
    ).mappings().first()
    if not row or int(row["ind_permite_comandar"] or 0) != 71:
        return False
    id_categoria = row["id_categoria"]
    if id_categoria is not None and int(id_categoria) in CATEGORIAS_EXCLUIDAS_PESAJE:
        return False
    return True


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
    condiciones = ["(pc.id_categoria IS NULL OR pc.id_categoria NOT IN :excluidas)"]
    parametros = {"excluidas": CATEGORIAS_EXCLUIDAS_PESAJE}

    if nombre:
        condiciones.append("pc.nombre_producto LIKE :nombre")
        parametros["nombre"] = f"%{nombre}%"
    if id_categoria is not None:
        condiciones.append("pc.id_categoria = :id_categoria")
        parametros["id_categoria"] = id_categoria
    if pesable is not None:
        condiciones.append("pc.pesable = :pesable")
        parametros["pesable"] = pesable

    where_sql = f"WHERE {' AND '.join(condiciones)}"

    query = text(f"""
        SELECT pc.id_pesaje_config, pc.id_producto, pc.nombre_producto, pc.codigo_producto,
               pc.id_categoria, pc.nombre_categoria, pc.cantidad_detalle, pc.peso_bruto, pc.tara,
               pc.gramos_por_oz, pc.pesable, pc.barcode, pc.nombre_perfil,
               vw.medida, vw.nombre_unidad_medida, vw.nombre_unidad_medida_detalle,
               vw.nombre_ind_permite_comandar
        FROM v9_pesaje_config_api pc
        LEFT JOIN vw_alm_producto_con_nombres vw ON vw.id = pc.id_producto
        {where_sql}
        ORDER BY pc.nombre_producto ASC, pc.nombre_perfil ASC
    """).bindparams(bindparam("excluidas", expanding=True))

    rows = list(db.execute(query, parametros).mappings().all())

    # Para la pestaña INCOMPLETOS, además de perfiles pesables con campos nulos,
    # incluimos los productos pesables habilitados que aún no tienen ninguna
    # configuración activa en app_producto_pesaje_config_api.
    if pesable == 1:
        condiciones_sin_config = [
            "a.estado = 'HAB'",
            "a.ind_permite_comandar = 71",
            "(a.id_categoria IS NULL OR a.id_categoria NOT IN :excluidas)",
            "NOT EXISTS (SELECT 1 FROM app_producto_pesaje_config_api p WHERE p.id_producto_almacen = a.id AND p.estado = 'HAB')",
        ]
        parametros_sin_config = {"excluidas": CATEGORIAS_EXCLUIDAS_PESAJE}

        if nombre:
            condiciones_sin_config.append("a.nombre LIKE :nombre")
            parametros_sin_config["nombre"] = f"%{nombre}%"
        if id_categoria is not None:
            condiciones_sin_config.append("a.id_categoria = :id_categoria")
            parametros_sin_config["id_categoria"] = id_categoria

        where_sin_config = f"WHERE {' AND '.join(condiciones_sin_config)}"

        query_sin_config = text(f"""
            SELECT NULL AS id_pesaje_config,
                   a.id AS id_producto,
                   a.nombre AS nombre_producto,
                   a.codigo AS codigo_producto,
                   a.id_categoria,
                   c.nombre AS nombre_categoria,
                   a.cantidad_detalle,
                   NULL AS peso_bruto,
                   NULL AS tara,
                   NULL AS gramos_por_oz,
                   1 AS pesable,
                   NULL AS barcode,
                   NULL AS nombre_perfil,
                   vw.medida,
                   vw.nombre_unidad_medida,
                   vw.nombre_unidad_medida_detalle,
                   vw.nombre_ind_permite_comandar
            FROM alm_producto a
            LEFT JOIN alm_categoria c ON c.id = a.id_categoria
            LEFT JOIN vw_alm_producto_con_nombres vw ON vw.id = a.id
            {where_sin_config}
            ORDER BY a.nombre ASC
        """).bindparams(bindparam("excluidas", expanding=True))

        rows_sin_config = db.execute(query_sin_config, parametros_sin_config).mappings().all()
        rows.extend(rows_sin_config)

    rows.sort(key=lambda row: (row["nombre_producto"] or "", row["nombre_perfil"] or ""))

    salida = []
    for row in rows:
        es_vino = int(row["id_categoria"] or 0) == ID_CATEGORIA_VINOS and int(row["pesable"] or 0) == 1
        tara = TARA_VINOS if es_vino else row["tara"]
        gramos_por_oz = GRAMOS_POR_OZ_VINOS if es_vino else row["gramos_por_oz"]

        salida.append(
            schemas.PesajeConfigItem(
                id=row["id_pesaje_config"],
                id_producto=row["id_producto"],
                nombre_producto=row["nombre_producto"],
                codigo_producto=row["codigo_producto"],
                id_categoria=row["id_categoria"],
                nombre_categoria=row["nombre_categoria"],
                volumen_oz=float(row["cantidad_detalle"]) if row["cantidad_detalle"] is not None else None,
                peso_bruto=float(row["peso_bruto"]) if row["peso_bruto"] is not None else None,
                tara=float(tara) if tara is not None else None,
                gramos_por_oz=float(gramos_por_oz) if gramos_por_oz is not None else None,
                pesable=row["pesable"],
                barcode=row["barcode"],
                nombre_perfil=row["nombre_perfil"],
                medida=float(row["medida"]) if row["medida"] is not None else None,
                nombre_unidad_medida=row["nombre_unidad_medida"],
                nombre_unidad_medida_detalle=row["nombre_unidad_medida_detalle"],
                nombre_ind_permite_comandar=row["nombre_ind_permite_comandar"],
            )
        )

    return salida


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

    # "Promover": un perfil pesable=0 (fila fantasma creada por el trigger de
    # INSERT, o legacy) se puede completar directo desde aca si el catalogo
    # dice que el producto deberia ser pesable — sin esto, la unica salida
    # era SQL directo (ver TODO.md "conflictos excepcionales de pesable").
    if perfil.pesable == 1 or _producto_deberia_ser_pesable(db, perfil.id_producto_almacen):
        tocando_pesaje = payload.peso_bruto is not None or payload.tara is not None
        es_vino = _es_producto_vino(db, perfil.id_producto_almacen)

        if tocando_pesaje:
            if es_vino:
                if payload.peso_bruto is None:
                    raise HTTPException(status_code=400, detail="peso_bruto es obligatorio para categoría VINOS.")
                if payload.tara is not None and abs(float(payload.tara) - TARA_VINOS) > 1e-9:
                    raise HTTPException(status_code=400, detail="En categoría VINOS la tara debe ser 0.")

                perfil.peso_bruto = payload.peso_bruto
                perfil.tara = TARA_VINOS
                perfil.gramos_por_oz = GRAMOS_POR_OZ_VINOS
                perfil.pesable = 1
            else:
                # peso_bruto y tara ya no son obligatorios juntos: el peso
                # bruto casi siempre se conoce de entrada, pero la tara recien
                # se puede medir cuando se termina el contenido de la botella.
                # Al caer al valor ya guardado (no provisto en el payload), solo
                # se lo toma como "ya conocido" si es > 0 -- un perfil recien
                # promovido puede traer ceros heredados de la fila fantasma
                # (peso_bruto/tara/gramos_por_oz en 0, no NULL), que no son un
                # dato real (ver TODO.md "conflictos excepcionales de pesable").
                if payload.peso_bruto is not None:
                    peso_bruto_final = float(payload.peso_bruto)
                elif perfil.peso_bruto is not None and float(perfil.peso_bruto) > 0:
                    peso_bruto_final = float(perfil.peso_bruto)
                else:
                    peso_bruto_final = None

                if payload.tara is not None:
                    tara_final = float(payload.tara)
                elif perfil.tara is not None and float(perfil.tara) > 0:
                    tara_final = float(perfil.tara)
                else:
                    tara_final = None

                if peso_bruto_final is None:
                    raise HTTPException(status_code=400, detail="peso_bruto es obligatorio para completar un perfil pesable.")
                perfil.peso_bruto = peso_bruto_final

                if tara_final is not None:
                    if tara_final >= peso_bruto_final:
                        raise HTTPException(status_code=400, detail="La tara no puede ser mayor o igual al peso bruto.")

                    volumen_oz = _obtener_onzas_por_botella_llena(db, perfil.id_producto_almacen)
                    if not volumen_oz:
                        raise HTTPException(status_code=400, detail="No se pudo determinar el volumen estándar del producto.")

                    perfil.tara = tara_final
                    perfil.gramos_por_oz = (peso_bruto_final - tara_final) / volumen_oz
                else:
                    # Tara todavia no medida: queda incompleto (visible y
                    # editable en INCOMPLETOS) hasta una segunda edicion.
                    perfil.tara = None
                    perfil.gramos_por_oz = None

                perfil.pesable = 1
    else:
        if payload.peso_bruto is not None or payload.tara is not None:
            raise HTTPException(
                status_code=400,
                detail="Este producto no está habilitado como pesable en el catálogo."
            )

    perfil.barcode = payload.barcode.strip() if payload.barcode else None

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

    es_vino = int(row["id_categoria"] or 0) == ID_CATEGORIA_VINOS and int(row["pesable"] or 0) == 1
    tara = TARA_VINOS if es_vino else row["tara"]
    gramos_por_oz = GRAMOS_POR_OZ_VINOS if es_vino else row["gramos_por_oz"]

    return schemas.PesajeConfigItem(
        id=row["id_pesaje_config"],
        id_producto=row["id_producto"],
        nombre_producto=row["nombre_producto"],
        codigo_producto=row["codigo_producto"],
        id_categoria=row["id_categoria"],
        nombre_categoria=row["nombre_categoria"],
        volumen_oz=float(row["cantidad_detalle"]) if row["cantidad_detalle"] is not None else None,
        peso_bruto=float(row["peso_bruto"]) if row["peso_bruto"] is not None else None,
        tara=float(tara) if tara is not None else None,
        gramos_por_oz=float(gramos_por_oz) if gramos_por_oz is not None else None,
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

def _agrupar_filas_producto_pesaje(rows) -> list[dict]:
    """Agrupa filas planas (producto x perfil de pesaje) en una lista de productos
    con su array de perfiles. Compartido por /pendientes y /catalogo/buscar para
    no duplicar la logica de agrupacion entre ambos endpoints.
    """
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
            es_vino = int(row["id_categoria"] or 0) == ID_CATEGORIA_VINOS
            tara = TARA_VINOS if es_vino else row["tara"]
            gramos_por_oz = GRAMOS_POR_OZ_VINOS if es_vino else row["gramos_por_oz"]

            # Si el perfil viene incompleto desde BD, se omite para no romper
            # la serialización del endpoint con valores None/cero en campos float.
            # peso_bruto aplica a ambos (vino y no-vino); tara/gramos_por_oz solo
            # importan para no-vino, ya que en vino estan siempre forzados arriba.
            incompleto = (
                row["tolerancia_oz"] is None
                or row["peso_bruto"] is None or row["peso_bruto"] <= 0
                or ((not es_vino) and (
                    row["tara"] is None
                    or row["gramos_por_oz"] is None or row["gramos_por_oz"] <= 0
                ))
            )
            if incompleto:
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
                "tara": float(tara),
                "gramos_por_oz": float(gramos_por_oz),
                "tolerancia_oz": _obtener_tolerancia_operativa_oz(row["pesable"]),
                "barcode": row["barcode"]
            })

    return list(productos_dict.values())


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

    return _agrupar_filas_producto_pesaje(rows)


@app.get("/api/inventario/catalogo/buscar", response_model=List[schemas.ProductoPendiente])
def buscar_productos_catalogo(
    request: Request,
    busqueda: str = Query("", description="Texto a buscar en nombre o código; vacío devuelve el catálogo completo"),
    limite: int = Query(15, ge=1, le=500, description="Máximo de productos a devolver"),
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_usuario_actual)
    ):
    """
    Busca productos en el catálogo completo de la barra operativa, sin filtrar
    por movimiento en la operación activa. Alimenta el flujo de "agregar producto
    sin movimiento" en PALOTEO 1/2/3: el usuario encontró físicamente un producto
    que no tuvo comandas/salidas esta operativa (ej. estaba oculto, o se dio de
    baja por error en un cierre previo) y necesita poder contarlo igual.

    Con `busqueda` vacía y `limite` alto, alimenta también el flujo de "paloteo
    completo": listar/agregar de una vez todos los productos de la barra, con o
    sin movimiento, para cuando corresponde recontar el catálogo entero.

    Misma forma de respuesta que /pendientes (schemas.ProductoPendiente) para que
    el frontend trate un resultado de búsqueda exactamente igual que uno cargado
    por movimiento, sin mapeos especiales.
    """
    # Resuelve y valida la barra operativa (X-Barra-Id) aunque no se use en el
    # WHERE: vista_inventario_barra_con_filtro ya viene fijada a la barra activa,
    # igual que en /pendientes; aqui solo nos interesa el efecto de validacion.
    _resolver_barra_operativa(request)

    patron = busqueda.strip()
    if patron and len(patron) < 2:
        raise HTTPException(status_code=400, detail="La búsqueda debe tener al menos 2 caracteres.")

    filtro_nombre = "AND (a.nombre LIKE :patron OR a.codigo LIKE :patron)" if patron else ""

    query = text(f"""
        SELECT
            a.id AS id_producto, a.codigo, a.nombre, a.ind_permite_comandar,
            i.cantidad_paq AS stock_ideal_unidades, i.cantidad_detalle AS stock_ideal_onzas,
            i.id_categoria, i.categoria_nombre,
            p.id AS perfil_id, p.pesable, p.nombre_perfil, p.peso_bruto, p.tara, p.gramos_por_oz, p.tolerancia_oz, p.barcode,
            a.cantidad_detalle AS onzas_por_botella_llena
        FROM alm_producto a
        INNER JOIN vista_inventario_barra_con_filtro i ON a.id = i.id_almacen
        LEFT JOIN app_producto_pesaje_config_api p ON a.id = p.id_producto_almacen AND p.estado = 'HAB'
        WHERE a.estado = 'HAB'
          {filtro_nombre}
        ORDER BY a.nombre ASC, p.id ASC
        LIMIT :limite
    """)

    rows = db.execute(query, {
        "patron": f"%{patron}%",
        "limite": limite,
    }).mappings().all()

    return _agrupar_filas_producto_pesaje(rows)


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
        tolerancia_oz = _obtener_tolerancia_operativa_oz(pesable)
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
    # La cardinalidad se valida sobre el MISMO conjunto que aplicar escribira en
    # bar_inventario (todo producto con fisico != ideal, tolerados incluidos, no
    # solo los que generan movimientos), para que el problema de datos aparezca
    # aqui en el preview y no recien al confirmar el ajuste.
    ids_a_igualar = [d["id_producto"] for d in deltas if d["delta_paq"] != 0.0 or d["delta_det_exacto"] != 0.0]
    _validar_cardinalidad_bar_inventario(db, payload.id_barra, ids_a_igualar)

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


def _mensaje_ajuste_aplicado(con_movimiento: int, igualados: int) -> str:
    mensaje = f"Ajuste aplicado correctamente sobre {con_movimiento} producto(s)."
    extras = igualados - con_movimiento
    if extras > 0:
        mensaje += (
            f" Se igualó además bar_inventario al físico en {extras} producto(s) "
            "con diferencia dentro de la banda de tolerancia."
        )
    return mensaje


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

    La igualación de bar_inventario es incondicional respecto de la banda de tolerancia:
    todo producto cuyo físico difiera del ideal se escribe al físico exacto, aunque su
    delta caiga dentro de la banda y no genere movimiento documental.
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
    # Igualacion incondicional: ademas de los productos que generan movimientos,
    # bar_inventario se escribe al fisico exacto para todo producto cuyo fisico
    # difiera del ideal aunque el delta caiga dentro de la banda de tolerancia.
    # Asi la garantia "bar_inventario queda igualado al fisico final" no depende
    # del invariante multiplo-de-0.5 ni de que el producto tenga ademas
    # diferencia de botellas. deltas_con_diferencia es subconjunto de
    # deltas_a_igualar (operativo != 0 implica exacto != 0).
    deltas_a_igualar = [
        d for d in deltas if d["delta_paq"] != 0.0 or d["delta_det_exacto"] != 0.0
    ]
    _validar_cardinalidad_bar_inventario(db, payload.id_barra, [d["id_producto"] for d in deltas_a_igualar])

    if not deltas_con_diferencia:
        return {
            "status": "skipped",
            "id_operacion": payload.id_operacion,
            "id_barra": payload.id_barra,
            "id_inventario_pos": inv_fisico_cabecera.id,
            "id_ajuste": None,
            "id_salida_inventario": None,
            "productos_afectados": 0,
            "igualacion_verificada": True,
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

        # Igualacion de bar_inventario sobre deltas_a_igualar (no solo los que
        # generaron movimientos): un producto con delta tolerado tambien queda
        # escrito al fisico exacto.
        # Cardinalidad ya validada por _validar_cardinalidad_bar_inventario antes
        # de iniciar la transaccion; aqui solo se obtiene la fila para mutarla.
        # with_for_update(): bloquea la fila por el resto de la transaccion para
        # evitar perder una escritura concurrente sobre el mismo bar_inventario.
        filas_inventario_tocadas = []
        for d in deltas_a_igualar:
            fila_inventario = db.query(models.InventarioBarra).filter(
                models.InventarioBarra.id_barra == payload.id_barra,
                models.InventarioBarra.id_producto == d["id_producto"],
                models.InventarioBarra.estado == 'HAB'
            ).with_for_update().first()
            fila_inventario.cantidad_paq = _decimal2(d["real_paq"])
            fila_inventario.cantidad_detalle = _decimal2(d["real_det"])
            fila_inventario.usuario_reg = username_actual
            fila_inventario.fecha_mod = fecha_actual
            filas_inventario_tocadas.append((fila_inventario, d))

        # Verificacion de igualacion: relee desde la BD (no desde el objeto en memoria)
        # cada fila que se acaba de actualizar y confirma que quedo exactamente igual
        # al fisico contado. Es una garantia en runtime de que la asignacion directa de
        # arriba realmente se aplico, no una suposicion basada en la lectura del codigo.
        db.flush()
        productos_no_igualados = []
        for fila_inventario, d in filas_inventario_tocadas:
            db.refresh(fila_inventario)
            esperado_paq = _decimal2(d["real_paq"])
            esperado_det = _decimal2(d["real_det"])
            if fila_inventario.cantidad_paq != esperado_paq or fila_inventario.cantidad_detalle != esperado_det:
                productos_no_igualados.append({
                    "id_producto": d["id_producto"],
                    "esperado_paq": float(esperado_paq),
                    "esperado_det": float(esperado_det),
                    "obtenido_paq": float(fila_inventario.cantidad_paq),
                    "obtenido_det": float(fila_inventario.cantidad_detalle),
                })

        if productos_no_igualados:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"La igualación de bar_inventario no coincide con el físico contado para: {productos_no_igualados}"
            )

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
                "igualaciones_sin_movimiento": [
                    d for d in deltas_a_igualar if d not in deltas_con_diferencia
                ],
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
        "igualacion_verificada": True,
        "mensaje": _mensaje_ajuste_aplicado(len(deltas_con_diferencia), len(deltas_a_igualar)),
    }

# --- EXPORTACIÓN PDF PALOTEO 3 ---

import os
from fpdf import FPDF

_LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "imgs", "backstage_horizontal_banner.png")
_FONTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "fonts")
_FONT_REGULAR_PATH = os.path.join(_FONTS_DIR, "SpaceGrotesk-Regular.ttf")
_FONT_BOLD_PATH = os.path.join(_FONTS_DIR, "SpaceGrotesk-Bold.ttf")
# Misma tipografia que la PWA (--font-family: "Space Grotesk", static/cellar-sync-tokens.css)
# para que el PDF exportado sea visualmente consistente con la app.
_FONT_FAMILY = "SpaceGrotesk"

def _color_diferencia(valor: float):
    if valor > 0:
        return (245, 158, 11)   # ámbar (#F59E0B)
    if valor < 0:
        return (239, 68, 68)    # rojo  (#EF4444)
    return (72, 232, 152)       # verde (#48E898)

def _fmt_cantidad_paq(valor):
    return "" if valor is None else str(round(valor))

def _fmt_cantidad_oz(valor):
    return "" if valor is None else f"{valor:.2f} oz"

def _fmt_peso_gramos(valor):
    if valor is None:
        return ""
    texto = f"{valor:.1f}".rstrip("0").rstrip(".")
    return f"{texto} g"

def _fmt_diff_paq(valor):
    return "" if valor is None else f"{'+' if valor > 0 else ''}{round(valor)}"

def _fmt_diff_oz(valor):
    return "" if valor is None else f"{'+' if valor > 0 else ''}{valor:.2f} oz"


class _ReportePDF(FPDF):
    """FPDF con footer discreto de numero de pagina ("PÁGINA n / N") en cada
    hoja. fpdf2 invoca footer() automaticamente al cerrar cada pagina; el
    placeholder {nb} se reemplaza con el total de paginas al renderizar."""

    def footer(self):
        self.set_y(-12)
        self.set_font(_FONT_FAMILY, "", 7)
        self.set_text_color(150, 150, 150)
        self.cell(0, 8, f"PÁGINA {self.page_no()} / {{nb}}", align="C")


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
        subtitulo_reporte = 'Stock Barra vs. Stock POS'

    nombre_archivo = f"PALOTEO_{payload.id_operacion}{sufijo_archivo}.pdf"

    ahora = datetime.now()
    fecha_hora = ahora.strftime("%d/%m/%Y %H:%M:%S")

    # Horizontal: 10 columnas (se agregaron PAQ POS/BAR y DET POS/BAR) no entran
    # con un ancho legible en A4 vertical (170mm utiles).
    pdf = _ReportePDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.alias_nb_pages()  # habilita el placeholder {nb} (total de paginas)
    pdf.add_font(_FONT_FAMILY, "", _FONT_REGULAR_PATH)
    pdf.add_font(_FONT_FAMILY, "B", _FONT_BOLD_PATH)
    pdf.add_page()
    pdf.set_margins(20, 15, 20)
    ancho_util = pdf.w - 40  # 297mm - 20mm margen izq. - 20mm margen der.
    x_derecha = pdf.w - 20

    # — Encabezado: logo + título —
    if os.path.exists(_LOGO_PATH):
        pdf.image(_LOGO_PATH, x=20, y=12, h=14)
    pdf.set_font(_FONT_FAMILY, "B", 10)
    pdf.set_text_color(51, 51, 51)
    pdf.set_xy(20, 13)
    pdf.cell(ancho_util, 5, titulo_reporte, align="R")
    pdf.set_xy(20, 18)
    pdf.cell(ancho_util, 5, subtitulo_reporte, align="R")

    # línea divisoria
    pdf.set_draw_color(200, 200, 200)
    pdf.line(20, 28, x_derecha, 28)
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
        pdf.set_font(_FONT_FAMILY, "B", 9)
        pdf.cell(label_w, row_h, etiqueta)
        pdf.set_font(_FONT_FAMILY, "", 9)
        pdf.cell(value_w, row_h, valor)
    pdf.set_y(meta_y0 + (len(meta) // 2) * row_h + 4)
    pdf.ln(6)

    # — Tabla —
    # ID | COD | Producto | Paq.Pos | Paq.Bar | Det.Pos | Peso | Det.Bar | Dif.Paq | Dif.Real | Dif.Op
    col_widths = [10, 16, 62, 18, 18, 22, 23, 22, 18, 24, 24]  # suma = 257mm = ancho_util
    headers    = ["ID", "COD", "PRODUCTO", "PAQ POS", "PAQ BAR", "DET POS", "PESO", "DET BAR", "DIF. PAQ.", "DIF REAL", "DIF OP"]
    aligns     = ["R", "L", "L", "R", "R", "R", "R", "R", "R", "R", "R"]
    # Jerarquía visual: ID/COD con menor peso, PRODUCTO en negrita, cantidades
    # absolutas (paq/det/peso) en texto neutro, diferencias con color semántico.
    jerarquias = ["muted", "muted", "primary", "neutral", "neutral", "neutral", "neutral", "neutral", "diff", "diff", "diff"]
    row_h = 7

    # cabecera de tabla (definida como helper para redibujarla en cada pagina
    # nueva: fpdf2 hace el salto de pagina automatico pero no repite el encabezado).
    def dibujar_cabecera_tabla():
        pdf.set_fill_color(242, 242, 242)
        pdf.set_draw_color(204, 204, 204)
        pdf.set_text_color(17, 17, 17)
        pdf.set_font(_FONT_FAMILY, "B", 7.5)
        for w, h, a in zip(col_widths, headers, aligns):
            pdf.cell(w, row_h, h, border=1, align=a, fill=True)
        pdf.ln()

    dibujar_cabecera_tabla()

    # filas de datos
    for idx, fila in enumerate(payload.filas):
        # Si la proxima fila no entra en la pagina, saltar manualmente y repetir
        # la cabecera arriba (nos adelantamos al auto page break de fpdf2, que
        # crearia la pagina sin encabezado de tabla).
        if pdf.get_y() + row_h > pdf.page_break_trigger:
            pdf.add_page()
            dibujar_cabecera_tabla()

        dif_oz_exacta = fila.difOnzasExactas if fila.difOnzasExactas is not None else fila.difOnzas
        dif_oz_pos = fila.difOnzasPos
        if dif_oz_pos is None and dif_oz_exacta is not None:
            # Unificamos granularidad con POS: incrementos de 0.5 oz.
            dif_oz_pos = round(dif_oz_exacta * 2.0) * 0.5

        valores = [
            fila.idProducto,
            fila.codigo,
            fila.nombre,
            _fmt_cantidad_paq(fila.paqPos),
            _fmt_cantidad_paq(fila.paqBar),
            _fmt_cantidad_oz(fila.detPos),
            _fmt_peso_gramos(fila.pesoGramos),
            _fmt_cantidad_oz(fila.detBar),
            _fmt_diff_paq(fila.difUnidades),
            _fmt_diff_oz(dif_oz_exacta),
            _fmt_diff_oz(dif_oz_pos),
        ]
        colores = [
            None, None, None,
            None, None, None, None, None,
            _color_diferencia(fila.difUnidades) if fila.difUnidades is not None else None,
            _color_diferencia(dif_oz_exacta) if dif_oz_exacta is not None else None,
            _color_diferencia(dif_oz_pos) if dif_oz_pos is not None else None,
        ]

        fondo = (245, 245, 245) if idx % 2 == 1 else (255, 255, 255)
        pdf.set_fill_color(*fondo)

        for w, val, align, color, jerarquia in zip(col_widths, valores, aligns, colores, jerarquias):
            if color:
                pdf.set_text_color(*color)
                pdf.set_font(_FONT_FAMILY, "B", 7.5)
            elif jerarquia == "muted":
                pdf.set_text_color(90, 90, 90)
                pdf.set_font(_FONT_FAMILY, "", 7)
            elif jerarquia == "primary":
                pdf.set_text_color(17, 17, 17)
                pdf.set_font(_FONT_FAMILY, "B", 8)
            elif jerarquia == "neutral":
                pdf.set_text_color(85, 85, 85)
                pdf.set_font(_FONT_FAMILY, "", 7.5)
            else:
                pdf.set_text_color(17, 17, 17)
                pdf.set_font(_FONT_FAMILY, "", 7.5)
            pdf.cell(w, row_h, str(val), border=1, align=align, fill=True)
        pdf.ln()

    pdf_bytes = bytes(pdf.output())

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'},
    )


# --- POUR COST (solo lectura, ver documentos/pour_cost/pourcost.md) ---
# Vistas fuente en adminerp/test_pos: v9_menubackstage, vw_pourcost_receta,
# vw_alm_producto_con_nombres, v9_cache_wac_producto. DDL versionado en
# querys/create_views_pourcost.sql (no aplica en este repo -- ya existen en
# test_pos, ver documentos/pour_cost/pourcost.md seccion 2).

ALMACEN_COSTOS_ID = 1  # Mismo almacen fijo que usa todo el motor de costos (WAC), no una decision de este modulo.


def _calcular_pour_cost_pct(costo_total: Decimal, precio_venta) -> Optional[Decimal]:
    """Pour cost % = costo / precio_venta x 100. None si no hay precio_venta valido (evita ZeroDivisionError)."""
    if precio_venta is None:
        return None
    precio = Decimal(str(precio_venta))
    if precio <= 0:
        return None
    return _decimal2(costo_total / precio * Decimal("100"))


def _calcular_precio_sugerido(costo_total: Decimal, target_pour_cost_pct) -> Optional[tuple[Decimal, Decimal]]:
    """Precio sugerido = costo_total / (target/100). Devuelve (exacto, redondeado a unidad entera) o
    None si el target no es un porcentaje valido. Redondeado a entero porque el 100% de los precios
    de venta reales en test_pos no usan centavos (ver documentos/pour_cost/pourcost.md, seccion 4)."""
    if target_pour_cost_pct is None:
        return None
    target = Decimal(str(target_pour_cost_pct))
    if target <= 0:
        return None
    exacto = costo_total / (target / Decimal("100"))
    redondeado = exacto.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return (_decimal2(exacto), redondeado)


def _tipo_parte_combo_es_opcional(tipo_parte_combo) -> bool:
    return str(tipo_parte_combo or "").strip().upper() == "OPCIONAL"


def _cantidad_unidad_base_simulada(ingrediente: dict) -> Decimal:
    receta = Decimal(str(ingrediente.get("cantidad_receta") or 0))
    if ingrediente.get("tipo_cantidad_combo") == "Unidad":
        return receta
    divisor = Decimal(str(ingrediente.get("unidades_detalle_por_base") or 0))
    if divisor <= 0:
        return Decimal("0")
    return receta / divisor


def _ingrediente_simulado_esta_incluido(ingrediente: dict) -> bool:
    if not _tipo_parte_combo_es_opcional(ingrediente.get("tipo_parte_combo")):
        return True
    return bool(ingrediente.get("incluido"))


def _calcular_costo_receta_simulado_crudo(ingredientes) -> Decimal:
    total = Decimal("0")
    for ingrediente in ingredientes:
        if not _ingrediente_simulado_esta_incluido(ingrediente):
            continue
        total += _cantidad_unidad_base_simulada(ingrediente) * Decimal(str(ingrediente.get("wac_actual") or 0))
    return total


def _calcular_costo_receta_simulado(ingredientes) -> Decimal:
    """Espejo puro del cálculo del modal: suma todos los PRINCIPAL y solo los OPCIONAL marcados."""
    total = _calcular_costo_receta_simulado_crudo(ingredientes)
    return _decimal2(total)


def _agregar_costo_receta(lineas) -> dict:
    """Agrupa lineas de vw_pourcost_receta (una fila por ingrediente) por id_combo_coctel, sumando
    cogs_ingrediente con Decimal para no arrastrar error de float. No toca precio_venta -- esa vista
    lo trae fijo a id_dia=1, se resuelve aparte contra v9_menubackstage (ver pourcost.md, seccion 8.2)."""
    combos: dict = {}
    for linea in lineas:
        id_combo = linea["id_combo_coctel"]
        combo = combos.get(id_combo)
        if combo is None:
            combo = {
                "codigo_combo": linea["codigo_combo"],
                "nombre_combo": linea["nombre_combo"],
                "descripcion_combo": linea["descripcion_combo"],
                "nombre_categoria_combo": linea["nombre_categoria_combo"],
                "costo_total": Decimal("0"),
                "costo_incompleto": False,
                "ingredientes": [],
            }
            combos[id_combo] = combo
        combo["costo_total"] += Decimal(str(linea["cogs_ingrediente"] or 0))
        if int(linea["sin_wac"] or 0) == 1:
            combo["costo_incompleto"] = True
        combo["ingredientes"].append(linea)
    return combos


def _float_o_none(valor) -> Optional[float]:
    return float(valor) if valor is not None else None


@app.get("/api/pourcost/menu", response_model=List[schemas.PourCostMenuItem])
def listar_pourcost_menu(
    id_dia: int = Query(1, ge=1, description="Horario de precio; 1 por defecto (ver pourcost.md, seccion 8.2)"),
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_usuario_administrador)
):
    """Menu activo (combos + productos sueltos) con su precio_venta para el id_dia pedido."""
    rows = db.execute(
        text("""
            SELECT codigo, nombre, precio_venta, descripcion, id_categoria, nombre_categoria,
                   tipo, id_origen, id_dia, fecha_precio
            FROM v9_menubackstage
            WHERE id_dia = :id_dia
            ORDER BY tipo, nombre
        """),
        {"id_dia": id_dia}
    ).mappings().all()

    return [
        schemas.PourCostMenuItem(
            codigo=row["codigo"],
            nombre=row["nombre"],
            precio_venta=_float_o_none(row["precio_venta"]),
            descripcion=row["descripcion"],
            id_categoria=row["id_categoria"],
            nombre_categoria=row["nombre_categoria"],
            tipo=row["tipo"],
            id_origen=row["id_origen"],
            id_dia=row["id_dia"],
            fecha_precio=row["fecha_precio"],
        )
        for row in rows
    ]


@app.get("/api/pourcost/recetas", response_model=List[schemas.PourCostReceta])
def listar_pourcost_recetas(
    id_dia: int = Query(1, ge=1, description="Horario de precio; 1 por defecto (ver pourcost.md, seccion 8.2)"),
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_usuario_administrador)
):
    """Costo de receta por combo/coctel (vw_pourcost_receta, agrupado) + precio_venta del id_dia pedido.

    vw_pourcost_receta trae su propio precio_venta fijo a id_dia=1 -- se ignora esa columna y el
    precio se resuelve aparte contra v9_menubackstage filtrando por el id_dia recibido (ver
    documentos/pour_cost/pourcost.md, seccion 8, punto 2)."""
    lineas = db.execute(
        text("""
            SELECT id_combo_coctel, codigo_combo, nombre_combo, descripcion_combo, nombre_categoria_combo,
                   id_producto, codigo_producto, nombre_producto, nombre_categoria_producto,
                   cantidad_receta, tipo_cantidad_combo, tipo_parte_combo, unidad_base, medida_unidad_base,
                   unidades_detalle_por_base, unidad_detalle, wac_actual, sin_wac, cantidad_unidad_base,
                   cogs_ingrediente
            FROM vw_pourcost_receta
            ORDER BY id_combo_coctel
        """)
    ).mappings().all()

    precios = db.execute(
        text("""
            SELECT id_origen, precio_venta
            FROM v9_menubackstage
            WHERE tipo = 'combo' AND id_dia = :id_dia
        """),
        {"id_dia": id_dia}
    ).mappings().all()
    precio_por_combo = {row["id_origen"]: row["precio_venta"] for row in precios}

    combos = _agregar_costo_receta(lineas)

    salida = []
    for id_combo, combo in combos.items():
        precio_venta = precio_por_combo.get(id_combo)
        salida.append(
            schemas.PourCostReceta(
                id_combo_coctel=id_combo,
                codigo_combo=combo["codigo_combo"],
                nombre_combo=combo["nombre_combo"],
                descripcion_combo=combo["descripcion_combo"],
                nombre_categoria_combo=combo["nombre_categoria_combo"],
                id_dia=id_dia,
                precio_venta=_float_o_none(precio_venta),
                costo_total_receta=float(_decimal2(combo["costo_total"])),
                costo_incompleto=combo["costo_incompleto"],
                pour_cost_pct=_float_o_none(_calcular_pour_cost_pct(combo["costo_total"], precio_venta)),
                ingredientes=[
                    schemas.PourCostIngrediente(
                        id_producto=linea["id_producto"],
                        codigo_producto=linea["codigo_producto"],
                        nombre_producto=linea["nombre_producto"],
                        nombre_categoria_producto=linea["nombre_categoria_producto"],
                        cantidad_receta=float(linea["cantidad_receta"]),
                        tipo_cantidad_combo=linea["tipo_cantidad_combo"],
                        tipo_parte_combo=linea["tipo_parte_combo"],
                        unidad_base=linea["unidad_base"],
                        medida_unidad_base=_float_o_none(linea["medida_unidad_base"]),
                        unidades_detalle_por_base=_float_o_none(linea["unidades_detalle_por_base"]),
                        unidad_detalle=linea["unidad_detalle"],
                        wac_actual=float(linea["wac_actual"] or 0),
                        sin_wac=bool(int(linea["sin_wac"] or 0)),
                        cantidad_unidad_base=float(linea["cantidad_unidad_base"]),
                        cogs_ingrediente=float(linea["cogs_ingrediente"] or 0),
                    )
                    for linea in combo["ingredientes"]
                ],
            )
        )
    return salida


@app.get("/api/pourcost/productos", response_model=List[schemas.PourCostProducto])
def listar_pourcost_productos(
    id_dia: int = Query(1, ge=1, description="Horario de precio; 1 por defecto (ver pourcost.md, seccion 8.2)"),
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_usuario_administrador)
):
    """Productos sueltos comandables (sin receta): costo = su WAC directo. No pasan por
    vw_pourcost_receta, que solo cubre combos (bar_detalle_combo_bar)."""
    rows = db.execute(
        text("""
            SELECT m.id_origen AS id_producto, m.codigo, m.nombre, m.precio_venta,
                   m.id_categoria, m.nombre_categoria, m.id_dia,
                   w.wac_unitario, w.fecha_actualizacion
            FROM v9_menubackstage m
            LEFT JOIN v9_cache_wac_producto w
                   ON w.id_producto = m.id_origen AND w.id_almacen = :id_almacen
            WHERE m.tipo = 'producto' AND m.id_dia = :id_dia
            ORDER BY m.nombre
        """),
        {"id_dia": id_dia, "id_almacen": ALMACEN_COSTOS_ID}
    ).mappings().all()

    salida = []
    for row in rows:
        wac = row["wac_unitario"]
        salida.append(
            schemas.PourCostProducto(
                id_producto=row["id_producto"],
                codigo=row["codigo"],
                nombre=row["nombre"],
                id_categoria=row["id_categoria"],
                nombre_categoria=row["nombre_categoria"],
                id_dia=row["id_dia"],
                precio_venta=_float_o_none(row["precio_venta"]),
                wac_unitario=_float_o_none(wac),
                sin_wac=wac is None,
                pour_cost_pct=_float_o_none(_calcular_pour_cost_pct(Decimal(str(wac)), row["precio_venta"])) if wac is not None else None,
                fecha_actualizacion_wac=row["fecha_actualizacion"],
            )
        )
    return salida


@app.get("/api/pourcost/insumos", response_model=List[schemas.PourCostInsumo])
def listar_pourcost_insumos(
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_usuario_administrador)
):
    """Catalogo completo de insumos (vw_alm_producto_con_nombres + WAC), para la simulacion 'agregar
    ingrediente' del sandbox de POUR COST (frontend, en memoria). No depende de id_dia."""
    rows = db.execute(
        text("""
            SELECT vc.id, vc.nombre, vc.descripcion, vc.codigo, vc.categoria, vc.proveedor, vc.nombre_barra,
                   vc.medida, vc.nombre_unidad_medida, vc.cantidad_detalle, vc.nombre_unidad_medida_detalle,
                   vc.ind_permite_comandar, vc.nombre_ind_permite_comandar,
                   w.wac_unitario, w.fecha_actualizacion
            FROM vw_alm_producto_con_nombres vc
            LEFT JOIN v9_cache_wac_producto w
                   ON w.id_producto = vc.id AND w.id_almacen = :id_almacen
            ORDER BY vc.nombre
        """),
        {"id_almacen": ALMACEN_COSTOS_ID}
    ).mappings().all()

    return [
        schemas.PourCostInsumo(
            id=row["id"],
            nombre=row["nombre"],
            descripcion=row["descripcion"],
            codigo=row["codigo"],
            categoria=row["categoria"],
            proveedor=row["proveedor"],
            nombre_barra=row["nombre_barra"],
            medida=_float_o_none(row["medida"]),
            nombre_unidad_medida=row["nombre_unidad_medida"],
            cantidad_detalle=_float_o_none(row["cantidad_detalle"]),
            nombre_unidad_medida_detalle=row["nombre_unidad_medida_detalle"],
            ind_permite_comandar=row["ind_permite_comandar"],
            nombre_ind_permite_comandar=row["nombre_ind_permite_comandar"],
            wac_unitario=_float_o_none(row["wac_unitario"]),
            sin_wac=row["wac_unitario"] is None,
            fecha_actualizacion_wac=row["fecha_actualizacion"],
        )
        for row in rows
    ]


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