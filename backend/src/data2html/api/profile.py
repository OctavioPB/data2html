"""EDA profile of a table, with an in-memory cache.

Local tables (Parquet from CSV) never change once created: their profile holds until the computed
columns change or `refresh` is requested. Remote ones expire after `REMOTE_TTL_S`. Profiles carry
localized warning messages, so the request language is part of the cache key.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Annotated

from fastapi import APIRouter, Query

from data2html import cancel
from data2html.api.deps import MetaDep, SettingsDep, SourceDep
from data2html.i18n import get_lang
from data2html.profiling.models import TableProfile
from data2html.profiling.profiler import LOCAL_KINDS, profile_table

router = APIRouter(prefix="/api/profile", tags=["profile"])

REMOTE_TTL_S = 600
_MAX_ENTRIES = 32


class _Cache:
    def __init__(self) -> None:
        self._items: OrderedDict[tuple[str, ...], tuple[float, TableProfile]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: tuple[str, ...], ttl_s: float | None) -> TableProfile | None:
        with self._lock:
            hit = self._items.get(key)
            if hit is None or (ttl_s is not None and time.monotonic() - hit[0] > ttl_s):
                return None
            self._items.move_to_end(key)
            return hit[1]

    def put(self, key: tuple[str, ...], value: TableProfile) -> None:
        with self._lock:
            self._items[key] = (time.monotonic(), value)
            self._items.move_to_end(key)
            while len(self._items) > _MAX_ENTRIES:
                self._items.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


cache = _Cache()


@router.get("/{source}/{table}")
def get_profile(
    table: str,
    src: SourceDep,
    meta: MetaDep,
    settings: SettingsDep,
    refresh: bool = False,
    query_id: Annotated[str | None, Query(pattern=cancel.QUERY_ID_RE.pattern)] = None,
) -> TableProfile:
    """Optional `query_id`: the studio sends it so it can cancel with POST /api/cancel/{query_id}."""
    computed = "|".join(f"{c.name}={c.expr}" for c in meta.get(src.id, table).computed)
    key = (str(settings.data_dir), src.id, table, computed, get_lang())
    ttl = None if src.kind in LOCAL_KINDS else REMOTE_TTL_S
    if not refresh and (hit := cache.get(key, ttl)) is not None:
        return hit
    profile = profile_table(src, meta, table, settings, query_id=query_id)
    cache.put(key, profile)
    return profile
