"""Tests de las funciones de calculo puras del modulo POUR COST.

Igual que test_calculos_pesaje.py: ninguna de estas funciones toca la base de
datos, reciben datos en memoria y devuelven numeros/estructuras deterministas.
Ver documentos/pour_cost/pourcost.md para el diseño completo.
"""
from decimal import Decimal

import pytest

from main import (
    _agregar_costo_receta,
    _calcular_pour_cost_pct,
    _calcular_precio_sugerido,
)


# --- _calcular_pour_cost_pct -------------------------------------------------

def test_pour_cost_pct_caso_real_test_pos():
    """Dato real de test_pos (2026-08-05): combo 'V CHUFLAY DEL REY', costo
    10.7856592593, precio 45.00 -> ~23.97% (verificado a mano en la sesion de diseño)."""
    resultado = _calcular_pour_cost_pct(Decimal("10.7856592593"), Decimal("45.00"))
    assert resultado == Decimal("23.97")


def test_pour_cost_pct_costo_cero():
    assert _calcular_pour_cost_pct(Decimal("0"), Decimal("45.00")) == Decimal("0.00")


@pytest.mark.parametrize("precio_venta", [None, Decimal("0"), Decimal("-5")])
def test_pour_cost_pct_sin_precio_valido_devuelve_none(precio_venta):
    """precio_venta ausente, cero o negativo no debe intentar dividir (ZeroDivisionError)."""
    assert _calcular_pour_cost_pct(Decimal("10"), precio_venta) is None


def test_pour_cost_pct_acepta_precio_como_float_crudo():
    """Las filas de BD pueden traer precio_venta como float; la funcion lo normaliza a Decimal."""
    resultado = _calcular_pour_cost_pct(Decimal("9"), 45.0)
    assert resultado == Decimal("20.00")


# --- _calcular_precio_sugerido -----------------------------------------------

def test_precio_sugerido_exacto_y_redondeado():
    exacto, redondeado = _calcular_precio_sugerido(Decimal("10.7856592593"), Decimal("20"))
    assert exacto == Decimal("53.93")
    assert redondeado == Decimal("54")


def test_precio_sugerido_empate_exacto_redondea_half_up_no_banker():
    """8.5 / (20/100) = 42.5 exacto: HALF_UP debe subir a 43, no bajar a 42 (banker's rounding)."""
    _, redondeado = _calcular_precio_sugerido(Decimal("8.5"), Decimal("20"))
    assert redondeado == Decimal("43")


def test_precio_sugerido_sin_redondeo_extra_cuando_ya_es_entero():
    exacto, redondeado = _calcular_precio_sugerido(Decimal("21"), Decimal("50"))
    assert exacto == Decimal("42.00")
    assert redondeado == Decimal("42")


@pytest.mark.parametrize("target", [None, Decimal("0"), Decimal("-10")])
def test_precio_sugerido_target_invalido_devuelve_none(target):
    assert _calcular_precio_sugerido(Decimal("10"), target) is None


# --- _agregar_costo_receta ----------------------------------------------------

def _linea(id_combo, id_producto, cogs, sin_wac=0, **overrides):
    base = {
        "id_combo_coctel": id_combo,
        "codigo_combo": f"C{id_combo}",
        "nombre_combo": f"Combo {id_combo}",
        "descripcion_combo": None,
        "nombre_categoria_combo": "COCTELES",
        "id_producto": id_producto,
        "cogs_ingrediente": cogs,
        "sin_wac": sin_wac,
    }
    base.update(overrides)
    return base


def test_agregar_costo_receta_suma_lineas_del_mismo_combo():
    lineas = [
        _linea(1, 100, Decimal("3.50")),
        _linea(1, 101, Decimal("2.25")),
    ]
    combos = _agregar_costo_receta(lineas)
    assert combos[1]["costo_total"] == Decimal("5.75")
    assert combos[1]["costo_incompleto"] is False
    assert len(combos[1]["ingredientes"]) == 2


def test_agregar_costo_receta_marca_incompleto_si_alguna_linea_sin_wac():
    lineas = [
        _linea(1, 100, Decimal("3.50"), sin_wac=0),
        _linea(1, 101, Decimal("0"), sin_wac=1),
    ]
    combos = _agregar_costo_receta(lineas)
    assert combos[1]["costo_incompleto"] is True


def test_agregar_costo_receta_separa_combos_distintos():
    lineas = [
        _linea(1, 100, Decimal("3.50")),
        _linea(2, 200, Decimal("9.00")),
    ]
    combos = _agregar_costo_receta(lineas)
    assert set(combos.keys()) == {1, 2}
    assert combos[1]["costo_total"] == Decimal("3.50")
    assert combos[2]["costo_total"] == Decimal("9.00")


def test_agregar_costo_receta_no_arrastra_error_de_float():
    """Sumar muchas lineas con residuo binario (0.1 + 0.2 != 0.3 en float) debe dar exacto en Decimal."""
    lineas = [_linea(1, i, Decimal("0.1")) for i in range(10)]
    combos = _agregar_costo_receta(lineas)
    assert combos[1]["costo_total"] == Decimal("1.0")


def test_agregar_costo_receta_lista_vacia():
    assert _agregar_costo_receta([]) == {}
