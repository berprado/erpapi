import json

from main import _normalizar_fila_paloteo_historico


def _fila(**cambios):
    fila = {
        "id_paloteo_cierre": 10,
        "id_operacion": 1303,
        "id_barra": 1,
        "barra": "BARRA 1",
        "id_producto": 42,
        "codigo_producto": "42",
        "producto": "PRODUCTO PYTEST",
        "categoria": "CATEGORIA PYTEST",
        "actual_paq": 1,
        "actual_detalle": 10,
        "fisico_paq": 1,
        "fisico_detalle": 10.5,
        "diferencia_paq": 0,
        "diferencia_detalle": 0.5,
        "tiene_diferencia": 1,
        "fecha_reg": None,
        "estado_producto": "HAB",
        "id_crudo": 99,
        "onzas_crudas": 10.25,
        "pesos_abiertas": json.dumps([{"peso": 500}, {"peso": 450}]),
    }
    fila.update(cambios)
    return fila


def test_normalizar_fila_conserva_diferencia_pos_y_enriquece_crudo():
    fila = _normalizar_fila_paloteo_historico(_fila())

    assert fila["diferencia_detalle"] == 0.5
    assert fila["diferencia_exacta_oz"] == 0.25
    assert fila["peso_gramos"] == 950.0
    assert fila["tiene_captura_cruda"] is True


def test_normalizar_fila_conserva_nulls_del_cierre():
    fila = _normalizar_fila_paloteo_historico(_fila(
        fisico_paq=None,
        fisico_detalle=None,
        diferencia_paq=None,
        diferencia_detalle=None,
        tiene_diferencia=0,
        id_crudo=None,
        onzas_crudas=None,
        pesos_abiertas=None,
    ))

    assert fila["fisico_paq"] is None
    assert fila["fisico_detalle"] is None
    assert fila["diferencia_paq"] is None
    assert fila["diferencia_detalle"] is None
    assert fila["diferencia_exacta_oz"] is None
    assert fila["peso_gramos"] is None
    assert fila["tiene_captura_cruda"] is False


def test_normalizar_fila_ignora_pesos_crudos_invalidos():
    fila = _normalizar_fila_paloteo_historico(_fila(
        pesos_abiertas=json.dumps([
            {"peso": 500},
            {"peso": "invalido"},
            {"sin_peso": 1},
        ])
    ))

    assert fila["peso_gramos"] == 500.0

def test_clasifica_contado_con_y_sin_diferencia():
    assert _normalizar_fila_paloteo_historico(_fila())["clasificacion"] == "con_diferencia"
    cuadrado = _normalizar_fila_paloteo_historico(_fila(diferencia_detalle=0, tiene_diferencia=0))
    assert cuadrado["clasificacion"] == "cuadrado"


def test_clasifica_movimiento_sin_contar_como_alerta():
    fila = _normalizar_fila_paloteo_historico(_fila(
        fisico_paq=None, fisico_detalle=None, diferencia_paq=None,
        diferencia_detalle=None, tiene_diferencia=0, ventas_paq=1,
    ))
    assert fila["tuvo_movimiento"] is True
    assert fila["clasificacion"] == "con_movimiento_sin_contar"


def test_clasifica_sin_movimiento_ni_conteo():
    fila = _normalizar_fila_paloteo_historico(_fila(
        fisico_paq=None, fisico_detalle=None, diferencia_paq=None,
        diferencia_detalle=None, tiene_diferencia=0,
        ventas_paq=0, ventas_detalle=0, ingreso_paq=0, ingreso_detalle=0,
    ))
    assert fila["tuvo_movimiento"] is False
    assert fila["clasificacion"] == "sin_movimiento"
