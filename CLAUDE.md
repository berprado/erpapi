# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BackStage API: a FastAPI backend + integrated PWA frontend for physical inventory control and bar auditing ("paloteo") of the BackStage POS system. Single-process app: `main.py` defines both the JSON API and serves the static PWA. See `README.md` for the full endpoint reference, business rules, and data flow — it is kept up to date and should be the first place to check before re-deriving behavior from code.

## Commands

```powershell
# Setup
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Run dev server (reload enabled)
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Tests (unit only — no DB needed)
pip install -r requirements-dev.txt
python -m pytest

# Generate a SECRET_KEY for .env
python -c "import secrets; print(secrets.token_hex(32))"
```

App: `http://localhost:8000/` — API docs (Swagger): `http://localhost:8000/docs`

There is a small pytest suite (`pytest.ini` sets `testpaths = tests`; install with `pip install -r requirements-dev.txt`). It covers **pure unit logic only** — weight rounding and the tolerance band (`tests/test_calculos_pesaje.py`) and the Pydantic validators (`tests/test_schemas_paloteo.py`). There are no DB fixtures and no endpoint/integration tests, so route handlers, SQL, and the adjustments flow are not covered — verify those by running the server and exercising endpoints via `/docs` or the PWA UI. No linter and no CI workflow are configured; nothing runs the suite automatically.

## Architecture

- `main.py` — all route handlers, JWT auth dependency (`get_usuario_actual`), admin role check (`_es_usuario_administrador`), and the paloteo/pesaje business logic (weight-to-ounce conversion, rounding, consolidation preview). This is the biggest file and where most logic lives; it's organized as one flat FastAPI app, not split into routers.
- `models.py` — SQLAlchemy ORM models. Intentionally maps only the columns actually used by the API (not full table schemas) — see the comment in `models.py` for the rationale. Many queries instead use raw SQL via `sqlalchemy.text()` for joins/columns not worth mapping (e.g. role lookups in `_es_usuario_administrador`).
- `schemas.py` — Pydantic request/response models, including field validators for business rules (no negative weights, unique `id_producto` per payload, etc).
- `config.py` — `pydantic-settings` `Settings` loaded from `.env`. Selects DB credentials based on `APP_ENV` (`test` = WAMP local, `production` = remote) via `settings.database_url`. Also owns paloteo "barra operativa" config (`PALOTEO_DEFAULT_BARRA_ID`, `PALOTEO_SELECTOR_ENABLED`, `PALOTEO_ALLOWED_BARRAS`).
- `database.py` — SQLAlchemy engine/session setup and the `get_db()` FastAPI dependency.
- `static/` — the PWA frontend (vanilla JS, Tailwind, service worker). Served at `/` with assets under `/assets`. Views: PALOTEO 1/2/3, REPORTE, PESAJE (admin-only). `sw.js` caches static assets cache-first and `/api/*` network-first.
- `querys/` — ad-hoc SQL dumps/snapshots, not application code.
- `documentos/` — design notes and process docs for specific features (paloteo storage, ajustes flow, etc).

### Key domain logic

- **Operativa state machine**: inventory actions are only allowed while the active `ope_operacion` is in state `24` (INICIO CIERRE). Endpoints re-validate this server-side, not just at session start.
- **Barra operativa resolution**: if `PALOTEO_SELECTOR_ENABLED=false`, the barra is fixed to `PALOTEO_DEFAULT_BARRA_ID`; if true, frontend may pass `X-Barra-Id` restricted to `PALOTEO_ALLOWED_BARRAS`. Any payload's `id_barra` must match the resolved barra.
- **Weight conversion** (`_redondear_media_onza_half_up` and surrounding helpers in `main.py`): grams → ounces using each product's `gramos_por_oz` from its weighing profile (`app_producto_pesaje_config_api`), with `peso_liquido = max(0, peso_medido - tara)`. Exact ounces are kept in raw audit (`app_paloteo_registro_crudo`); POS values are rounded to the nearest 0.5 oz using HALF_UP rounding (`Decimal`, not float rounding) to keep backend/frontend in sync.
- **Tolerance band**: `_obtener_tolerancia_operativa_oz` defines the dead-band a weight delta must exceed before it counts as a real adjustment. Since v10.39 it is a flat **0.5 oz for every `pesable=1` product** (no per-category distinction) and `0.0` for non-weighable ones, which are counted in whole units and have no scale noise to filter. 0.5 oz is deliberately the POS rounding step: both `real_det` and `ideal_det` are always multiples of 0.5, so any delta that clears the band already sits on the grid and quantizing it introduces no distortion. A band *smaller* than the grid would amplify (a 0.25 oz delta would round up to 0.50 on the voucher). `_cuantizar_delta_onzas_operativo` applies it: `abs(delta) < tolerancia` → `0.0`, otherwise `_redondear_media_onza_half_up`. The comparison is strict, so a delta of exactly 0.50 oz *does* trigger an adjustment. Applied in `_calcular_diferencias_paloteo`, the single source of truth shared by the consolidation preview and by applying adjustments — the only place in the system where tolerance decides anything (elsewhere `tolerancia_oz` is merely reported in the profile payload). It is never applied during capture. Only `delta_det_operativo` is written to `bar_detalle_ajuste`/`bar_detalle_salida_inv`; `delta_paq` (closed bottles) bypasses tolerance and rounding entirely. `bar_inventario` is set to the exact physical `real_det` **only for products that produce an adjustment** — the equalization loop iterates the tolerance-filtered list, so a tolerated product is never written. That is a no-op today (a tolerated product has `delta_det_exacto == 0.0`) but holds only while the multiple-of-0.5 invariant does; making it unconditional is a pending item in `TODO.md`. `static/app.js` mirrors the formula in `cuantizarDeltaOnzas` so the UI matches what the backend persists. Full rationale: `documentos/redondeo_y_tolerancia.md`.
- **`tolerancia_oz` column is vestigial**: `app_producto_pesaje_config_api.tolerancia_oz` still exists, is mapped in `models.py`, is selected by the product queries, and is exposed in the `PerfilPesaje` schema — but its stored value is **never used**. The API overwrites it with `_obtener_tolerancia_operativa_oz()` before responding; the column survives only as a `None`-check guard for incomplete profiles. It is a leftover of the pre-v10.39 per-category scheme. Do not read tolerance from the DB — call the helper.
- **Roles**: admin-only endpoints (Pesaje module) are gated by `_es_usuario_administrador`, checking `seg_permiso`/`seg_rol` for `ROLE_ADMIN`. Login response includes `is_admin` so the frontend can hide the Pesaje menu entry.
- **Soft deletes**: most tables use `estado` (`'HAB'`/`'DES'`) rather than hard deletes; pesaje profile deletion is blocked if it's the last active profile for a product.

## Mandatory rule: PWA cache busting

**Any modification to project files requires a cache-busting version bump**, enforced by `.github/instructions/cache-busting-obligatorio.instructions.md`:

- Bump `CACHE_NAME` in `static/sw.js`.
- Bump the `?v=X.Y` query string on versioned assets in `static/index.html`.
- Versioning: `MAJOR.MINOR` — MINOR +0.1 for incremental changes (fix/text/logic), MAJOR +1.0 for architecture/breaking changes.
- Keep `CACHE_NAME` and `static/index.html` asset versions numerically in sync to avoid mixed caches.

Do this for every change, even backend-only ones, per the instructions file.

## Environments

`APP_ENV` in `.env` selects the DB: `test` → WAMP local (`TEST_DB_*`), `production` → remote (`PROD_DB_*`). `SECRET_KEY` must be ≥32 chars (validated in `config.py`).
