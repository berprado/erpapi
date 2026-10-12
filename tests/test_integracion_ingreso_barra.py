"""POST /api/operaciones/ingreso-barra (y /preview): ingreso de proveedor ->
traspaso -> recepcion en barra en una sola transaccion, contra la BD de test
local (ver conftest.py: todo se revierte al terminar cada test).

Las filas esperadas son las que dejo el POS en las pruebas en vivo de test_pos
(documentos/operaciones_pos/01_ingreso_traspaso_recepcion.md).

Los tests del flujo simulan la verificacion del motor WAC (corren aunque la
base no tenga V9.44) y no miran el costo promedio. test_wac_igual_al_pos usa
el trigger real: corre si la base tiene trg_wac_alm_ingreso_after_update
(la BD local lo tiene desde el 2026-10-12) y se omite si no.
"""
import uuid
from datetime import date

import pytest
from sqlalchemy import text

URL = "/api/operaciones/ingreso-barra"
BARRA = 1
DOC_OTRO = 40


class EscenarioIngreso:
    def __init__(self, db):
        self.db = db
        # Las operativas EN PROCESO que ya hubiera en la BD local se pasan a
        # CERRADO dentro de la transaccion del test: el flujo exige una sola.
        self.db.execute(text("UPDATE ope_operacion SET estado_operacion = 23 WHERE estado_operacion IN (22, 24)"))
        self.db.execute(text("""
            INSERT INTO ope_operacion (fecha, nombre_operacion, estado_operacion, comision, id_dia, usuario_reg, estado)
            VALUES ('2026-10-07', 'OPERATIVA PYTEST INGRESO', 22, 0, 1, 'pytest_ope', 'HAB')
        """))
        self.id_operacion = self._id()
        self.db.execute(text("INSERT INTO alm_almacen (nombre, usuario_reg, estado) VALUES ('ALMACEN PYTEST', 'pytest', 'HAB')"))
        self.id_almacen = self._id()
        self.db.execute(text("INSERT INTO alm_proveedor (nombre, usuario_reg, estado) VALUES ('PROVEEDOR PYTEST', 'pytest', 'HAB')"))
        self.id_proveedor = self._id()
        self.db.execute(text("""
            INSERT INTO alm_categoria (nombre, p_grupo_categoria, usuario_reg, estado)
            VALUES ('CATEGORIA PYTEST INGRESO', 8, 'pytest', 'HAB')
        """))
        self.id_categoria = self._id()
        self.db.commit()

    def _id(self) -> int:
        return self.db.execute(text("SELECT LAST_INSERT_ID()")).scalar()

    def producto(self, nombre, *, almacen_paq=None, barra_paq=None, operacion_paq=None,
                 contenido=25.5, medida=750, wac=None) -> int:
        """Producto con filas opcionales en alm_inventario, bar_inventario y
        bar_inventario_operacion (None = sin fila) y WAC opcional."""
        self.db.execute(text("""
            INSERT INTO alm_producto (nombre, correlativo, id_categoria, medida, p_unidad_medida,
                                      cantidad_detalle, codigo, usuario_reg, estado)
            VALUES (:nombre, 0, :categoria, :medida, 11, :contenido, :codigo, 'pytest', 'HAB')
        """), {"nombre": nombre, "categoria": self.id_categoria, "medida": medida,
               "contenido": contenido, "codigo": f"PYT-{uuid.uuid4().hex[:8]}"})
        id_producto = self._id()
        if almacen_paq is not None:
            self.db.execute(text("""
                INSERT INTO alm_inventario (cantidad_paq, cantidad_detalle, id_producto, id_almacen, usuario_reg, estado)
                VALUES (:paq, 0, :p, :a, 'pytest', 'HAB')
            """), {"paq": almacen_paq, "p": id_producto, "a": self.id_almacen})
        if barra_paq is not None:
            self.db.execute(text("""
                INSERT INTO bar_inventario (cantidad_paq, cantidad_detalle, id_producto, id_barra, usuario_reg, estado)
                VALUES (:paq, 0, :p, :b, 'pytest', 'HAB')
            """), {"paq": barra_paq, "p": id_producto, "b": BARRA})
        if operacion_paq is not None:
            self.db.execute(text("""
                INSERT INTO bar_inventario_operacion (cantidad_paq, cantidad_detalle, inicial_paq, inicial_detalle,
                                                      id_barra, id_operacion, id_producto, usuario_reg, estado)
                VALUES (:paq, 0, :paq, 0, :b, :o, :p, 'pytest', 'HAB')
            """), {"paq": operacion_paq, "b": BARRA, "o": self.id_operacion, "p": id_producto})
        if wac is not None:
            self.db.execute(text("""
                INSERT INTO cache_wac_producto (id_almacen, id_producto, wac_actual) VALUES (:a, :p, :w)
                ON DUPLICATE KEY UPDATE wac_actual = VALUES(wac_actual)
            """), {"a": self.id_almacen, "p": id_producto, "w": wac})
        self.db.commit()
        return id_producto

    def payload(self, lineas, **extra) -> dict:
        datos = {
            "id_almacen": self.id_almacen,
            "id_proveedor": self.id_proveedor,
            "ind_tipo_documento": DOC_OTRO,
            "id_barra": BARRA,
            "clave_idempotencia": uuid.uuid4().hex,
            "lineas": lineas,
        }
        datos.update(extra)
        return datos

    def fila(self, sql, **params):
        return self.db.execute(text(sql), params).mappings().first()

    def filas(self, sql, **params):
        return self.db.execute(text(sql), params).mappings().all()

    def contar_documentos(self) -> tuple:
        return tuple(self.db.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar() for t in (
            "alm_ingreso", "alm_detalle_ingreso", "alm_salida_inventario", "alm_detalle_salida_inv",
            "ope_novedades", "app_operacion_pos_control"))


