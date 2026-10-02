"""Tests de integracion de GET /api/inventario/pendientes (lista de PALOTEO por
barra) y GET /api/inventario/traspasos-sin-recepcion, contra la BD de test.

El criterio de "producto con movimiento" se valido en vivo contra el POS
(test_pos, operativa 163, 2026-10-01), leyendo la BD antes y despues de cada
accion:

- Comanda 25 PENDIENTE (creada, o bloqueada por stock insuficiente): no mueve
  stock. Imprimir = procesar (26): descuenta solo en la barra de la comanda.
  Anular (27): el POS devuelve el stock, pero bar_comanda_impresion conserva la
  fila de la impresion; una anulada impresa pudo servirse y si entra.
  Cortesia (tipo_salida 51) mueve stock igual que la venta (50).
- Traspaso almacen -> barra: 16 registrado y 20 despachado no suman en la barra
  (20 = en transito); 21 EN BARRA si.
- Devolucion barra -> almacen: bar_salida_inventario tipo 76, al procesarse
  (20) baja la barra. El tipo 77 son las bajas por ajuste de esta API.

Todo en una misma operativa con dos barras: cada producto debe aparecer solo en
la barra donde se movio (antes las comandas no se filtraban por barra y un
producto vendido en la barra 2 aparecia "colado" en el paloteo de la barra 1).
Todo se revierte por transaccion.
"""
import pytest
from sqlalchemy import text

PENDIENTES = "/api/inventario/pendientes"
TRASPASOS_SIN_RECEPCION = "/api/inventario/traspasos-sin-recepcion"


class Movimientos:
    """Siembra comandas, traspasos y devoluciones como los deja el POS."""

    def __init__(self, db, id_usuario):
        self.db = db
        self.id_usuario = id_usuario

    def _id(self):
        return self.db.execute(text("SELECT LAST_INSERT_ID()")).scalar()

    def comanda(self, id_operacion, id_barra, id_producto, estado, tipo_salida=50, impresa=False):
        self.db.execute(text("""
            INSERT INTO bar_comanda (fecha, id_barra, id_operacion, id_usuario, estado_comanda,
                                     estado_impresion, tipo_salida, usuario_reg, fecha_reg, estado)
            VALUES (NOW(), :barra, :op, :usuario, :estado, NULL, :tipo, 'pytest', CURDATE(), 'HAB')
        """), {"barra": id_barra, "op": id_operacion, "usuario": self.id_usuario,
               "estado": estado, "tipo": tipo_salida})
        id_comanda = self._id()
        self.db.execute(text("""
            INSERT INTO bar_detalle_comanda_salida (cantidad, id_comanda, id_producto, precio_venta,
                                                    sub_total, id_barra, usuario_reg, fecha_reg, estado)
            VALUES (1, :comanda, :producto, 10, 10, :barra, 'pytest', CURDATE(), 'HAB')
        """), {"comanda": id_comanda, "producto": id_producto, "barra": id_barra})
        if impresa:
            self.db.execute(text("""
                INSERT INTO bar_comanda_impresion (id_comanda, nombre_barra, impresora, texto, ind_estado_impresion)
                VALUES (:comanda, 'BARRA PYTEST', 'PYTEST', 'pytest', 31)
            """), {"comanda": id_comanda})

    def traspaso(self, id_operacion, id_barra, id_producto, estado):
        self.db.execute(text("""
            INSERT INTO alm_salida_inventario (fecha_salida, responsable, ind_estado_salida, id_almacen,
                                               id_barra, id_operacion, ind_tipo_movimiento, ind_tipo_salida,
                                               usuario_reg, fecha_reg, estado)
            VALUES (CURDATE(), 'PYTEST', :estado, 1, :barra, :op, 83, 34, 'pytest', CURDATE(), 'HAB')
        """), {"estado": estado, "barra": id_barra, "op": id_operacion})
        self.db.execute(text("""
            INSERT INTO alm_detalle_salida_inv (cantidad, ind_paq_detalle, id_salida_inventario, id_producto,
                                                usuario_reg, fecha_reg, estado)
            VALUES (2, '1', :salida, :producto, 'pytest', CURDATE(), 'HAB')
        """), {"salida": self._id(), "producto": id_producto})

    def salida_barra(self, id_operacion, id_barra, id_producto, tipo, estado):
        self.db.execute(text("""
            INSERT INTO bar_salida_inventario (fecha_salida, responsable, ind_estado_salida, id_almacen,
                                               id_barra, id_operacion, ind_tipo_salida, usuario_reg,
                                               fecha_reg, estado)
            VALUES (CURDATE(), 'PYTEST', :estado, 1, :barra, :op, :tipo, 'pytest', CURDATE(), 'HAB')
        """), {"estado": estado, "barra": id_barra, "op": id_operacion, "tipo": tipo})
        self.db.execute(text("""
            INSERT INTO bar_detalle_salida_inv (cantidad, ind_paq_detalle, id_salida_inventario, id_producto,
                                                usuario_reg, fecha_reg, estado)
            VALUES (1, '1', :salida, :producto, 'pytest', CURDATE(), 'HAB')
        """), {"salida": self._id(), "producto": id_producto})


