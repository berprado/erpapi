"""Cobertura de integracion para PUT /api/pesaje/config/{id} ("promover").

Antes de este fix, un perfil pesable=0 (fila fantasma creada por
trg_alm_producto_after_insert) no se podia completar desde la app: el
endpoint solo permitia editar barcode. La correccion permite completar el
perfil directo desde aca -- solo si el catalogo (ind_permite_comandar=71 y
categoria fuera de CATEGORIAS_EXCLUIDAS_PESAJE) dice que el producto deberia
ser pesable -- y ya no exige peso_bruto/tara juntos (la tara recien se
conoce cuando se termina el contenido de la botella).
"""
from sqlalchemy import text
from sqlalchemy.orm import Session


def _crear_producto(db: Session, *, id_categoria: int, ind_permite_comandar: int | None,
                     nombre: str) -> int:
    db.execute(text("""
        INSERT INTO alm_producto
            (nombre, correlativo, id_categoria, medida, p_unidad_medida,
             cantidad_detalle, ind_permite_comandar, codigo, usuario_reg, estado)
        VALUES (:nombre, 0, :id_categoria, 750, 0, 25.5, :comandar, :codigo, 'pytest', 'HAB')
    """), {"nombre": nombre, "id_categoria": id_categoria, "comandar": ind_permite_comandar,
           "codigo": f"PYT-{nombre[:12]}"})
    id_producto = db.execute(text("SELECT LAST_INSERT_ID()")).scalar()
    db.commit()
    return id_producto


def _crear_perfil_fantasma(db: Session, id_producto: int) -> int:
    """Fila pesable=0 con ceros, igual a como quedaban los productos
    "atascados" (ver TODO.md, conflictos excepcionales de pesable)."""
    db.execute(text("""
        INSERT INTO app_producto_pesaje_config_api
            (id_producto_almacen, nombre_perfil, peso_bruto, tara, gramos_por_oz,
             pesable, tolerancia_oz, estado, usuario_reg)
        VALUES (:id_producto, 'Estándar', 0.00, 0.00, 0.000000, 0, 1.50, 'HAB', 'pytest')
    """), {"id_producto": id_producto})
    id_perfil = db.execute(text("SELECT LAST_INSERT_ID()")).scalar()
    db.commit()
    return id_perfil


def _categoria_pytest(db: Session) -> int:
    db.execute(text("""
        INSERT INTO alm_categoria (nombre, p_grupo_categoria, usuario_reg, estado)
        VALUES ('CATEGORIA PYTEST PESAJE', 8, 'pytest', 'HAB')
    """))
    id_categoria = db.execute(text("SELECT LAST_INSERT_ID()")).scalar()
    db.commit()
    return id_categoria


