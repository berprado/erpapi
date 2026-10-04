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
from datetime import datetime, timedelta, timezone, date
import logging
from decimal import Decimal, ROUND_HALF_UP

logger = logging.getLogger(__name__)
from config import settings
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from branding import get_brand, build_manifest

# Marca visual de esta instancia desplegada (logo/paleta). No cambia en
# runtime: una instancia = una BRAND_ID = una marca (ver branding.py).
_brand_activa = get_brand(settings.BRAND_ID)

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


MARGEN_CAPTURA_CRUDA_OZ = Decimal("0.255")


def _obtener_capturas_crudas_por_conteo(
    db: Session, id_operacion: int, conteos: dict[int, tuple[float, float]]
) -> dict[int, models.PaloteoRegistroCrudo]:
    """Última captura cruda de cada producto que explica su conteo registrado.

    app_paloteo_registro_crudo no guarda id_barra: con más de una barra por
    operativa, la última captura de un producto puede ser la de la otra barra.
    Solo se acepta una captura con las mismas botellas cerradas que el conteo
    (paq, det) de esta barra y cuyas onzas pudieron redondear a det: a no más
    de 0.25 oz (media grilla POS) más 0.005 (onzas_calculadas se guarda con 2
    decimales, así que 10.25 puede venir de un exacto 10.249 registrado como
    10.0; re-redondear el guardado daría 10.5). Si ninguna coincide, el
    producto queda sin captura y quien consume cae a lo registrado en el POS.
    """
    if not conteos:
        return {}

    registros = db.query(models.PaloteoRegistroCrudo).filter(
        models.PaloteoRegistroCrudo.id_operacion == id_operacion,
        models.PaloteoRegistroCrudo.id_producto.in_(list(conteos)),
    ).order_by(models.PaloteoRegistroCrudo.id.desc()).all()

    capturas = {}
    for registro in registros:
        if registro.id_producto in capturas:
            continue
        paq, det = conteos[registro.id_producto]
        if float(registro.botellas_cerradas or 0) != float(paq or 0):
            continue
        onzas = Decimal(str(registro.onzas_calculadas or 0))
        if abs(onzas - Decimal(str(det or 0))) > MARGEN_CAPTURA_CRUDA_OZ:
            continue
        capturas[registro.id_producto] = registro
    return capturas


def _pesos_de_captura_cruda(registro: models.PaloteoRegistroCrudo) -> list:
    try:
        pesos = json.loads(registro.pesos_abiertas) if registro.pesos_abiertas else []
    except (TypeError, json.JSONDecodeError):
        pesos = []
    return pesos if isinstance(pesos, list) else []


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


