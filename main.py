from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.responses import FileResponse, JSONResponse, Response
import hashlib
import json
from database import get_db
import models
import schemas
from typing import List
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from datetime import datetime, timedelta, timezone
import logging

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

# --- FUNCIÓN DE ENCRIPTACIÓN ---
def hash_password(password: str) -> str:
    """Aplica SHA-256 puro para coincidir con el POS actual."""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def _validar_operacion_inicio_cierre(db: Session, id_operacion: int) -> models.Operacion:
    operacion = db.query(models.Operacion).filter(models.Operacion.id == id_operacion).first()
    if not operacion or operacion.estado_operacion != 24:
        raise HTTPException(status_code=400, detail="Operación inválida o barra no está en INICIO CIERRE.")
    return operacion


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
            models.ProductoPesajeConfig.id_producto_almacen == item.id_producto
        ).all()

        # Registrar productos sin configuración en la lista de omitidos.
        if not configs_producto:
            logger.warning("Producto id=%s omitido: sin configuración de pesaje en app_producto_pesaje_config", item.id_producto)
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

        onzas_redondeadas_pos = round(total_onzas * 2) / 2

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
        "nombres": f"{usuario_db.paterno} {usuario_db.materno}, {usuario_db.nombres}"
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

    detalles = [
        {
            "id_producto": detalle.id_producto,
            "botellas_cerradas": float(detalle.cantidad_unidad or 0),
            "onzas_pos": float(detalle.cantidad_detalle or 0),
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
    current_user: models.Usuario = Depends(get_usuario_actual)
):
    """Crea un nuevo modelo de botella para un producto pesable."""
    if payload.tara >= payload.peso_bruto:
        raise HTTPException(status_code=400, detail="La tara no puede ser mayor o igual al peso bruto.")

    nombre_perfil = payload.nombre_perfil.strip()

    insert_sql = text("""
        INSERT INTO app_producto_pesaje_config
        (id_producto_almacen, nombre_perfil, peso_bruto, tara, gramos_por_oz, tolerancia_oz, pesable, usuario_reg)
        VALUES
        (:id_producto, :nombre_perfil, :peso_bruto, :tara, :gramos_por_oz, :tolerancia_oz, 1, :usuario_reg)
    """)

    try:
        result = db.execute(insert_sql, {
            "id_producto": payload.id_producto,
            "nombre_perfil": nombre_perfil,
            "peso_bruto": payload.peso_bruto,
            "tara": payload.tara,
            "gramos_por_oz": payload.gramos_por_oz,
            "tolerancia_oz": payload.tolerancia_oz,
            "usuario_reg": current_user.usuario,
        })
        db.commit()
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

    perfil_id = getattr(result, "lastrowid", None)
    return schemas.PerfilPesaje(
        id=perfil_id,
        nombre_perfil=nombre_perfil,
        peso_bruto=float(payload.peso_bruto),
        tara=float(payload.tara),
        gramos_por_oz=float(payload.gramos_por_oz),
        tolerancia_oz=float(payload.tolerancia_oz),
    )

# OBTENEMOS LOS PRODUCTOS PARA EL PALOTEO

@app.get("/api/inventario/pendientes", response_model=List[schemas.ProductoPendiente])
def obtener_productos_pendientes(
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_usuario_actual) # <-- CANDADO AQUÍ
    ):
    """
    Devuelve la lista de productos que tuvieron movimiento en la operación activa,
    junto con su stock ideal y parámetros de pesaje.
    """
    query = text("""
        SELECT 
            a.id AS id_producto, a.codigo, a.nombre, a.ind_permite_comandar,
            i.cantidad_paq AS stock_ideal_unidades, i.cantidad_detalle AS stock_ideal_onzas,
            i.categoria_nombre,
            p.id AS perfil_id, p.pesable, p.nombre_perfil, p.peso_bruto, p.tara, p.gramos_por_oz, p.tolerancia_oz,
            a.cantidad_detalle AS onzas_por_botella_llena
        FROM (
            SELECT DISTINCT d.id_producto_receta 
            FROM comandas_v9_detallada d
            INNER JOIN bar_comanda c ON d.id_comanda = c.id
            WHERE d.id_operacion = (SELECT MAX(id_operacion) FROM bar_comanda)
            AND c.estado_comanda = 26
        ) mov
        INNER JOIN alm_producto a ON mov.id_producto_receta = a.id
        INNER JOIN vista_inventario_barra_con_filtro i ON a.id = i.id_almacen 
        LEFT JOIN app_producto_pesaje_config p ON a.id = p.id_producto_almacen
        ORDER BY a.nombre ASC, p.id ASC;
 
          """)

    rows = db.execute(query).mappings().all()

    # Agrupamos perfiles de pesaje por producto porque ahora puede haber
    # múltiples modelos de botella para el mismo id_producto.
    productos_dict = {}
    for row in rows:
        prod_id = row["id_producto"]
        if prod_id not in productos_dict:
            productos_dict[prod_id] = {
                "id_producto": prod_id,
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
            productos_dict[prod_id]["perfiles"].append({
                "id": row["perfil_id"],
                "nombre_perfil": row["nombre_perfil"],
                "peso_bruto": float(row["peso_bruto"]),
                "tara": float(row["tara"]),
                "gramos_por_oz": float(row["gramos_por_oz"]),
                "tolerancia_oz": float(row["tolerancia_oz"])
            })

    return list(productos_dict.values())

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
    col_widths = [14, 22, 94, 22, 18]   # ID | Codigo | Producto | Dif.Unid | Dif.Onzas
    headers   = ["ID", "CODIGO", "PRODUCTO", "DIF. UNID", "DIF. ONZAS"]
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
        texto_oz = ""
        color_unid = None
        color_oz = None

        if fila.difUnidades is not None:
            texto_unid = f"{'+' if fila.difUnidades > 0 else ''}{round(fila.difUnidades)}"
            color_unid = _color_diferencia(fila.difUnidades)

        if fila.difOnzas is not None:
            texto_oz = f"{'+' if fila.difOnzas > 0 else ''}{fila.difOnzas:.2f} oz"
            color_oz = _color_diferencia(fila.difOnzas)

        fondo = (245, 245, 245) if idx % 2 == 1 else (255, 255, 255)
        pdf.set_fill_color(*fondo)

        valores = [fila.idProducto, fila.codigo, fila.nombre, texto_unid, texto_oz]
        colores = [None, None, None, color_unid, color_oz]

        for w, val, align, color in zip(col_widths, valores, aligns, colores):
            if color:
                pdf.set_text_color(*color)
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