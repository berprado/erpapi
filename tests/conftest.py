"""Fixtures compartidas de la suite.

Los tests unitarios (test_calculos_pesaje, test_schemas_paloteo) no usan nada
de aqui. Estas fixtures dan soporte a los tests de INTEGRACION contra la BD
de test local (APP_ENV=test, adminerp_copy en WAMP):

- Toda la actividad de un test ocurre dentro de UNA transaccion externa sobre
  una unica conexion. La sesion que se inyecta a la app se une a esa
  transaccion con savepoints (join_transaction_mode="create_savepoint"), asi
  que los db.commit() de los endpoints solo liberan savepoints; al terminar
  el test la transaccion externa se revierte y la BD queda exactamente como
  estaba. Ninguna fila de fixture ni de endpoint sobrevive al test.
- Guarda de entorno: los tests de integracion abortan con error explicito si
  APP_ENV no es "test" o el host de BD no es local. Sus fixtures escriben
  datos: jamas deben apuntar a test_pos (POS real) ni a produccion.
- Si la BD local no esta disponible, los tests de integracion se omiten
  (skip) y los unitarios siguen corriendo igual que siempre.

Las fixtures de datos hacen db_session.commit() al terminar de sembrar: eso
solo libera el savepoint (sigue dentro de la transaccion externa), pero deja
la semilla a salvo del db.rollback() que los endpoints ejecutan al fallar,
reproduciendo la semantica real de datos pre-existentes.
"""
import uuid
from collections import namedtuple
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import settings


BARRA_FIXTURE = 1  # vista_inventario_barra_con_filtro esta cableada a id_barra = 1


def _abortar_si_entorno_inseguro():
    if settings.APP_ENV != "test":
        pytest.fail(
            "Los tests de integracion escriben fixtures en la BD y solo pueden correr con "
            f"APP_ENV=test (adminerp_copy local). APP_ENV actual: '{settings.APP_ENV}'. "
            "Nunca ejecutarlos contra test_pos ni produccion.",
            pytrace=False,
        )
    if settings.TEST_DB_HOST not in ("localhost", "127.0.0.1"):
        pytest.fail(
            f"TEST_DB_HOST='{settings.TEST_DB_HOST}' no es local. Los tests de integracion "
            "solo corren contra la BD local de WAMP.",
            pytrace=False,
        )


@pytest.fixture(scope="session")
def conexion_bd():
    """Conexion unica para toda la sesion de pytest, o skip si la BD no responde."""
    _abortar_si_entorno_inseguro()
    from database import engine

    try:
        conexion = engine.connect()
    except Exception as exc:
        pytest.skip(
            f"BD de test no disponible ({exc.__class__.__name__}); se omiten los tests de integracion."
        )
    yield conexion
    conexion.close()


@pytest.fixture()
def db_session(conexion_bd):
    """Sesion unida a una transaccion externa que se revierte al final del test."""
    transaccion = conexion_bd.begin()
    sesion = Session(bind=conexion_bd, join_transaction_mode="create_savepoint")
    try:
        yield sesion
    finally:
        sesion.close()
        if transaccion.is_active:
            transaccion.rollback()


@pytest.fixture()
def client(db_session):
    """TestClient de la app con get_db inyectando la sesion transaccional del test."""
    from fastapi.testclient import TestClient

    from database import get_db
    from main import app

    def _get_db_override():
        # Mismo contrato que database.get_db: al terminar el request la sesion
        # se cierra, descartando escrituras pendientes no commiteadas (rollback
        # del savepoint). Sin esto, un request que falla a mitad de transaccion
        # dejaria residuos visibles para las aserciones del test, cosa que en
        # produccion nunca ocurre.
        try:
            yield db_session
        finally:
            db_session.close()

    app.dependency_overrides[get_db] = _get_db_override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def _token_jwt(usuario: str) -> dict:
    from main import ALGORITHM, SECRET_KEY

    token = jwt.encode(
        {"sub": usuario, "exp": datetime.now(timezone.utc) + timedelta(minutes=30)},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )
    return {"Authorization": f"Bearer {token}"}


UsuarioTest = namedtuple("UsuarioTest", ["usuario", "headers"])


