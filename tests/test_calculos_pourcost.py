"""Tests de las funciones de calculo puras del modulo POUR COST.

Igual que test_calculos_pesaje.py: ninguna de estas funciones toca la base de
datos, reciben datos en memoria y devuelven numeros/estructuras deterministas.
Ver documentos/pour_cost/pourcost.md para el diseño completo.
"""
from decimal import Decimal

import pytest

from main import (
    _calcular_costo_receta_simulado,
    _calcular_costo_receta_simulado_crudo,
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


# --- _agregar_costo_receta: opcional por defecto segun categoria ---------------

# {id_categoria: id_producto}, como lo entrega settings.pourcost_opcional_por_categoria.
REGLAS = {5: 60, 7: 63, 9: 61}  # SINGANI -> GINGER ALE, VODKAS -> SPRITE, GIN -> AGUA TONICA


def _receta_singani(id_categoria=5):
    """Principal 87 + opcionales: GINGER ALE (60), SPRITE (63), COCA COLA (62)."""
    kw = {"id_categoria_combo": id_categoria}
    return [
        _linea(1, 19, Decimal("87"), tipo_parte_combo="PRINCIPAL", **kw),
        _linea(1, 60, Decimal("4.4477"), tipo_parte_combo="OPCIONAL", **kw),
        _linea(1, 63, Decimal("5.5070"), tipo_parte_combo="OPCIONAL", **kw),
        _linea(1, 62, Decimal("5.8956"), tipo_parte_combo="OPCIONAL", **kw),
    ]


def test_costo_incluye_principal_mas_opcional_por_defecto_de_la_categoria():
    combo = _agregar_costo_receta(_receta_singani(), REGLAS)[1]
    assert combo["costo_total"] == Decimal("91.4477")
    marcadas = {l["id_producto"]: l["incluido_por_defecto"] for l in combo["ingredientes"]}
    assert marcadas == {19: True, 60: True, 63: False, 62: False}


def test_cada_categoria_usa_su_propio_opcional():
    combo = _agregar_costo_receta(_receta_singani(id_categoria=7), REGLAS)[1]
    assert combo["costo_total"] == Decimal("92.5070")  # VODKAS -> SPRITE 3LT (63)


def test_sin_configuracion_solo_cuenta_principales():
    for reglas in (None, {}):
        combo = _agregar_costo_receta(_receta_singani(), reglas)[1]
        assert combo["costo_total"] == Decimal("87")
        assert not any(l["incluido_por_defecto"] for l in combo["ingredientes"] if l["tipo_parte_combo"] == "OPCIONAL")


def test_categoria_sin_regla_solo_cuenta_principales():
    combo = _agregar_costo_receta(_receta_singani(id_categoria=6), REGLAS)[1]  # VINOS
    assert combo["costo_total"] == Decimal("87")


def test_linea_sin_id_categoria_combo_solo_cuenta_principales():
    lineas = [l for l in _receta_singani()]
    for l in lineas:
        del l["id_categoria_combo"]
    assert _agregar_costo_receta(lineas, REGLAS)[1]["costo_total"] == Decimal("87")


def test_opcional_por_defecto_ausente_en_el_combo_no_se_sustituye():
    """GIN -> AGUA TONICA (61); si el combo no la trae entre sus opcionales, no se elige otra."""
    combo = _agregar_costo_receta(_receta_singani(id_categoria=9), REGLAS)[1]
    assert combo["costo_total"] == Decimal("87")


def test_producto_por_defecto_como_principal_no_se_duplica():
    """Solo un OPCIONAL puede ser el default; un PRINCIPAL con ese id cuenta una sola vez."""
    lineas = [_linea(1, 60, Decimal("10"), tipo_parte_combo="PRINCIPAL", id_categoria_combo=5)]
    assert _agregar_costo_receta(lineas, REGLAS)[1]["costo_total"] == Decimal("10")


def test_costo_incompleto_ignora_opcionales_no_incluidos():
    lineas = _receta_singani()
    lineas[2]["sin_wac"] = 1  # SPRITE sin WAC, pero no es el default de SINGANI
    assert _agregar_costo_receta(lineas, REGLAS)[1]["costo_incompleto"] is False
    lineas[1]["sin_wac"] = 1  # GINGER ALE sin WAC y si cuenta
    assert _agregar_costo_receta(lineas, REGLAS)[1]["costo_incompleto"] is True


# --- settings.pourcost_opcional_por_categoria (lectura de POURCOST_OPCIONAL_CAT<id>) ---

def _reglas_desde(monkeypatch, dotenv, entorno=None):
    import config
    monkeypatch.setattr(config, "dotenv_values", lambda _ruta: dotenv)
    for clave in [k for k in config.os.environ if k.upper().startswith("POURCOST_OPCIONAL_CAT")]:
        monkeypatch.delenv(clave)
    for clave, valor in (entorno or {}).items():
        monkeypatch.setenv(clave, valor)
    return config.Settings.pourcost_opcional_por_categoria.fget(None)


def test_config_lee_una_variable_por_categoria(monkeypatch):
    reglas = _reglas_desde(monkeypatch, {"POURCOST_OPCIONAL_CAT1": "64", "POURCOST_OPCIONAL_CAT21": " 61 ", "OTRA": "9"})
    assert reglas == {1: 64, 21: 61}


def test_config_ignora_valores_invalidos(monkeypatch):
    reglas = _reglas_desde(monkeypatch, {
        "POURCOST_OPCIONAL_CAT1": "abc", "POURCOST_OPCIONAL_CAT2": "0",
        "POURCOST_OPCIONAL_CAT3": "-4", "POURCOST_OPCIONAL_CAT4": "", "POURCOST_OPCIONAL_CAT5": "60",
        "POURCOST_OPCIONAL_CATX": "7",
    })
    assert reglas == {5: 60}


def test_config_variable_de_entorno_real_gana_sobre_el_dotenv(monkeypatch):
    reglas = _reglas_desde(monkeypatch, {"POURCOST_OPCIONAL_CAT1": "64"}, {"POURCOST_OPCIONAL_CAT1": "99", "POURCOST_OPCIONAL_CAT2": "62"})
    assert reglas == {1: 99, 2: 62}


def test_config_sin_variables_devuelve_vacio(monkeypatch):
    assert _reglas_desde(monkeypatch, {}) == {}


# --- Casos de aceptacion: formulas de cantidad_receta → cogs_ingrediente -----
# Estos tests validan la formula que la UI de JS replica con pourCostCantidadUnidadBase.
# El backend calcula cogs_ingrediente en vw_pourcost_receta; aqui se verifica la
# consistencia aritmetica para los casos del enunciado (Long Island y Chuflay).

def test_long_island_37_lenguas_cantidad_1oz():
    """37 LENGUAS: 1 oz / 34 oz rendimiento * Bs 80 WAC ≈ Bs 2.35."""
    cantidad_receta = Decimal("1")
    rendimiento = Decimal("34")
    wac = Decimal("80")
    cogs = (cantidad_receta / rendimiento) * wac
    assert round(cogs, 2) == Decimal("2.35")


def test_long_island_37_lenguas_cantidad_1_5oz():
    """Al simular 1,5 oz: (1.5 / 34) * 80 ≈ Bs 3.53."""
    cantidad_receta = Decimal("1.5")
    rendimiento = Decimal("34")
    wac = Decimal("80")
    cogs = (cantidad_receta / rendimiento) * wac
    assert round(cogs, 2) == Decimal("3.53")


def test_chuflay_casa_real_negra_fraccion_interna():
    """Casa Real Negra: 1.5 oz visibles / 34 oz rendimiento = fraccion interna 0.044..."""
    cantidad_receta = Decimal("1.5")
    rendimiento = Decimal("34")
    cantidad_unidad_base = cantidad_receta / rendimiento
    # Fraccion interna: exactamente 1.5/34, no redondeada.
    assert abs(cantidad_unidad_base - Decimal("0.0441176470588235")) < Decimal("0.000001")


def test_division_por_cero_produce_cero_en_cantidad_unidad_base():
    """Si rendimiento es 0 el cogs debe ser 0 (sin ZeroDivisionError)."""
    # La logica de JS pourCostCantidadUnidadBase devuelve 0 si divisor == 0.
    # Este test documenta el contrato equivalente en Python.
    cantidad_receta = Decimal("1")
    rendimiento = Decimal("0")
    if rendimiento == 0:
        cogs = Decimal("0")
    else:
        cogs = cantidad_receta / rendimiento
    assert cogs == Decimal("0")


def _ingrediente_simulado(id_producto, *, cantidad, wac, tipo_parte='PRINCIPAL', incluido=True, divisor='1', tipo_cantidad='Detalle'):
    return {
        'id_producto': id_producto,
        'cantidad_receta': cantidad,
        'wac_actual': wac,
        'tipo_parte_combo': tipo_parte,
        'incluido': incluido,
        'tipo_cantidad_combo': tipo_cantidad,
        'unidades_detalle_por_base': divisor,
    }


def test_costo_simulado_chuflay_inicial_solo_principal():
    ingredientes = [
        _ingrediente_simulado(1, cantidad='1.5', wac='100', divisor='34', tipo_parte='PRINCIPAL'),
        _ingrediente_simulado(2, cantidad='4', wac='6', divisor='67.5', tipo_parte='OPCIONAL', incluido=False),
        _ingrediente_simulado(3, cantidad='4', wac='9', divisor='34', tipo_parte='OPCIONAL', incluido=False),
        _ingrediente_simulado(4, cantidad='4', wac='15', divisor='67.5', tipo_parte='OPCIONAL', incluido=False),
        _ingrediente_simulado(5, cantidad='4', wac='18.58', divisor='101.5', tipo_parte='OPCIONAL', incluido=False),
    ]

    costo = _calcular_costo_receta_simulado(ingredientes)
    pct = _calcular_pour_cost_pct(_calcular_costo_receta_simulado_crudo(ingredientes), Decimal('35'))

    assert costo == Decimal('4.41')
    assert pct == Decimal('12.61')


def test_costo_simulado_chuflay_con_todos_los_opcionales():
    ingredientes = [
        _ingrediente_simulado(1, cantidad='1.5', wac='100', divisor='34', tipo_parte='PRINCIPAL'),
        _ingrediente_simulado(2, cantidad='1', wac='0.50', divisor='1', tipo_parte='OPCIONAL', incluido=True, tipo_cantidad='Unidad'),
        _ingrediente_simulado(3, cantidad='1', wac='0.60', divisor='1', tipo_parte='OPCIONAL', incluido=True, tipo_cantidad='Unidad'),
        _ingrediente_simulado(4, cantidad='1', wac='0.70', divisor='1', tipo_parte='OPCIONAL', incluido=True, tipo_cantidad='Unidad'),
        _ingrediente_simulado(5, cantidad='1', wac='0.938236', divisor='1', tipo_parte='OPCIONAL', incluido=True, tipo_cantidad='Unidad'),
    ]

    costo = _calcular_costo_receta_simulado(ingredientes)
    pct = _calcular_pour_cost_pct(_calcular_costo_receta_simulado_crudo(ingredientes), Decimal('35'))

    assert costo == Decimal('7.15')
    assert pct == Decimal('20.43')


def test_cambio_en_opcional_no_seleccionado_no_modifica_total():
    base = [
        _ingrediente_simulado(1, cantidad='1.5', wac='100', divisor='34', tipo_parte='PRINCIPAL'),
        _ingrediente_simulado(2, cantidad='4', wac='18.58', divisor='101.5', tipo_parte='OPCIONAL', incluido=False),
    ]
    modificado = [
        _ingrediente_simulado(1, cantidad='1.5', wac='100', divisor='34', tipo_parte='PRINCIPAL'),
        _ingrediente_simulado(2, cantidad='8', wac='999', divisor='101.5', tipo_parte='OPCIONAL', incluido=False),
    ]

    assert _calcular_costo_receta_simulado(base) == Decimal('4.41')
    assert _calcular_costo_receta_simulado(modificado) == Decimal('4.41')


def test_costo_simulado_permita_varios_principales_y_solo_opcionales_marcados():
    ingredientes = [
        _ingrediente_simulado(1, cantidad='1', wac='34', divisor='34', tipo_parte='PRINCIPAL'),
        _ingrediente_simulado(2, cantidad='2', wac='50', divisor='25', tipo_parte='PRINCIPAL'),
        _ingrediente_simulado(3, cantidad='1', wac='10', divisor='10', tipo_parte='OPCIONAL', incluido=False),
        _ingrediente_simulado(4, cantidad='1', wac='5', divisor='5', tipo_parte='OPCIONAL', incluido=True),
    ]

    assert _calcular_costo_receta_simulado(ingredientes) == Decimal('6.00')


def test_costo_simulado_sin_opcionales_mantiene_comportamiento_previo():
    ingredientes = [
        _ingrediente_simulado(1, cantidad='1', wac='80', divisor='34', tipo_parte='PRINCIPAL'),
        _ingrediente_simulado(2, cantidad='4', wac='20', divisor='100', tipo_parte='PRINCIPAL'),
    ]

    assert _calcular_costo_receta_simulado(ingredientes) == Decimal('3.15')


def test_costo_simulado_evita_division_por_cero_en_ingrediente_seleccionado():
    ingredientes = [
        _ingrediente_simulado(1, cantidad='1', wac='80', divisor='0', tipo_parte='PRINCIPAL'),
        _ingrediente_simulado(2, cantidad='1', wac='10', divisor='10', tipo_parte='OPCIONAL', incluido=True),
    ]

    assert _calcular_costo_receta_simulado(ingredientes) == Decimal('1.00')
