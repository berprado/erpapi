"""Cobertura de integracion para GET /api/pesaje/config y GET /api/pesaje/categorias.

Hasta el fix de PR #7 (CHANGELOG v12.6), ambos endpoints excluian siempre las
categorias de CATEGORIAS_EXCLUIDAS_PESAJE del listado -- no solo de la logica
de derivacion de "que deberia ser pesable por defecto" -- escondiendo
perfiles reales (pesables y no pesables) que ya existen en esas categorias.
Ej. real: CERVEZAS (id=11) tiene productos pesable=0 (la mayoria) y un
pesable=1 real (BARRIL PACEÑA 50L, la excepcion que se pesa aunque la
categoria en general no se pese) -- ver
querys/backfill_productos_no_pesables_pesaje_config_api.sql y
querys/backfill_producto_barril_pesable_pesaje_config_api.sql.

Estos tests fijan esa regresion: category=11 se usa deliberadamente por ser
una categoria excluida real y ya usada en test_integracion_pesaje.py
(test_no_promueve_categoria_excluida), no una categoria de prueba nueva.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

CATEGORIA_EXCLUIDA_CERVEZAS = 11


def _crear_producto_con_perfil(db: Session, *, id_categoria: int, nombre: str,
                                pesable: int) -> tuple[int, int]:
    """Alta minima de producto + su unico perfil de pesaje, en la categoria dada.

    trg_alm_producto_after_insert ya crea una fila 'Estándar' al insertar el
    producto (ver README "Triggers de base de datos"); se normaliza esa fila
    a los valores que el test necesita via ON DUPLICATE KEY UPDATE, mismo
    patron que _crear_perfil_fantasma en test_integracion_pesaje.py."""
    db.execute(text("""
        INSERT INTO alm_producto
            (nombre, correlativo, id_categoria, medida, p_unidad_medida,
             cantidad_detalle, ind_permite_comandar, codigo, usuario_reg, estado)
        VALUES (:nombre, 0, :id_categoria, 750, 0, 25.5, 71, :codigo, 'pytest', 'HAB')
    """), {"nombre": nombre, "id_categoria": id_categoria, "codigo": f"PYT-{nombre[:12]}"})
    id_producto = db.execute(text("SELECT LAST_INSERT_ID()")).scalar()

    db.execute(text("""
        INSERT INTO app_producto_pesaje_config_api
            (id_producto_almacen, nombre_perfil, peso_bruto, tara, gramos_por_oz,
             pesable, tolerancia_oz, estado, usuario_reg)
        VALUES (:id_producto, 'Estándar', NULL, NULL, NULL, :pesable, 1.50, 'HAB', 'pytest')
        ON DUPLICATE KEY UPDATE
            id = LAST_INSERT_ID(id),
            pesable = VALUES(pesable),
            estado = VALUES(estado)
    """), {"id_producto": id_producto, "pesable": pesable})
    id_perfil = db.execute(text("SELECT LAST_INSERT_ID()")).scalar()
    db.commit()
    return id_producto, id_perfil


def test_config_lista_no_pesable_de_categoria_excluida(client, crear_usuario, db_session):
    """Un producto pesable=0 en una categoria de CATEGORIAS_EXCLUIDAS_PESAJE
    (CERVEZAS=11) debe listarse igual en GET /api/pesaje/config?pesable=0 --
    antes del fix, la condicion de categoria escondia esta fila."""
    admin = crear_usuario(admin=True)
    id_producto, _ = _crear_producto_con_perfil(
        db_session, id_categoria=CATEGORIA_EXCLUIDA_CERVEZAS,
        nombre="PYTEST CERVEZA NO PES", pesable=0,
    )

    r = client.get("/api/pesaje/config",
                    params={"pesable": 0, "id_categoria": CATEGORIA_EXCLUIDA_CERVEZAS},
                    headers=admin.headers)
    assert r.status_code == 200, r.text
    ids = [item["id_producto"] for item in r.json()]
    assert id_producto in ids


def test_config_lista_pesable_de_categoria_excluida(client, crear_usuario, db_session):
    """Excepcion real dentro de una categoria excluida (ej. BARRIL PACEÑA
    50L en CERVEZAS): un pesable=1 en categoria excluida tambien debe
    listarse en GET /api/pesaje/config?pesable=1."""
    admin = crear_usuario(admin=True)
    id_producto, id_perfil = _crear_producto_con_perfil(
        db_session, id_categoria=CATEGORIA_EXCLUIDA_CERVEZAS,
        nombre="PYTEST CERVEZA PESABLE", pesable=1,
    )
    # Perfil completo (no NULL) para no depender de la logica de INCOMPLETOS.
    db_session.execute(text("""
        UPDATE app_producto_pesaje_config_api
        SET peso_bruto = 50000.00, tara = 0.00, gramos_por_oz = 100.00
        WHERE id = :id
    """), {"id": id_perfil})
    db_session.commit()

    r = client.get("/api/pesaje/config",
                    params={"pesable": 1, "id_categoria": CATEGORIA_EXCLUIDA_CERVEZAS},
                    headers=admin.headers)
    assert r.status_code == 200, r.text
    ids = [item["id_producto"] for item in r.json()]
    assert id_producto in ids


def test_categorias_incluye_categoria_excluida_de_pesable(client, crear_usuario):
    """El selector de categorias del modulo PESAJE ya no esconde las
    categorias de CATEGORIAS_EXCLUIDAS_PESAJE (ej. CERVEZAS=11): tienen
    perfiles reales que filtrar, pesables y no pesables."""
    admin = crear_usuario(admin=True)

    r = client.get("/api/pesaje/categorias", headers=admin.headers)
    assert r.status_code == 200, r.text
    ids = [item["id_categoria"] for item in r.json()]
    assert CATEGORIA_EXCLUIDA_CERVEZAS in ids


def test_incompletos_no_sugiere_categoria_excluida_sin_config(client, crear_usuario, db_session):
    """El bloque de INCOMPLETOS (productos elegibles sin ninguna fila de
    config aun) sigue excluyendo CATEGORIAS_EXCLUIDAS_PESAJE -- esa exclusion
    describe una regla de negocio real (que categoria no deriva pesable por
    defecto) y el fix de listado no la tocó ahí a propósito."""
    admin = crear_usuario(admin=True)

    db_session.execute(text("""
        INSERT INTO alm_producto
            (nombre, correlativo, id_categoria, medida, p_unidad_medida,
             cantidad_detalle, ind_permite_comandar, codigo, usuario_reg, estado)
        VALUES ('PYTEST CERVEZA SIN CFG', 0, :id_categoria, 750, 0, 25.5, 71,
                'PYT-CERVSINCFG', 'pytest', 'HAB')
    """), {"id_categoria": CATEGORIA_EXCLUIDA_CERVEZAS})
    id_producto = db_session.execute(text("SELECT LAST_INSERT_ID()")).scalar()

    # trg_alm_producto_after_insert crea una fila fantasma para este
    # producto; se desactiva para simular "sin ninguna config activa" de
    # verdad (mismo patron que agregar_producto_catalogo(perfil=None) en
    # tests/conftest.py).
    db_session.execute(text("""
        UPDATE app_producto_pesaje_config_api
        SET estado = 'DES'
        WHERE id_producto_almacen = :id AND estado = 'HAB'
    """), {"id": id_producto})
    db_session.commit()

    r = client.get("/api/pesaje/config",
                    params={"pesable": 1, "id_categoria": CATEGORIA_EXCLUIDA_CERVEZAS},
                    headers=admin.headers)
    assert r.status_code == 200, r.text
    ids = [item["id_producto"] for item in r.json()]
    assert id_producto not in ids
