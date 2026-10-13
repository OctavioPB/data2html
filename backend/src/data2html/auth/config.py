"""Authentication providers from `config/auth.yaml` (no secrets: only NAMES of environment variables).

Microsoft Entra ID is configured as a generic OIDC provider. Recommended there: App Roles (`roles` claim)
for both report access/RLS groups and the author role, because the `groups` claim carries opaque ids and
is dropped from the token for users in more than 200 groups (ADR 0010).
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

_ENV_NAME = r"^[A-Z_][A-Z0-9_]{0,63}$"
_CLAIM = r"^[A-Za-z_][A-Za-z0-9_.:/-]{0,127}$"
# Teradata user names: letters, digits, _ $ # (no quotes, no semicolons: it goes into a QUERY_BAND)
DB_USER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$#]{0,127}$")


class _Cfg(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DbUserRule(_Cfg):
    """How a token claim becomes the Teradata PROXYUSER. The result must match `DB_USER`, or the identity
    gets no Teradata data (it is never passed through unvalidated)."""

    claim: Annotated[str, Field(pattern=_CLAIM)] = "preferred_username"
    transform: Literal["none", "local_part", "upper", "local_part_upper"] = "local_part_upper"

    def apply(self, value: object) -> str | None:
        if not isinstance(value, str) or not value:
            return None
        if self.transform in ("local_part", "local_part_upper"):
            value = value.split("@", 1)[0]
        if self.transform in ("upper", "local_part_upper"):
            value = value.upper()
        return value if DB_USER.match(value) else None


class OidcConfig(_Cfg):
    label: str = Field(default="Microsoft", max_length=40, description="Text of the sign-in button")
    issuer: str = Field(description="e.g. https://login.microsoftonline.com/<tenant-id>/v2.0")
    client_id: Annotated[str, Field(min_length=1, max_length=200)]
    client_secret_env: Annotated[str, Field(pattern=_ENV_NAME)]
    scopes: tuple[str, ...] = ("openid", "profile", "email")
    user_id_claim: Annotated[str, Field(pattern=_CLAIM)] = "oid"  # Entra: stable object id; else "sub"
    email_claim: Annotated[str, Field(pattern=_CLAIM)] = "preferred_username"
    groups_claim: Annotated[str, Field(pattern=_CLAIM)] = "roles"
    author_role: str | None = Field(default="data2html.author", description="Value in groups_claim")
    db_user: DbUserRule | None = DbUserRule()

    @field_validator("issuer")
    @classmethod
    def _https(cls, v: str) -> str:
        local = v.startswith(("http://localhost", "http://127.0.0.1"))
        if not (v.startswith("https://") or local):
            raise ValueError("the OIDC issuer must use https")
        return v.rstrip("/")

    @field_validator("scopes")
    @classmethod
    def _openid(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        if "openid" not in v:
            raise ValueError("scopes must include 'openid'")
        return v


class AuthConfig(_Cfg):
    local: bool = True  # username/password from config/users.yaml
    oidc: OidcConfig | None = None
    session_hours: Annotated[int, Field(ge=1, le=24)] = 8
    trusted_origins: tuple[str, ...] = ()  # extra origins allowed to POST (besides the request's own)


@lru_cache
def _load(path: Path, mtime: float) -> AuthConfig:
    return AuthConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


def load_auth_config(path: Path | None) -> AuthConfig:
    if path is None or not path.exists():
        return AuthConfig()
    return _load(path, path.stat().st_mtime)