@pytest.fixture()
def motor_wac_simulado(monkeypatch):
    import main
    monkeypatch.setattr(main, "_motor_wac_v944_instalado", lambda db: True)


@pytest.fixture()
def escenario(db_session, motor_wac_simulado):
    return EscenarioIngreso(db_session)


@pytest.fixture()
def admin(crear_usuario):
    return crear_usuario(admin=True)


def test_flujo_completo_deja_las_filas_del_pos(client, escenario, admin):
    # A: ya tiene stock en almacen, en barra y fila de la operativa. B: sin ninguna fila.
    a = escenario.producto("PYTEST COCA", almacen_paq=3, barra_paq=5, operacion_paq=5)
    b = escenario.producto("PYTEST HAVANA")
    respuesta = client.post(URL, headers=admin.headers, json=escenario.payload([
        {"id_producto": a, "cantidad": 6, "precio_costo": 19, "cantidad_a_barra": 3},
        {"id_producto": b, "cantidad": 2, "precio_costo": 135, "cantidad_a_barra": 2},
    ], observaciones="PRUEBA PYTEST"))
    assert respuesta.status_code == 200, respuesta.text
    datos = respuesta.json()
    assert datos["status"] == "success"
    id_ingreso, id_salida = datos["id_ingreso"], datos["id_salida_inventario"]
    nombre = f"FIXTURE PYTEST, {admin.usuario}"

    ingreso = escenario.fila("SELECT * FROM alm_ingreso WHERE id = :i", i=id_ingreso)
    assert ingreso["ind_estado_ingreso"] == "1"
    assert ingreso["ind_tipo_ingreso"] == 80
    assert ingreso["id_operacion"] == escenario.id_operacion
    assert ingreso["recepcionado_por"] == nombre
    assert ingreso["usuario_reg"] == admin.usuario
    assert ingreso["numero_documento"] == "0"
    assert ingreso["fecha_mod"] is not None  # dos lineas: el POS vuelve a guardar la cabecera
    assert ingreso["id_barra"] is None and ingreso["ind_tipo_pago"] is None

    detalles = {f["id_producto"]: f for f in escenario.filas(
        "SELECT * FROM alm_detalle_ingreso WHERE id_ingreso = :i", i=id_ingreso)}
    assert str(detalles[a]["precio_costo_real"]) == "20.65217"
    assert str(detalles[b]["precio_costo_real"]) == "146.73912"
    assert {d["ind_paq_detalle"] for d in detalles.values()} == {"1"}

    almacen = {f["id_producto"]: f for f in escenario.filas(
        "SELECT * FROM alm_inventario WHERE id_almacen = :a", a=escenario.id_almacen)}
    assert float(almacen[a]["cantidad_paq"]) == 6.0  # 3 + 6 - 3
    assert almacen[a]["usuario_reg"] == admin.usuario
    assert float(almacen[b]["cantidad_paq"]) == 0.0  # fila creada: 0 + 2 - 2
    assert float(almacen[b]["cantidad_detalle"]) == 0.0

    salida = escenario.fila("SELECT * FROM alm_salida_inventario WHERE id = :s", s=id_salida)
    assert (salida["ind_estado_salida"], salida["ind_tipo_movimiento"], salida["ind_tipo_salida"]) == (21, 83, 34)
    assert salida["id_operacion"] == escenario.id_operacion
    assert salida["responsable"] == nombre and salida["responsable_recepcion"] == nombre
    assert salida["observaciones_recepcion"] == "OK"
    assert salida["observaciones_salida"] == "PRUEBA PYTEST"
    assert salida["fecha_recepcion"] is not None and salida["fecha_mod"] is not None
    assert salida["correlativo"] is None and salida["id_proveedor"] is None
    cantidades = {f["id_producto"]: float(f["cantidad"]) for f in escenario.filas(
        "SELECT * FROM alm_detalle_salida_inv WHERE id_salida_inventario = :s", s=id_salida)}
    assert cantidades == {a: 3.0, b: 2.0}

    novedad = escenario.fila("SELECT * FROM ope_novedades WHERE id_operacion = :o", o=escenario.id_operacion)
    assert novedad["evento"] == (
        f"Se registró una salida del Almacen: ALMACEN PYTEST, con el correlativo NRO  {id_salida} en fecha: 07/10/2026"
    )
    assert novedad["usuario"] == admin.usuario

    barra = {f["id_producto"]: f for f in escenario.filas(
        "SELECT * FROM bar_inventario WHERE id_barra = :b AND id_producto IN (:a, :p)", b=BARRA, a=a, p=b)}
    assert float(barra[a]["cantidad_paq"]) == 8.0
    assert barra[a]["usuario_reg"] == admin.usuario and barra[a]["fecha_mod"] is not None
    assert float(barra[b]["cantidad_paq"]) == 2.0 and float(barra[b]["cantidad_detalle"]) == 0.0
    assert barra[b]["fecha_mod"] is None

    operacion = {f["id_producto"]: f for f in escenario.filas(
        "SELECT * FROM bar_inventario_operacion WHERE id_operacion = :o", o=escenario.id_operacion)}
    assert float(operacion[a]["cantidad_paq"]) == 8.0 and float(operacion[a]["inicial_paq"]) == 5.0
    assert operacion[a]["usuario_reg"] == admin.usuario
    # Fila nueva como la crea copyBarInventToInevetOperacion: usuario y estado de la operativa.
    assert float(operacion[b]["cantidad_paq"]) == 2.0
    assert operacion[b]["inicial_paq"] is None and operacion[b]["cantidad_detalle"] is None
    assert operacion[b]["usuario_reg"] == "pytest_ope" and operacion[b]["estado"] == "HAB"

    control = escenario.fila("SELECT * FROM app_operacion_pos_control WHERE id_ingreso = :i", i=id_ingreso)
    assert control["id_salida_inventario"] == id_salida and control["estado"] == "APLICADO"

    lineas = {l["id_producto"]: l for l in datos["lineas"]}
    assert (lineas[a]["almacen_antes"], lineas[a]["almacen_despues"]) == (3.0, 6.0)
    assert (lineas[a]["barra_antes"], lineas[a]["barra_despues"]) == (5.0, 8.0)
    assert datos["total"] == 6 * 19 + 2 * 135


