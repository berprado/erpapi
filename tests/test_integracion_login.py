"""Tests de integracion de /api/auth/login contra la BD de test local.

Cubren el flujo completo: credenciales correctas (JWT valido y usable, registro
en seg_acceso y en la auditoria), credenciales invalidas (401 generico, sin
distinguir usuario inexistente de password mala), usuario deshabilitado (403),
flag is_admin y rate limit (429 tras N fallos, por usuario, sin registrar el
intento frenado). Todo dentro de la transaccion del test (ver conftest.py);
ninguna fila de auditoria persiste.

Cada test manda un X-Forwarded-For unico: el endpoint lo toma como IP del
cliente (_obtener_ip_cliente), asi el contador de fallos por IP de un test no
contamina a los demas.
"""
import uuid

import jwt
import pytest
from sqlalchemy import text

from config import settings

LOGIN = "/api/auth/login"


def _ip_unica() -> dict:
    return {"X-Forwarded-For": f"ip-pytest-{uuid.uuid4().hex[:10]}"}


def test_login_correcto_devuelve_jwt_usable_y_registra_acceso(client, crear_usuario, db_session):
    user = crear_usuario(contrasena="Secreta123!")

    r = client.post(LOGIN, json={"usuario": user.usuario, "contrasena": "Secreta123!"},
                    headers=_ip_unica())
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["token_type"] == "Bearer"
    assert data["is_admin"] is False
    assert data["nombres"].startswith("FIXTURE PYTEST,")

    # el token es un JWT real firmado con la clave de la app y con el sub correcto
    from main import ALGORITHM, SECRET_KEY
    payload = jwt.decode(data["access_token"], SECRET_KEY, algorithms=[ALGORITHM])
    assert payload["sub"] == user.usuario
    assert payload["id"] == data["usuario_id"]

    # y sirve contra un endpoint protegido (404 = paso la autenticacion)
    r2 = client.get("/api/inventario/paloteo/999999999",
                    headers={"Authorization": f"Bearer {data['access_token']}"})
    assert r2.status_code == 404

    # rastro en seg_acceso (compatibilidad POS) y en la auditoria propia
    accesos = db_session.execute(text(
        "SELECT COUNT(*) FROM seg_acceso WHERE usuario = :u"), {"u": user.usuario}).scalar()
    assert accesos == 1
    exitos = db_session.execute(text(
        "SELECT COUNT(*) FROM app_login_auditoria_api WHERE usuario = :u AND exito = 1"),
        {"u": user.usuario}).scalar()
    assert exitos == 1


def test_login_de_admin_devuelve_is_admin_true(client, crear_usuario):
    admin = crear_usuario(admin=True, contrasena="Secreta123!")
    r = client.post(LOGIN, json={"usuario": admin.usuario, "contrasena": "Secreta123!"},
                    headers=_ip_unica())
    assert r.status_code == 200, r.text
    assert r.json()["is_admin"] is True


def test_login_credenciales_invalidas_401_generico(client, crear_usuario, db_session):
    """Password mala y usuario inexistente responden el mismo 401 generico
    (no se filtra si la cuenta existe); el fallo queda auditado con motivo
    CREDENCIALES."""
    user = crear_usuario(contrasena="Secreta123!")

    r = client.post(LOGIN, json={"usuario": user.usuario, "contrasena": "incorrecta"},
                    headers=_ip_unica())
    assert r.status_code == 401
    detalle_existente = r.json()["detail"]

    r2 = client.post(LOGIN, json={"usuario": f"no_existe_{uuid.uuid4().hex[:8]}",
                                  "contrasena": "incorrecta"},
                     headers=_ip_unica())
    assert r2.status_code == 401
    assert r2.json()["detail"] == detalle_existente

    motivo = db_session.execute(text(
        "SELECT motivo FROM app_login_auditoria_api WHERE usuario = :u AND exito = 0"),
        {"u": user.usuario}).scalar()
    assert motivo == "CREDENCIALES"


def test_login_usuario_deshabilitado_403(client, crear_usuario, db_session):
    """Con credenciales CORRECTAS pero cuenta deshabilitada: 403 con motivo
    DESHABILITADO (la password se valida antes que el estado para no filtrar
    informacion, por eso este caso exige conocer la contrasena)."""
    user = crear_usuario(contrasena="Secreta123!", habilitado='0')

    r = client.post(LOGIN, json={"usuario": user.usuario, "contrasena": "Secreta123!"},
                    headers=_ip_unica())
    assert r.status_code == 403

    motivo = db_session.execute(text(
        "SELECT motivo FROM app_login_auditoria_api WHERE usuario = :u AND exito = 0"),
        {"u": user.usuario}).scalar()
    assert motivo == "DESHABILITADO"


def test_login_rate_limit_por_usuario_429(client, crear_usuario, db_session):
    user = crear_usuario(contrasena="Secreta123!")
    ip = _ip_unica()
    max_fallos = settings.LOGIN_MAX_INTENTOS_USUARIO

    for _ in range(max_fallos):
        r = client.post(LOGIN, json={"usuario": user.usuario, "contrasena": "incorrecta"},
                        headers=ip)
        assert r.status_code == 401

    # alcanzado el limite, ni la contrasena correcta pasa
    r = client.post(LOGIN, json={"usuario": user.usuario, "contrasena": "Secreta123!"},
                    headers=ip)
    assert r.status_code == 429

    # el freno es por usuario: cambiar de IP no lo esquiva
    r = client.post(LOGIN, json={"usuario": user.usuario, "contrasena": "Secreta123!"},
                    headers=_ip_unica())
    assert r.status_code == 429

    # los intentos frenados con 429 no agregan filas de auditoria (el corte es
    # ANTES de evaluar credenciales)
    fallos = db_session.execute(text(
        "SELECT COUNT(*) FROM app_login_auditoria_api WHERE usuario = :u AND exito = 0"),
        {"u": user.usuario}).scalar()
    assert fallos == max_fallos
