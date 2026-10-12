"""App FastAPI. Uvicorn: `uvicorn data2html.api.main:app --reload`."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from data2html.spec import FieldType, allowed_marks

app = FastAPI(title="data2html", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite en desarrollo
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/catalog")
def catalog() -> dict[str, list[object]]:
    return {"sources": []}  # Fase 1


@app.get("/api/compat")
def compat(dimension: FieldType | None = None, has_color: bool = False) -> dict[str, list[str]]:
    return {"marks": [m.value for m in allowed_marks(dimension, has_color=has_color)]}
