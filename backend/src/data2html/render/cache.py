"""Viewer cache: LRU with TTL. The key always includes the reader's full identity (security-rls
skill, invariant 2), the exact report and model content, the parameters and the cross-filters."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import threading
import time
from collections import OrderedDict

from pydantic import BaseModel

from data2html.sources.base import Identity


def cache_key(
    *, report: BaseModel, model: BaseModel, visual_id: str, identity: Identity,
    params: dict[str, object], cross: list[tuple[str, str]], computed: dict[str, str] | None = None,
) -> str:
    raw = json.dumps(
        {
            "report": report.model_dump(mode="json"),
            "model": model.model_dump(mode="json"),
            "visual": visual_id,
            "identity": dataclasses.asdict(identity),
            "params": params,
            "cross": sorted(cross),
            "computed": computed or {},  # an edited computed column changes the result
        },
        sort_keys=True, default=str, ensure_ascii=False,
    )
    return hashlib.sha256(raw.encode()).hexdigest()


class TTLCache[V]:
    def __init__(self, ttl_s: int, max_entries: int) -> None:
        self._ttl = ttl_s
        self._max = max_entries
        self._items: OrderedDict[str, tuple[float, V]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> V | None:
        with self._lock:
            hit = self._items.get(key)
            if hit is None:
                return None
            expires, value = hit
            if expires < time.monotonic():
                del self._items[key]
                return None
            self._items.move_to_end(key)
            return value

    def put(self, key: str, value: V) -> None:
        if self._ttl <= 0:
            return
        with self._lock:
            self._items[key] = (time.monotonic() + self._ttl, value)
            self._items.move_to_end(key)
            while len(self._items) > self._max:
                self._items.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
