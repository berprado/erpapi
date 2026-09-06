from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
import logging

from branding import BRAND_IDS, DEFAULT_BRAND_ID

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    APP_ENV: str = "test"
    SECRET_KEY: str  # Clave para firma de tokens JWT

    # Piel visual (logo/paleta) de esta instancia desplegada. Cada sucursal
    # corre el mismo código y solo cambia esta variable — ver branding.py.
    BRAND_ID: str = DEFAULT_BRAND_ID
    PALOTEO_DEFAULT_BARRA_ID: int = 1
    PALOTEO_SELECTOR_ENABLED: bool = False
    PALOTEO_ALLOWED_BARRAS: str = "1"

    # Grupos de ope_dia que POUR COST debe ofrecer como horario de precio
    # seleccionable (separados por coma). ope_dia puede tener más filas de
    # las que el negocio realmente usa hoy (ej. un grupo creado pero nunca
    # puesto en producción, con precios en 0) — este allowlist es la fuente
    # de verdad de "cuáles están realmente activos", igual que
    # PALOTEO_ALLOWED_BARRAS para barras. Hoy: solo el grupo 1.
    POURCOST_DIAS_PRECIO_ACTIVOS: str = "1"

    # Freno de fuerza bruta en /api/auth/login: máximo de intentos fallidos
    # dentro de la ventana antes de responder 429. Un login exitoso resetea
    # el contador de ese usuario/IP.
    LOGIN_MAX_INTENTOS_USUARIO: int = 5
    LOGIN_MAX_INTENTOS_IP: int = 20
    LOGIN_VENTANA_MINUTOS: int = 5

    # Orígenes cross-origin permitidos (separados por coma). Vacío = la API
    # solo se consume desde el mismo origen (la PWA integrada) y no se
    # habilita el middleware CORS.
    CORS_ALLOWED_ORIGINS: str = ""

    # Fix #21: Validar longitud mínima de SECRET_KEY para garantizar tokens seguros.
    @field_validator('SECRET_KEY')
    @classmethod
    def validar_secret_key(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError('SECRET_KEY debe tener al menos 32 caracteres. Genera una con: python -c "import secrets; print(secrets.token_hex(32))"')
        return v

    @field_validator('APP_ENV')
    @classmethod
    def validar_app_env(cls, v: str) -> str:
        permitidos = {"test", "test_pos", "production"}
        valor = (v or "").strip().lower()
        if valor not in permitidos:
            raise ValueError(f"APP_ENV debe ser uno de: {', '.join(sorted(permitidos))}")
        return valor

    @field_validator('BRAND_ID')
    @classmethod
    def validar_brand_id(cls, v: str) -> str:
        valor = (v or "").strip().lower()
        if valor not in BRAND_IDS:
            raise ValueError(f"BRAND_ID debe ser uno de: {', '.join(sorted(BRAND_IDS))}")
        return valor

    @field_validator('PALOTEO_DEFAULT_BARRA_ID')
    @classmethod
    def validar_barra_por_defecto(cls, v: int) -> int:
        if v <= 0:
            raise ValueError('PALOTEO_DEFAULT_BARRA_ID debe ser mayor a 0.')
        return v

    @property
    def cors_allowed_origins(self) -> list[str]:
        return [o.strip() for o in (self.CORS_ALLOWED_ORIGINS or "").split(',') if o.strip()]

    @property
    def paloteo_allowed_barras(self) -> list[int]:
        valores = []
        for token in (self.PALOTEO_ALLOWED_BARRAS or "").split(','):
            token = token.strip()
            if not token:
                continue
            try:
                barra = int(token)
            except ValueError:
                continue
            if barra > 0:
                valores.append(barra)

        if not valores:
            valores = [self.PALOTEO_DEFAULT_BARRA_ID]

        # Mantiene orden y elimina duplicados.
        valores_unicos = list(dict.fromkeys(valores))
        if self.PALOTEO_DEFAULT_BARRA_ID not in valores_unicos:
            valores_unicos.insert(0, self.PALOTEO_DEFAULT_BARRA_ID)
        return valores_unicos

    @property
    def pourcost_dias_precio_activos(self) -> list[int]:
        valores = []
        for token in (self.POURCOST_DIAS_PRECIO_ACTIVOS or "").split(','):
            token = token.strip()
            if not token:
                continue
            try:
                id_dia = int(token)
            except ValueError:
                continue
            if id_dia > 0:
                valores.append(id_dia)

        if not valores:
            valores = [1]

        return list(dict.fromkeys(valores))

    # Variables de prueba (WAMP local)
    TEST_DB_HOST: str
    TEST_DB_USER: str
    TEST_DB_PASS: str
    TEST_DB_NAME: str
    TEST_DB_PORT: str

    # Variables de prueba con POS (remoto)
    TEST_POS_DB_HOST: str = ""
    TEST_POS_DB_USER: str = ""
    TEST_POS_DB_PASS: str = ""
    TEST_POS_DB_NAME: str = ""
    TEST_POS_DB_PORT: str = ""

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
            logger.info("Conectando a BASE DE DATOS DE PRODUCCIÓN")
            return f"mysql+pymysql://{self.PROD_DB_USER}:{self.PROD_DB_PASS}@{self.PROD_DB_HOST}:{self.PROD_DB_PORT}/{self.PROD_DB_NAME}"

        if self.APP_ENV == "test_pos":
            logger.info("Conectando a BASE DE DATOS DE PRUEBAS CON POS (Remoto)")
            if not self.TEST_POS_DB_PASS:
                return f"mysql+pymysql://{self.TEST_POS_DB_USER}@{self.TEST_POS_DB_HOST}:{self.TEST_POS_DB_PORT}/{self.TEST_POS_DB_NAME}"
            return f"mysql+pymysql://{self.TEST_POS_DB_USER}:{self.TEST_POS_DB_PASS}@{self.TEST_POS_DB_HOST}:{self.TEST_POS_DB_PORT}/{self.TEST_POS_DB_NAME}"

        logger.info("Conectando a BASE DE DATOS DE PRUEBAS (WAMP Local)")
        if not self.TEST_DB_PASS:
            return f"mysql+pymysql://{self.TEST_DB_USER}@{self.TEST_DB_HOST}:{self.TEST_DB_PORT}/{self.TEST_DB_NAME}"
        return f"mysql+pymysql://{self.TEST_DB_USER}:{self.TEST_DB_PASS}@{self.TEST_DB_HOST}:{self.TEST_DB_PORT}/{self.TEST_DB_NAME}"

settings = Settings()