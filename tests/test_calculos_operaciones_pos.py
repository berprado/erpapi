"""Calculos puros del flujo ingreso -> traspaso -> recepcion en barra (sin BD).

Los valores esperados son los que dejo el POS en test_pos el 2026-10-10
(ingresos 837 y 838, salida 738): documentos/operaciones_pos/01_ingreso_traspaso_recepcion.md
"""
from datetime import date
from decimal import Decimal

import pytest

from main import _evento_salida_almacen, _precio_costo_real_pos


@pytest.mark.parametrize("precio, tipo_documento, esperado", [
    # Recibo u otro: precio / 0.92 en float de 32 bits (Java).
    ("19", 40, "20.65217"),
    ("135", 40, "146.73912"),  # en doble precision seria 146.73913
    ("170", 40, "184.78261"),
    # Factura: precio - 13%.
    ("16", 38, "13.92000"),
    ("10", 38, "8.70000"),
    ("0", 38, "0.00000"),
])
def test_precio_costo_real_igual_al_pos(precio, tipo_documento, esperado):
    assert _precio_costo_real_pos(Decimal(precio), tipo_documento) == Decimal(esperado)


def test_evento_salida_usa_fecha_de_la_operativa_y_doble_espacio():
    assert _evento_salida_almacen("ALMACEN GARDEN", 740, date(2026, 10, 7)) == (
        "Se registró una salida del Almacen: ALMACEN GARDEN, con el correlativo NRO  740 en fecha: 07/10/2026"
    )
