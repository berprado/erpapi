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
