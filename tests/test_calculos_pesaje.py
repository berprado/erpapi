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


@pytest.mark.parametrize("delta, esperado", [
    (33.59, 33.5),    # supra-banda fuera de grilla: el voucher pierde el residuo 0.09
    (33.74, 33.5),    # bajo la mitad del paso: redondea al 0.5 inferior
    (33.75, 34.0),    # mitad exacta del paso: HALF_UP sube
    (-33.59, -33.5),  # negativos: mismo residuo, lejos del cero
    (0.7, 0.5),       # apenas sobre la banda: cuantiza al paso inferior
])
def test_cuantizar_delta_fuera_de_grilla(delta, esperado):
    """Deltas fuera de la grilla 0.5 solo existen si el invariante multiplo-de-0.5
    se rompe (ej. residuo 0.07 oz de recetas mal configuradas). La cuantizacion
    los lleva al paso mas cercano: el documento (voucher) absorbe hasta ±0.25 de
    residuo; el stock NO, porque la igualacion escribe el fisico exacto."""
    assert _cuantizar_delta_onzas_operativo(delta, 0.5) == esperado


def test_borde_de_banda_es_fragil_al_float_fuera_de_grilla():
    """Documenta una fragilidad conocida, NO un comportamiento deseado: fuera de
    la grilla, dos restas que en decimal valen identicamente 0.50 caen de lados
    distintos de la banda segun su representacion binaria. Dentro de la grilla
    esto es imposible (los multiplos de 0.5 son exactos en float y la resta
    tambien), que es una razon mas para proteger el invariante. Desde v10.77 el
    caso mal tolerado igual converge en stock (la igualacion escribe el fisico
    exacto); solo se pierde el voucher de 0.5 oz."""
    assert 0.57 - 0.07 == 0.49999999999999994  # decimal: 0.50 exacto
    assert _cuantizar_delta_onzas_operativo(0.57 - 0.07, 0.5) == 0.0    # tolerado
    assert _cuantizar_delta_onzas_operativo(12.33 - 11.83, 0.5) == 0.5  # ajusta
    # en grilla, el mismo borde es determinista:
    assert _cuantizar_delta_onzas_operativo(26.0 - 25.5, 0.5) == 0.5


@pytest.mark.parametrize("valor, esperado", [
    (1.005, Decimal("1.01")),  # caso exacto de mitad, HALF_UP redondea hacia arriba
    (2.0, Decimal("2.00")),
    (1.004, Decimal("1.00")),
])
def test_decimal2(valor, esperado):
    assert _decimal2(valor) == esperado
