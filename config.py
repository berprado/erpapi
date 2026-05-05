from pydantic_settings import BaseSettings
from pydantic import field_validator
import logging

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    APP_ENV: str = "test"
    SECRET_KEY: str  # Clave para firma de tokens JWT

    # Fix #21: Validar longitud mínima de SECRET_KEY para garantizar tokens seguros.
    @field_validator('SECRET_KEY')
    @classmethod
    def validar_secret_key(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError('SECRET_KEY debe tener al menos 32 caracteres. Genera una con: python -c "import secrets; print(secrets.token_hex(32))"')
        return v
    
    # Variables de prueba
    TEST_DB_HOST: str
    TEST_DB_USER: str
    TEST_DB_PASS: str
    TEST_DB_NAME: str
    TEST_DB_PORT: str
    
    # Variables de producción
    PROD_DB_HOST: str
    PROD_DB_USER: str
    PROD_DB_PASS: str
    PROD_DB_NAME: str
    PROD_DB_PORT: str

    @property
    def database_url(self) -> str:
        """Genera la URL de conexión de SQLAlchemy dinámicamente."""
        if self.APP_ENV == "production":
            # Fix #20: usar logging en lugar de print()
            logger.info("Conectando a BASE DE DATOS DE PRODUCCIÓN")
            return f"mysql+pymysql://{self.PROD_DB_USER}:{self.PROD_DB_PASS}@{self.PROD_DB_HOST}:{self.PROD_DB_PORT}/{self.PROD_DB_NAME}"
        
        logger.info("Conectando a BASE DE DATOS DE PRUEBAS (WAMP Local)")
        # Si no hay password local, formateamos la URL sin los dos puntos
        if not self.TEST_DB_PASS:
            return f"mysql+pymysql://{self.TEST_DB_USER}@{self.TEST_DB_HOST}:{self.TEST_DB_PORT}/{self.TEST_DB_NAME}"
        return f"mysql+pymysql://{self.TEST_DB_USER}:{self.TEST_DB_PASS}@{self.TEST_DB_HOST}:{self.TEST_DB_PORT}/{self.TEST_DB_NAME}"

    class Config:
        env_file = ".env"

settings = Settings()