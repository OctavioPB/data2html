"""FastAPI app. Uvicorn: `uvicorn data2html.api.main:app --reload`."""

from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from data2html import __version__
from data2html.api import catalog, csv, explore, ingest, login, profile, reports, semantic, sql, viewer
from data2html.api.deps import SettingsDep, get_settings, install_error_handlers
from data2html.api.schemas import Compat, Health
from data2html.auth import check_origin, require_author
from data2html.i18n import LanguageMiddleware
from data2html.render.theme import Theme, load_theme
from data2html.spec import FieldType, allowed_marks

__all__ = ["app", "get_settings"]

# Every state-changing browser request must come from our own origin (CSRF; ADR 0010)
app = FastAPI(title="data2html", version=__version__, dependencies=[Depends(check_origin)])
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite in development
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["*"],
)
# Request language (Accept-Language) for server messages; set before routing and body validation.
app.add_middleware(LanguageMiddleware)
install_error_handlers(app)
# The studio: single author (ADR 0005). Every route requires a session with the author role.
_author = [Depends(require_author)]
for r in (catalog.router, csv.router, explore.router, profile.router, sql.router, sql.jobs, semantic.router,
          semantic.visuals, reports.router, ingest.router):
    app.include_router(r, dependencies=_author)
# Sign-in, and the live viewer (multi-reader, identity from data2html.auth)
app.include_router(login.pages)
app.include_router(login.api)
app.include_router(viewer.pages)
app.include_router(viewer.api)
app.mount("/r-static", viewer.static, name="viewer-static")


@app.get("/health")
def health() -> Health:
    return Health(status="ok", version=__version__)


@app.get("/api/theme", dependencies=_author)
def theme(settings: SettingsDep) -> Theme:
    """Palette, font and currency of `config/theme.yaml`, shared by the studio and the viewer."""
    return load_theme(settings.theme_file)


@app.get("/api/compat", dependencies=_author)
def compat(dimension: FieldType | None = None, has_color: bool = False) -> Compat:
    return Compat(marks=allowed_marks(dimension, has_color=has_color))
