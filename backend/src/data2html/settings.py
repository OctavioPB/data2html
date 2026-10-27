"""Configuration from environment variables. No secrets here: only paths and limits."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]

# The viewer loads ECharts from this CDN with Subresource Integrity (the hash of exactly this file).
# To self-host it, set D2H_ECHARTS_URL to your copy of the same file (the hash still applies).
ECHARTS_URL = "https://cdn.jsdelivr.net/npm/echarts@6.1.0/dist/echarts.min.js"
ECHARTS_SRI = "sha384-C2iskrW/uPW46KzOjrvJIQo4YkV8lkD+QS0CrDN18IIPIpT/g2USu8bTP3nvmIAD"


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    sources_file: Path | None = None  # config/sources.yaml; None = CSV only
    content_dir: Path | None = None  # content/: semantic models and reports (versioned in git)
    max_upload_mb: int = 500
    duckdb_memory_limit: str = "2GB"
    duckdb_threads: int = 4
    query_timeout_s: int = 60
    theme_file: Path | None = None  # config/theme.yaml (palette, font, currency)
    # Development identities (auth/dev.py), localhost only; None = disabled. Never in production.
    dev_identities_file: Path | None = None
    dev_hosts: tuple[str, ...] = ("127.0.0.1", "::1", "localhost")  # clients allowed to use them
    viewer_cache_ttl_s: int = 60
    viewer_cache_max_entries: int = 1000
    echarts_url: str = ECHARTS_URL
    auth_file: Path | None = None  # config/auth.yaml (providers); None = local login only
    users_file: Path | None = None  # config/users.yaml (local users, hashed passwords)
    ai_file: Path | None = None  # config/ai.yaml (what the AI may see per source); None = metadata only
    # Public origin when behind a proxy (OIDC redirect URI, CSRF origin check), e.g. https://bi.example.com
    public_url: str | None = None

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
    def reports_dir(self) -> Path:
        return (self.content_dir or self.data_dir / "content") / "reports"

    @property
    def snapshots_path(self) -> Path:
        return self.data_dir / "snapshots.sqlite"

    @property
    def sessions_path(self) -> Path:
        return self.data_dir / "sessions.sqlite"

    @property
    def catalog_meta_path(self) -> Path:
        return self.data_dir / "catalog_meta.json"

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ
        dev = env.get("D2H_DEV_IDENTITIES") == "1"
        return cls(
            data_dir=Path(env.get("D2H_DATA_DIR", _REPO_ROOT / "data")),
            sources_file=Path(env.get("D2H_SOURCES_FILE", _REPO_ROOT / "config/sources.yaml")),
            content_dir=Path(env.get("D2H_CONTENT_DIR", _REPO_ROOT / "content")),
            max_upload_mb=int(env.get("D2H_MAX_UPLOAD_MB", "500")),
            duckdb_memory_limit=env.get("D2H_DUCKDB_MEMORY", "2GB"),
            duckdb_threads=int(env.get("D2H_DUCKDB_THREADS", "4")),
            query_timeout_s=int(env.get("D2H_QUERY_TIMEOUT_S", "60")),
            theme_file=Path(env.get("D2H_THEME_FILE", _REPO_ROOT / "config/theme.yaml")),
            dev_identities_file=(
                Path(env.get("D2H_DEV_IDENTITIES_FILE", _REPO_ROOT / "config/dev_identities.yaml"))
                if dev else None
            ),
            viewer_cache_ttl_s=int(env.get("D2H_VIEWER_CACHE_TTL_S", "60")),
            viewer_cache_max_entries=int(env.get("D2H_VIEWER_CACHE_MAX", "1000")),
            echarts_url=env.get("D2H_ECHARTS_URL", ECHARTS_URL),
            auth_file=Path(env.get("D2H_AUTH_FILE", _REPO_ROOT / "config/auth.yaml")),
            users_file=Path(env.get("D2H_USERS_FILE", _REPO_ROOT / "config/users.yaml")),
            ai_file=Path(env.get("D2H_AI_FILE", _REPO_ROOT / "config/ai.yaml")),
            public_url=env.get("D2H_PUBLIC_URL") or None,
        )
