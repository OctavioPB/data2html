"""Errores comunes a todas las fuentes. La API los traduce a códigos HTTP (api/deps.py)."""

from __future__ import annotations

import threading
from collections.abc import Callable


class SourceError(ValueError):
    """Error atribuible a la petición (→ 4xx)."""


class NotFound(SourceError):
    pass


class Conflict(SourceError):
    pass


class TooLarge(SourceError):
    pass


class SourceUnavailable(RuntimeError):
    """La fuente no responde (→ 503). El mensaje nunca incluye la cadena de conexión."""


class QueryInterrupted(RuntimeError):
    pass


class Deadline:
    """Tiempo límite de una consulta: interrumpe al vencer y recuerda si fue eso o una cancelación."""

    def __init__(self, timeout_s: int, interrupt: Callable[[], None]) -> None:
        self.timeout_s = timeout_s
        self._expired = threading.Event()

        def fire() -> None:
            self._expired.set()
            interrupt()

        self._timer = threading.Timer(timeout_s, fire)

    def __enter__(self) -> Deadline:
        self._timer.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._timer.cancel()

    def interrupted(self) -> QueryInterrupted:
        if self._expired.is_set():
            return QueryInterrupted(f"la consulta superó el tiempo límite de {self.timeout_s} s")
        return QueryInterrupted("consulta cancelada")
