"""Definiciones de marca (piel visual) por instancia desplegada.

Cada sucursal corre el mismo código (mismo repo/rama `main`, ver
documentos/despliegue_seenode.md) pero se conecta a su propia base de datos
y puede mostrar su propio logo/paleta. La marca activa se selecciona con la
variable de entorno `BRAND_ID` (ver `config.py`) — nunca con una rama de
código ni con una copia del repo.

Los colores de cada marca son CSS custom properties (definidas en
static/cellar-sync-tokens.css y sobreescritas por static/brands/<id>.css),
no valores Python: este módulo solo referencia el nombre del archivo CSS a
enlazar. Así, para dar de alta una marca nueva alcanza con:
  1. agregar sus assets en static/imgs/brands/<id>/ y static/icons/brands/<id>/
  2. agregar static/brands/<id>.css con el override de colores
  3. agregar una entrada acá con esas rutas
  4. setear BRAND_ID=<id> en las env vars de esa instancia de Seenode
"""

from typing import TypedDict


class Brand(TypedDict):
    title: str
    app_name: str
    short_name: str
    description: str
    theme_color: str
    background_color: str
    icon_dir: str
    css_href: str
    logo_login: str
    logo_navbar_full: str
    logo_navbar_isotipo: str
    glitch_enabled: bool


# Tamaños de ícono Android que manifest.json expone para "instalar" la PWA.
# Debe existir un archivo android-icon-{size}x{size}.png en icon_dir para
# cada uno de estos tamaños.
_ANDROID_ICON_SIZES = [36, 48, 72, 96, 144, 192, 384, 512]

BRANDS: dict[str, Brand] = {
    "backstage": {
        "title": "BackStage | Live Dashboard",
        "app_name": "BackStage",
        "short_name": "BackStage",
        "description": "Control de inventario físico para barra BackStage",
        "theme_color": "#39ff14",
        "background_color": "#0d1515",
        "icon_dir": "/assets/icons",
        "css_href": "/assets/brands/backstage.css",
        "logo_login": "/assets/imgs/login_transp.png",
        "logo_navbar_full": "/assets/imgs/backstage_horizontal_banner.png",
        "logo_navbar_isotipo": "/assets/imgs/isotipo.png",
        "glitch_enabled": True,
    },
    "beer_garden": {
        "title": "Beer Garden | Live Dashboard",
        "app_name": "Beer Garden",
        "short_name": "Beer Garden",
        "description": "Control de inventario físico para barra Beer Garden",
        "theme_color": "#c5a674",
        "background_color": "#050505",
        "icon_dir": "/assets/icons/brands/beer_garden",
        "css_href": "/assets/brands/beer_garden.css",
        # Isotipo único (escudo cuadrado): sirve igual para login, navbar
        # completo y navbar colapsado — no hay (todavía) un lockup horizontal
        # separado como el de casa matriz.
        "logo_login": "/assets/imgs/brands/beer_garden/logo.png",
        "logo_navbar_full": "/assets/imgs/brands/beer_garden/logo.png",
        "logo_navbar_isotipo": "/assets/imgs/brands/beer_garden/logo.png",
        "glitch_enabled": False,
    },
}

DEFAULT_BRAND_ID = "backstage"
BRAND_IDS = set(BRANDS.keys())


def get_brand(brand_id: str) -> Brand:
    """Devuelve la config de marca para `brand_id`, o la de por defecto si
    no matchea (config.py ya valida BRAND_ID contra BRAND_IDS, así que este
    fallback es solo una red de seguridad)."""
    return BRANDS.get(brand_id, BRANDS[DEFAULT_BRAND_ID])


def build_manifest(brand: Brand) -> dict:
    """Arma el manifest.json (Web App Manifest) para la marca dada."""
    return {
        "name": f"{brand['app_name']} Inventario",
        "short_name": brand["short_name"],
        "description": brand["description"],
        "id": "/",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait",
        "background_color": brand["background_color"],
        "theme_color": brand["theme_color"],
        "lang": "es",
        "icons": [
            {
                "src": f"{brand['icon_dir']}/android-icon-{size}x{size}.png",
                "sizes": f"{size}x{size}",
                "type": "image/png",
                **({"purpose": "any"} if size in (192, 512) else {}),
            }
            for size in _ANDROID_ICON_SIZES
        ],
    }
