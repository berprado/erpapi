from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db, engine
from fastapi import FastAPI, Depends, HTTPException, status, Request
from datetime import datetime
import hashlib

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
@app.get("/api/health")
def health_check(db: Session = Depends(get_db)):
    try:
        resultado = db.execute(text("SELECT VERSION()")).scalar()
        return {"status": "ok", "database": "conectada", "mysql_version": resultado}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error de conexión: {str(e)}")

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
    db.commit() # Guardamos los cambios en MySQL

    # 5. Generar y devolver el Token (Por ahora un token simulado)
    token_simulado = f"jwt-token-secreto-para-{usuario_db.id}"
    
    return {
        "access_token": token_simulado,
        "token_type": "Bearer",
        "usuario_id": usuario_db.id,
        "nombres": f"{usuario_db.nombres} {usuario_db.paterno}"
    }

app = FastAPI(
    title="API Inventario POS",
    description="Backend para control de pesaje y auditoría de barra",
    version="1.0.0"
)

@app.get("/")
def read_root():
    return {"mensaje": "API del Sistema POS en línea y funcionando"}

@app.get("/api/health")
def health_check(db: Session = Depends(get_db)):
    """Endpoint para verificar la conexión a la base de datos MySQL."""
    try:
        # Ejecutamos una consulta SQL cruda muy simple
        resultado = db.execute(text("SELECT VERSION()")).scalar()
        return {
            "status": "ok", 
            "database": "conectada", 
            "mysql_version": resultado
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error de conexión a la BD: {str(e)}")