"""FastAPI app. Uvicorn: `uvicorn data2html.api.main:app --reload`."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from data2html import __version__
from data2html.api import catalog, csv, explore, profile, semantic, sql
from data2html.api.deps import get_settings, install_error_handlers
from data2html.api.schemas import Compat, Health
from data2html.i18n import LanguageMiddleware
from data2html.spec import FieldType, allowed_marks

__all__ = ["app", "get_settings"]

app = FastAPI(title="data2html", version=__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite in development
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["*"],
)
# Request language (Accept-Language) for server messages; set before routing and body validation.
app.add_middleware(LanguageMiddleware)
install_error_handlers(app)
app.include_router(catalog.router)
app.include_router(csv.router)
app.include_router(explore.router)
app.include_router(profile.router)
app.include_router(sql.router)
app.include_router(sql.jobs)
app.include_router(semantic.router)
app.include_router(semantic.visuals)


@app.get("/health")
def health() -> Health:
    return Health(status="ok", version=__version__)


@app.get("/api/compat")
def compat(dimension: FieldType | None = None, has_color: bool = False) -> Compat:
    return Compat(marks=allowed_marks(dimension, has_color=has_color))
