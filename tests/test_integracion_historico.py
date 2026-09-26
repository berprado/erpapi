"""Tests de integracion del historico de paloteo contra la BD de test.

Cubren GET /api/paloteo3/historico/operativas (solo barras que operaron),
GET /api/paloteo3/historico (clasificacion de filas y VALOR desde el snapshot
congelado del ajuste aplicado) y POST /api/paloteo3/historico/exportar-pdf
(misma estructura que el PDF de Ajustes). El cierre POS se siembra directo en
bar_paloteo_cierre, la tabla de v9_paloteo_cierre. Todo se revierte por
transaccion (ver conftest.py).
"""
from datetime import date
from io import BytesIO

from pypdf import PdfReader
from sqlalchemy import text

HISTORICO = "/api/paloteo3/historico"
OPERATIVAS = "/api/paloteo3/historico/operativas"
PDF_HISTORICO = "/api/paloteo3/historico/exportar-pdf"
BARRA_SIN_ACTIVIDAD = 2


def _cierre(db, esc, id_producto, *, id_barra=None, actual_paq=0, actual_det=0,
            fisico_paq=None, fisico_det=None, ventas_paq=0):
    """Una fila del cierre POS; diferencia = fisico - actual solo si hubo fisico."""
    dif_paq = None if fisico_paq is None else fisico_paq - actual_paq
    dif_det = None if fisico_det is None else fisico_det - actual_det
    db.execute(text("""
        INSERT INTO bar_paloteo_cierre
            (inicial_paq, inicial_detalle, ingreso_paq, ingreso_detalle,
             ventas_paq, ventas_detalle, actual_paq, actual_detalle,
             fisico_paq, fisico_detalle, diferencia_paq, diferencia_detalle,
             id_barra, id_operacion, id_producto, usuario_reg, fecha_reg, estado)
        VALUES (:actual_paq, :actual_det, 0, 0, :ventas_paq, 0, :actual_paq, :actual_det,
                :fisico_paq, :fisico_det, :dif_paq, :dif_det,
                :id_barra, :id_operacion, :id_producto, 'pytest', NOW(), 'HAB')
    """), {
        "actual_paq": actual_paq, "actual_det": actual_det, "ventas_paq": ventas_paq,
        "fisico_paq": fisico_paq, "fisico_det": fisico_det,
        "dif_paq": dif_paq, "dif_det": dif_det,
        "id_barra": id_barra or esc.id_barra, "id_operacion": esc.id_operacion,
        "id_producto": id_producto,
    })


def _armar_cierre(esc, db):
    """Operativa cerrada con un producto de cada clase en la barra 1 y la
    barra 2 con cierre escrito pero sin ninguna actividad."""
    esc.crear_operacion(estado_operacion=23)
    ids = {}
    for clave in ("faltante", "cuadra", "sin_contar", "sin_movimiento"):
        ids[clave], _ = esc.agregar_producto_catalogo(f"PYTEST HIST {clave.upper()}", perfil="unidades")
    _cierre(db, esc, ids["faltante"], actual_paq=3, fisico_paq=2, fisico_det=0, ventas_paq=1)
    _cierre(db, esc, ids["cuadra"], actual_paq=5, fisico_paq=5, fisico_det=0)
    _cierre(db, esc, ids["sin_contar"], actual_paq=4, ventas_paq=2)
    _cierre(db, esc, ids["sin_movimiento"], actual_paq=7)
    for id_producto in ids.values():
        _cierre(db, esc, id_producto, id_barra=BARRA_SIN_ACTIVIDAD, actual_paq=1)
    db.commit()
    return ids


def _aplicar_snapshot(esc, db, id_producto, valor_neto):
    """Control APLICADO + snapshot congelado, como los deja aplicar ajustes."""
    db.execute(text("""
        INSERT INTO app_paloteo_ajuste_control
            (id_operacion, id_barra, id_inventario_fisico, estado, payload_json, usuario_reg, fecha_reg)
        VALUES (:op, :barra, :fisico, 'APLICADO', '{}', 'pytest', NOW())
    """), {"op": esc.id_operacion, "barra": esc.id_barra, "fisico": esc.id_inventario_fisico})
    id_control = db.execute(text("SELECT LAST_INSERT_ID()")).scalar()
    db.execute(text("""
        INSERT INTO analytics_varianza_inventario (
            id_operacion, id_barra, id_inventario_fisico, id_control_ajuste,
            id_producto, fecha_aplicacion, id_almacen, delta_paq,
            delta_det_exacto, delta_det_operativo, origen_wac,
            estado_valoracion, valor_paq, valor_detalle_operativo, valor_neto,
            usuario_reg, fecha_reg
        ) VALUES (:op, :barra, :fisico, :control, :producto, NOW(), 1, -1, 0, 0,
                  'cache_wac_producto', 'VALORIZADO', :valor, 0, :valor, 'pytest', NOW())
    """), {"op": esc.id_operacion, "barra": esc.id_barra, "fisico": esc.id_inventario_fisico,
           "control": id_control, "producto": id_producto, "valor": valor_neto})
    db.commit()


def test_operativas_lista_solo_barras_que_operaron(client, crear_usuario, escenario_ajustes, db_session):
    esc = escenario_ajustes
    _armar_cierre(esc, db_session)
    admin = crear_usuario(admin=True)
    hoy = date.today().isoformat()

    r = client.get(f"{OPERATIVAS}?fecha_desde={hoy}&fecha_hasta={hoy}", headers=admin.headers)

    assert r.status_code == 200, r.text
    pares = {(o["id_operacion"], o["id_barra"]) for o in r.json()["operativas"]}
    assert (esc.id_operacion, esc.id_barra) in pares
    # El POS escribe cierre para la barra 2, pero no tuvo comandas, paloteo ni
    # ventas/ingresos: no debe ofrecerse.
    assert (esc.id_operacion, BARRA_SIN_ACTIVIDAD) not in pares


