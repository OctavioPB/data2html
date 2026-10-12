"""Errores comunes a todas las fuentes. La API los traduce a códigos HTTP (api/deps.py)."""

from __future__ import annotations


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
