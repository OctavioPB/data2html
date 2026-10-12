"""Configuration from environment variables. No secrets here: only paths and limits."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    sources_file: Path | None = None  # config/sources.yaml; None = CSV only
    content_dir: Path | None = None  # content/: semantic models and reports (versioned in git)
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
    def semantic_dir(self) -> Path:
        return (self.content_dir or self.data_dir / "content") / "semantic"

    @property
    def catalog_meta_path(self) -> Path:
        return self.data_dir / "catalog_meta.json"

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ
        return cls(
            data_dir=Path(env.get("D2H_DATA_DIR", _REPO_ROOT / "data")),
            sources_file=Path(env.get("D2H_SOURCES_FILE", _REPO_ROOT / "config/sources.yaml")),
            content_dir=Path(env.get("D2H_CONTENT_DIR", _REPO_ROOT / "content")),
            max_upload_mb=int(env.get("D2H_MAX_UPLOAD_MB", "500")),
            duckdb_memory_limit=env.get("D2H_DUCKDB_MEMORY", "2GB"),
            duckdb_threads=int(env.get("D2H_DUCKDB_THREADS", "4")),
            query_timeout_s=int(env.get("D2H_QUERY_TIMEOUT_S", "60")),
        )