@pytest.fixture()
def dos_barras(monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "PALOTEO_SELECTOR_ENABLED", True)
    monkeypatch.setattr(settings, "PALOTEO_ALLOWED_BARRAS", "1,2")


@pytest.fixture()
def escenario_movimientos(escenario_paloteo, crear_usuario, db_session, dos_barras):
    """Operativa en INICIO CIERRE con un producto por caso del criterio. Cada
    producto tiene stock (fila de bar_inventario) en las DOS barras, asi que
    solo el filtro de movimiento decide en que lista aparece."""
    esc = escenario_paloteo
    id_usuario = db_session.execute(text("SELECT MIN(id) FROM seg_usuario")).scalar()

    # Operativa anterior, creada primero (id menor) para que la del escenario
    # sea MAX(id_operacion) de bar_comanda en el fallback sin id_operacion.
    db_session.execute(text("""
        INSERT INTO ope_operacion (fecha, nombre_operacion, estado_operacion, comision, id_dia, usuario_reg, estado)
        VALUES (CURDATE(), 'OPERATIVA PYTEST ANTERIOR', 23, 0, 1, 'pytest', 'HAB')
    """))
    id_operacion_anterior = db_session.execute(text("SELECT LAST_INSERT_ID()")).scalar()
    esc.crear_operacion(estado_operacion=24, con_cabecera_fisico=False)
    op, b1, b2 = esc.id_operacion, esc.id_barra, esc.id_barra + 1

    casos = [
        "VENTA BARRA 1", "VENTA BARRA 2", "CORTESIA BARRA 1", "ANULADA IMPRESA",
        "ANULADA SIN IMPRIMIR", "PENDIENTE", "TRASPASO EN BARRA", "TRASPASO EN TRANSITO",
        "TRASPASO REGISTRADO", "DEVOLUCION PROCESADA", "DEVOLUCION PENDIENTE",
        "BAJA POR AJUSTE API", "VENTA OTRA OPERATIVA",
    ]
    ids = {}
    for caso in casos:
        id_producto, _ = esc.agregar_producto_catalogo(f"PYTEST MOV {caso}", capacidad_oz=23.67)
        ids[caso] = id_producto
        # Campos de catalogo que ProductoPendiente exige y que el fixture no llena.
        db_session.execute(text("UPDATE alm_producto SET ind_permite_comandar = 71 WHERE id = :id"),
                           {"id": id_producto})
        db_session.execute(text("""
            INSERT INTO bar_inventario (cantidad_paq, cantidad_detalle, id_producto, id_barra, usuario_reg, estado)
            VALUES (0, 0, :id, :barra, 'pytest', 'HAB')
        """), {"id": id_producto, "barra": b2})

    mov = Movimientos(db_session, id_usuario)
    mov.comanda(op, b1, ids["VENTA BARRA 1"], estado=26)
    mov.comanda(op, b2, ids["VENTA BARRA 2"], estado=26)
    mov.comanda(op, b1, ids["CORTESIA BARRA 1"], estado=26, tipo_salida=51)
    mov.comanda(op, b1, ids["ANULADA IMPRESA"], estado=27, impresa=True)
    mov.comanda(op, b1, ids["ANULADA SIN IMPRIMIR"], estado=27)
    mov.comanda(op, b1, ids["PENDIENTE"], estado=25)
    mov.traspaso(op, b1, ids["TRASPASO EN BARRA"], estado=21)
    mov.traspaso(op, b1, ids["TRASPASO EN TRANSITO"], estado=20)
    mov.traspaso(op, b1, ids["TRASPASO REGISTRADO"], estado=16)
    mov.salida_barra(op, b1, ids["DEVOLUCION PROCESADA"], tipo=76, estado=20)
    mov.salida_barra(op, b1, ids["DEVOLUCION PENDIENTE"], tipo=76, estado=16)
    mov.salida_barra(op, b1, ids["BAJA POR AJUSTE API"], tipo=77, estado=20)
    mov.comanda(id_operacion_anterior, b1, ids["VENTA OTRA OPERATIVA"], estado=26)
    db_session.commit()

    usuario = crear_usuario()
    return {
        "op": op, "b1": b1, "b2": b2, "ids": ids,
        "headers": {b: {**usuario.headers, "X-Barra-Id": str(b)} for b in (b1, b2)},
    }


