"""Cancellation of multi-query jobs (SQL editor, profiling) by `query_id`.

`DataSource.cancel` interrupts the query that is running; this additionally flags the job so it does
not start the next one (e.g. the count after the page, or the next profiling pass), and lets callers
register their own interrupters (the private DuckDB used to profile remote sources).
"""

from __future__ import annotations

import re
import threading
from collections import OrderedDict
from collections.abc import Callable

from data2html.i18n import tr
from data2html.sources.errors import QueryInterrupted, SourceError

QUERY_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_MAX_REMEMBERED = 256

_lock = threading.Lock()
_cancelled: OrderedDict[str, None] = OrderedDict()
_hooks: dict[str, list[Callable[[], None]]] = {}


def check_id(query_id: str) -> str:
    if not QUERY_ID_RE.match(query_id):
        raise SourceError(tr("invalid query_id"))
    return query_id


def request(query_id: str) -> None:
    with _lock:
        _cancelled[query_id] = None
        while len(_cancelled) > _MAX_REMEMBERED:
            _cancelled.popitem(last=False)
        hooks = list(_hooks.get(query_id, []))
    for hook in hooks:
        hook()


def raise_if_cancelled(query_id: str | None) -> None:
    if query_id is None:
        return
    with _lock:
        if query_id in _cancelled:
            raise QueryInterrupted(tr("query cancelled"))


def on_cancel(query_id: str, hook: Callable[[], None]) -> Callable[[], None]:
    """Register an interrupter for the duration of a job. Returns the function that removes it."""
    with _lock:
        _hooks.setdefault(query_id, []).append(hook)

    def remove() -> None:
        with _lock:
            hooks = _hooks.get(query_id, [])
            if hook in hooks:
                hooks.remove(hook)
            if not hooks:
                _hooks.pop(query_id, None)

    return remove
