from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi import FastAPI, Depends, HTTPException, status, Request
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

    # 2. Evaluamos la regla de negocio: ¿Está en proceso de venta?
    if operacion_actual.estado_operacion == 22:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Aún hay ventas activas. Cambie el estado de la operativa a INICIO CIERRE en el POS para poder realizar el inventario."
        )

    # 3. Luz Verde: ¿Está lista para cierre?
    if operacion_actual.estado_operacion == 24:
        return {
            "id_operacion": operacion_actual.id,
            "nombre": operacion_actual.nombre_operacion,
            "mensaje": "Luz verde: Operación en INICIO CIERRE. Puede comenzar el paloteo."
        }

    # 4. Si tiene otro estado distinto (ej. ya se cerró completamente)
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"La operación no está en un estado válido para paloteo (Estado: {operacion_actual.estado_operacion})."
    )
    
@app.post("/api/inventario/paloteo")
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
    operacion = db.query(models.Operacion).filter(models.Operacion.id == payload.id_operacion).first()
    if not operacion or operacion.estado_operacion != 24:
        raise HTTPException(status_code=400, detail="Operación inválida o barra no está en INICIO CIERRE.")

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

    resultados_procesados = []
    margen_error_balanza = 10.0

    # 3. PROCESAR PRODUCTOS
    for item in payload.items:
        configs_producto = db.query(models.ProductoPesajeConfig).filter(
            models.ProductoPesajeConfig.id_producto_almacen == item.id_producto
        ).all()
        
        # Fix #6: Registrar productos sin configuración de pesaje en lugar de ignorarlos silenciosamente.
        if not configs_producto:
            logger.warning("Producto id=%s omitido: sin configuración de pesaje en app_producto_pesaje_config", item.id_producto)
            continue

        config_base = configs_producto[0]
        perfiles = [cfg for cfg in configs_producto if cfg.pesable == 1]

        total_onzas = 0.0
        if config_base.pesable == 1 and perfiles:
            for abierta in item.pesos_abiertas:
                perfil_index = abierta.perfil_index
                if perfil_index < 0 or perfil_index >= len(perfiles):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Perfil de botella inválido para producto {item.id_producto}."
                    )

                perfil = perfiles[perfil_index]
                gr_oz = float(perfil.gramos_por_oz)
                tara = float(perfil.tara)
                peso_medido = float(abierta.peso)

                if peso_medido >= (tara - margen_error_balanza):
                    peso_liquido = max(0, peso_medido - tara)
                    total_onzas += (peso_liquido / gr_oz)

        # --- NUEVO: Redondear a la media onza más cercana para el POS ---
        # Ej: 11.92 * 2 = 23.84 -> round(23.84) = 24 -> 24 / 2 = 12.00
        # Ej: 11.21 * 2 = 22.42 -> round(22.42) = 22 -> 22 / 2 = 11.00
        # Ej: 11.26 * 2 = 22.52 -> round(22.52) = 23 -> 23 / 2 = 11.50
        onzas_redondeadas_pos = round(total_onzas * 2) / 2

        # 4. GUARDAR DETALLE EN EL POS (Con el valor redondeado)
        nuevo_detalle_pos = models.DetalleFisicoPOS(
            cantidad_unidad=item.botellas_cerradas,
            cantidad_detalle=onzas_redondeadas_pos,
            id_producto=item.id_producto,
            id_inventario_fisico=nueva_cabecera_pos.id, 
            usuario_reg=username_actual,
            fecha_reg=fecha_actual.date(),
            estado='HAB'
        )
        db.add(nuevo_detalle_pos)

        # 5. GUARDAR AUDITORÍA CRUDA (Con el valor exacto)
        registro_crudo = models.PaloteoRegistroCrudo(
            id_operacion=payload.id_operacion,
            id_producto=item.id_producto,
            botellas_cerradas=item.botellas_cerradas,
            pesos_abiertas=json.dumps([entrada.model_dump() for entrada in item.pesos_abiertas]),
            onzas_calculadas=total_onzas, # Exacto: 11.92
            usuario_reg=username_actual,
            fecha_reg=fecha_actual
        )
        db.add(registro_crudo)
        
        resultados_procesados.append({
            "id_producto": item.id_producto,
            "onzas_exactas": round(total_onzas, 2),
            "onzas_pos": onzas_redondeadas_pos
        })

    db.commit()

    # Fix #6: Incluir en la respuesta los productos que fueron omitidos por falta de configuración.
    ids_procesados = {r['id_producto'] for r in resultados_procesados}
    productos_omitidos = [item.id_producto for item in payload.items if item.id_producto not in ids_procesados]

    return {
        "status": "success",
        "id_inventario_pos": nueva_cabecera_pos.id,
        "mensaje": f"Se registraron {len(resultados_procesados)} productos en el POS exitosamente.",
        "detalles": resultados_procesados,
        "productos_omitidos": productos_omitidos
    }

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
            p.pesable, p.nombre_perfil, p.peso_bruto, p.tara, p.gramos_por_oz, p.tolerancia_oz,
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
        ORDER BY a.nombre ASC;
 
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
                "nombre_perfil": row["nombre_perfil"],
                "peso_bruto": float(row["peso_bruto"]),
                "tara": float(row["tara"]),
                "gramos_por_oz": float(row["gramos_por_oz"]),
                "tolerancia_oz": float(row["tolerancia_oz"])
            })

    return list(productos_dict.values())

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