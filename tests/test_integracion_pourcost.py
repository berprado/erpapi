"""Tests de integracion de POUR COST contra la BD de test (adminerp local).

Cubren GET /api/pourcost/recetas y GET /api/pourcost/productos de punta a punta:
la consulta real con el join a bar_combo_coctel, la regla del opcional por
defecto por categoria (v12.41) y el control de acceso (solo administradores).

Son solo de lectura y trabajan sobre las recetas reales de la BD local, por lo
que verifican invariantes (no valores fijos de costo). La regla se inyecta en
cada test para no depender de las POURCOST_OPCIONAL_CAT* del .env de quien
corra la suite.
"""
import pytest
from sqlalchemy import text

import main

RECETAS = "/api/pourcost/recetas?id_dia=1"
PRODUCTOS = "/api/pourcost/productos?id_dia=1"

# {id alm_categoria: id alm_producto} del entorno test (ver pourcost.md seccion 6.4).
REGLAS_TEST = {1: 64, 2: 62, 3: 479, 4: 62, 5: 60, 7: 63, 9: 61, 10: 63, 11: 492, 21: 61}


def _fijar_reglas(monkeypatch, reglas):
    monkeypatch.setattr(
        type(main.settings), "pourcost_opcional_por_categoria", property(lambda self: reglas)
    )


def _recetas(client, admin):
    r = client.get(RECETAS, headers=admin.headers)
    assert r.status_code == 200, r.text
    return r.json()


def _es_opcional(ing):
    return str(ing["tipo_parte_combo"] or "").strip().upper() == "OPCIONAL"


def test_costo_es_la_suma_de_las_lineas_incluidas(client, crear_usuario, monkeypatch):
    _fijar_reglas(monkeypatch, REGLAS_TEST)
    combos = _recetas(client, crear_usuario(admin=True))
    assert combos, "la BD de test debe tener combos con receta"

    for combo in combos:
        incluidas = [i for i in combo["ingredientes"] if i["incluido_por_defecto"]]
        esperado = sum(i["cogs_ingrediente"] for i in incluidas)
        assert combo["costo_total_receta"] == pytest.approx(esperado, abs=0.011), combo["nombre_combo"]
        # Todo PRINCIPAL cuenta y, como mucho, un OPCIONAL.
        assert all(i["incluido_por_defecto"] for i in combo["ingredientes"] if not _es_opcional(i))
        assert sum(1 for i in incluidas if _es_opcional(i)) <= 1, combo["nombre_combo"]


def test_el_opcional_por_defecto_es_el_de_la_categoria(client, crear_usuario, monkeypatch):
    _fijar_reglas(monkeypatch, REGLAS_TEST)
    combos = _recetas(client, crear_usuario(admin=True))

    singani = [c for c in combos if (c["nombre_categoria_combo"] or "").strip() == "SINGANI"
               and any(_es_opcional(i) for i in c["ingredientes"])]
    if not singani:
        pytest.skip("la BD de test no tiene combos SINGANI con opcionales")
    for combo in singani:
        marcados = [i["id_producto"] for i in combo["ingredientes"]
                    if _es_opcional(i) and i["incluido_por_defecto"]]
        assert marcados == [60], combo["nombre_combo"]  # GINGER ALE 2LT

    # Categoria sin regla (VINOS no tiene variable): solo cuentan los principales.
    for combo in combos:
        if (combo["nombre_categoria_combo"] or "").strip() == "VINOS":
            assert not any(i["incluido_por_defecto"] for i in combo["ingredientes"] if _es_opcional(i))


def test_sin_reglas_configuradas_solo_cuentan_los_principales(client, crear_usuario, monkeypatch):
    _fijar_reglas(monkeypatch, {})
    combos = _recetas(client, crear_usuario(admin=True))

    for combo in combos:
        principales = sum(i["cogs_ingrediente"] for i in combo["ingredientes"] if not _es_opcional(i))
        assert combo["costo_total_receta"] == pytest.approx(principales, abs=0.011), combo["nombre_combo"]
        assert not any(i["incluido_por_defecto"] for i in combo["ingredientes"] if _es_opcional(i))


def test_el_join_con_bar_combo_coctel_no_pierde_ni_duplica_lineas(client, crear_usuario, db_session):
    combos = _recetas(client, crear_usuario(admin=True))
    lineas_api = sum(len(c["ingredientes"]) for c in combos)
    lineas_vista = db_session.execute(text("SELECT COUNT(*) FROM vw_pourcost_receta")).scalar()
    assert lineas_api == lineas_vista


def test_productos_sueltos_responde_con_su_forma(client, crear_usuario):
    r = client.get(PRODUCTOS, headers=crear_usuario(admin=True).headers)
    assert r.status_code == 200, r.text
    productos = r.json()
    assert productos
    assert {"id_producto", "nombre", "wac_unitario", "pour_cost_pct", "sin_wac"} <= set(productos[0])


@pytest.mark.parametrize("ruta", [RECETAS, PRODUCTOS])
def test_solo_administradores_acceden(client, crear_usuario, ruta):
    assert client.get(ruta).status_code == 401
    assert client.get(ruta, headers=crear_usuario(admin=False).headers).status_code == 403