@pytest.fixture()
def crear_usuario(db_session):
    """Fabrica de usuarios de prueba. Devuelve UsuarioTest(usuario, headers) con
    las cabeceras Authorization listas.

    admin=True otorga el permiso sobre el seg_rol ROLE_ADMIN ya existente en la
    BD de test (no se crea el rol: si faltara, el fixture falla explicitamente).
    """

    def _crear(admin: bool = False, contrasena: str | None = None, habilitado: str = '1') -> UsuarioTest:
        from main import hash_password

        usuario = f"pytest_{uuid.uuid4().hex[:12]}"
        # contrasena=None deja un hash inutilizable: el usuario sirve para JWT
        # directo pero no puede loguearse (los tests de login pasan una real).
        hash_contrasena = hash_password(contrasena) if contrasena else 'sin-password-usable'
        db_session.execute(text("""
            INSERT INTO seg_usuario
                (paterno, materno, nombres, nro_documento, email, p_cargo, usuario,
                 contrasena, fechacreacion, tipousuario, fechainiciovigencia,
                 fechafinvigencia, habilitado, estado)
            VALUES
                ('FIXTURE', 'PYTEST', :usuario, '0', 'fixture@pytest.local', 0, :usuario,
                 :contrasena, CURDATE(), '1', CURDATE(),
                 DATE_ADD(CURDATE(), INTERVAL 10 YEAR), :habilitado, 'HAB')
        """), {"usuario": usuario, "contrasena": hash_contrasena, "habilitado": habilitado})
        id_usuario = db_session.execute(text("SELECT LAST_INSERT_ID()")).scalar()

        if admin:
            id_rol = db_session.execute(text(
                "SELECT id FROM seg_rol WHERE codigo = 'ROLE_ADMIN' AND estado = 'HAB' LIMIT 1"
            )).scalar()
            assert id_rol is not None, "La BD de test debe tener seg_rol ROLE_ADMIN HAB"
            db_session.execute(text(
                "INSERT INTO seg_permiso (id_usuario, id_rol, estado) VALUES (:u, :r, 'HAB')"
            ), {"u": id_usuario, "r": id_rol})

        db_session.commit()
        return UsuarioTest(usuario=usuario, headers=_token_jwt(usuario))

    return _crear


