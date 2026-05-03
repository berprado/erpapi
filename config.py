from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_ENV: str = "test"
    
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
            print("🚀 Conectando a PRODUCCIÓN (Túnel Remoto)...")
            return f"mysql+pymysql://{self.PROD_DB_USER}:{self.PROD_DB_PASS}@{self.PROD_DB_HOST}:{self.PROD_DB_PORT}/{self.PROD_DB_NAME}"
        
        print("🛠️ Conectando a PRUEBAS (WAMP Local)...")
        # Si no hay password local, formateamos la URL sin los dos puntos
        if not self.TEST_DB_PASS:
            return f"mysql+pymysql://{self.TEST_DB_USER}@{self.TEST_DB_HOST}:{self.TEST_DB_PORT}/{self.TEST_DB_NAME}"
        return f"mysql+pymysql://{self.TEST_DB_USER}:{self.TEST_DB_PASS}@{self.TEST_DB_HOST}:{self.TEST_DB_PORT}/{self.TEST_DB_NAME}"

    class Config:
        env_file = ".env"

settings = Settings()