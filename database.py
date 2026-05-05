from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from config import settings

# Crear el motor de conexión
# pool_pre_ping=True verifica la conexión antes de usarla, evitando errores 500 tras reinicios del servidor MySQL
engine = create_engine(settings.database_url, echo=False, pool_pre_ping=True)

# Crear la fábrica de sesiones
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Clase base para nuestros futuros modelos de tablas
Base = declarative_base()

# Dependencia para inyectar la base de datos en las rutas de FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()