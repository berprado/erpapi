from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from sqlalchemy.engine import URL
from dotenv import dotenv_values
import logging
import os
import re

from branding import BRAND_IDS, DEFAULT_BRAND_ID

logger = logging.getLogger(__name__)

_ENV_FILE = ".env"
_PATRON_OPCIONAL_CAT = re.compile(r"^POURCOST_OPCIONAL_CAT(\d+)$", re.IGNORECASE)

class Settings(BaseSettings):
    # extra="ignore": las claves POURCOST_OPCIONAL_CAT<id> son dinámicas (una por
    # categoría) y no pueden declararse como campos; ver pourcost_opcional_por_categoria.
    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

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

    @property
    def pourcost_opcional_por_categoria(self) -> dict[int, int]:
        """Producto OPCIONAL que POUR COST cuenta por defecto en el costo de un combo, por categoría.

        Se configura con una variable por categoría: POURCOST_OPCIONAL_CAT<id_categoria>=<id_producto>,
        ej. POURCOST_OPCIONAL_CAT1=64 (WHISKYS -> AGUA S-GAS 2LT). id_categoria es
        bar_combo_coctel.id_categoria (= alm_categoria.id); id_producto es alm_producto.id, que cambia
        entre entornos, por eso vive en el .env de cada uno. Categoría sin variable = sin opcional por
        defecto (solo cuentan los PRINCIPAL). Se leen el .env y las variables de entorno reales (en
        el despliegue no hay .env); estas últimas ganan. Valores no numéricos o <= 0 se ignoran."""
        crudo = {**dotenv_values(_ENV_FILE), **os.environ}
        resultado: dict[int, int] = {}
        for clave, valor in crudo.items():
            coincide = _PATRON_OPCIONAL_CAT.match(clave)
            if not coincide:
                continue
            try:
                id_producto = int(str(valor).strip())
            except ValueError:
                logger.warning("%s=%r ignorada: no es un id de producto numérico", clave, valor)
                continue
            if id_producto <= 0:
                logger.warning("%s=%r ignorada: el id de producto debe ser mayor a 0", clave, valor)
                continue
            resultado[int(coincide.group(1))] = id_producto
        return resultado

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

    @staticmethod
    def _url_mysql(usuario: str, contrasena: str, host: str, puerto: str, nombre_bd: str) -> URL:
        # URL.create escapa cada componente: una contraseña con '@', ':', '/'
        # o '#' interpolada en un f-string rompía el parseo de la URL.
        # Contraseña vacía (root de WAMP sin clave) -> None, sin ':' colgando.
        return URL.create(
            "mysql+pymysql",
            username=usuario,
            password=contrasena or None,
            host=host,
            port=int(puerto) if puerto else None,
            database=nombre_bd,
        )

    @property
    def database_url(self) -> URL:
        """Genera la URL de conexión de SQLAlchemy dinámicamente."""
        if self.APP_ENV == "production":
            logger.info("Conectando a BASE DE DATOS DE PRODUCCIÓN")
            return self._url_mysql(self.PROD_DB_USER, self.PROD_DB_PASS, self.PROD_DB_HOST,
                                   self.PROD_DB_PORT, self.PROD_DB_NAME)

        if self.APP_ENV == "test_pos":
            logger.info("Conectando a BASE DE DATOS DE PRUEBAS CON POS (Remoto)")
            return self._url_mysql(self.TEST_POS_DB_USER, self.TEST_POS_DB_PASS, self.TEST_POS_DB_HOST,
                                   self.TEST_POS_DB_PORT, self.TEST_POS_DB_NAME)

        logger.info("Conectando a BASE DE DATOS DE PRUEBAS (WAMP Local)")
        return self._url_mysql(self.TEST_DB_USER, self.TEST_DB_PASS, self.TEST_DB_HOST,
                               self.TEST_DB_PORT, self.TEST_DB_NAME)

settings = Settings()