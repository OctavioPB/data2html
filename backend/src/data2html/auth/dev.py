"""Development identities: try the studio and the viewer's RLS as several people without passwords.

Enabled only with `D2H_DEV_IDENTITIES=1`, and only for clients in `Settings.dev_hosts` (localhost);
the production image refuses to start with it (ADR 0010). Pick one at `/login`; from then on it comes from
the server-side session, never from a header, query parameter or body.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, ConfigDict, Field

from data2html.auth.config import DB_USER
from data2html.sources.base import Identity


class DevIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    email: str
    groups: tuple[str, ...] = ()
    author: bool = False
    db_user: Annotated[str, Field(pattern=DB_USER.pattern)] | None = None


class DevIdentitiesFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    identities: dict[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,62}$")], DevIdentity]


@lru_cache
def load_dev_identities(path: Path) -> dict[str, Identity]:
    if not path.exists():
        return {}
    data = DevIdentitiesFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
    return {
        uid: Identity(user_id=uid, email=i.email, provider="dev", groups=i.groups, author=i.author,
                      db_user=i.db_user)
        for uid, i in data.identities.items()
    }
