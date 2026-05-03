from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db, engine

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