def test_preview_no_deja_nada_escrito(client, escenario, admin):
    a = escenario.producto("PYTEST PREVIEW", almacen_paq=1, barra_paq=1, operacion_paq=1)
    antes = escenario.contar_documentos()
    respuesta = client.post(URL + "/preview", headers=admin.headers, json=escenario.payload([
        {"id_producto": a, "cantidad": 4, "precio_costo": 10, "cantidad_a_barra": 4},
    ]))
    assert respuesta.status_code == 200, respuesta.text
    datos = respuesta.json()
    assert datos["status"] == "preview" and datos["id_ingreso"] is None
    assert datos["lineas"][0]["barra_despues"] == 5.0
    assert escenario.contar_documentos() == antes
    assert float(escenario.fila("SELECT cantidad_paq FROM bar_inventario WHERE id_producto = :p", p=a)["cantidad_paq"]) == 1.0


def test_misma_clave_no_duplica_el_ingreso(client, escenario, admin):
    a = escenario.producto("PYTEST CLAVE", almacen_paq=0)
    payload = escenario.payload([{"id_producto": a, "cantidad": 2, "precio_costo": 5}])
    assert client.post(URL, headers=admin.headers, json=payload).status_code == 200
    repetido = client.post(URL, headers=admin.headers, json=payload)
    assert repetido.status_code == 409
    assert "ya fue registrada" in repetido.json()["detail"]
    assert float(escenario.fila("SELECT cantidad_paq FROM alm_inventario WHERE id_producto = :p", p=a)["cantidad_paq"]) == 2.0


