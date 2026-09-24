"""URL de conexion a la BD (config.Settings._url_mysql).

Las credenciales se interpolaban en un f-string: una contrasena con '@', ':',
'/' o '#' rompia el parseo de la URL. URL.create escapa cada componente.
"""
from sqlalchemy.engine import make_url

from config import Settings


def test_contrasena_con_caracteres_reservados_sobrevive_el_parseo():
    url = Settings._url_mysql("root", "p@ss:w/rd#1", "db.example", "3306", "adminerp")
    parseada = make_url(url.render_as_string(hide_password=False))
    assert parseada.password == "p@ss:w/rd#1"
    assert parseada.host == "db.example"
    assert parseada.port == 3306
    assert parseada.database == "adminerp"


def test_contrasena_vacia_se_omite_de_la_url():
    url = Settings._url_mysql("root", "", "localhost", "3306", "adminerp")
    assert url.password is None
    assert url.render_as_string(hide_password=False) == "mysql+pymysql://root@localhost:3306/adminerp"
