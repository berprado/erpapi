"""Tests de integracion de POST /api/inventario/paloteo contra la BD de test.

Cubren la captura del fisico punta a punta: conversion peso->onzas con el
perfil real, redondeo HALF_UP de la SUMA (no de cada botella), persistencia en
bar_inventario_fisico / bar_detalle_fisico / app_paloteo_registro_crudo,
productos sin configuracion (omitidos) y no pesables (por unidades), y los
rechazos: operativa fuera de INICIO CIERRE (400), barra distinta a la
operativa (400), inventario duplicado (409), peso sobre el bruto del perfil
(400) y sobrecapacidad de onzas (400). Todo se revierte por transaccion.

El perfil fixture es el de BRIGHTON PINK 700ML (doc redondeo_y_tolerancia.md
seccion 6): tara 558 g, 29.063830 g/oz, peso bruto 1241 g.
"""
from sqlalchemy import text

PALOTEO = "/api/inventario/paloteo"


def _payload(esc, items, observaciones=None):
    return {
        "id_operacion": esc.id_operacion,
        "id_barra": esc.id_barra,
        "observaciones": observaciones,
        "items": items,
    }


def test_paloteo_valido_persiste_fisico_y_crudo(client, crear_usuario, escenario_paloteo,
                                                db_session):
    """Caso 1 del doc: botella de 1106 g -> 18.855 oz exactas -> 19.0 oz POS.
    El exacto queda en el registro crudo; el POS recibe el redondeado."""
    esc = escenario_paloteo
    esc.crear_operacion(estado_operacion=24, con_cabecera_fisico=False)
    id_producto, id_perfil = esc.agregar_producto_catalogo(
        "PYTEST BRIGHTON", ideal_paq=2, ideal_det=19.0)
    user = crear_usuario()

    r = client.post(PALOTEO, json=_payload(esc, [{
        "id_producto": id_producto,
        "botellas_cerradas": 2,
        "pesos_abiertas": [{"peso": 1106, "perfil_id": id_perfil}],
    }]), headers=user.headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "success"
    assert data["productos_omitidos"] == []
    assert data["detalles"] == [
        {"id_producto": id_producto, "onzas_exactas": 18.86, "onzas_pos": 19.0}
    ]

    cabecera = db_session.execute(text(
        "SELECT estado_registro, id_barra, estado FROM bar_inventario_fisico WHERE id = :id"),
        {"id": data["id_inventario_pos"]}).fetchone()
    assert tuple(cabecera) == (62, esc.id_barra, "HAB")

    detalle = db_session.execute(text(
        "SELECT cantidad_unidad, cantidad_detalle FROM bar_detalle_fisico "
        "WHERE id_inventario_fisico = :id AND id_producto = :p AND estado = 'HAB'"),
        {"id": data["id_inventario_pos"], "p": id_producto}).fetchone()
    assert (float(detalle[0]), float(detalle[1])) == (2.0, 19.0)

    crudo = db_session.execute(text(
        "SELECT botellas_cerradas, onzas_calculadas, pesos_abiertas "
        "FROM app_paloteo_registro_crudo WHERE id_operacion = :op AND id_producto = :p"),
        {"op": esc.id_operacion, "p": id_producto}).fetchone()
    assert crudo[0] == 2
    assert float(crudo[1]) == 18.86  # exacto (2 decimales), NO el redondeado a 0.5
    assert '"peso": 1106' in crudo[2]


def test_paloteo_redondea_la_suma_no_cada_botella(client, crear_usuario, escenario_paloteo):
    """Caso 3 del doc: dos botellas de 855 g (10.219 oz c/u) suman 20.438 oz
    -> 20.5 POS. Redondear cada botella daria 10.0 + 10.0 = 20.0 (salida
    fantasma de 0.5). Una tercera "botella" bajo la tara menos el margen de
    balanza (500 g < 548) aporta 0 oz sin romper la captura."""
    esc = escenario_paloteo
    esc.crear_operacion(estado_operacion=24, con_cabecera_fisico=False)
    id_producto, id_perfil = esc.agregar_producto_catalogo("PYTEST SUMA")
    user = crear_usuario()

    r = client.post(PALOTEO, json=_payload(esc, [{
        "id_producto": id_producto,
        "botellas_cerradas": 0,
        "pesos_abiertas": [
            {"peso": 855, "perfil_id": id_perfil},
            {"peso": 855, "perfil_id": id_perfil},
            {"peso": 500, "perfil_id": id_perfil},
        ],
    }]), headers=user.headers)
    assert r.status_code == 200, r.text
    assert r.json()["detalles"] == [
        {"id_producto": id_producto, "onzas_exactas": 20.44, "onzas_pos": 20.5}
    ]


def test_paloteo_sin_config_omitido_y_no_pesable_por_unidades(client, crear_usuario,
                                                              escenario_paloteo, db_session):
    """Un producto sin configuracion de pesaje no rompe la captura: se reporta
    en productos_omitidos (no en silencio). Uno con config pesable=0 se
    registra solo por botellas (0 oz)."""
    esc = escenario_paloteo
    esc.crear_operacion(estado_operacion=24, con_cabecera_fisico=False)
    id_sin_config, _ = esc.agregar_producto_catalogo("PYTEST SIN CONFIG", perfil=None)
    id_unidades, _ = esc.agregar_producto_catalogo("PYTEST CERVEZA", perfil="unidades")
    user = crear_usuario()

    r = client.post(PALOTEO, json=_payload(esc, [
        {"id_producto": id_sin_config, "botellas_cerradas": 3, "pesos_abiertas": []},
        {"id_producto": id_unidades, "botellas_cerradas": 5, "pesos_abiertas": []},
    ]), headers=user.headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["productos_omitidos"] == [id_sin_config]
    assert data["detalles"] == [
        {"id_producto": id_unidades, "onzas_exactas": 0.0, "onzas_pos": 0.0}
    ]

    filas = db_session.execute(text(
        "SELECT id_producto, cantidad_unidad, cantidad_detalle FROM bar_detalle_fisico "
        "WHERE id_inventario_fisico = :id AND estado = 'HAB'"),
        {"id": data["id_inventario_pos"]}).fetchall()
    assert [(f[0], float(f[1]), float(f[2])) for f in filas] == [(id_unidades, 5.0, 0.0)]


def test_paloteo_exige_operacion_en_inicio_cierre(client, crear_usuario, escenario_paloteo):
    esc = escenario_paloteo
    esc.crear_operacion(estado_operacion=23, con_cabecera_fisico=False)  # CERRADO, no 24
    id_producto, _ = esc.agregar_producto_catalogo("PYTEST ESTADO")
    user = crear_usuario()

    r = client.post(PALOTEO, json=_payload(esc, [
        {"id_producto": id_producto, "botellas_cerradas": 1, "pesos_abiertas": []},
    ]), headers=user.headers)
    assert r.status_code == 400
    assert "INICIO CIERRE" in r.json()["detail"]


def test_paloteo_rechaza_barra_distinta_a_la_operativa(client, crear_usuario, escenario_paloteo):
    esc = escenario_paloteo
    esc.crear_operacion(estado_operacion=24, con_cabecera_fisico=False)
    id_producto, _ = esc.agregar_producto_catalogo("PYTEST BARRA")
    user = crear_usuario()

    payload = _payload(esc, [
        {"id_producto": id_producto, "botellas_cerradas": 1, "pesos_abiertas": []},
    ])
    payload["id_barra"] = esc.id_barra + 1
    r = client.post(PALOTEO, json=payload, headers=user.headers)
    assert r.status_code == 400
    assert "no coincide" in r.json()["detail"]


def test_paloteo_duplicado_para_la_misma_operacion_409(client, crear_usuario, escenario_paloteo):
    esc = escenario_paloteo
    esc.crear_operacion(estado_operacion=24, con_cabecera_fisico=False)
    id_producto, _ = esc.agregar_producto_catalogo("PYTEST DUP")
    user = crear_usuario()

    payload = _payload(esc, [
        {"id_producto": id_producto, "botellas_cerradas": 1, "pesos_abiertas": []},
    ])
    assert client.post(PALOTEO, json=payload, headers=user.headers).status_code == 200
    r = client.post(PALOTEO, json=payload, headers=user.headers)
    assert r.status_code == 409
    assert "Ya existe un inventario" in r.json()["detail"]


def test_paloteo_peso_sobre_el_bruto_400_y_no_deja_residuos(client, crear_usuario,
                                                            escenario_paloteo, db_session):
    """1500 g > peso bruto del perfil (1241 g): bloqueo duro. El error ocurre
    despues de flushear la cabecera, pero el request fallido no debe dejarla
    persistida (la sesion del request se descarta sin commit)."""
    esc = escenario_paloteo
    esc.crear_operacion(estado_operacion=24, con_cabecera_fisico=False)
    id_producto, id_perfil = esc.agregar_producto_catalogo("PYTEST EXCESO")
    user = crear_usuario()

    r = client.post(PALOTEO, json=_payload(esc, [{
        "id_producto": id_producto,
        "botellas_cerradas": 0,
        "pesos_abiertas": [{"peso": 1500, "perfil_id": id_perfil}],
    }]), headers=user.headers)
    assert r.status_code == 400
    assert "supera el peso bruto" in r.json()["detail"]

    cabeceras = db_session.execute(text(
        "SELECT COUNT(*) FROM bar_inventario_fisico WHERE id_operacion = :op"),
        {"op": esc.id_operacion}).scalar()
    assert cabeceras == 0


def test_paloteo_sobrecapacidad_de_onzas_400(client, crear_usuario, escenario_paloteo):
    """Con capacidad declarada de 10 oz, una captura de 18.86 oz (1106 g, bajo
    el peso bruto) excede la botella llena y se bloquea."""
    esc = escenario_paloteo
    esc.crear_operacion(estado_operacion=24, con_cabecera_fisico=False)
    id_producto, id_perfil = esc.agregar_producto_catalogo("PYTEST CAPACIDAD",
                                                           capacidad_oz=10.0)
    user = crear_usuario()

    r = client.post(PALOTEO, json=_payload(esc, [{
        "id_producto": id_producto,
        "botellas_cerradas": 0,
        "pesos_abiertas": [{"peso": 1106, "perfil_id": id_perfil}],
    }]), headers=user.headers)
    assert r.status_code == 400
    assert "Capacidad excedida" in r.json()["detail"]

def test_pendientes_incluye_productos_ya_contados_sin_movimiento(client, crear_usuario,
                                                                 escenario_paloteo, db_session):
    """Un producto agregado a mano (sin comandas ni traspasos) y ya contado en la
    operativa debe volver en /pendientes con sin_movimiento=True: antes
    desaparecia de PALOTEO 1/2/3 al recargar (caso HAVANA 7A, operativa 1306),
    aunque el servidor lo seguia usando al consolidar."""
    esc = escenario_paloteo
    esc.crear_operacion(estado_operacion=24)
    id_producto = esc.agregar_producto(
        "PYTEST CONTADO SIN MOVIMIENTO", pesable=True,
        ideal_paq=1, ideal_det=10.0, real_paq=1, real_det=10.0,
    )
    # El fixture no llena estos campos de catalogo, que ProductoPendiente exige
    # y que todo producto real tiene.
    db_session.execute(text(
        "UPDATE alm_producto SET ind_permite_comandar = 71, cantidad_detalle = 23.67 WHERE id = :id"
    ), {"id": id_producto})
    db_session.commit()
    usuario = crear_usuario()
    headers = {**usuario.headers, "X-Barra-Id": str(esc.id_barra)}

    r = client.get(f"/api/inventario/pendientes?id_operacion={esc.id_operacion}", headers=headers)
    assert r.status_code == 200, r.text
    fila = next((p for p in r.json() if p["id_producto"] == id_producto), None)
    assert fila is not None
    assert fila["sin_movimiento"] is True

    # Sin id_operacion (cliente viejo) el comportamiento anterior no cambia.
    r_sin_operacion = client.get("/api/inventario/pendientes", headers=headers)
    assert r_sin_operacion.status_code == 200, r_sin_operacion.text
    assert id_producto not in {p["id_producto"] for p in r_sin_operacion.json()}


def test_paloteo_dos_barras_en_la_misma_operativa(client, crear_usuario, escenario_paloteo,
                                                   db_session, monkeypatch):
    """Cada barra de la operativa tiene su propio inventario fisico (caso Beer
    Garden, operativa 167): antes el alta rechazaba la segunda barra con 409
    y la consulta devolvia el inventario de la primera, que la PWA intentaba
    corregir con el id_barra de la segunda ("no coincide con el inventario").
    Un producto contado en ambas barras restaura en cada una SU captura cruda,
    aunque la ultima del registro crudo (que no guarda id_barra) sea de la otra."""
    from config import settings
    monkeypatch.setattr(settings, "PALOTEO_SELECTOR_ENABLED", True)
    monkeypatch.setattr(settings, "PALOTEO_ALLOWED_BARRAS", "1,2")

    esc = escenario_paloteo
    esc.crear_operacion(estado_operacion=24, con_cabecera_fisico=False)
    id_producto, id_perfil = esc.agregar_producto_catalogo("PYTEST DOS BARRAS")
    user = crear_usuario()
    barra_1, barra_2 = esc.id_barra, esc.id_barra + 1
    headers_1 = {**user.headers, "X-Barra-Id": str(barra_1)}
    headers_2 = {**user.headers, "X-Barra-Id": str(barra_2)}

    def _payload_barra(id_barra, cerradas, peso):
        payload = _payload(esc, [{
            "id_producto": id_producto,
            "botellas_cerradas": cerradas,
            "pesos_abiertas": [{"peso": peso, "perfil_id": id_perfil}],
        }])
        payload["id_barra"] = id_barra
        return payload

    r1 = client.post(PALOTEO, json=_payload_barra(barra_1, 2, 1106), headers=headers_1)
    assert r1.status_code == 200, r1.text
    r2 = client.post(PALOTEO, json=_payload_barra(barra_2, 1, 855), headers=headers_2)
    assert r2.status_code == 200, r2.text
    id_inv_1, id_inv_2 = r1.json()["id_inventario_pos"], r2.json()["id_inventario_pos"]
    assert id_inv_1 != id_inv_2

    # La consulta resuelve la barra por el header; la ultima captura cruda del
    # producto es la de la barra 2, pero la barra 1 recupera la suya.
    g1 = client.get(f"{PALOTEO}/{esc.id_operacion}", headers=headers_1)
    assert g1.status_code == 200, g1.text
    assert (g1.json()["id_inventario_pos"], g1.json()["id_barra"]) == (id_inv_1, barra_1)
    assert [p["peso"] for p in g1.json()["detalles"][0]["pesos_abiertas"]] == [1106]

    g2 = client.get(f"{PALOTEO}/{esc.id_operacion}", headers=headers_2)
    assert g2.status_code == 200, g2.text
    assert (g2.json()["id_inventario_pos"], g2.json()["id_barra"]) == (id_inv_2, barra_2)
    assert [p["peso"] for p in g2.json()["detalles"][0]["pesos_abiertas"]] == [855]

    # Sin header (cliente viejo): barra por defecto, como antes.
    g_sin_header = client.get(f"{PALOTEO}/{esc.id_operacion}", headers=user.headers)
    assert g_sin_header.json()["id_inventario_pos"] == id_inv_1

    # El duplicado sigue bloqueado, ahora por barra.
    r_dup = client.post(PALOTEO, json=_payload_barra(barra_2, 1, 855), headers=headers_2)
    assert r_dup.status_code == 409

    # Corregir la barra 2 no toca la barra 1.
    r_put = client.put(f"{PALOTEO}/{id_inv_2}", json=_payload_barra(barra_2, 3, 855),
                       headers=headers_2)
    assert r_put.status_code == 200, r_put.text
    conteos = dict(db_session.execute(text(
        "SELECT id_inventario_fisico, cantidad_unidad FROM bar_detalle_fisico "
        "WHERE id_producto = :p AND estado = 'HAB'"), {"p": id_producto}).fetchall())
    assert {k: float(v) for k, v in conteos.items()} == {id_inv_1: 2.0, id_inv_2: 3.0}


def _dos_barras(esc, crear_usuario, monkeypatch, nombre):
    """Operativa en INICIO CIERRE con selector de barra habilitado (barras 1 y 2)."""
    from config import settings
    monkeypatch.setattr(settings, "PALOTEO_SELECTOR_ENABLED", True)
    monkeypatch.setattr(settings, "PALOTEO_ALLOWED_BARRAS", "1,2")
    esc.crear_operacion(estado_operacion=24, con_cabecera_fisico=False)
    id_producto, id_perfil = esc.agregar_producto_catalogo(nombre)
    user = crear_usuario()
    barras = (esc.id_barra, esc.id_barra + 1)
    headers = {b: {**user.headers, "X-Barra-Id": str(b)} for b in barras}

    def payload(id_barra, cerradas, peso):
        p = _payload(esc, [{
            "id_producto": id_producto,
            "botellas_cerradas": cerradas,
            "pesos_abiertas": [{"peso": peso, "perfil_id": id_perfil}],
        }])
        p["id_barra"] = id_barra
        return p

    return id_producto, barras, headers, payload


def _pesos_precargados(client, esc, headers):
    r = client.get(f"{PALOTEO}/{esc.id_operacion}", headers=headers)
    assert r.status_code == 200, r.text
    return [p["peso"] for p in r.json()["detalles"][0]["pesos_abiertas"]]


def test_paloteo_mismo_conteo_en_dos_barras_cada_una_lee_su_pesaje(
        client, crear_usuario, escenario_paloteo, db_session, monkeypatch):
    """El caso que la regla "captura que explica el conteo" no distinguia (v12.37):
    850 g y 855 g dan 10.05 y 10.22 oz, ambos 10.0 en el POS, con la misma botella
    cerrada. Desde v12.45 el registro crudo guarda id_barra y cada barra
    recupera su propio pesaje, aunque la ultima captura sea de la otra."""
    esc = escenario_paloteo
    id_producto, (b1, b2), headers, payload = _dos_barras(
        esc, crear_usuario, monkeypatch, "PYTEST MISMO CONTEO")

    assert client.post(PALOTEO, json=payload(b1, 1, 850), headers=headers[b1]).status_code == 200
    assert client.post(PALOTEO, json=payload(b2, 1, 855), headers=headers[b2]).status_code == 200

    crudos = db_session.execute(text(
        "SELECT id_barra, botellas_cerradas FROM app_paloteo_registro_crudo "
        "WHERE id_operacion = :op AND id_producto = :p ORDER BY id"),
        {"op": esc.id_operacion, "p": id_producto}).fetchall()
    assert [tuple(c) for c in crudos] == [(b1, 1), (b2, 1)]

    assert _pesos_precargados(client, esc, headers[b1]) == [850]
    assert _pesos_precargados(client, esc, headers[b2]) == [855]


def test_paloteo_captura_sin_barra_usa_la_regla_de_respaldo(
        client, crear_usuario, escenario_paloteo, db_session, monkeypatch):
    """Filas anteriores a v12.45 (id_barra NULL): sin captura propia, la barra
    toma la ultima sin barra que explica su conteo."""
    esc = escenario_paloteo
    id_producto, (b1, _b2), headers, payload = _dos_barras(
        esc, crear_usuario, monkeypatch, "PYTEST CRUDO LEGADO")

    assert client.post(PALOTEO, json=payload(b1, 1, 850), headers=headers[b1]).status_code == 200
    db_session.execute(text(
        "UPDATE app_paloteo_registro_crudo SET id_barra = NULL "
        "WHERE id_operacion = :op AND id_producto = :p"),
        {"op": esc.id_operacion, "p": id_producto})
    db_session.commit()

    assert _pesos_precargados(client, esc, headers[b1]) == [850]


def test_paloteo_nunca_usa_la_captura_de_otra_barra(
        client, crear_usuario, escenario_paloteo, db_session, monkeypatch):
    """Una captura marcada con otra barra no se usa aunque explique el conteo:
    sin captura propia ni legada, la precarga queda sin pesos."""
    esc = escenario_paloteo
    id_producto, (b1, b2), headers, payload = _dos_barras(
        esc, crear_usuario, monkeypatch, "PYTEST CRUDO AJENO")

    assert client.post(PALOTEO, json=payload(b1, 1, 850), headers=headers[b1]).status_code == 200
    db_session.execute(text(
        "UPDATE app_paloteo_registro_crudo SET id_barra = :otra "
        "WHERE id_operacion = :op AND id_producto = :p"),
        {"otra": b2, "op": esc.id_operacion, "p": id_producto})
    db_session.commit()

    assert _pesos_precargados(client, esc, headers[b1]) == []
