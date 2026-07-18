"""Tests de integracion del modulo AJUSTES contra la BD de test local.

Cubren /api/inventario/consolidar/preview y /api/inventario/ajustes/aplicar
punta a punta: SQL real de _calcular_diferencias_paloteo (incluida la vista
vista_inventario_barra_con_filtro y la exclusion via inventario_excluido),
tolerancia/cuantizacion, generacion de cabeceras y detalles, igualacion de
bar_inventario, idempotencia, cardinalidad, gating de admin y estado de la
operativa. Todo corre dentro de una transaccion que se revierte (ver
conftest.py); la BD queda intacta.

Los escenarios replican los casos de documentos/redondeo_y_tolerancia.md
seccion 6 (BRIGHTON PINK / GEORGE FORSTER) con productos fixture propios.

NOTA (igualacion incondicional de bar_inventario): desde v10.77 toda
consolidacion que SE APLICA escribe el fisico exacto de todo producto cuyo
fisico difiera del ideal, aunque su delta caiga dentro de la banda de
tolerancia y no genere movimiento documental
(test_aplicar_iguala_bar_inventario_de_producto_tolerado). El limite de la
garantia: si NINGUN producto genera movimientos, aplicar responde skipped sin
escribir nada — no hay consolidacion, y las diferencias toleradas quedan como
estaban (test_aplicar_todo_tolerado_responde_skipped_sin_escribir).
"""
from sqlalchemy import text


PREVIEW = "/api/inventario/consolidar/preview"
APLICAR = "/api/inventario/ajustes/aplicar"


def _payload(esc, observaciones="AJUSTE PYTEST"):
    return {
        "id_operacion": esc.id_operacion,
        "id_barra": esc.id_barra,
        "observaciones": observaciones,
    }


def _armar_escenario_base(esc):
    """Escenario compartido: control sin diferencia, sobrante det de 0.5,
    caso mixto (falta 1 botella, sobran 66 oz), sobrante de 2 unidades no
    pesables y un delta de 0.3 oz dentro de la banda de tolerancia."""
    esc.crear_operacion(estado_operacion=23)
    productos = {
        "control": esc.agregar_producto(
            "PYTEST CONTROL", pesable=True,
            ideal_paq=2, ideal_det=19.0, real_paq=2, real_det=19.0),
        "sobrante_det": esc.agregar_producto(
            "PYTEST SOBRANTE DET", pesable=True,
            ideal_paq=0, ideal_det=40.0, real_paq=0, real_det=40.5),
        "mixto": esc.agregar_producto(
            "PYTEST MIXTO", pesable=True,
            ideal_paq=2, ideal_det=5.0, real_paq=1, real_det=71.0),
        "paq": esc.agregar_producto(
            "PYTEST PAQ", pesable=False,
            ideal_paq=10, ideal_det=0, real_paq=12, real_det=0),
        "tolerado": esc.agregar_producto(
            "PYTEST TOLERADO", pesable=True,
            ideal_paq=0, ideal_det=19.0, real_paq=0, real_det=19.3),
    }
    return productos


# ---------------------------------------------------------------------------
# PREVIEW
# ---------------------------------------------------------------------------

