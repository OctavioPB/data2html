"""Cancelación de trabajos de varias consultas (editor SQL, perfilado) por `query_id`.

`DataSource.cancel` interrumpe la consulta que esté corriendo; esto además marca el trabajo para que
no lance la siguiente (p. ej. el conteo tras la página, o la siguiente pasada del perfil), y permite
registrar interruptores propios (el DuckDB privado del perfilado de fuentes remotas).
"""

from __future__ import annotations

import re
import threading
from collections import OrderedDict
from collections.abc import Callable

from data2html.sources.errors import QueryInterrupted, SourceError

QUERY_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_MAX_REMEMBERED = 256

_lock = threading.Lock()
_cancelled: OrderedDict[str, None] = OrderedDict()
_hooks: dict[str, list[Callable[[], None]]] = {}


def check_id(query_id: str) -> str:
    if not QUERY_ID_RE.match(query_id):
        raise SourceError("query_id inválido")
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
            raise QueryInterrupted("consulta cancelada")


def on_cancel(query_id: str, hook: Callable[[], None]) -> Callable[[], None]:
    """Registra un interruptor mientras dura un trabajo. Devuelve la función que lo quita."""
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
