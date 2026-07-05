"""Tests de las funciones de calculo puras usadas por el paloteo/pesaje.

Ninguna de estas funciones toca la base de datos: reciben numeros, devuelven
numeros, siempre el mismo resultado para la misma entrada. Por eso no
necesitan fixtures ni mocks, solo llamarlas y comparar con assert.
"""
from decimal import Decimal

import pytest

from main import (
    _cuantizar_delta_onzas_operativo,
    _decimal2,
    _obtener_tolerancia_operativa_oz,
    _redondear_media_onza_half_up,
)


@pytest.mark.parametrize("valor, esperado", [
    (0.25, 0.5),    # justo en el medio, HALF_UP redondea hacia arriba
    (0.24, 0.0),    # por debajo del medio, redondea hacia abajo
    (0.75, 1.0),    # medio entre 0.5 y 1.0, redondea hacia arriba
    (1.5, 1.5),     # ya es multiplo de 0.5, no cambia
    (0.0, 0.0),
    (-0.25, -0.5),  # HALF_UP redondea lejos del cero tambien en negativos
])
def test_redondear_media_onza_half_up(valor, esperado):
    assert _redondear_media_onza_half_up(valor) == esperado


@pytest.mark.parametrize("pesable, esperado", [
    (1, 0.5),     # pesable: banda de 0.5 oz
    (0, 0.0),     # no pesable: sin banda
    (None, 0.0),  # sin dato: se trata como no pesable
    (2, 0.0),     # cualquier valor distinto de 1 cuenta como no pesable
])
def test_obtener_tolerancia_operativa_oz(pesable, esperado):
    assert _obtener_tolerancia_operativa_oz(pesable) == esperado


@pytest.mark.parametrize("delta, tolerancia, esperado", [
    (0.3, 0.5, 0.0),  # dentro de la banda muerta: no cuenta como diferencia
    (0.5, 0.5, 0.5),  # exactamente en el limite: SI cuenta (comparacion es "<", no "<=")
    (1.0, 0.5, 1.0),  # fuera de la banda, ya multiplo de 0.5
    (0.3, 0.0, 0.5),  # sin tolerancia (no pesable): cualquier delta se redondea igual
])
def test_cuantizar_delta_onzas_operativo(delta, tolerancia, esperado):
    assert _cuantizar_delta_onzas_operativo(delta, tolerancia) == esperado


@pytest.mark.parametrize("valor, esperado", [
    (1.005, Decimal("1.01")),  # caso exacto de mitad, HALF_UP redondea hacia arriba
    (2.0, Decimal("2.00")),
    (1.004, Decimal("1.00")),
])
def test_decimal2(valor, esperado):
    assert _decimal2(valor) == esperado