def _validar_operacion_inicio_cierre(db: Session, id_operacion: int, bloquear: bool = False) -> models.Operacion:
    # bloquear=True: SELECT ... FOR UPDATE sobre la fila de ope_operacion (por PK,
    # una sola fila) hasta el commit/rollback del request. Serializa escrituras
    # concurrentes de la misma operativa sin tocar ninguna otra fila del POS.
    consulta = db.query(models.Operacion).filter(models.Operacion.id == id_operacion)
    if bloquear:
        consulta = consulta.with_for_update()
    operacion = consulta.first()
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

        # `perfiles` ya filtra pesable==1: es la unica señal correcta de "este
        # producto tiene pesaje real que validar". Antes se exigia ademas
        # `configs_producto[0].pesable == 1` (la PRIMERA fila del producto,
        # sin ORDER BY -- orden arbitrario de MySQL), asumiendo una sola fila
        # de config por producto. Esa asuncion se rompe con normalidad desde
        # que trg_alm_producto_after_insert crea una fila fantasma
        # 'Estándar' (pesable=0) para todo producto nuevo (ver "Triggers de
        # base de datos" en README.md): un producto con multiples modelos de
        # botella (perfil "Estándar" fantasma sin promover + un modelo real
        # con nombre propio, pesable=1) podia caer con la fantasma primera en
        # `configs_producto` y saltarse toda validacion de peso en silencio
        # (total_onzas quedaba en 0 sin lanzar 400, aunque el perfil pesable
        # real existiera y el payload lo referenciara por perfil_id).
        perfiles = sorted([cfg for cfg in configs_producto if cfg.pesable == 1], key=lambda cfg: cfg.id or 0)

        total_onzas = 0.0
        if perfiles:
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

    # 1. Validar Operación, bloqueando su fila: dos capturas simultáneas de la
    # misma operativa (doble tap, dos dispositivos) quedan en fila en vez de
    # pasar ambas el chequeo de duplicado de abajo y crear dos cabeceras.
    _validar_operacion_inicio_cierre(db, payload.id_operacion, bloquear=True)

    barra_operativa = _resolver_barra_operativa(request)
    if payload.id_barra != barra_operativa:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"La barra enviada ({payload.id_barra}) no coincide con la barra operativa configurada ({barra_operativa})."
        )

    # Fix #5: Prevenir inventario duplicado por operación y barra.
    # Si ya existe una cabecera HAB para este id_operacion en esta barra,
    # rechazamos el registro. Cada barra de la operativa tiene su propia
    # cabecera: el ajuste/consolidación ya las resuelve por (operación, barra).
    # with_for_update() no es por el bloqueo en sí (ya lo da la fila de
    # ope_operacion) sino para forzar una lectura actual: con REPEATABLE READ la
    # sesión ya tiene snapshot desde la consulta de autenticación, y un SELECT
    # normal no vería la cabecera que el request que esperaba acaba de commitear.
    # Usa el índice de id_operacion, así que solo bloquea el rango de esa operativa.
    inventario_existente = db.query(models.InventarioFisicoPOS).filter(
        models.InventarioFisicoPOS.id_operacion == payload.id_operacion,
        models.InventarioFisicoPOS.id_barra == payload.id_barra,
        models.InventarioFisicoPOS.estado == 'HAB'
    ).with_for_update().first()
    if inventario_existente:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un inventario registrado para esta operación y barra (ID: {inventario_existente.id}). No se puede registrar dos veces."
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
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_usuario_actual)
):
    # Sin X-Barra-Id (cliente viejo) resuelve la barra por defecto, como antes.
    id_barra = _resolver_barra_operativa(request)
    inventario = db.query(models.InventarioFisicoPOS).filter(
        models.InventarioFisicoPOS.id_operacion == id_operacion,
        models.InventarioFisicoPOS.id_barra == id_barra,
        models.InventarioFisicoPOS.estado == 'HAB'
    ).first()

    if not inventario:
        raise HTTPException(status_code=404, detail="No existe inventario físico registrado para esta operación y barra.")

    operacion = db.query(models.Operacion).filter(models.Operacion.id == id_operacion).first()
    puede_editar = bool(operacion and operacion.estado_operacion == 24)

    detalles_db = db.query(models.DetalleFisicoPOS).filter(
        models.DetalleFisicoPOS.id_inventario_fisico == inventario.id,
        models.DetalleFisicoPOS.estado == 'HAB'
    ).all()
    capturas = _obtener_capturas_crudas_por_conteo(db, inventario.id_operacion, {
        detalle.id_producto: (detalle.cantidad_unidad, detalle.cantidad_detalle)
        for detalle in detalles_db
    })

    detalles = [
        {
            "id_producto": detalle.id_producto,
            "botellas_cerradas": float(detalle.cantidad_unidad or 0),
            "onzas_pos": float(detalle.cantidad_detalle or 0),
            "pesos_abiertas": (
                _pesos_de_captura_cruda(capturas[detalle.id_producto])
                if detalle.id_producto in capturas else []
            ),
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


# Unidades de medida (alm_producto.p_unidad_medida) que identifican un
# producto pesable. Reemplaza desde 2026-09-09 al criterio anterior
# (ind_permite_comandar=71 + categoria fuera de una lista negra de 9
# categorias) -- ver "Pesaje config es synced from alm_producto by DB
# triggers" en CLAUDE.md y CHANGELOG. 11 = unidad usada por todo el catalogo
# de licores/vinos pesables existente (verificado 1:1 contra
# app_producto_pesaje_config_api.pesable=1 antes de este cambio); 61 =
# barril/keg (ej. BARRIL PACEÑA 50L), la unica excepcion pesable dentro de
# una categoria (CERVEZAS) que en general no se pesa -- antes requeria un
# backfill manual por SQL, ahora la deriva sola cualquier producto nuevo con
# esa unidad.
UNIDADES_MEDIDA_PESABLES = (11, 61)


def _producto_deberia_ser_pesable(db: Session, id_producto: int) -> bool:
    """Mismo criterio que usan trg_alm_producto_after_insert/after_update para
    derivar `pesable` desde el catalogo: p_unidad_medida en
    UNIDADES_MEDIDA_PESABLES. Se usa para permitir "promover" un perfil
    pesable=0 sin depender de que el listado ya lo haya filtrado antes."""
    p_unidad_medida = db.execute(
        text("SELECT p_unidad_medida FROM alm_producto WHERE id = :id_producto LIMIT 1"),
        {"id_producto": id_producto}
    ).scalar()
    if p_unidad_medida is None:
        return False
    return int(p_unidad_medida) in UNIDADES_MEDIDA_PESABLES


@app.get("/api/pesaje/categorias", response_model=List[schemas.CategoriaItem])
def listar_categorias_pesaje(
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_usuario_administrador)
):
    """Lista de categorías habilitadas, para el filtro del módulo PESAJE.

    No filtra por categoría: la derivación de "qué es pesable" vive en
    UNIDADES_MEDIDA_PESABLES (triggers y _producto_deberia_ser_pesable), no
    en la categoría del producto. Desde el backfill de 2026-09-08
    app_producto_pesaje_config_api tiene fila (pesable=0 o 1) para todo el
    catálogo HAB, categorías antes excluidas por la lógica vieja incluidas —
    filtrarlas aquí las escondía del selector aunque tuvieran perfiles reales
    que listar (ej. CERVEZAS, con productos no pesables y con la excepción
    pesable del barril).
    """
    rows = db.execute(
        text("""
            SELECT id, nombre FROM alm_categoria
            WHERE estado = 'HAB'
            ORDER BY nombre
        """)
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
    """Listado de perfiles de pesaje (tabla app_producto_pesaje_config_api vía v9_pesaje_config_api), para el módulo PESAJE.

    No filtra por categoría: la derivación de "qué es pesable" vive en
    UNIDADES_MEDIDA_PESABLES, no en la categoría del producto. Desde el
    backfill de 2026-09-08, app_producto_pesaje_config_api ya tiene fila real
    (pesable=0 o 1) para todo el catálogo HAB, así que filtrar por categoría
    escondía perfiles legítimos de ambas pestañas (ej. CERVEZAS: la mayoría
    de sus productos son pesable=0, pero el barril es la excepción
    pesable=1 real).
    """
    condiciones = ["1=1"]
    parametros = {}

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
               vw.nombre_ind_permite_comandar, vw.p_unidad_medida
        FROM v9_pesaje_config_api pc
        LEFT JOIN vw_alm_producto_con_nombres vw ON vw.id = pc.id_producto
        {where_sql}
        ORDER BY pc.nombre_producto ASC, pc.nombre_perfil ASC
    """)

    rows = list(db.execute(query, parametros).mappings().all())

    # Para la pestaña INCOMPLETOS, además de perfiles pesables con campos nulos,
    # incluimos los productos pesables habilitados que aún no tienen ninguna
    # configuración activa en app_producto_pesaje_config_api.
    if pesable == 1:
        condiciones_sin_config = [
            "a.estado = 'HAB'",
            "a.p_unidad_medida IN :pesables",
            "NOT EXISTS (SELECT 1 FROM app_producto_pesaje_config_api p WHERE p.id_producto_almacen = a.id AND p.estado = 'HAB')",
        ]
        parametros_sin_config = {"pesables": UNIDADES_MEDIDA_PESABLES}

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
                   vw.nombre_ind_permite_comandar,
                   a.p_unidad_medida
            FROM alm_producto a
            LEFT JOIN alm_categoria c ON c.id = a.id_categoria
            LEFT JOIN vw_alm_producto_con_nombres vw ON vw.id = a.id
            {where_sin_config}
            ORDER BY a.nombre ASC
        """).bindparams(bindparam("pesables", expanding=True))

        rows_sin_config = db.execute(query_sin_config, parametros_sin_config).mappings().all()
        rows.extend(rows_sin_config)

    rows.sort(key=lambda row: (row["nombre_producto"] or "", row["nombre_perfil"] or ""))

    salida = []
    for row in rows:
        es_vino = int(row["id_categoria"] or 0) == ID_CATEGORIA_VINOS and int(row["pesable"] or 0) == 1
        tara = TARA_VINOS if es_vino else row["tara"]
        gramos_por_oz = GRAMOS_POR_OZ_VINOS if es_vino else row["gramos_por_oz"]
        p_unidad_medida = row["p_unidad_medida"]
        catalogo_permite_pesar = p_unidad_medida is not None and int(p_unidad_medida) in UNIDADES_MEDIDA_PESABLES

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
                catalogo_permite_pesar=catalogo_permite_pesar,
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
                # Solo /pendientes trae con_movimiento; /catalogo/buscar no lo usa.
                "sin_movimiento": row.get("con_movimiento", 1) == 0,
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


# Productos con movimiento en una barra durante una operativa (parámetros
# :id_barra, :id_operacion_movimiento). Cada rama es una fuente que mueve
# bar_inventario de ESA barra; los estados están verificados contra el POS
# (ver docstring de /api/inventario/pendientes).
_SQL_PRODUCTOS_CON_MOVIMIENTO = """
                -- Comandas de la barra: procesadas, o anuladas que llegaron a imprimirse.
                SELECT DISTINCT d.id_producto_receta AS id_producto, 1 AS con_movimiento
                FROM comandas_v9_detallada d
                INNER JOIN bar_comanda c ON d.id_comanda = c.id
                WHERE c.id_operacion = :id_operacion_movimiento
                AND c.id_barra = :id_barra
                AND d.id_producto_receta IS NOT NULL
                AND (
                    c.estado_comanda = 26
                    OR (
                        c.estado_comanda = 27
                        AND EXISTS (SELECT 1 FROM bar_comanda_impresion ci WHERE ci.id_comanda = c.id)
                    )
                )

                UNION ALL

                -- Traspasos almacén -> barra ya recepcionados (21 EN BARRA).
                SELECT DISTINCT dsi.id_producto AS id_producto, 1 AS con_movimiento
                FROM alm_salida_inventario asi
                INNER JOIN alm_detalle_salida_inv dsi ON dsi.id_salida_inventario = asi.id
                WHERE asi.id_operacion = :id_operacion_movimiento
                AND asi.estado = 'HAB'
                AND dsi.estado = 'HAB'
                AND asi.id_barra = :id_barra
                AND asi.ind_tipo_movimiento = 83
                AND asi.ind_tipo_salida = 34
                AND asi.ind_estado_salida = 21

                UNION ALL

                -- Devoluciones barra -> almacén procesadas (tipo 76 MOVIMIENTO, 20 PROCESADO).
                SELECT DISTINCT bdsi.id_producto AS id_producto, 1 AS con_movimiento
                FROM bar_salida_inventario bsi
                INNER JOIN bar_detalle_salida_inv bdsi ON bdsi.id_salida_inventario = bsi.id
                WHERE bsi.id_operacion = :id_operacion_movimiento
                AND bsi.id_barra = :id_barra
                AND bsi.ind_tipo_salida = 76
                AND bsi.ind_estado_salida = 20
                AND bsi.estado = 'HAB'
                AND bdsi.estado = 'HAB'
"""


@app.get("/api/inventario/traspasos-sin-recepcion", response_model=List[schemas.TraspasoSinRecepcion])
def listar_traspasos_sin_recepcion(
    request: Request,
    id_operacion: int = Query(..., gt=0, description="Operativa activa"),
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_usuario_actual)
):
    """
    Traspasos almacén -> barra de la operativa ya despachados por el almacén
    (20 PROCESADO) que la barra todavía no recepcionó. Sus unidades están en
    tránsito: salieron del almacén pero bar_inventario aún no las suma. Si se
    palotea así y las botellas ya están físicamente en la barra, el ajuste las
    registra como sobrante y la recepción posterior las vuelve a sumar (stock
    duplicado). La PWA lo muestra como advertencia antes de contar.

    Solo la operativa activa: el respaldo de Beer Garden arrastra traspasos de
    2024 que quedaron en 20 para siempre; avisarlos cada noche sería ruido.
    """
    id_barra = _resolver_barra_operativa(request)
    filas = db.execute(text("""
        SELECT asi.id AS id_salida, asi.fecha_salida, asi.id_operacion,
               dsi.id_producto, a.nombre, dsi.cantidad, dsi.ind_paq_detalle
        FROM alm_salida_inventario asi
        INNER JOIN alm_detalle_salida_inv dsi ON dsi.id_salida_inventario = asi.id
        LEFT JOIN alm_producto a ON a.id = dsi.id_producto
        WHERE asi.id_barra = :id_barra
          AND asi.id_operacion = :id_operacion
          AND asi.estado = 'HAB'
          AND dsi.estado = 'HAB'
          AND asi.ind_tipo_movimiento = 83
          AND asi.ind_tipo_salida = 34
          AND asi.ind_estado_salida = 20
        ORDER BY asi.id, a.nombre
    """), {"id_barra": id_barra, "id_operacion": id_operacion}).mappings().all()

    traspasos: dict[int, dict] = {}
    for fila in filas:
        traspaso = traspasos.setdefault(fila["id_salida"], {
            "id_salida": fila["id_salida"],
            "fecha_salida": fila["fecha_salida"],
            "id_operacion": fila["id_operacion"],
            "productos": [],
        })
        traspaso["productos"].append({
            "id_producto": fila["id_producto"],
            "nombre": fila["nombre"] or "",
            "cantidad": float(fila["cantidad"] or 0),
            "por_unidad": str(fila["ind_paq_detalle"]) == "1",
        })
    return list(traspasos.values())


