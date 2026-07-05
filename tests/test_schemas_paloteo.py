"""Tests de las reglas de validacion de Pydantic en schemas.py.

Se instancia el modelo con un payload y se verifica que Pydantic lo acepte
o lo rechace (ValidationError) segun corresponda. No se toca la base de
datos: estos modelos validan la forma del payload antes de que llegue a
cualquier endpoint.
"""
import pytest
from pydantic import ValidationError

from schemas import PaloteoItem, PaloteoRequest, PesoAbierta


def _item(id_producto=1, botellas_cerradas=1, pesos_abiertas=None):
    return PaloteoItem(
        id_producto=id_producto,
        botellas_cerradas=botellas_cerradas,
        pesos_abiertas=pesos_abiertas or [],
    )


def test_items_duplicados_rechazados():
    with pytest.raises(ValidationError):
        PaloteoRequest(
            id_operacion=1,
            id_barra=1,
            items=[_item(id_producto=5), _item(id_producto=5)],
        )


def test_items_unicos_aceptados():
    request = PaloteoRequest(
        id_operacion=1,
        id_barra=1,
        items=[_item(id_producto=5), _item(id_producto=6)],
    )
    assert len(request.items) == 2


def test_items_vacio_rechazado():
    with pytest.raises(ValidationError):
        PaloteoRequest(id_operacion=1, id_barra=1, items=[])


def test_peso_negativo_rechazado_en_peso_abierta():
    with pytest.raises(ValidationError):
        PesoAbierta(peso=-5)


def test_peso_negativo_rechazado_dentro_de_item():
    with pytest.raises(ValidationError):
        PaloteoItem(
            id_producto=1,
            botellas_cerradas=0,
            pesos_abiertas=[{"peso": -5}],
        )


def test_botellas_cerradas_negativas_rechazadas():
    with pytest.raises(ValidationError):
        PaloteoItem(id_producto=1, botellas_cerradas=-1)


def test_id_producto_invalido_rechazado():
    with pytest.raises(ValidationError):
        PaloteoItem(id_producto=0, botellas_cerradas=1)
