from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi import FastAPI, Depends, HTTPException, status, Request
from datetime import datetime
import hashlib
import json
from database import get_db, engine
import models
import schemas

app = FastAPI(
    title="API Inventario POS",
    description="Backend para control de pesaje y auditoría de barra",
    version="1.0.0"
)

# --- FUNCIÓN DE ENCRIPTACIÓN ---
def hash_password(password: str) -> str:
    """Aplica SHA-256 puro para coincidir con el POS actual."""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

# --- ENDPOINTS ---
@app.get("/")
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
        fecha=datetime.now(), 
        ip=client_ip
    )
    db.add(nuevo_acceso)
    db.commit()

    # 5. Generar y devolver el Token (Por ahora un token simulado)
    token_simulado = f"jwt-token-secreto-para-{usuario_db.id}"
    
    return {
        "access_token": token_simulado,
        "token_type": "Bearer",
        "usuario_id": usuario_db.id,
        "nombres": f"{usuario_db.nombres} {usuario_db.paterno}"
    }
    
@app.get("/api/operacion/activa", response_model=schemas.OperacionResponse)
def verificar_operacion_activa(db: Session = Depends(get_db)):
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
def procesar_paloteo(payload: schemas.PaloteoRequest, db: Session = Depends(get_db)):
    usuario_actual = "BERNARDO" 
    fecha_actual = datetime.now()
    
    # 1. Validar Operación (Guardia de Seguridad)
    operacion = db.query(models.Operacion).filter(models.Operacion.id == payload.id_operacion).first()
    if not operacion or operacion.estado_operacion != 24:
        raise HTTPException(status_code=400, detail="Operación inválida o barra no está en INICIO CIERRE.")

    # 2. CREAR CABECERA EN EL POS (bar_inventario_fisico)
    nueva_cabecera_pos = models.InventarioFisicoPOS(
        fecha=fecha_actual.date(),
        observaciones="Carga automática mediante App de Pesaje",
        procesado_por=usuario_actual,
        estado_registro=1,
        id_barra=payload.id_barra,
        id_operacion=payload.id_operacion,
        usuario_reg=usuario_actual,
        fecha_reg=fecha_actual.date(),
        estado='HAB'
    )
    db.add(nueva_cabecera_pos)
    db.flush() # flush() nos da el ID generado sin cerrar la transacción todavía

    resultados_procesados = []
    margen_error_balanza = 10.0

    # 3. PROCESAR PRODUCTOS
    for item in payload.items:
        config = db.query(models.ProductoPesajeConfig).filter(
            models.ProductoPesajeConfig.id_producto_almacen == item.id_producto
        ).first()
        
        if not config: continue # O manejar error según prefieras

        # Cálculo de Onzas (Tu lógica ya probada)
        total_onzas = 0.0
        if config.pesable == 1:
            gr_oz = float(config.gramos_por_oz)
            tara = float(config.tara)
            for peso_medido in item.pesos_abiertas:
                if peso_medido >= (tara - margen_error_balanza):
                    peso_liquido = max(0, peso_medido - tara)
                    total_onzas += (peso_liquido / gr_oz)

        # 4. GUARDAR DETALLE EN EL POS (bar_detalle_fisico)
        nuevo_detalle_pos = models.DetalleFisicoPOS(
            cantidad_unidad=item.botellas_cerradas,
            cantidad_detalle=total_onzas,
            id_producto=item.id_producto,
            id_inventario_fisico=nueva_cabecera_pos.id, # Link a la cabecera creada arriba
            usuario_reg=usuario_actual,
            fecha_reg=fecha_actual.date(),
            estado='HAB'
        )
        db.add(nuevo_detalle_pos)

        # 5. GUARDAR AUDITORÍA CRUDA (Tu tabla app_paloteo_registro_crudo)
        registro_crudo = models.PaloteoRegistroCrudo(
            id_operacion=payload.id_operacion,
            id_producto=item.id_producto,
            botellas_cerradas=item.botellas_cerradas,
            pesos_abiertas=json.dumps(item.pesos_abiertas),
            onzas_calculadas=total_onzas,
            usuario_reg=usuario_actual,
            fecha_reg=fecha_actual
        )
        db.add(registro_crudo)
        
        resultados_procesados.append({
            "id_producto": item.id_producto,
            "onzas": round(total_onzas, 2)
        })

    # 6. COMMIT FINAL (Si algo falla arriba, no se guarda nada en ninguna tabla)
    db.commit()

    return {
        "status": "success",
        "id_inventario_pos": nueva_cabecera_pos.id,
        "mensaje": f"Se registraron {len(resultados_procesados)} productos en el POS exitosamente."
    }