class EscenarioAjustes:
    """Constructor de escenarios para los modulos de inventario (AJUSTES y
    captura de paloteo).

    Crea una categoria propia (fuera de las excluidas 18/10 por auto_increment),
    una operativa (con o sin cabecera de inventario fisico) y productos de
    catalogo con su ideal (bar_inventario) y, para AJUSTES, su conteo fisico
    (bar_detalle_fisico). Todo queda dentro de la transaccion del test.
    """

    def __init__(self, db: Session):
        self.db = db
        self.id_barra = BARRA_FIXTURE
        self.id_operacion = None
        self.id_inventario_fisico = None
        self.db.execute(text("""
            INSERT INTO alm_categoria (nombre, p_grupo_categoria, usuario_reg, estado)
            VALUES ('CATEGORIA PYTEST AJUSTES', 8, 'pytest', 'HAB')
        """))
        self.id_categoria = self._ultimo_id()

    def _ultimo_id(self) -> int:
        return self.db.execute(text("SELECT LAST_INSERT_ID()")).scalar()

    def crear_operacion(self, estado_operacion: int = 23,
                        con_cabecera_fisico: bool = True) -> "EscenarioAjustes":
        """Operativa en el estado dado (23 = CERRADO, exigido por preview/aplicar;
        24 = INICIO CIERRE, exigido por la captura de paloteo).

        con_cabecera_fisico=False deja la operativa sin cabecera HAB de
        bar_inventario_fisico — como la encuentra POST /api/inventario/paloteo,
        que crea la suya y responde 409 si ya existe una."""
        self.db.execute(text("""
            INSERT INTO ope_operacion
                (fecha, nombre_operacion, estado_operacion, comision, id_dia, usuario_reg, estado)
            VALUES (CURDATE(), 'OPERATIVA PYTEST AJUSTES', :estado_op, 0, 1, 'pytest', 'HAB')
        """), {"estado_op": estado_operacion})
        self.id_operacion = self._ultimo_id()

        if con_cabecera_fisico:
            self.db.execute(text("""
                INSERT INTO bar_inventario_fisico
                    (fecha, observaciones, estado_registro, id_barra, id_operacion,
                     usuario_reg, fecha_reg, estado)
                VALUES (CURDATE(), 'FIXTURE PYTEST', 1, :id_barra, :id_operacion,
                        'pytest', CURDATE(), 'HAB')
            """), {"id_barra": self.id_barra, "id_operacion": self.id_operacion})
            self.id_inventario_fisico = self._ultimo_id()
        self.db.commit()
        return self

    def agregar_producto_catalogo(
        self,
        nombre: str,
        *,
        perfil: str | None = "pesable",
        ideal_paq: float = 0.0,
        ideal_det: float = 0.0,
        filas_inventario: int = 1,
        excluido: bool = False,
        capacidad_oz: float | None = None,
    ) -> tuple[int, int | None]:
        """Producto de catalogo + stock ideal en bar_inventario, SIN conteo
        fisico (la captura de paloteo lo registra ella misma). Devuelve
        (id_producto, id_perfil).

        perfil: "pesable" (config con pesable=1, perfil BRIGHTON PINK del doc
        redondeo_y_tolerancia.md seccion 6: tara 558 g, 29.063830 g/oz, bruto
        1241 g), "unidades" (config con pesable=0, se cuenta por botellas) o
        None (sin configuracion: la captura lo reporta en productos_omitidos).
        capacidad_oz llena alm_producto.cantidad_detalle (onzas de botella
        llena, usada por la validacion de sobrecapacidad del paloteo)."""
        self.db.execute(text("""
            INSERT INTO alm_producto
                (nombre, correlativo, id_categoria, medida, p_unidad_medida,
                 cantidad_detalle, codigo, usuario_reg, estado)
            VALUES (:nombre, 0, :id_categoria, 750, 0, :capacidad, :codigo, 'pytest', 'HAB')
        """), {"nombre": nombre, "id_categoria": self.id_categoria,
               "capacidad": capacidad_oz, "codigo": f"PYT-{nombre[:12]}"})
        id_producto = self._ultimo_id()

        id_perfil = None
        if perfil is not None:
            self.db.execute(text("""
                INSERT INTO app_producto_pesaje_config_api
                    (id_producto_almacen, nombre_perfil, peso_bruto, tara,
                     gramos_por_oz, pesable, usuario_reg)
                VALUES (:id_producto, 'PERFIL PYTEST', 1241.00, 558.00,
                        29.063830, :pesable, 'pytest')
            """), {"id_producto": id_producto, "pesable": 1 if perfil == "pesable" else 0})
            id_perfil = self._ultimo_id()

        for _ in range(filas_inventario):
            self.db.execute(text("""
                INSERT INTO bar_inventario
                    (cantidad_paq, cantidad_detalle, id_producto, id_barra, usuario_reg, estado)
                VALUES (:paq, :det, :id_producto, :id_barra, 'pytest', 'HAB')
            """), {
                "paq": ideal_paq, "det": ideal_det,
                "id_producto": id_producto, "id_barra": self.id_barra,
            })
            if excluido:
                self.db.execute(
                    text("INSERT INTO inventario_excluido (id) VALUES (:id)"),
                    {"id": self._ultimo_id()},
                )
        self.db.commit()
        return id_producto, id_perfil

    def agregar_producto(
        self,
        nombre: str,
        *,
        pesable: bool,
        ideal_paq: float,
        ideal_det: float,
        real_paq: float,
        real_det: float,
        filas_inventario: int = 1,
        excluido: bool = False,
    ) -> int:
        """Alta de producto + ideal + conteo fisico ya registrado (escenarios de
        AJUSTES). Devuelve el id del producto.

        pesable=False crea el producto sin configuracion de pesaje (solo el
        EXISTS pesable=1 decide en _calcular_diferencias_paloteo).
        filas_inventario controla la cardinalidad en bar_inventario (0 = sin
        fila, 2 = duplicada) para los tests de _validar_cardinalidad.
        excluido=True registra la fila de bar_inventario en inventario_excluido.
        """
        assert self.id_inventario_fisico, "Llamar crear_operacion() antes de agregar productos"

        id_producto, _ = self.agregar_producto_catalogo(
            nombre,
            perfil="pesable" if pesable else None,
            ideal_paq=ideal_paq,
            ideal_det=ideal_det,
            filas_inventario=filas_inventario,
            excluido=excluido,
        )

        self.db.execute(text("""
            INSERT INTO bar_detalle_fisico
                (cantidad_unidad, cantidad_detalle, id_producto, id_inventario_fisico,
                 usuario_reg, fecha_reg, estado)
            VALUES (:paq, :det, :id_producto, :id_fisico, 'pytest', CURDATE(), 'HAB')
        """), {
            "paq": real_paq, "det": real_det,
            "id_producto": id_producto, "id_fisico": self.id_inventario_fisico,
        })
        self.db.commit()
        return id_producto

    def inventario_de(self, id_producto: int) -> list[tuple]:
        """Filas HAB (cantidad_paq, cantidad_detalle) de bar_inventario del producto."""
        filas = self.db.execute(text("""
            SELECT cantidad_paq, cantidad_detalle FROM bar_inventario
            WHERE id_producto = :p AND id_barra = :b AND estado = 'HAB'
        """), {"p": id_producto, "b": self.id_barra}).fetchall()
        return [(float(f[0]), float(f[1])) for f in filas]


@pytest.fixture()
def escenario_ajustes(db_session):
    return EscenarioAjustes(db_session)


@pytest.fixture()
def escenario_paloteo(db_session):
    """Mismo constructor de escenarios; alias para los tests de captura de
    paloteo, que usan crear_operacion(24, con_cabecera_fisico=False) y
    agregar_producto_catalogo (sin conteo fisico previo)."""
    return EscenarioAjustes(db_session)
