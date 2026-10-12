"""Configuración desde variables de entorno. Sin secretos aquí: solo rutas y límites."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    max_upload_mb: int = 500
    duckdb_memory_limit: str = "2GB"
    duckdb_threads: int = 4
    query_timeout_s: int = 60

    @property
    def csv_dir(self) -> Path:
        return self.data_dir / "csv"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def catalog_meta_path(self) -> Path:
        return self.data_dir / "catalog_meta.json"

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ
        return cls(
            data_dir=Path(env.get("D2H_DATA_DIR", _REPO_ROOT / "data")),
            max_upload_mb=int(env.get("D2H_MAX_UPLOAD_MB", "500")),
            duckdb_memory_limit=env.get("D2H_DUCKDB_MEMORY", "2GB"),
            duckdb_threads=int(env.get("D2H_DUCKDB_THREADS", "4")),
            query_timeout_s=int(env.get("D2H_QUERY_TIMEOUT_S", "60")),
        )