def test_preview_calcula_deltas_y_buckets(client, crear_usuario, escenario_ajustes):
    esc = escenario_ajustes
    productos = _armar_escenario_base(esc)
    usuario = crear_usuario()

    r = client.post(PREVIEW, json=_payload(esc), headers=usuario.headers)
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["status"] == "ok"
    assert data["ya_aplicado"] is False
    assert data["resumen"] == {
        "productos_evaluados": 5,
        "productos_con_diferencia": 3,
        "movimientos_generados": 4,
    }

    deltas = {d["id_producto"]: d for d in data["deltas"]}
    assert set(deltas) == set(productos.values())

    d_sobrante = deltas[productos["sobrante_det"]]
    assert d_sobrante["pesable"] == 1
    assert d_sobrante["tolerancia_oz"] == 0.5
    assert d_sobrante["delta_paq"] == 0.0
    # limite estricto de la banda: |0.5| < 0.5 es falso, el delta SI ajusta
    assert d_sobrante["delta_det_exacto"] == 0.5
    assert d_sobrante["delta_det_operativo"] == 0.5

    d_mixto = deltas[productos["mixto"]]
    assert d_mixto["delta_paq"] == -1.0
    assert d_mixto["delta_det_operativo"] == 66.0

    d_paq = deltas[productos["paq"]]
    assert d_paq["pesable"] == 0
    assert d_paq["tolerancia_oz"] == 0.0
    assert d_paq["delta_paq"] == 2.0

    d_tolerado = deltas[productos["tolerado"]]
    assert abs(d_tolerado["delta_det_exacto"] - 0.3) < 1e-9
    assert d_tolerado["delta_det_operativo"] == 0.0

    sobrantes_det = {m["id_producto"]: m for m in data["sobrantes_det"]}
    assert set(sobrantes_det) == {productos["sobrante_det"], productos["mixto"]}
    assert sobrantes_det[productos["sobrante_det"]]["cantidad"] == 0.5
    assert sobrantes_det[productos["sobrante_det"]]["ind_paq_detalle"] == "0"
    assert sobrantes_det[productos["mixto"]]["cantidad"] == 66.0
    assert data["faltantes_paq"] == [
        {"id_producto": productos["mixto"], "cantidad": 1.0, "ind_paq_detalle": "1"}
    ]
    assert data["sobrantes_paq"] == [
        {"id_producto": productos["paq"], "cantidad": 2.0, "ind_paq_detalle": "1"}
    ]
    assert data["faltantes_det"] == []