def test_sin_traspaso_solo_ingresa_al_almacen(client, escenario, admin):
    a = escenario.producto("PYTEST SOLO ALMACEN", almacen_paq=1)
    respuesta = client.post(URL, headers=admin.headers, json=escenario.payload(
        [{"id_producto": a, "cantidad": 3, "precio_costo": 7}], id_barra=None))
    assert respuesta.status_code == 200, respuesta.text
    datos = respuesta.json()
    assert datos["id_salida_inventario"] is None
    ingreso = escenario.fila("SELECT * FROM alm_ingreso WHERE id = :i", i=datos["id_ingreso"])
    assert ingreso["fecha_mod"] is None  # una sola linea
    assert escenario.fila("SELECT COUNT(*) n FROM ope_novedades WHERE id_operacion = :o", o=escenario.id_operacion)["n"] == 0
    assert float(escenario.fila("SELECT cantidad_paq FROM alm_inventario WHERE id_producto = :p", p=a)["cantidad_paq"]) == 4.0


def test_traspaso_sin_barra_se_rechaza(client, escenario, admin):
    a = escenario.producto("PYTEST SIN BARRA", almacen_paq=0)
    respuesta = client.post(URL, headers=admin.headers, json=escenario.payload(
        [{"id_producto": a, "cantidad": 3, "precio_costo": 7, "cantidad_a_barra": 1}], id_barra=None))
    assert respuesta.status_code == 400


def test_operativa_en_inicio_cierre_no_escribe_nada(client, escenario, admin, db_session):
    a = escenario.producto("PYTEST CIERRE", almacen_paq=0)
    db_session.execute(text("UPDATE ope_operacion SET estado_operacion = 24 WHERE id = :o"), {"o": escenario.id_operacion})
    db_session.commit()
    antes = escenario.contar_documentos()
    respuesta = client.post(URL, headers=admin.headers, json=escenario.payload(
        [{"id_producto": a, "cantidad": 1, "precio_costo": 1, "cantidad_a_barra": 1}]))
    assert respuesta.status_code == 409
    assert "INICIO CIERRE" in respuesta.json()["detail"]
    assert escenario.contar_documentos() == antes


def test_sin_motor_wac_v944_se_rechaza(client, escenario, admin, monkeypatch):
    import main
    monkeypatch.setattr(main, "_motor_wac_v944_instalado", lambda db: False)
    a = escenario.producto("PYTEST SIN MOTOR", almacen_paq=0)
    respuesta = client.post(URL, headers=admin.headers, json=escenario.payload(
        [{"id_producto": a, "cantidad": 1, "precio_costo": 1}]))
    assert respuesta.status_code == 409
    assert "V9.44" in respuesta.json()["detail"]


def test_producto_sin_medidas_no_se_traspasa(client, escenario, admin):
    a = escenario.producto("PYTEST SIN CONTENIDO", almacen_paq=0, contenido=None)
    con_barra = client.post(URL, headers=admin.headers, json=escenario.payload(
        [{"id_producto": a, "cantidad": 1, "precio_costo": 1, "cantidad_a_barra": 1}]))
    assert con_barra.status_code == 400
    solo_almacen = client.post(URL, headers=admin.headers, json=escenario.payload(
        [{"id_producto": a, "cantidad": 1, "precio_costo": 1}]))
    assert solo_almacen.status_code == 200, solo_almacen.text


def test_fila_duplicada_en_barra_se_rechaza(client, escenario, admin, db_session):
    a = escenario.producto("PYTEST DUPLICADO", almacen_paq=0, barra_paq=1)
    db_session.execute(text("""
        INSERT INTO bar_inventario (cantidad_paq, cantidad_detalle, id_producto, id_barra, usuario_reg, estado)
        VALUES (1, 0, :p, :b, 'pytest', 'HAB')
    """), {"p": a, "b": BARRA})
    db_session.commit()
    antes = escenario.contar_documentos()
    respuesta = client.post(URL, headers=admin.headers, json=escenario.payload(
        [{"id_producto": a, "cantidad": 1, "precio_costo": 1, "cantidad_a_barra": 1}]))
    assert respuesta.status_code == 409
    assert escenario.contar_documentos() == antes