def test_operativas_incluye_barra_con_paloteo_aunque_no_vendiera(
        client, crear_usuario, escenario_ajustes, db_session):
    esc = escenario_ajustes
    _armar_cierre(esc, db_session)
    db_session.execute(text("""
        INSERT INTO bar_inventario_fisico
            (fecha, observaciones, estado_registro, id_barra, id_operacion, usuario_reg, fecha_reg, estado)
        VALUES (CURDATE(), 'FIXTURE PYTEST', 1, :barra, :op, 'pytest', CURDATE(), 'HAB')
    """), {"barra": BARRA_SIN_ACTIVIDAD, "op": esc.id_operacion})
    db_session.commit()
    admin = crear_usuario(admin=True)
    hoy = date.today().isoformat()

    r = client.get(f"{OPERATIVAS}?fecha_desde={hoy}&fecha_hasta={hoy}", headers=admin.headers)

    pares = {(o["id_operacion"], o["id_barra"]) for o in r.json()["operativas"]}
    assert (esc.id_operacion, BARRA_SIN_ACTIVIDAD) in pares


def test_historico_clasifica_filas_y_valora_desde_el_snapshot(
        client, crear_usuario, escenario_ajustes, db_session):
    esc = escenario_ajustes
    ids = _armar_cierre(esc, db_session)
    _aplicar_snapshot(esc, db_session, ids["faltante"], -140)
    admin = crear_usuario(admin=True)

    r = client.get(f"{HISTORICO}?id_operacion={esc.id_operacion}&id_barra={esc.id_barra}",
                   headers=admin.headers)

    assert r.status_code == 200, r.text
    data = r.json()
    assert data["resumen"] == {
        "con_diferencia": 1, "cuadrados": 1, "con_movimiento_sin_contar": 1, "sin_movimiento": 1,
    }
    filas = {f["id_producto"]: f for f in data["filas"]}
    # Los sin movimiento solo se cuentan: no viajan como filas.
    assert set(filas) == {ids["faltante"], ids["cuadra"], ids["sin_contar"]}
    assert filas[ids["faltante"]]["clasificacion"] == "con_diferencia"
    assert filas[ids["faltante"]]["valor_neto"] == -140.0
    # Cuadraba al aplicar: vale 0 Bs aunque no tenga snapshot.
    assert filas[ids["cuadra"]]["estado_valoracion"] == "VALORIZADO"
    assert filas[ids["cuadra"]]["valor_neto"] == 0.0
    assert filas[ids["sin_contar"]]["clasificacion"] == "con_movimiento_sin_contar"
    assert filas[ids["sin_contar"]]["estado_valoracion"] is None
    assert data["ajuste_aplicado"] is True
    assert data["valoracion"]["faltantes"] == 140.0


def test_historico_sin_ajuste_aplicado_no_inventa_valor(
        client, crear_usuario, escenario_ajustes, db_session):
    esc = escenario_ajustes
    _armar_cierre(esc, db_session)
    admin = crear_usuario(admin=True)

    r = client.get(f"{HISTORICO}?id_operacion={esc.id_operacion}&id_barra={esc.id_barra}",
                   headers=admin.headers)

    data = r.json()
    assert data["ajuste_aplicado"] is False
    assert data["valoracion"] is None
    assert all(f["estado_valoracion"] is None and f["valor_neto"] is None for f in data["filas"])


def test_pdf_historico_tiene_la_estructura_del_reporte_de_ajustes(
        client, crear_usuario, escenario_ajustes, db_session):
    esc = escenario_ajustes
    _armar_cierre(esc, db_session)
    admin = crear_usuario(admin=True)

    r = client.post(PDF_HISTORICO, json={
        "id_operacion": esc.id_operacion, "id_barra": esc.id_barra, "usuario": admin.usuario,
    }, headers=admin.headers)

    assert r.status_code == 200, r.text
    texto = _texto_pdf(r)
    assert "DIF OP" in texto and "VALOR" in texto and "DIF REAL" in texto
    assert "PYTEST HIST FALTANTE" in texto
    assert "PYTEST HIST CUADRA" in texto
    assert "CON MOVIMIENTO SIN CONTAR" in texto
    assert "PYTEST HIST SIN_CONTAR" in texto
    assert "PYTEST HIST SIN_MOVIMIENTO" not in texto
    assert "1 sin movimiento (omitidos)" in texto
    assert "Sin ajuste aplicado" in texto


def test_pdf_historico_con_ajuste_aplicado_muestra_valor_y_totales(
        client, crear_usuario, escenario_ajustes, db_session):
    esc = escenario_ajustes
    ids = _armar_cierre(esc, db_session)
    _aplicar_snapshot(esc, db_session, ids["faltante"], -140)
    admin = crear_usuario(admin=True)

    r = client.post(PDF_HISTORICO, json={
        "id_operacion": esc.id_operacion, "id_barra": esc.id_barra, "usuario": admin.usuario,
    }, headers=admin.headers)

    assert r.status_code == 200, r.text
    texto = _texto_pdf(r)
    assert "-140.00 Bs" in texto
    assert "FALTANTES: -140.00 Bs" in texto
    assert "Sin ajuste aplicado" not in texto


def _texto_pdf(respuesta) -> str:
    return "\n".join(p.extract_text() or "" for p in PdfReader(BytesIO(respuesta.content)).pages)