def test_preview_sin_diferencias_reporta_skipped(client, crear_usuario, escenario_ajustes):
    esc = escenario_ajustes
    esc.crear_operacion()
    esc.agregar_producto("PYTEST CONTROL", pesable=True,
                         ideal_paq=2, ideal_det=19.0, real_paq=2, real_det=19.0)
    usuario = crear_usuario()

    r = client.post(PREVIEW, json=_payload(esc), headers=usuario.headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "skipped"
    assert data["resumen"]["productos_evaluados"] == 1
    assert data["resumen"]["productos_con_diferencia"] == 0


def test_preview_producto_excluido_no_participa(client, crear_usuario, escenario_ajustes):
    """inventario_excluido saca al producto del calculo aunque tenga diferencia.
    Este join roto en una rama anterior dejo los deltas vacios en silencio:
    es exactamente la regresion que este test vigila."""
    esc = escenario_ajustes
    esc.crear_operacion()
    id_normal = esc.agregar_producto("PYTEST NORMAL", pesable=False,
                                     ideal_paq=10, ideal_det=0, real_paq=12, real_det=0)
    id_excluido = esc.agregar_producto("PYTEST EXCLUIDO", pesable=False,
                                       ideal_paq=0, ideal_det=0, real_paq=5, real_det=0,
                                       excluido=True)
    usuario = crear_usuario()

    r = client.post(PREVIEW, json=_payload(esc), headers=usuario.headers)
    assert r.status_code == 200, r.text
    data = r.json()
    ids = {d["id_producto"] for d in data["deltas"]}
    assert id_normal in ids
    assert id_excluido not in ids
    assert data["resumen"]["productos_evaluados"] == 1


# ---------------------------------------------------------------------------
# APLICAR — camino feliz y estado resultante en BD
# ---------------------------------------------------------------------------

def test_aplicar_genera_movimientos_e_iguala_inventario(client, crear_usuario,
                                                        escenario_ajustes, db_session):
    esc = escenario_ajustes
    productos = _armar_escenario_base(esc)
    admin = crear_usuario(admin=True)

    r = client.post(APLICAR, json=_payload(esc), headers=admin.headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "success"
    assert data["productos_afectados"] == 3
    assert data["igualacion_verificada"] is True
    assert data["id_ajuste"] is not None          # hay sobrantes
    assert data["id_salida_inventario"] is not None  # hay faltantes

    cab_ajuste = db_session.execute(text(
        "SELECT ind_estado_ingreso, ind_tipo_movimiento, id_barra, estado "
        "FROM bar_ajuste WHERE id = :id"), {"id": data["id_ajuste"]}).fetchone()
    assert tuple(cab_ajuste) == (20, 84, esc.id_barra, "HAB")

    cab_salida = db_session.execute(text(
        "SELECT ind_estado_salida, ind_tipo_salida, id_barra, estado "
        "FROM bar_salida_inventario WHERE id = :id"), {"id": data["id_salida_inventario"]}).fetchone()
    assert tuple(cab_salida) == (20, 77, esc.id_barra, "HAB")

    det_ingreso = db_session.execute(text(
        "SELECT id_producto, cantidad, ind_paq_detalle FROM bar_detalle_ajuste "
        "WHERE id_ajuste = :id ORDER BY id"), {"id": data["id_ajuste"]}).fetchall()
    assert {(f[0], float(f[1]), f[2]) for f in det_ingreso} == {
        (productos["sobrante_det"], 0.5, "0"),
        (productos["mixto"], 66.0, "0"),
        (productos["paq"], 2.0, "1"),
    }

    det_salida = db_session.execute(text(
        "SELECT id_producto, cantidad, ind_paq_detalle FROM bar_detalle_salida_inv "
        "WHERE id_salida_inventario = :id"), {"id": data["id_salida_inventario"]}).fetchall()
    assert {(f[0], float(f[1]), f[2]) for f in det_salida} == {
        (productos["mixto"], 1.0, "1"),
    }

    # bar_inventario igualado al fisico exacto para los productos ajustados
    assert esc.inventario_de(productos["sobrante_det"]) == [(0.0, 40.5)]
    assert esc.inventario_de(productos["mixto"]) == [(1.0, 71.0)]
    assert esc.inventario_de(productos["paq"]) == [(12.0, 0.0)]
    # el producto sin diferencia alguna no se toca
    assert esc.inventario_de(productos["control"]) == [(2.0, 19.0)]

    control = db_session.execute(text(
        "SELECT estado, id_ajuste, id_salida_inventario FROM app_paloteo_ajuste_control "
        "WHERE id_operacion = :op AND id_barra = :b AND id_inventario_fisico = :f"),
        {"op": esc.id_operacion, "b": esc.id_barra, "f": esc.id_inventario_fisico}).fetchall()
    assert len(control) == 1
    assert tuple(control[0]) == ("APLICADO", data["id_ajuste"], data["id_salida_inventario"])


def test_aplicar_iguala_bar_inventario_de_producto_tolerado(client, crear_usuario,
                                                            escenario_ajustes, db_session):
    """Igualacion incondicional (v10.77): un producto cuya unica diferencia cae
    dentro de la banda no genera movimiento, pero bar_inventario SI recibe su
    fisico exacto (19.3, no el ideal 19.0). Sin esto, si el invariante
    multiplo-de-0.5 se rompiera, la diferencia tolerada divergiria en silencio
    y se arrastraria entre operativas via bar_inventario_cierre."""
    esc = escenario_ajustes
    productos = _armar_escenario_base(esc)
    admin = crear_usuario(admin=True)

    r = client.post(APLICAR, json=_payload(esc), headers=admin.headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert esc.inventario_de(productos["tolerado"]) == [(0.0, 19.3)]
    # sin movimiento documental para el tolerado: no aparece en ningun detalle
    en_detalles = db_session.execute(text(
        "SELECT COUNT(*) FROM bar_detalle_ajuste WHERE id_ajuste = :id AND id_producto = :p"),
        {"id": data["id_ajuste"], "p": productos["tolerado"]}).scalar()
    assert en_detalles == 0
    # la igualacion extra queda auditada en el control y avisada en el mensaje
    payload_control = db_session.execute(text(
        "SELECT payload_json FROM app_paloteo_ajuste_control WHERE id_operacion = :op"),
        {"op": esc.id_operacion}).scalar()
    assert '"igualaciones_sin_movimiento"' in payload_control
    assert str(productos["tolerado"]) in payload_control
    assert "banda de tolerancia" in data["mensaje"]


def test_aplicar_todo_tolerado_responde_skipped_sin_escribir(client, crear_usuario,
                                                             escenario_ajustes, db_session):
    """Limite documentado de la garantia: si ningun producto genera movimientos
    no hay consolidacion que aplicar — se responde skipped, no se crea control
    y bar_inventario no se toca (coherente con el preview, que en este caso
    reporta skipped y la PWA ni ofrece el boton de aplicar)."""
    esc = escenario_ajustes
    esc.crear_operacion()
    id_tolerado = esc.agregar_producto("PYTEST SOLO TOLERADO", pesable=True,
                                       ideal_paq=0, ideal_det=19.0, real_paq=0, real_det=19.3)
    admin = crear_usuario(admin=True)

    r = client.post(APLICAR, json=_payload(esc), headers=admin.headers)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "skipped"
    assert esc.inventario_de(id_tolerado) == [(0.0, 19.0)]
    control = db_session.execute(text(
        "SELECT COUNT(*) FROM app_paloteo_ajuste_control WHERE id_operacion = :op"),
        {"op": esc.id_operacion}).scalar()
    assert control == 0


def test_aplicar_asimetria_producto_con_delta_paq_arrastra_det_tolerado(
        client, crear_usuario, escenario_ajustes):
    """Si el producto ademas tiene diferencia de botellas, SI entra a la lista
    y bar_inventario recibe el fisico exacto CON la diferencia de onzas
    tolerada incluida (19.3, no 19.0) — la asimetria documentada en TODO.md.
    Este comportamiento debe mantenerse tras la igualacion incondicional."""
    esc = escenario_ajustes
    esc.crear_operacion()
    id_asimetrico = esc.agregar_producto(
        "PYTEST ASIMETRICO", pesable=True,
        ideal_paq=2, ideal_det=19.0, real_paq=1, real_det=19.3)
    admin = crear_usuario(admin=True)

    r = client.post(APLICAR, json=_payload(esc), headers=admin.headers)
    assert r.status_code == 200, r.text
    data = r.json()
    # la unica diferencia operativa es la botella faltante...
    assert data["id_salida_inventario"] is not None
    assert data["id_ajuste"] is None
    # ...pero la igualacion escribe el fisico exacto, onzas toleradas incluidas
    assert esc.inventario_de(id_asimetrico) == [(1.0, 19.3)]


def test_aplicar_sin_diferencias_responde_skipped_sin_crear_nada(client, crear_usuario,
                                                                 escenario_ajustes, db_session):
    esc = escenario_ajustes
    esc.crear_operacion()
    esc.agregar_producto("PYTEST CONTROL", pesable=True,
                         ideal_paq=2, ideal_det=19.0, real_paq=2, real_det=19.0)
    admin = crear_usuario(admin=True)

    r = client.post(APLICAR, json=_payload(esc), headers=admin.headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "skipped"
    assert data["id_ajuste"] is None
    assert data["id_salida_inventario"] is None

    control = db_session.execute(text(
        "SELECT COUNT(*) FROM app_paloteo_ajuste_control WHERE id_operacion = :op"),
        {"op": esc.id_operacion}).scalar()
    assert control == 0


# ---------------------------------------------------------------------------
# APLICAR — idempotencia, permisos, estado de operativa, cardinalidad
# ---------------------------------------------------------------------------

def test_aplicar_dos_veces_responde_409(client, crear_usuario, escenario_ajustes):
    esc = escenario_ajustes
    _armar_escenario_base(esc)
    admin = crear_usuario(admin=True)

    r1 = client.post(APLICAR, json=_payload(esc), headers=admin.headers)
    assert r1.status_code == 200, r1.text

    r2 = client.post(APLICAR, json=_payload(esc), headers=admin.headers)
    assert r2.status_code == 409
    assert "ya fueron aplicados" in r2.json()["detail"]

    # y el preview lo reporta sin bloquear la consulta
    r3 = client.post(PREVIEW, json=_payload(esc), headers=admin.headers)
    assert r3.status_code == 200
    assert r3.json()["ya_aplicado"] is True


def test_aplicar_requiere_rol_admin(client, crear_usuario, escenario_ajustes):
    esc = escenario_ajustes
    _armar_escenario_base(esc)
    operador = crear_usuario(admin=False)

    # preview es de cualquier usuario autenticado; aplicar exige ROLE_ADMIN
    assert client.post(PREVIEW, json=_payload(esc), headers=operador.headers).status_code == 200
    r = client.post(APLICAR, json=_payload(esc), headers=operador.headers)
    assert r.status_code == 403


def test_endpoints_exigen_operacion_en_estado_23(client, crear_usuario, escenario_ajustes):
    esc = escenario_ajustes
    esc.crear_operacion(estado_operacion=24)  # INICIO CIERRE: valido para paloteo, no para ajustes
    esc.agregar_producto("PYTEST PAQ", pesable=False,
                         ideal_paq=10, ideal_det=0, real_paq=12, real_det=0)
    admin = crear_usuario(admin=True)

    for endpoint in (PREVIEW, APLICAR):
        r = client.post(endpoint, json=_payload(esc), headers=admin.headers)
        assert r.status_code == 400, f"{endpoint}: {r.text}"
        assert "CERRADO (23)" in r.json()["detail"]


def test_cardinalidad_producto_sin_fila_en_bar_inventario(client, crear_usuario,
                                                          escenario_ajustes):
    """bar_inventario sin UNIQUE(barra, producto): un producto contado en el
    fisico pero sin fila de stock debe cortar preview y aplicar con 500
    explicito, no fallar a mitad de la transaccion."""
    esc = escenario_ajustes
    esc.crear_operacion()
    id_sin_fila = esc.agregar_producto("PYTEST SIN FILA", pesable=False,
                                       ideal_paq=0, ideal_det=0, real_paq=5, real_det=0,
                                       filas_inventario=0)
    admin = crear_usuario(admin=True)

    for endpoint in (PREVIEW, APLICAR):
        r = client.post(endpoint, json=_payload(esc), headers=admin.headers)
        assert r.status_code == 500, f"{endpoint}: {r.text}"
        assert "sin registro en bar_inventario" in r.json()["detail"]
        assert str(id_sin_fila) in r.json()["detail"]


def test_cardinalidad_producto_con_fila_duplicada(client, crear_usuario, escenario_ajustes):
    esc = escenario_ajustes
    esc.crear_operacion()
    id_duplicado = esc.agregar_producto("PYTEST DUPLICADO", pesable=False,
                                        ideal_paq=10, ideal_det=0, real_paq=12, real_det=0,
                                        filas_inventario=2)
    admin = crear_usuario(admin=True)

    for endpoint in (PREVIEW, APLICAR):
        r = client.post(endpoint, json=_payload(esc), headers=admin.headers)
        assert r.status_code == 500, f"{endpoint}: {r.text}"
        assert "duplicadas" in r.json()["detail"]
        assert str(id_duplicado) in r.json()["detail"]


def test_cardinalidad_cubre_tambien_productos_tolerados(client, crear_usuario,
                                                        escenario_ajustes):
    """Desde la igualacion incondicional (v10.77) la cardinalidad se valida
    sobre todo producto que se va a escribir en bar_inventario, incluidos los
    de diferencia tolerada: un dato roto en un tolerado corta preview y
    aplicar con 500 explicito en vez de fallar (o pasar) a mitad del UPDATE."""
    esc = escenario_ajustes
    esc.crear_operacion()
    id_tolerado_roto = esc.agregar_producto("PYTEST TOLERADO ROTO", pesable=True,
                                            ideal_paq=0, ideal_det=19.0,
                                            real_paq=0, real_det=19.3,
                                            filas_inventario=2)
    admin = crear_usuario(admin=True)

    for endpoint in (PREVIEW, APLICAR):
        r = client.post(endpoint, json=_payload(esc), headers=admin.headers)
        assert r.status_code == 500, f"{endpoint}: {r.text}"
        assert "duplicadas" in r.json()["detail"]
        assert str(id_tolerado_roto) in r.json()["detail"]