@pytest.mark.parametrize("lineas", [
    [{"id_producto": 1, "cantidad": 1, "precio_costo": 1}, {"id_producto": 1, "cantidad": 2, "precio_costo": 1}],
    [{"id_producto": 1, "cantidad": 1, "precio_costo": 1, "cantidad_a_barra": 2}],
    [{"id_producto": 1, "cantidad": 1, "precio_costo": 1.234}],
    [{"id_producto": 1, "cantidad": 0, "precio_costo": 1}],
])
def test_payload_invalido(client, escenario, admin, lineas):
    respuesta = client.post(URL, headers=admin.headers, json=escenario.payload(lineas))
    assert respuesta.status_code == 422


def test_solo_administrador(client, escenario, crear_usuario):
    a = escenario.producto("PYTEST NO ADMIN", almacen_paq=0)
    usuario = crear_usuario(admin=False)
    respuesta = client.post(URL, headers=usuario.headers, json=escenario.payload(
        [{"id_producto": a, "cantidad": 1, "precio_costo": 1}]))
    assert respuesta.status_code == 403


def test_contexto_y_buscador(client, escenario, admin):
    a = escenario.producto("PYTEST BUSCAR XYZ", almacen_paq=4, barra_paq=2, wac=12.5)
    contexto = client.get(URL + "/contexto", headers=admin.headers)
    assert contexto.status_code == 200, contexto.text
    datos = contexto.json()
    assert datos["operativa_lista"] and datos["operativa"]["id_operacion"] == escenario.id_operacion
    assert {"id": 38, "nombre": "FACTURA"} in datos["tipos_documento"]
    assert any(al["id"] == escenario.id_almacen for al in datos["almacenes"])

    encontrados = client.get(URL + "/productos", headers=admin.headers, params={
        "q": "BUSCAR XYZ", "id_almacen": escenario.id_almacen, "id_barra": BARRA}).json()
    assert len(encontrados) == 1
    assert encontrados[0]["id_producto"] == a
    assert (encontrados[0]["stock_almacen"], encontrados[0]["stock_barra"], encontrados[0]["wac_actual"]) == (4.0, 2.0, 12.5)
    assert encontrados[0]["traspasable"] is True
    assert (encontrados[0]["stock_almacen_detalle"], encontrados[0]["stock_barra_detalle"]) == (0.0, 0.0)

    por_ids = client.get(URL + "/productos", headers=admin.headers, params={
        "ids": str(a), "id_almacen": escenario.id_almacen, "id_barra": BARRA}).json()
    assert [p["id_producto"] for p in por_ids] == [a]
    assert client.get(URL + "/productos", headers=admin.headers,
                      params={"id_almacen": escenario.id_almacen}).status_code == 422


def test_wac_igual_al_pos(client, db_session, crear_usuario):
    """Con el motor V9.44 real (corregido 2026-10-12). El POS y la API suman el
    stock antes de pasar el ingreso a '1'; el trigger descuenta lo que el mismo
    ingreso ya sumó, así que sin stock previo el WAC toma el costo nuevo
    (HAVANA 7A: 169.2853 -> 135.0000). Con el trigger anterior a la corrección
    quedaba en 152.1427 (las unidades compradas contadas dos veces)."""
    import main
    if not main._motor_wac_v944_instalado(db_session):
        pytest.skip("La BD local no tiene trg_wac_alm_ingreso_after_update (motor WAC V9.44).")
    escenario = EscenarioIngreso(db_session)
    admin = crear_usuario(admin=True)
    b = escenario.producto("PYTEST WAC", almacen_paq=0, wac=169.2853)
    respuesta = client.post(URL, headers=admin.headers, json=escenario.payload(
        [{"id_producto": b, "cantidad": 2, "precio_costo": 135, "cantidad_a_barra": 2}]))
    assert respuesta.status_code == 200, respuesta.text
    linea = respuesta.json()["lineas"][0]
    assert (linea["wac_antes"], linea["wac_despues"]) == (169.2853, 135.0)
    historial = escenario.fila("SELECT * FROM cache_wac_historial WHERE id_ingreso = :i", i=respuesta.json()["id_ingreso"])
    assert float(historial["wac_anterior"]) == 169.2853