def test_promover_con_solo_peso_bruto(client, crear_usuario, db_session):
    """Perfil pesable=0 elegible por catalogo: PUT con peso_bruto solo lo
    promueve a pesable=1, dejando tara/gramos_por_oz en NULL (no exige tara)."""
    admin = crear_usuario(admin=True)
    id_categoria = _categoria_pytest(db_session)
    id_producto = _crear_producto(db_session, id_categoria=id_categoria,
                                   ind_permite_comandar=71, nombre="PYTEST PROMOVER")
    id_perfil = _crear_perfil_fantasma(db_session, id_producto)

    r = client.put(f"/api/pesaje/config/{id_perfil}", json={"peso_bruto": 1000.0},
                    headers=admin.headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["pesable"] == 1
    assert data["peso_bruto"] == 1000.0
    assert data["tara"] is None
    assert data["gramos_por_oz"] is None


def test_completar_tara_en_segunda_edicion(client, crear_usuario, db_session):
    """Sobre un perfil ya promovido con peso_bruto solo, una segunda edicion
    con peso_bruto + tara completa gramos_por_oz y el perfil queda completo."""
    admin = crear_usuario(admin=True)
    id_categoria = _categoria_pytest(db_session)
    id_producto = _crear_producto(db_session, id_categoria=id_categoria,
                                   ind_permite_comandar=71, nombre="PYTEST TARA")
    id_perfil = _crear_perfil_fantasma(db_session, id_producto)

    r1 = client.put(f"/api/pesaje/config/{id_perfil}", json={"peso_bruto": 1000.0},
                     headers=admin.headers)
    assert r1.status_code == 200, r1.text

    r2 = client.put(f"/api/pesaje/config/{id_perfil}", json={"peso_bruto": 1000.0, "tara": 300.0},
                     headers=admin.headers)
    assert r2.status_code == 200, r2.text
    data = r2.json()
    assert data["pesable"] == 1
    assert data["peso_bruto"] == 1000.0
    assert data["tara"] == 300.0
    assert data["gramos_por_oz"] == round((1000.0 - 300.0) / 25.5, 6)


def test_no_promueve_categoria_excluida(client, crear_usuario, db_session):
    """Categoria excluida (CERVEZAS=11) con ind_permite_comandar=71: el PUT
    rechaza el intento de cargar peso_bruto y pesable sigue en 0. Mismo caso
    real que AMSTEL/HUARI (revertido en produccion el 2026-07-30)."""
    admin = crear_usuario(admin=True)
    id_producto = _crear_producto(db_session, id_categoria=11,
                                   ind_permite_comandar=71, nombre="PYTEST CERVEZA")
    id_perfil = _crear_perfil_fantasma(db_session, id_producto)

    r = client.put(f"/api/pesaje/config/{id_perfil}", json={"peso_bruto": 500.0},
                    headers=admin.headers)
    assert r.status_code == 400, r.text

    fila = db_session.execute(
        text("SELECT pesable, peso_bruto FROM app_producto_pesaje_config_api WHERE id = :id"),
        {"id": id_perfil}
    ).mappings().first()
    assert fila["pesable"] == 0
    assert float(fila["peso_bruto"]) == 0.0


def test_no_promueve_sin_ind_permite_comandar(client, crear_usuario, db_session):
    """ind_permite_comandar != 71 (catalogo no lo marca pesable): mismo
    rechazo aunque la categoria no este excluida."""
    admin = crear_usuario(admin=True)
    id_categoria = _categoria_pytest(db_session)
    id_producto = _crear_producto(db_session, id_categoria=id_categoria,
                                   ind_permite_comandar=70, nombre="PYTEST NO COMANDA")
    id_perfil = _crear_perfil_fantasma(db_session, id_producto)

    r = client.put(f"/api/pesaje/config/{id_perfil}", json={"peso_bruto": 500.0},
                    headers=admin.headers)
    assert r.status_code == 400, r.text


def test_promover_vino_se_completa_en_un_paso(client, crear_usuario, db_session):
    """Categoria VINOS (id=6): con peso_bruto solo alcanza para completarlo
    del todo -- tara=0 y gramos_por_oz=1 se fuerzan igual que en un perfil
    creado por POST, no queda incompleto esperando una segunda edicion."""
    admin = crear_usuario(admin=True)
    id_producto = _crear_producto(db_session, id_categoria=6,
                                   ind_permite_comandar=71, nombre="PYTEST VINO")
    id_perfil = _crear_perfil_fantasma(db_session, id_producto)

    r = client.put(f"/api/pesaje/config/{id_perfil}", json={"peso_bruto": 5.0},
                    headers=admin.headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["pesable"] == 1
    assert data["peso_bruto"] == 5.0
    assert data["tara"] == 0.0
    assert data["gramos_por_oz"] == 1.0


def test_editar_solo_barcode_no_promueve(client, crear_usuario, db_session):
    """Un PUT que solo manda barcode (sin peso_bruto/tara) no toca pesable,
    aunque el producto no sea elegible por catalogo -- sigue permitido editar
    el codigo de barras de un perfil no pesable."""
    admin = crear_usuario(admin=True)
    id_producto = _crear_producto(db_session, id_categoria=11,
                                   ind_permite_comandar=71, nombre="PYTEST BARCODE")
    id_perfil = _crear_perfil_fantasma(db_session, id_producto)

    r = client.put(f"/api/pesaje/config/{id_perfil}", json={"barcode": "7791234567890"},
                    headers=admin.headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["pesable"] == 0
    assert data["barcode"] == "7791234567890"
