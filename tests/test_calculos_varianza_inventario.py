from decimal import Decimal

from main import _calcular_valor_varianza, _resumir_valoracion_varianzas


def _delta(delta_paq, delta_det_operativo):
    return {
        "delta_paq": delta_paq,
        "delta_det_operativo": delta_det_operativo,
    }


def test_valor_varianza_suma_envases_y_detalle_operativo():
    valoracion = _calcular_valor_varianza(
        _delta(-1, 2),
        {"wac_snapshot": Decimal("100"), "rendimiento_por_envase": Decimal("34")},
    )

    assert valoracion["estado_valoracion"] == "VALORIZADO"
    assert valoracion["valor_paq"] == Decimal("-100")
    assert valoracion["valor_detalle_operativo"] == Decimal("5.882352941176470588235294118")
    assert valoracion["valor_neto"] == Decimal("-94.11764705882352941176470588")


def test_valor_varianza_no_trata_wac_faltante_como_cero():
    valoracion = _calcular_valor_varianza(_delta(1, 0), None)

    assert valoracion == {
        "estado_valoracion": "SIN_WAC",
        "valor_paq": None,
        "valor_detalle_operativo": None,
        "valor_neto": None,
    }


def test_valor_varianza_detecta_rendimiento_invalido_sin_perder_valor_paq():
    valoracion = _calcular_valor_varianza(
        _delta(1, -2),
        {"wac_snapshot": Decimal("100"), "rendimiento_por_envase": Decimal("0")},
    )

    assert valoracion["estado_valoracion"] == "RENDIMIENTO_INVALIDO"
    assert valoracion["valor_paq"] == Decimal("100")
    assert valoracion["valor_detalle_operativo"] is None
    assert valoracion["valor_neto"] is None


def test_resumen_excluye_lineas_no_valorizadas():
    resumen = _resumir_valoracion_varianzas([
        {"estado_valoracion": "VALORIZADO", "valor_neto": -12.5},
        {"estado_valoracion": "VALORIZADO", "valor_neto": 5},
        {"estado_valoracion": "SIN_WAC", "valor_neto": None},
    ])

    assert resumen == {
        "faltantes": 12.5,
        "sobrantes": 5.0,
        "neto": -7.5,
        "productos_sin_valoracion": 1,
    }