def _casos_en_lista(client, esc, barra, con_operacion=True):
    url = f"{PENDIENTES}?id_operacion={esc['op']}" if con_operacion else PENDIENTES
    r = client.get(url, headers=esc["headers"][barra])
    assert r.status_code == 200, r.text
    por_id = {caso: id_producto for caso, id_producto in esc["ids"].items()}
    presentes = {p["id_producto"] for p in r.json()}
    return {caso for caso, id_producto in por_id.items() if id_producto in presentes}


def test_pendientes_lista_solo_lo_movido_en_cada_barra(client, escenario_movimientos):
    esc = escenario_movimientos
    assert _casos_en_lista(client, esc, esc["b1"]) == {
        "VENTA BARRA 1",          # comanda procesada en la barra
        "CORTESIA BARRA 1",       # la cortesia mueve stock igual que la venta
        "ANULADA IMPRESA",        # se imprimio: el trago pudo servirse
        "TRASPASO EN BARRA",      # recepcionado (21)
        "DEVOLUCION PROCESADA",   # devolucion barra -> almacen (76, 20)
    }
    # Barra 2: solo su venta. Nada de lo movido en la barra 1 se cuela.
    assert _casos_en_lista(client, esc, esc["b2"]) == {"VENTA BARRA 2"}


def test_pendientes_sin_id_operacion_usa_ultima_operativa_con_comandas(client, escenario_movimientos):
    """Cliente viejo sin id_operacion: misma lista (la operativa del escenario
    es la ultima con comandas), sin la venta de la operativa anterior."""
    esc = escenario_movimientos
    assert _casos_en_lista(client, esc, esc["b1"], con_operacion=False) == \
        _casos_en_lista(client, esc, esc["b1"])


def test_traspasos_sin_recepcion_solo_los_despachados_de_la_barra(client, escenario_movimientos):
    esc = escenario_movimientos
    url = f"{TRASPASOS_SIN_RECEPCION}?id_operacion={esc['op']}"

    r1 = client.get(url, headers=esc["headers"][esc["b1"]])
    assert r1.status_code == 200, r1.text
    productos = [p["id_producto"] for t in r1.json() for p in t["productos"]]
    # Solo el despachado sin recepcionar (20); ni el registrado (16) ni el recepcionado (21).
    assert productos == [esc["ids"]["TRASPASO EN TRANSITO"]]
    assert r1.json()[0]["productos"][0]["cantidad"] == 2.0
    assert r1.json()[0]["productos"][0]["por_unidad"] is True

    r2 = client.get(url, headers=esc["headers"][esc["b2"]])
    assert r2.status_code == 200, r2.text
    assert r2.json() == []