@app.get("/api/inventario/pendientes", response_model=List[schemas.ProductoPendiente])
def obtener_productos_pendientes(
    request: Request,
    id_operacion: Optional[int] = Query(None, gt=0, description="Operativa activa: suma los productos ya contados en ella"),
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_usuario_actual) # <-- CANDADO AQUÍ
    ):
    """
    Devuelve la lista de productos que tuvieron movimiento EN ESTA BARRA durante
    la operativa, junto con su stock ideal y parámetros de pesaje.

    Movimiento (criterio validado en vivo contra el POS, test_pos operativa 163,
    2026-10-01; detalle en _SQL_PRODUCTOS_CON_MOVIMIENTO):
    - comandas de la barra procesadas (26), o anuladas (27) que llegaron a
      imprimirse (fila en bar_comanda_impresion): el POS descuenta al procesar y
      devuelve al anular, pero un trago servido y luego anulado sí movió la
      botella. 25 PENDIENTE (incluye las bloqueadas por stock) no movió nada.
      Venta (50) y cortesía (51) por igual.
    - traspasos almacén -> barra recepcionados (21 EN BARRA).
    - devoluciones barra -> almacén procesadas (bar_salida_inventario tipo 76,
      estado 20). Nunca tipo 77: son las bajas por ajuste de esta misma API.

    Antes las comandas no se filtraban por barra (un producto vendido en la barra
    2 aparecía "colado" en el paloteo de la barra 1) y se tomaban de
    MAX(id_operacion) de bar_comanda en vez de la operativa activa.

    Con id_operacion (la PWA siempre lo envía) se usa esa operativa y se suman
    los productos ya contados en el paloteo de esa operativa/barra aunque no
    tengan movimiento (agregados a mano desde el catálogo), marcados
    sin_movimiento=True. Sin esto desaparecían de PALOTEO 1/2/3 al recargar la
    página. Sin id_operacion (cliente viejo) se usa la última operativa con
    comandas, como antes, y no se suman los contados.
    """
    id_barra_operativa = _resolver_barra_operativa(request)
    id_operacion_movimiento = id_operacion or db.execute(
        text("SELECT MAX(id_operacion) FROM bar_comanda")
    ).scalar()

    query = text("""
        SELECT
            a.id AS id_producto, a.codigo, a.nombre, a.ind_permite_comandar,
            i.cantidad_paq AS stock_ideal_unidades, i.cantidad_detalle AS stock_ideal_onzas,
            i.id_categoria, i.categoria_nombre,
            p.id AS perfil_id, p.pesable, p.nombre_perfil, p.peso_bruto, p.tara, p.gramos_por_oz, p.tolerancia_oz, p.barcode,
            a.cantidad_detalle AS onzas_por_botella_llena,
            mov.con_movimiento
        FROM (
            SELECT u.id_producto, MAX(u.con_movimiento) AS con_movimiento
            FROM (
                """ + _SQL_PRODUCTOS_CON_MOVIMIENTO + """

                UNION ALL

                -- Ya contados en esta operativa/barra (sin id_operacion no matchea nada).
                SELECT DISTINCT df.id_producto AS id_producto, 0 AS con_movimiento
                FROM bar_detalle_fisico df
                INNER JOIN bar_inventario_fisico f ON f.id = df.id_inventario_fisico
                WHERE f.id_operacion = :id_operacion
                AND f.id_barra = :id_barra
                AND f.estado = 'HAB'
                AND df.estado = 'HAB'
            ) u
            GROUP BY u.id_producto
        ) mov
        INNER JOIN alm_producto a ON mov.id_producto = a.id
        -- id_barra filtrado explícitamente: vista_inventario_barra_con_filtro NO
        -- viene fijada a la barra activa (no filtra por id_barra en su propia
        -- definición) -- en un entorno con más de una barra con movimiento,
        -- un producto puede tener una fila en bar_inventario por cada una,
        -- duplicando esta fila (y con ella cada perfil de pesaje del LEFT JOIN
        -- de abajo) tantas veces como barras tenga. Ver hallazgo en sesión UX.
        INNER JOIN vista_inventario_barra_con_filtro i ON a.id = i.id_almacen AND i.id_barra = :id_barra
        LEFT JOIN app_producto_pesaje_config_api p ON a.id = p.id_producto_almacen AND p.estado = 'HAB'
        ORDER BY a.nombre ASC, p.id ASC;

          """)

    rows = db.execute(query, {
        "id_barra": id_barra_operativa,
        "id_operacion": id_operacion,
        "id_operacion_movimiento": id_operacion_movimiento,
    }).mappings().all()

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
    # id_barra se usa explícitamente en el JOIN de abajo: vista_inventario_barra_con_filtro
    # NO viene fijada a la barra activa (no filtra por id_barra en su propia
    # definición) -- en un entorno con más de una barra, un producto puede
    # tener una fila en bar_inventario por cada una, duplicando esta fila (y
    # cada perfil de pesaje del LEFT JOIN de abajo) tantas veces como barras
    # tenga. Ver hallazgo en sesión UX / mismo fix que en /pendientes.
    id_barra_operativa = _resolver_barra_operativa(request)

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
        INNER JOIN vista_inventario_barra_con_filtro i ON a.id = i.id_almacen AND i.id_barra = :id_barra
        LEFT JOIN app_producto_pesaje_config_api p ON a.id = p.id_producto_almacen AND p.estado = 'HAB'
        WHERE a.estado = 'HAB'
          {filtro_nombre}
        ORDER BY a.nombre ASC, p.id ASC
        LIMIT :limite
    """)

    rows = db.execute(query, {
        "patron": f"%{patron}%",
        "limite": limite,
        "id_barra": id_barra_operativa,
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
              AND v.id_barra = :id_barra
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


ALMACEN_WAC_AJUSTES_ID = 1


def _calcular_valor_varianza(delta: dict, costo: dict | None) -> dict:
    """Valora un delta operativo con el WAC y rendimiento capturados.

    El signo se conserva como real - ideal: un importe negativo representa un
    faltante. El delta exacto se guarda para auditoría, pero no altera el monto
    que explica los movimientos de ajuste del POS.
    """
    if (Decimal(str(delta["delta_paq"])) == 0
            and Decimal(str(delta["delta_det_operativo"])) == 0):
        # Sin variacion operativa no hay nada que valorar: vale 0 Bs aunque el
        # producto no tenga WAC. Antes caia en SIN_WAC y un producto contado que
        # cuadraba se reportaba como "sin valoracion".
        return {"estado_valoracion": "VALORIZADO", "valor_paq": Decimal("0"),
                "valor_detalle_operativo": Decimal("0"), "valor_neto": Decimal("0")}

    wac = None if costo is None else costo.get("wac_snapshot")
    if wac is None:
        return {"estado_valoracion": "SIN_WAC", "valor_paq": None,
                "valor_detalle_operativo": None, "valor_neto": None}

    wac_decimal = Decimal(str(wac))
    if wac_decimal <= 0:
        return {"estado_valoracion": "WAC_INVALIDO", "valor_paq": None,
                "valor_detalle_operativo": None, "valor_neto": None}

    valor_paq = Decimal(str(delta["delta_paq"])) * wac_decimal
    delta_detalle = Decimal(str(delta["delta_det_operativo"]))
    if delta_detalle == 0:
        return {
            "estado_valoracion": "VALORIZADO",
            "valor_paq": valor_paq,
            "valor_detalle_operativo": Decimal("0"),
            "valor_neto": valor_paq,
        }

    rendimiento = None if costo is None else costo.get("rendimiento_por_envase")
    if rendimiento is None or Decimal(str(rendimiento)) <= 0:
        return {"estado_valoracion": "RENDIMIENTO_INVALIDO", "valor_paq": valor_paq,
                "valor_detalle_operativo": None, "valor_neto": None}

    valor_detalle = delta_detalle / Decimal(str(rendimiento)) * wac_decimal
    return {
        "estado_valoracion": "VALORIZADO",
        "valor_paq": valor_paq,
        "valor_detalle_operativo": valor_detalle,
        "valor_neto": valor_paq + valor_detalle,
    }


def _enriquecer_deltas_con_valoracion(db: Session, deltas: list[dict]) -> list[dict]:
    """Añade snapshots de WAC/rendimiento y su valoración a los deltas dados."""
    if not deltas:
        return deltas

    ids_producto = [delta["id_producto"] for delta in deltas]
    query_costos = text("""
        SELECT p.id AS id_producto, p.cantidad_detalle AS rendimiento_por_envase,
               umd.nombre AS unidad_detalle, w.wac_actual AS wac_snapshot,
               w.fecha_actualizacion AS fecha_actualizacion_wac
        FROM alm_producto p
        LEFT JOIN parameter_table umd
               ON umd.id = p.p_unidad_medida_detalle
              AND umd.id_master = 4
              AND umd.estado = 'HAB'
        LEFT JOIN cache_wac_producto w
               ON w.id_producto = p.id
              AND w.id_almacen = :id_almacen
        WHERE p.id IN :ids_producto
    """).bindparams(bindparam("ids_producto", expanding=True))
    filas = db.execute(query_costos, {
        "ids_producto": ids_producto,
        "id_almacen": ALMACEN_WAC_AJUSTES_ID,
    }).mappings().all()
    costos = {fila["id_producto"]: dict(fila) for fila in filas}

    for delta in deltas:
        costo = costos.get(delta["id_producto"])
        valoracion = _calcular_valor_varianza(delta, costo)
        delta.update({
            "id_almacen_wac": ALMACEN_WAC_AJUSTES_ID,
            "rendimiento_por_envase": (
                float(costo["rendimiento_por_envase"])
                if costo and costo["rendimiento_por_envase"] is not None else None
            ),
            "unidad_detalle": costo["unidad_detalle"] if costo else None,
            "wac_snapshot": (
                float(costo["wac_snapshot"])
                if costo and costo["wac_snapshot"] is not None else None
            ),
            "fecha_actualizacion_wac": (
                costo["fecha_actualizacion_wac"] if costo else None
            ),
            "origen_wac": "cache_wac_producto",
            **{
                clave: float(valor) if isinstance(valor, Decimal) else valor
                for clave, valor in valoracion.items()
            },
        })
    return deltas


def _resumir_valoracion_varianzas(deltas: list[dict]) -> dict:
    """Resume importes operativos sin mezclar líneas no valorizables con Bs 0."""
    valores = [
        Decimal(str(delta["valor_neto"]))
        for delta in deltas
        if delta.get("estado_valoracion") == "VALORIZADO"
        and delta.get("valor_neto") is not None
    ]
    return {
        "faltantes": float(sum((-valor for valor in valores if valor < 0), Decimal("0"))),
        "sobrantes": float(sum((valor for valor in valores if valor > 0), Decimal("0"))),
        "neto": float(sum(valores, Decimal("0"))),
        "productos_sin_valoracion": sum(
            1 for delta in deltas if delta.get("estado_valoracion") != "VALORIZADO"
        ),
    }


def _serializar_snapshot_varianza(snapshot: models.VarianzaInventario) -> dict:
    """Adapta un snapshot persistido al contrato de deltas del preview."""
    return {
        "id_producto": snapshot.id_producto,
        "id_categoria": snapshot.id_categoria,
        "pesable": 0,
        "tolerancia_oz": 0.0,
        "delta_paq": float(snapshot.delta_paq),
        "delta_det_exacto": float(snapshot.delta_det_exacto),
        "delta_det_operativo": float(snapshot.delta_det_operativo),
        "id_almacen_wac": snapshot.id_almacen,
        "rendimiento_por_envase": (
            float(snapshot.rendimiento_por_envase)
            if snapshot.rendimiento_por_envase is not None else None
        ),
        "unidad_detalle": snapshot.unidad_detalle,
        "wac_snapshot": float(snapshot.wac_snapshot) if snapshot.wac_snapshot is not None else None,
        "fecha_actualizacion_wac": snapshot.fecha_actualizacion_wac,
        "origen_wac": snapshot.origen_wac,
        "estado_valoracion": snapshot.estado_valoracion,
        "valor_paq": float(snapshot.valor_paq) if snapshot.valor_paq is not None else None,
        "valor_detalle_operativo": (
            float(snapshot.valor_detalle_operativo)
            if snapshot.valor_detalle_operativo is not None else None
        ),
        "valor_neto": float(snapshot.valor_neto) if snapshot.valor_neto is not None else None,
    }


# Claves únicas que delatan una aplicación duplicada de ajustes (DDL en
# documentos/DOCUMENTACION_INGRESOS_SALIDAS_AJUSTE_PWA.md y
# querys/ddl_analytics_varianza_inventario.sql).
CLAVES_UNICAS_AJUSTE_APLICADO = ("uk_paloteo_ajuste_unico", "uk_varianza_inventario_unica")


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

    if control_aplicado:
        snapshots = db.query(models.VarianzaInventario).filter(
            models.VarianzaInventario.id_control_ajuste == control_aplicado.id
        ).all()
        deltas = [_serializar_snapshot_varianza(snapshot) for snapshot in snapshots]
    else:
        deltas = _enriquecer_deltas_con_valoracion(
            db, _calcular_diferencias_paloteo(db, payload.id_barra, inv_fisico_cabecera.id)
        )

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
                "valoracion": _resumir_valoracion_varianzas([]),
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
            "valoracion": _resumir_valoracion_varianzas(deltas),
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

    deltas = _enriquecer_deltas_con_valoracion(
        db, _calcular_diferencias_paloteo(db, payload.id_barra, inv_fisico_cabecera.id)
    )
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
    fecha_operacion = db.query(models.Operacion.fecha).filter(
        models.Operacion.id == payload.id_operacion
    ).scalar()
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
        db.flush()

        # Snapshot analítico propio: se persiste dentro de la misma transacción
        # que los movimientos POS, sin escribir ni reinterpretar tablas legacy.
        for d in deltas_a_igualar:
            db.add(models.VarianzaInventario(
                id_operacion=payload.id_operacion,
                id_barra=payload.id_barra,
                id_inventario_fisico=inv_fisico_cabecera.id,
                id_control_ajuste=control.id,
                id_producto=d["id_producto"],
                id_categoria=d["id_categoria"],
                fecha_operacion=fecha_operacion,
                fecha_aplicacion=fecha_actual,
                id_almacen=d["id_almacen_wac"],
                delta_paq=_decimal2(d["delta_paq"]),
                delta_det_exacto=Decimal(str(d["delta_det_exacto"])),
                delta_det_operativo=_decimal2(d["delta_det_operativo"]),
                rendimiento_por_envase=(
                    Decimal(str(d["rendimiento_por_envase"]))
                    if d["rendimiento_por_envase"] is not None else None
                ),
                unidad_detalle=d["unidad_detalle"],
                wac_snapshot=(
                    Decimal(str(d["wac_snapshot"]))
                    if d["wac_snapshot"] is not None else None
                ),
                fecha_actualizacion_wac=d["fecha_actualizacion_wac"],
                origen_wac=d["origen_wac"],
                estado_valoracion=d["estado_valoracion"],
                valor_paq=(
                    Decimal(str(d["valor_paq"])) if d["valor_paq"] is not None else None
                ),
                valor_detalle_operativo=(
                    Decimal(str(d["valor_detalle_operativo"]))
                    if d["valor_detalle_operativo"] is not None else None
                ),
                valor_neto=(
                    Decimal(str(d["valor_neto"])) if d["valor_neto"] is not None else None
                ),
                usuario_reg=username_actual,
                fecha_reg=fecha_actual,
            ))

        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        # Dos aplicaciones simultáneas pasan ambas _obtener_control_aplicado (la
        # segunda lee su snapshot previo al commit de la primera); la que llega
        # después choca aquí con la clave única del control o de las varianzas.
        # Es el mismo caso que el 409 de arriba, no un error del servidor.
        if any(clave in str(exc.orig) for clave in CLAVES_UNICAS_AJUSTE_APLICADO):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Los ajustes para esta operativa/barra ya fueron aplicados anteriormente."
            ) from exc
        logger.exception(
            "Error de integridad aplicando ajustes para operación %s / barra %s",
            payload.id_operacion, payload.id_barra,
        )
        raise HTTPException(status_code=500, detail="No se pudo aplicar el ajuste de inventario.") from exc
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


@app.get("/api/ajustes/varianzas", response_model=schemas.ReporteVarianzasHistoricasResponse)
def reportar_varianzas_historicas(
    fecha_inicio: date = Query(..., description="Inicio inclusivo del periodo"),
    fecha_fin: date = Query(..., description="Fin inclusivo del periodo"),
    agrupacion: str = Query("dia", pattern="^(dia|semana|mes)$"),
    id_barra: Optional[int] = Query(None, gt=0),
    id_producto: Optional[int] = Query(None, gt=0),
    id_categoria: Optional[int] = Query(None, gt=0),
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_usuario_administrador),
):
    """Agrega snapshots históricos de varianzas, sin consultar WAC vigente."""
    if fecha_fin < fecha_inicio:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="fecha_fin no puede ser anterior a fecha_inicio.",
        )

    expresiones_periodo = {
        "dia": "DATE(fecha_aplicacion)",
        "semana": "DATE_SUB(DATE(fecha_aplicacion), INTERVAL WEEKDAY(fecha_aplicacion) DAY)",
        "mes": "DATE_FORMAT(fecha_aplicacion, '%Y-%m-01')",
    }
    periodo_sql = expresiones_periodo[agrupacion]
    filtros = ["fecha_aplicacion >= :fecha_inicio", "fecha_aplicacion < :fecha_fin_exclusiva"]
    parametros = {
        "fecha_inicio": fecha_inicio,
        "fecha_fin_exclusiva": fecha_fin + timedelta(days=1),
    }
    for campo, valor in (("id_barra", id_barra), ("id_producto", id_producto), ("id_categoria", id_categoria)):
        if valor is not None:
            filtros.append(f"{campo} = :{campo}")
            parametros[campo] = valor

    select_resumen = """
        COUNT(*) AS productos_con_varianza,
        COALESCE(SUM(CASE WHEN estado_valoracion = 'VALORIZADO' AND valor_neto < 0 THEN -valor_neto ELSE 0 END), 0) AS faltantes,
        COALESCE(SUM(CASE WHEN estado_valoracion = 'VALORIZADO' AND valor_neto > 0 THEN valor_neto ELSE 0 END), 0) AS sobrantes,
        COALESCE(SUM(CASE WHEN estado_valoracion = 'VALORIZADO' THEN valor_neto ELSE 0 END), 0) AS neto,
        COALESCE(SUM(CASE WHEN estado_valoracion <> 'VALORIZADO' THEN 1 ELSE 0 END), 0) AS productos_sin_valoracion
    """
    where_sql = " AND ".join(filtros)
    resumen = db.execute(text(f"""
        SELECT {select_resumen}
        FROM analytics_varianza_inventario
        WHERE {where_sql}
    """), parametros).mappings().one()
    filas_periodo = db.execute(text(f"""
        SELECT {periodo_sql} AS periodo, {select_resumen}
        FROM analytics_varianza_inventario
        WHERE {where_sql}
        GROUP BY {periodo_sql}
        ORDER BY periodo ASC
    """), parametros).mappings().all()

    def serializar(fila, periodo):
        return {
            "periodo": periodo,
            "productos_con_varianza": int(fila["productos_con_varianza"] or 0),
            "faltantes": float(fila["faltantes"] or 0),
            "sobrantes": float(fila["sobrantes"] or 0),
            "neto": float(fila["neto"] or 0),
            "productos_sin_valoracion": int(fila["productos_sin_valoracion"] or 0),
        }

    return {
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "agrupacion": agrupacion,
        "resumen": serializar(resumen, fecha_inicio),
        "periodos": [serializar(fila, fila["periodo"]) for fila in filas_periodo],
    }


def _peso_total_crudo(pesos_abiertas) -> Optional[float]:
    if not isinstance(pesos_abiertas, list):
        return None
    pesos = []
    for entrada in pesos_abiertas:
        if not isinstance(entrada, dict):
            continue
        try:
            pesos.append(float(entrada["peso"]))
        except (KeyError, TypeError, ValueError):
            continue
    return sum(pesos) if pesos else 0.0


def _normalizar_fila_paloteo_historico(fila) -> dict:
    actual_detalle = fila["actual_detalle"]
    onzas_crudas = fila["onzas_crudas"]
    diferencia_exacta = None
    if actual_detalle is not None and onzas_crudas is not None:
        diferencia_exacta = float(onzas_crudas) - float(actual_detalle)

    pesos_abiertas = []
    if fila["pesos_abiertas"]:
        try:
            pesos_abiertas = json.loads(fila["pesos_abiertas"])
        except (TypeError, json.JSONDecodeError):
            pesos_abiertas = []

    contado = fila["fisico_paq"] is not None or fila["fisico_detalle"] is not None
    # Movimiento segun el propio cierre POS: ventas o ingresos distintos de cero.
    tuvo_movimiento = any(
        float(fila.get(campo) or 0) != 0
        for campo in ("ventas_paq", "ventas_detalle", "ingreso_paq", "ingreso_detalle")
    )
    if contado:
        clasificacion = "con_diferencia" if fila["tiene_diferencia"] else "cuadrado"
    elif tuvo_movimiento:
        # Vendido o traspasado y nadie lo conto: alerta de auditoria.
        clasificacion = "con_movimiento_sin_contar"
    else:
        clasificacion = "sin_movimiento"

    return {
        "id_paloteo_cierre": fila["id_paloteo_cierre"],
        "id_operacion": fila["id_operacion"],
        "id_barra": fila["id_barra"],
        "barra": fila["barra"],
        "id_producto": fila["id_producto"],
        "codigo_producto": fila["codigo_producto"],
        "producto": fila["producto"],
        "categoria": fila["categoria"],
        "actual_paq": float(fila["actual_paq"]) if fila["actual_paq"] is not None else None,
        "actual_detalle": float(actual_detalle) if actual_detalle is not None else None,
        "fisico_paq": float(fila["fisico_paq"]) if fila["fisico_paq"] is not None else None,
        "fisico_detalle": float(fila["fisico_detalle"]) if fila["fisico_detalle"] is not None else None,
        "diferencia_paq": float(fila["diferencia_paq"]) if fila["diferencia_paq"] is not None else None,
        "diferencia_detalle": float(fila["diferencia_detalle"]) if fila["diferencia_detalle"] is not None else None,
        "peso_gramos": _peso_total_crudo(pesos_abiertas) if fila["id_crudo"] is not None else None,
        "diferencia_exacta_oz": diferencia_exacta,
        "tiene_captura_cruda": fila["id_crudo"] is not None,
        "tiene_diferencia": bool(fila["tiene_diferencia"]),
        "fecha_reg": fila["fecha_reg"],
        "estado_producto": fila["estado_producto"],
        "pesable": bool(fila.get("pesable", 1)),
        "tuvo_movimiento": tuvo_movimiento,
        "clasificacion": clasificacion,
        "valor_neto": None,
        "estado_valoracion": None,
    }


def _obtener_filas_paloteo_historico(db: Session, id_operacion: int, id_barra: int) -> list[dict]:
    """Lee un cierre POS histórico sin depender del inventario vivo ni del navegador."""
    query = text("""
        SELECT
            c.id_paloteo_cierre,
            c.id_operacion,
            c.id_barra,
            c.barra,
            c.id_producto,
            c.codigo_producto,
            c.producto,
            c.categoria,
            c.actual_paq,
            c.actual_detalle,
            c.fisico_paq,
            c.fisico_detalle,
            c.diferencia_paq,
            c.diferencia_detalle,
            c.tiene_diferencia,
            c.fecha_reg,
            c.estado_producto,
            c.ventas_paq,
            c.ventas_detalle,
            c.ingreso_paq,
            c.ingreso_detalle,
            -- Mismo criterio de pesable que _calcular_diferencias_paloteo.
            CASE WHEN EXISTS (
                SELECT 1 FROM app_producto_pesaje_config_api p
                WHERE p.id_producto_almacen = c.id_producto AND p.pesable = 1
            ) THEN 1 ELSE 0 END AS pesable,
            r.id AS id_crudo,
            r.onzas_calculadas AS onzas_crudas,
            r.pesos_abiertas
        FROM v9_paloteo_cierre c
        INNER JOIN (
            SELECT MAX(id_paloteo_cierre) AS id_paloteo_cierre
            FROM v9_paloteo_cierre
            WHERE id_operacion = :id_operacion
              AND id_barra = :id_barra
              AND estado_paloteo = 'HAB'
            GROUP BY id_operacion, id_barra, id_producto
        ) ultima_cierre ON ultima_cierre.id_paloteo_cierre = c.id_paloteo_cierre
        -- El registro crudo no guarda id_barra: solo vale la ultima captura
        -- que explica el conteo de esta barra (mismas botellas y onzas a no mas
        -- de MARGEN_CAPTURA_CRUDA_OZ), igual que _obtener_capturas_crudas_por_conteo.
        LEFT JOIN app_paloteo_registro_crudo r
          ON r.id = (
              SELECT MAX(r2.id)
              FROM app_paloteo_registro_crudo r2
              WHERE r2.id_operacion = c.id_operacion
                AND r2.id_producto = c.id_producto
                AND r2.botellas_cerradas = COALESCE(c.fisico_paq, 0)
                AND ABS(COALESCE(r2.onzas_calculadas, 0) - COALESCE(c.fisico_detalle, 0)) <= 0.255
          )
        WHERE c.id_operacion = :id_operacion
          AND c.id_barra = :id_barra
          AND c.estado_paloteo = 'HAB'
        ORDER BY c.id_producto ASC
    """)
    filas = db.execute(query, {
        "id_operacion": id_operacion,
        "id_barra": id_barra,
    }).mappings().all()
    return [_normalizar_fila_paloteo_historico(fila) for fila in filas]


def _obtener_reporte_paloteo_historico(db: Session, id_operacion: int, id_barra: int) -> Optional[dict]:
    """Cierre historico con la misma lectura que el reporte de Ajustes.

    Devuelve solo los productos contados (con diferencia o cuadrados) y los que
    tuvieron movimiento sin contarse (alerta); los sin movimiento, que son casi
    todo el catalogo, solo se cuentan. VALOR sale del snapshot congelado del
    ajuste aplicado (analytics_varianza_inventario), nunca del WAC de hoy: sin
    ajuste aplicado la columna queda vacia. None si no hay cierre.
    """
    filas = _obtener_filas_paloteo_historico(db, id_operacion, id_barra)
    if not filas:
        return None

    resumen = {"con_diferencia": 0, "cuadrados": 0, "con_movimiento_sin_contar": 0, "sin_movimiento": 0}
    claves_resumen = {
        "con_diferencia": "con_diferencia",
        "cuadrado": "cuadrados",
        "con_movimiento_sin_contar": "con_movimiento_sin_contar",
        "sin_movimiento": "sin_movimiento",
    }
    for fila in filas:
        resumen[claves_resumen[fila["clasificacion"]]] += 1
    visibles = [fila for fila in filas if fila["clasificacion"] != "sin_movimiento"]

    control_aplicado = db.query(models.PaloteoAjusteControl).filter(
        models.PaloteoAjusteControl.id_operacion == id_operacion,
        models.PaloteoAjusteControl.id_barra == id_barra,
        models.PaloteoAjusteControl.estado == 'APLICADO',
    ).order_by(models.PaloteoAjusteControl.id.desc()).first()

    valoracion = None
    if control_aplicado:
        snapshots = {
            snapshot.id_producto: snapshot
            for snapshot in db.query(models.VarianzaInventario).filter(
                models.VarianzaInventario.id_control_ajuste == control_aplicado.id
            ).all()
        }
        for fila in visibles:
            snapshot = snapshots.get(fila["id_producto"])
            if snapshot is not None:
                fila["estado_valoracion"] = snapshot.estado_valoracion
                fila["valor_neto"] = float(snapshot.valor_neto) if snapshot.valor_neto is not None else None
            elif fila["clasificacion"] == "cuadrado":
                # Cuadraba al aplicar (aplicar congela todo delta != 0): vale 0 Bs.
                fila["estado_valoracion"] = "VALORIZADO"
                fila["valor_neto"] = 0.0
            # Con diferencia en el cierre pero sin snapshot (el ajuste se aplico
            # sobre otros datos) o sin contar: se deja vacio, no se inventa un 0.
        valoracion = _resumir_valoracion_varianzas([
            {"estado_valoracion": snapshot.estado_valoracion, "valor_neto": snapshot.valor_neto}
            for snapshot in snapshots.values()
        ])

    return {
        "id_operacion": id_operacion,
        "id_barra": id_barra,
        "fecha_cierre": max((fila["fecha_reg"] for fila in filas if fila["fecha_reg"]), default=None),
        "filas": visibles,
        "resumen": resumen,
        "ajuste_aplicado": control_aplicado is not None,
        "valoracion": valoracion,
    }


@app.get("/api/paloteo3/historico", response_model=schemas.PaloteoHistoricoResponse)
def obtener_paloteo_historico(
    id_operacion: int = Query(..., gt=0),
    id_barra: int = Query(..., gt=0),
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_usuario_administrador),
):
    reporte = _obtener_reporte_paloteo_historico(db, id_operacion, id_barra)
    if reporte is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No existe un cierre histórico para la operativa y barra solicitadas.",
        )
    return reporte


@app.get("/api/paloteo3/historico/operativas", response_model=schemas.PaloteoHistoricoOperativasResponse)
def listar_operativas_paloteo_historico(
    fecha_desde: Optional[date] = Query(None, description="Inicio inclusivo del rango (default: fecha_hasta - 30 dias)"),
    fecha_hasta: Optional[date] = Query(None, description="Fin inclusivo del rango (default: hoy)"),
    id_barra: Optional[int] = Query(None, gt=0),
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_usuario_administrador),
):
    """Lista operativas/barras con cierre historico disponible en v9_paloteo_cierre,
    acotado por defecto a los ultimos 30 dias porque el endpoint no pagina.

    Solo barras que operaron: el POS escribe cierre para toda barra, tenga o no
    actividad (en local la barra 2 no tuvo comandas, paloteo ni movimiento en
    ninguna operativa reciente y aun asi aparecia). Una barra opero si tuvo
    comandas (en cualquier estado), un paloteo registrado, o ventas/ingresos
    distintos de cero en su propio cierre."""
    fecha_hasta = fecha_hasta or date.today()
    fecha_desde = fecha_desde or (fecha_hasta - timedelta(days=30))
    if fecha_hasta < fecha_desde:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="fecha_hasta no puede ser anterior a fecha_desde.",
        )

    filtros = ["pc.estado = 'HAB'", "o.fecha >= :fecha_desde", "o.fecha < :fecha_hasta_exclusiva"]
    parametros = {"fecha_desde": fecha_desde, "fecha_hasta_exclusiva": fecha_hasta + timedelta(days=1)}
    if id_barra is not None:
        filtros.append("pc.id_barra = :id_barra")
        parametros["id_barra"] = id_barra

    # Directo sobre bar_paloteo_cierre (la tabla de v9_paloteo_cierre), no sobre
    # la vista: con la vista MySQL arranca desde alm_producto y recorre las
    # ~335k filas del cierre (~0.9 s); asi usa el indice por operativa (~0.01 s).
    # Se agrupa primero (tabla derivada) y se filtra despues: MySQL 5.6 evaluaba
    # mal las EXISTS correlacionadas dentro de HAVING (dejaba pasar barras sin
    # actividad).
    query = text(f"""
        SELECT g.id_operacion, g.id_barra, g.barra, g.nombre_operacion, g.fecha
        FROM (
            SELECT
                pc.id_operacion,
                pc.id_barra,
                MAX(b.nombre) AS barra,
                o.nombre_operacion,
                o.fecha,
                SUM(
                    COALESCE(pc.ventas_paq, 0) <> 0 OR COALESCE(pc.ventas_detalle, 0) <> 0
                    OR COALESCE(pc.ingreso_paq, 0) <> 0 OR COALESCE(pc.ingreso_detalle, 0) <> 0
                ) AS productos_con_movimiento
            FROM bar_paloteo_cierre pc
            INNER JOIN ope_operacion o ON o.id = pc.id_operacion
            LEFT JOIN bar_barra b ON b.id = pc.id_barra
            WHERE {' AND '.join(filtros)}
            GROUP BY pc.id_operacion, pc.id_barra, o.nombre_operacion, o.fecha
        ) g
        WHERE g.productos_con_movimiento > 0
           OR EXISTS (
               SELECT 1 FROM bar_comanda bc
               WHERE bc.id_operacion = g.id_operacion AND bc.id_barra = g.id_barra
           )
           OR EXISTS (
               SELECT 1 FROM bar_inventario_fisico f
               WHERE f.id_operacion = g.id_operacion AND f.id_barra = g.id_barra AND f.estado = 'HAB'
           )
        ORDER BY g.fecha DESC, g.id_operacion DESC, g.id_barra ASC
    """)
    filas = db.execute(query, parametros).mappings().all()
    return {"operativas": [dict(fila) for fila in filas]}

# --- EXPORTACIÓN PDF PALOTEO 3 ---

import os
from fpdf import FPDF

# Logo de marca para el encabezado del PDF: reusa el mismo asset "navbar
# completo" de la marca activa (ver branding.py) en vez de un archivo fijo,
# para que el export quede consistente con la piel visual de cada instancia.
_LOGO_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "static" + _brand_activa["logo_navbar_full"][len("/assets"):],
)
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


def _fmt_valor_varianza(valor, estado_valoracion):
    # estado None: la fila no tiene valoracion aplicable (ej. historico de una
    # operativa sin ajuste aplicado) y la celda queda vacia.
    if estado_valoracion is None:
        return ""
    if estado_valoracion != "VALORIZADO" or valor is None:
        return "SIN WAC"
    monto = Decimal(str(valor))
    return f"{'+' if monto > 0 else ''}{monto:.2f} Bs"


class _ReportePDF(FPDF):
    """FPDF con footer discreto de numero de pagina ("PÁGINA n / N") en cada
    hoja. fpdf2 invoca footer() automaticamente al cerrar cada pagina; el
    placeholder {nb} se reemplaza con el total de paginas al renderizar."""

    def footer(self):
        self.set_y(-12)
        self.set_font(_FONT_FAMILY, "", 7)
        self.set_text_color(150, 150, 150)
        self.cell(0, 8, f"PÁGINA {self.page_no()} / {{nb}}", align="C")


# Columnas del reporte de diferencias, compartidas por el PDF de Ajustes y el
# historico para que ambos documentos se lean exactamente igual.
# ID | COD | Producto | Paq.Pos | Paq.Bar | Det.Pos | Peso | Det.Bar | Dif.Paq | Dif.Real | Dif.Op | Valor
_PDF_DIF_ANCHOS = [8, 14, 48, 16, 16, 19, 18, 19, 15, 20, 20, 44]  # suma = 257mm = ancho util A4 horizontal
_PDF_DIF_TITULOS = ["ID", "COD", "PRODUCTO", "PAQ POS", "PAQ BAR", "DET POS", "PESO", "DET BAR", "DIF. PAQ.", "DIF REAL", "DIF OP", "VALOR"]
_PDF_DIF_ALINEACION = ["R", "L", "L", "R", "R", "R", "R", "R", "R", "R", "R", "R"]
# Jerarquía visual: ID/COD con menor peso, PRODUCTO en negrita, cantidades
# absolutas (paq/det/peso) en texto neutro, diferencias con color semántico.
_PDF_DIF_JERARQUIA = ["muted", "muted", "primary", "neutral", "neutral", "neutral", "neutral", "neutral", "diff", "diff", "diff", "diff"]


def _renderizar_pdf_diferencias(
    *,
    titulo: str,
    subtitulo: str,
    meta: list[tuple[str, str]],
    secciones: list[dict],
    linea_superior: Optional[str] = None,
    lineas_resumen: list[str] = (),
    notas: list[str] = (),
) -> bytes:
    """Renderer unico del reporte de diferencias (Ajustes e historico).

    secciones: lista de {"titulo": str | None, "filas": [...]}; las vacias se
    omiten. Cada fila trae id_producto, codigo, nombre, paq_pos, paq_bar,
    det_pos, peso_gramos, det_bar, dif_paq, dif_real, dif_op, valor_neto y
    estado_valoracion (None en cualquier campo = celda vacia).
    """
    # Horizontal: 12 columnas no entran con un ancho legible en A4 vertical.
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
    pdf.cell(ancho_util, 5, titulo, align="R")
    pdf.set_xy(20, 18)
    pdf.cell(ancho_util, 5, subtitulo, align="R")

    # línea divisoria
    pdf.set_draw_color(200, 200, 200)
    pdf.line(20, 28, x_derecha, 28)
    pdf.ln(20)

    # — Metadata (dos columnas) —
    pdf.set_text_color(34, 34, 34)
    label_w, value_w, meta_h = 24, 61, 6
    meta_y0 = pdf.get_y()
    for i, (etiqueta, valor) in enumerate(meta):
        x = 20 + (label_w + value_w) * (i % 2)
        y = meta_y0 + (i // 2) * meta_h
        pdf.set_xy(x, y)
        pdf.set_font(_FONT_FAMILY, "B", 9)
        pdf.cell(label_w, meta_h, etiqueta)
        pdf.set_font(_FONT_FAMILY, "", 9)
        pdf.cell(value_w, meta_h, valor)
    pdf.set_y(meta_y0 + ((len(meta) + 1) // 2) * meta_h + 4)
    if linea_superior:
        pdf.set_font(_FONT_FAMILY, "B", 8.5)
        pdf.set_text_color(51, 51, 51)
        pdf.cell(ancho_util, 5, linea_superior)
        pdf.ln(5)
    pdf.ln(6)

    row_h = 7

    # cabecera de tabla (helper para redibujarla en cada pagina nueva: fpdf2
    # hace el salto de pagina automatico pero no repite el encabezado).
    def dibujar_cabecera_tabla():
        pdf.set_fill_color(242, 242, 242)
        pdf.set_draw_color(204, 204, 204)
        pdf.set_text_color(17, 17, 17)
        pdf.set_font(_FONT_FAMILY, "B", 7.5)
        for w, h, a in zip(_PDF_DIF_ANCHOS, _PDF_DIF_TITULOS, _PDF_DIF_ALINEACION):
            pdf.cell(w, row_h, h, border=1, align=a, fill=True)
        pdf.ln()

    for seccion in secciones:
        filas = seccion["filas"]
        if not filas:
            continue
        titulo_seccion = seccion.get("titulo")
        # Titulo + cabecera + al menos una fila juntos: nunca un titulo huerfano
        # al pie de una pagina.
        if pdf.get_y() + row_h * 2 + (7 if titulo_seccion else 0) > pdf.page_break_trigger:
            pdf.add_page()
        if titulo_seccion:
            pdf.set_font(_FONT_FAMILY, "B", 9)
            pdf.set_text_color(51, 51, 51)
            pdf.cell(ancho_util, 6, titulo_seccion)
            pdf.ln(7)
        dibujar_cabecera_tabla()

        for idx, fila in enumerate(filas):
            # Si la proxima fila no entra en la pagina, saltar manualmente y
            # repetir la cabecera arriba (nos adelantamos al auto page break de
            # fpdf2, que crearia la pagina sin encabezado de tabla).
            if pdf.get_y() + row_h > pdf.page_break_trigger:
                pdf.add_page()
                dibujar_cabecera_tabla()

            valor_neto = fila["valor_neto"]
            valores = [
                fila["id_producto"],
                fila["codigo"] or "",
                fila["nombre"],
                _fmt_cantidad_paq(fila["paq_pos"]),
                _fmt_cantidad_paq(fila["paq_bar"]),
                _fmt_cantidad_oz(fila["det_pos"]),
                _fmt_peso_gramos(fila["peso_gramos"]),
                _fmt_cantidad_oz(fila["det_bar"]),
                _fmt_diff_paq(fila["dif_paq"]),
                _fmt_diff_oz(fila["dif_real"]),
                _fmt_diff_oz(fila["dif_op"]),
                _fmt_valor_varianza(valor_neto, fila["estado_valoracion"]),
            ]
            colores = [
                None, None, None,
                None, None, None, None, None,
                _color_diferencia(fila["dif_paq"]) if fila["dif_paq"] is not None else None,
                _color_diferencia(fila["dif_real"]) if fila["dif_real"] is not None else None,
                _color_diferencia(fila["dif_op"]) if fila["dif_op"] is not None else None,
                _color_diferencia(valor_neto) if valor_neto is not None else None,
            ]

            fondo = (245, 245, 245) if idx % 2 == 1 else (255, 255, 255)
            pdf.set_fill_color(*fondo)

            for w, val, align, color, jerarquia in zip(
                _PDF_DIF_ANCHOS, valores, _PDF_DIF_ALINEACION, colores, _PDF_DIF_JERARQUIA
            ):
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
        pdf.ln(4)

    for linea in lineas_resumen:
        pdf.set_font(_FONT_FAMILY, "B", 8)
        pdf.set_text_color(51, 51, 51)
        pdf.cell(ancho_util, 5, linea, align="R")
        pdf.ln(5)
    for nota in notas:
        pdf.set_font(_FONT_FAMILY, "", 7)
        pdf.set_text_color(90, 90, 90)
        pdf.cell(ancho_util, 4, nota, align="R")
        pdf.ln(4)

    return bytes(pdf.output())


def _obtener_ultima_captura_cruda_por_producto(
    db: Session, id_operacion: int, conteos: dict[int, tuple[float, float]]
) -> dict[int, dict]:
    """Onzas exactas y peso total de la captura cruda que explica el conteo de
    esta barra (ver _obtener_capturas_crudas_por_conteo), para las columnas
    PESO y DIF REAL."""
    return {
        id_producto: {
            "onzas": float(registro.onzas_calculadas) if registro.onzas_calculadas is not None else None,
            "peso_gramos": _peso_total_crudo(_pesos_de_captura_cruda(registro)),
        }
        for id_producto, registro in _obtener_capturas_crudas_por_conteo(db, id_operacion, conteos).items()
    }


def _obtener_filas_reporte_ajustes(db: Session, id_operacion: int, id_barra: int) -> Optional[dict]:
    """Filas y totales del reporte de diferencias de Ajustes, armados en el servidor.

    Filas y totales salen de la misma fuente, para que el PDF nunca muestre un
    total que sus filas no explican. Antes las filas las armaba el navegador
    desde las tarjetas en pantalla mientras el total salia de BD: en la
    operativa 1306 faltaba la fila de HAVANA 7A (-1 botella, -140 Bs) pero el
    total de FALTANTES si la contaba.

    - Universo: todo producto contado (bar_detalle_fisico HAB), con o sin
      diferencia: el paloteo es justamente lo que demuestra que cuadra.
    - Ajuste aplicado: deltas y valoracion desde el snapshot congelado
      (analytics_varianza_inventario). Un producto contado sin snapshot no
      tenia diferencia al aplicar (aplicar congela todo delta != 0) y va en cero.
    - Sin aplicar: _calcular_diferencias_paloteo con la valoracion vigente, lo
      mismo que muestra el preview y lo que ejecutaria aplicar.

    Devuelve None si no hay paloteo registrado para la operativa/barra.
    """
    inventario_fisico = db.query(models.InventarioFisicoPOS).filter(
        models.InventarioFisicoPOS.id_operacion == id_operacion,
        models.InventarioFisicoPOS.id_barra == id_barra,
        models.InventarioFisicoPOS.estado == 'HAB',
    ).first()
    if not inventario_fisico:
        return None

    deltas = _calcular_diferencias_paloteo(db, id_barra, inventario_fisico.id)
    control_aplicado = _obtener_control_aplicado(db, id_operacion, id_barra, inventario_fisico.id)
    if control_aplicado:
        snapshots = {
            snapshot.id_producto: snapshot
            for snapshot in db.query(models.VarianzaInventario).filter(
                models.VarianzaInventario.id_control_ajuste == control_aplicado.id
            ).all()
        }
        for delta in deltas:
            snapshot = snapshots.get(delta["id_producto"])
            if snapshot is None:
                delta.update({
                    "delta_paq": 0.0, "delta_det_exacto": 0.0, "delta_det_operativo": 0.0,
                    "estado_valoracion": "VALORIZADO", "valor_neto": 0.0,
                })
            else:
                delta.update({
                    "delta_paq": float(snapshot.delta_paq),
                    "delta_det_exacto": float(snapshot.delta_det_exacto),
                    "delta_det_operativo": float(snapshot.delta_det_operativo),
                    "estado_valoracion": snapshot.estado_valoracion,
                    "valor_neto": float(snapshot.valor_neto) if snapshot.valor_neto is not None else None,
                })
        valoracion = _resumir_valoracion_varianzas([
            {"estado_valoracion": snapshot.estado_valoracion, "valor_neto": snapshot.valor_neto}
            for snapshot in snapshots.values()
        ])
    else:
        deltas = _enriquecer_deltas_con_valoracion(db, deltas)
        valoracion = _resumir_valoracion_varianzas(deltas)

    productos = {}
    ids_producto = [delta["id_producto"] for delta in deltas]
    if ids_producto:
        productos = {
            fila["id"]: fila
            for fila in db.execute(
                text("SELECT id, codigo, nombre FROM alm_producto WHERE id IN :ids")
                .bindparams(bindparam("ids", expanding=True)),
                {"ids": ids_producto},
            ).mappings().all()
        }
    capturas = _obtener_ultima_captura_cruda_por_producto(db, id_operacion, {
        delta["id_producto"]: (delta["real_paq"], delta["real_det"]) for delta in deltas
    })

    filas = []
    for delta in deltas:
        producto = productos.get(delta["id_producto"]) or {}
        pesable = delta["pesable"] == 1
        ideal_paq = delta["real_paq"] - delta["delta_paq"]
        ideal_det = delta["real_det"] - delta["delta_det_exacto"]
        captura = capturas.get(delta["id_producto"]) if pesable else None
        dif_real = None
        if pesable:
            # DIF REAL: onzas exactas de la balanza contra el ideal; sin captura
            # cruda, el delta sobre lo registrado (ya en grilla POS).
            dif_real = (
                captura["onzas"] - ideal_det
                if captura and captura["onzas"] is not None
                else delta["delta_det_exacto"]
            )
        filas.append({
            "id_producto": delta["id_producto"],
            "codigo": producto.get("codigo") or "",
            "nombre": producto.get("nombre") or "",
            "paq_pos": ideal_paq,
            "paq_bar": delta["real_paq"],
            # Los no pesables se cuentan en unidades: sin columnas de onzas.
            "det_pos": ideal_det if pesable else None,
            "peso_gramos": captura["peso_gramos"] if captura else None,
            "det_bar": delta["real_det"] if pesable else None,
            "dif_paq": delta["delta_paq"],
            "dif_real": dif_real,
            "dif_op": delta["delta_det_operativo"] if pesable else None,
            "valor_neto": delta.get("valor_neto"),
            "estado_valoracion": delta.get("estado_valoracion"),
        })

    return {
        "filas": filas,
        "valoracion": valoracion,
        "ajuste_aplicado": control_aplicado is not None,
    }


def _filtrar_filas_reporte_por_tipo(filas: list[dict], tipo_reporte: str) -> list[dict]:
    """ingreso/salida: solo las filas con esa parte del movimiento, anulando la
    parte opuesta (mismo criterio que tenia el cliente). DIF REAL sigue a DIF OP."""
    if tipo_reporte not in ("ingreso", "salida"):
        return filas
    signo = 1 if tipo_reporte == "ingreso" else -1
    filtradas = []
    for fila in filas:
        paq_aplica = fila["dif_paq"] is not None and fila["dif_paq"] * signo > 0
        det_aplica = fila["dif_op"] is not None and fila["dif_op"] * signo > 0
        if not (paq_aplica or det_aplica):
            continue
        filtradas.append({
            **fila,
            "dif_paq": fila["dif_paq"] if paq_aplica else None,
            "dif_op": fila["dif_op"] if det_aplica else None,
            "dif_real": fila["dif_real"] if det_aplica else None,
        })
    return filtradas


def _ordenar_filas_reporte(filas: list[dict], ordenar_por: Optional[str], orden_dir: str) -> list[dict]:
    """Orden elegido en pantalla (por defecto nombre, como la lista de PALOTEO);
    empates por id_producto ascendente (sorted es estable, tambien en reverse)."""
    claves = {
        "idProducto": lambda fila: fila["id_producto"],
        "codigo": lambda fila: str(fila["codigo"] or "").casefold(),
        "nombre": lambda fila: str(fila["nombre"] or "").casefold(),
    }
    por_id = sorted(filas, key=lambda fila: fila["id_producto"])
    return sorted(por_id, key=claves[ordenar_por or "nombre"], reverse=orden_dir == "desc")


@app.post("/api/paloteo3/exportar-pdf")
def exportar_pdf_paloteo3(
    payload: schemas.ExportarPdfRequest,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_usuario_actual),
):
    reporte = _obtener_filas_reporte_ajustes(db, payload.id_operacion, payload.id_barra)
    if reporte is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No hay paloteo registrado para esta operativa y barra. Registra el paloteo antes de exportar el PDF.",
        )

    tipo_reporte = payload.tipo_reporte
    filas = _ordenar_filas_reporte(
        _filtrar_filas_reporte_por_tipo(reporte["filas"], tipo_reporte),
        payload.ordenar_por,
        payload.orden_dir,
    )
    if not filas:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "ingreso": "No hay productos con ingreso por ajuste (sobrantes) para exportar.",
                "salida": "No hay productos con salida por ajuste (faltantes) para exportar.",
            }.get(tipo_reporte, "El paloteo registrado no tiene productos contados para exportar."),
        )

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
    resumen_valoracion = reporte["valoracion"]
    notas = []
    if resumen_valoracion["productos_sin_valoracion"]:
        notas.append(
            f"{resumen_valoracion['productos_sin_valoracion']} producto(s) sin valoración por WAC o rendimiento inválido."
        )

    pdf_bytes = _renderizar_pdf_diferencias(
        titulo=titulo_reporte,
        subtitulo=subtitulo_reporte,
        meta=[
            ("Generado:", datetime.now().strftime("%d/%m/%Y %H:%M:%S")),
            ("Usuario:", payload.usuario),
            ("Operativa:", str(payload.id_operacion)),
            ("Barra:", str(payload.id_barra)),
        ],
        secciones=[{"titulo": None, "filas": filas}],
        lineas_resumen=[
            f"FALTANTES: -{resumen_valoracion['faltantes']:.2f} Bs    "
            f"SOBRANTES: +{resumen_valoracion['sobrantes']:.2f} Bs    "
            f"NETO: {resumen_valoracion['neto']:+.2f} Bs"
        ],
        notas=notas,
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'},
    )


def _fila_pdf_desde_historico(fila: dict) -> dict:
    """Adapta una fila del cierre historico a las columnas del reporte de
    diferencias (las mismas del PDF de Ajustes). En el cierre POS
    diferencia_detalle ya esta en grilla de 0.5 oz: es la DIF OP."""
    pesable = fila["pesable"]
    contado = fila["clasificacion"] in ("con_diferencia", "cuadrado")
    dif_real = None
    if pesable and contado:
        dif_real = (
            fila["diferencia_exacta_oz"]
            if fila["diferencia_exacta_oz"] is not None
            else fila["diferencia_detalle"]
        )
    nombre = fila["producto"] or ""
    if fila["estado_producto"] and fila["estado_producto"] != "HAB":
        nombre = f"{nombre} (DES)"
    return {
        "id_producto": fila["id_producto"],
        "codigo": fila["codigo_producto"] or "",
        "nombre": nombre,
        "paq_pos": fila["actual_paq"],
        "paq_bar": fila["fisico_paq"],
        # Los no pesables se cuentan en unidades: sin columnas de onzas.
        "det_pos": fila["actual_detalle"] if pesable else None,
        "peso_gramos": fila["peso_gramos"],
        "det_bar": fila["fisico_detalle"] if pesable else None,
        "dif_paq": fila["diferencia_paq"],
        "dif_real": dif_real,
        "dif_op": fila["diferencia_detalle"] if pesable else None,
        "valor_neto": fila["valor_neto"],
        "estado_valoracion": fila["estado_valoracion"],
    }


@app.post("/api/paloteo3/historico/exportar-pdf")
def exportar_pdf_paloteo3_historico(
    payload: schemas.ExportarPdfHistoricoRequest,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_usuario_administrador),
):
    """PDF del cierre historico con la misma estructura que el de Ajustes: una
    tabla con todo producto contado (con o sin diferencia) y, aparte, los que
    tuvieron movimiento sin contarse. Las filas se recalculan aqui desde
    v9_paloteo_cierre (fuente de verdad congelada), no se reciben del cliente."""
    reporte = _obtener_reporte_paloteo_historico(db, payload.id_operacion, payload.id_barra)
    if reporte is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No existe un cierre histórico para la operativa y barra solicitadas.",
        )

    def por_nombre(filas):
        return _ordenar_filas_reporte(filas, "nombre", "asc")

    contados = por_nombre([
        _fila_pdf_desde_historico(fila) for fila in reporte["filas"]
        if fila["clasificacion"] in ("con_diferencia", "cuadrado")
    ])
    sin_contar = por_nombre([
        _fila_pdf_desde_historico(fila) for fila in reporte["filas"]
        if fila["clasificacion"] == "con_movimiento_sin_contar"
    ])
    if not contados and not sin_contar:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La operativa no tiene productos contados ni con movimiento en esta barra.",
        )

    resumen = reporte["resumen"]
    linea_superior = (
        f"{resumen['con_diferencia']} con diferencia  ·  {resumen['cuadrados']} cuadrados  ·  "
        f"{resumen['con_movimiento_sin_contar']} con movimiento sin contar  ·  "
        f"{resumen['sin_movimiento']} sin movimiento (omitidos)"
    )

    lineas_resumen = []
    notas = []
    valoracion = reporte["valoracion"]
    if valoracion is not None:
        lineas_resumen.append(
            f"FALTANTES: -{valoracion['faltantes']:.2f} Bs    "
            f"SOBRANTES: +{valoracion['sobrantes']:.2f} Bs    "
            f"NETO: {valoracion['neto']:+.2f} Bs"
        )
        if valoracion["productos_sin_valoracion"]:
            notas.append(
                f"{valoracion['productos_sin_valoracion']} producto(s) sin valoración por WAC o rendimiento inválido."
            )
    else:
        notas.append("Sin ajuste aplicado: la valoración se congela recién al aplicar el ajuste de esta operativa.")

    fecha_cierre = reporte["fecha_cierre"]
    pdf_bytes = _renderizar_pdf_diferencias(
        titulo="REPORTE HISTÓRICO DE DIFERENCIAS",
        subtitulo="Stock Barra vs. Cierre POS",
        meta=[
            ("Generado:", datetime.now().strftime("%d/%m/%Y %H:%M:%S")),
            ("Usuario:", payload.usuario),
            ("Operativa:", str(payload.id_operacion)),
            ("Barra:", str(payload.id_barra)),
            ("Cierre POS:", fecha_cierre.strftime("%d/%m/%Y %H:%M:%S") if fecha_cierre else "N/D"),
        ],
        linea_superior=linea_superior,
        secciones=[
            {"titulo": None, "filas": contados},
            {"titulo": "CON MOVIMIENTO SIN CONTAR  (vendido o traspasado, sin captura física)", "filas": sin_contar},
        ],
        lineas_resumen=lineas_resumen,
        notas=notas,
    )

    nombre_archivo = f"PALOTEO_HISTORICO_{payload.id_operacion}_{payload.id_barra}.pdf"
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


def _id_opcional_por_defecto(id_categoria_combo, lineas_combo, opcional_por_categoria) -> Optional[int]:
    """Id del opcional incluido por defecto para este combo, o None si la categoria no tiene regla
    configurada o el producto de la regla no figura entre los OPCIONAL del combo (nunca se
    sustituye por otro). opcional_por_categoria: {id_categoria: id_producto}, ver
    settings.pourcost_opcional_por_categoria."""
    id_defecto = opcional_por_categoria.get(id_categoria_combo)
    if id_defecto is None:
        return None
    for linea in lineas_combo:
        if _tipo_parte_combo_es_opcional(linea.get("tipo_parte_combo")) and linea["id_producto"] == id_defecto:
            return id_defecto
    return None


def _agregar_costo_receta(lineas, opcional_por_categoria=None) -> dict:
    """Agrupa lineas de vw_pourcost_receta (una fila por ingrediente) por id_combo_coctel, sumando
    cogs_ingrediente con Decimal para no arrastrar error de float. No toca precio_venta -- esa vista
    lo trae fijo a id_dia=1, se resuelve aparte contra v9_menubackstage (ver pourcost.md, seccion 8.2).

    El costo suma todos los PRINCIPAL mas, como mucho, el OPCIONAL por defecto de la categoria
    (opcional_por_categoria, configurado en el .env; sin el, solo los PRINCIPAL); es el mismo criterio con el que el modal arranca sus
    checkboxes (campo `incluido_por_defecto` de cada ingrediente). `costo_incompleto` solo mira
    las lineas incluidas, no los opcionales que nadie marco."""
    opcional_por_categoria = opcional_por_categoria or {}
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
                "id_categoria_combo": linea.get("id_categoria_combo"),
                "costo_total": Decimal("0"),
                "costo_incompleto": False,
                "ingredientes": [],
            }
            combos[id_combo] = combo
        combo["ingredientes"].append(dict(linea))

    for combo in combos.values():
        id_defecto = _id_opcional_por_defecto(combo["id_categoria_combo"], combo["ingredientes"], opcional_por_categoria)
        defecto_ya_incluido = False
        for linea in combo["ingredientes"]:
            incluido = not _tipo_parte_combo_es_opcional(linea.get("tipo_parte_combo"))
            # Un solo opcional por combo: si la receta repite la linea del opcional por defecto
            # (dato duplicado en el ERP), solo cuenta la primera; contarla dos veces duplicaria
            # su costo y dejaria dos checkboxes con el mismo id_producto en el modal.
            if not incluido and id_defecto is not None and linea["id_producto"] == id_defecto and not defecto_ya_incluido:
                incluido = True
                defecto_ya_incluido = True
            linea["incluido_por_defecto"] = incluido
            if not incluido:
                continue
            combo["costo_total"] += Decimal(str(linea["cogs_ingrediente"] or 0))
            if int(linea["sin_wac"] or 0) == 1:
                combo["costo_incompleto"] = True
    return combos


def _float_o_none(valor) -> Optional[float]:
    return float(valor) if valor is not None else None


@app.get("/api/pourcost/dias", response_model=List[schemas.PourCostDia])
def listar_pourcost_dias(
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_usuario_administrador)
):
    """Grupos de precio (ope_dia) que el negocio realmente usa hoy, según el
    allowlist POURCOST_DIAS_PRECIO_ACTIVOS -- ope_dia puede tener más filas de
    las que están en producción real (ver config.py, pourcost_dias_precio_activos).
    ope_dia no está mapeada en models.py (tabla externa al ORM de esta app,
    igual que otras consultadas solo via sqlalchemy.text() en este módulo)."""
    dias_activos = settings.pourcost_dias_precio_activos
    if not dias_activos:
        return []

    placeholders = ", ".join(f":dia_{i}" for i in range(len(dias_activos)))
    params = {f"dia_{i}": id_dia for i, id_dia in enumerate(dias_activos)}
    rows = db.execute(
        text(f"""
            SELECT id, dia
            FROM ope_dia
            WHERE estado = 'HAB' AND id IN ({placeholders})
            ORDER BY id
        """),
        params
    ).mappings().all()

    return [schemas.PourCostDia(id_dia=row["id"], nombre=row["dia"]) for row in rows]


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
            SELECT v.id_combo_coctel, v.codigo_combo, v.nombre_combo, v.descripcion_combo, v.nombre_categoria_combo,
                   b.id_categoria AS id_categoria_combo,
                   v.id_producto, v.codigo_producto, v.nombre_producto, v.nombre_categoria_producto,
                   v.cantidad_receta, v.tipo_cantidad_combo, v.tipo_parte_combo, v.unidad_base, v.medida_unidad_base,
                   v.unidades_detalle_por_base, v.unidad_detalle, v.wac_actual, v.sin_wac, v.cantidad_unidad_base,
                   v.cogs_ingrediente
            FROM vw_pourcost_receta v
            JOIN bar_combo_coctel b ON b.id = v.id_combo_coctel
            ORDER BY v.id_combo_coctel
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

    combos = _agregar_costo_receta(lineas, settings.pourcost_opcional_por_categoria)

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
                        incluido_por_defecto=linea["incluido_por_defecto"],
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

# icon_dir de la marca activa es una ruta URL bajo /assets (p.ej.
# "/assets/icons/brands/beer_garden"); esta la traduce a su carpeta real en
# disco ("static/icons/brands/beer_garden") para FileResponse.
_brand_icon_fs_dir = "static" + _brand_activa["icon_dir"][len("/assets"):]

# manifest.json depende de la marca activa (nombre, ícono, theme_color), así
# que se genera en runtime en vez de servirse como archivo estático. Debe
# registrarse ANTES del mount de /assets: FastAPI prueba las rutas en el
# orden en que se agregan, así esta ruta puntual gana por sobre el catch-all
# del mount para ese path exacto.
@app.get("/assets/manifest.json", include_in_schema=False)
def serve_manifest():
    return JSONResponse(build_manifest(_brand_activa))

# Montamos una carpeta llamada 'static' donde vivirá el HTML, CSS y JS
app.mount("/assets", StaticFiles(directory="static"), name="assets")

# Favicon canónico de la marca activa: se sirve desde static/icons(/brands/<id>)
# sin duplicar archivos en la raíz.
@app.get("/favicon.ico", include_in_schema=False)
def serve_favicon():
    return FileResponse(f"{_brand_icon_fs_dir}/favicon.ico")

# Ruta principal que devuelve la página web. index.html es una plantilla con
# un puñado de placeholders __BRAND_*__ (título, favicons, logos, glitch on/
# off, hoja de estilos de override) que se completan acá según BRAND_ID —
# los colores en sí NO se inyectan por texto: viven como CSS custom
# properties y el override de marca los pisa por cascada
# (static/brands/<id>.css, enlazado vía __BRAND_CSS_HREF__).
@app.get("/")
def serve_frontend():
    with open("static/index.html", "r", encoding="utf-8") as f:
        html = f.read()

    reemplazos = {
        "__BRAND_TITLE__": _brand_activa["title"],
        "__BRAND_APP_NAME__": _brand_activa["app_name"],
        "__BRAND_THEME_COLOR__": _brand_activa["theme_color"],
        "__BRAND_ICON_DIR__": _brand_activa["icon_dir"],
        "__BRAND_CSS_HREF__": _brand_activa["css_href"],
        "__BRAND_LOGO_LOGIN__": _brand_activa["logo_login"],
        "__BRAND_LOGO_NAVBAR_FULL__": _brand_activa["logo_navbar_full"],
        "__BRAND_LOGO_NAVBAR_ISOTIPO__": _brand_activa["logo_navbar_isotipo"],
        "__BRAND_GLITCH_ENABLED__": "true" if _brand_activa["glitch_enabled"] else "false",
    }
    for placeholder, valor in reemplazos.items():
        html = html.replace(placeholder, valor)

    return HTMLResponse(html)