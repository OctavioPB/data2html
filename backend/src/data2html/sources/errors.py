"""Errors shared by all sources. The API maps them to HTTP status codes (api/deps.py)."""

from __future__ import annotations

import threading
from collections.abc import Callable

from data2html.i18n import tr


class SourceError(ValueError):
    """Error attributable to the request (→ 4xx)."""


class NotFound(SourceError):
    pass


class Conflict(SourceError):
    pass


class TooLarge(SourceError):
    pass


class SourceUnavailable(RuntimeError):
    """The source does not respond (→ 503). The message never includes the connection string."""


class QueryInterrupted(RuntimeError):
    pass


class Deadline:
    """A query's time limit: interrupts when it expires and remembers whether that, or a cancel, happened."""

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
            msg = tr("the query exceeded the {seconds} s time limit", seconds=self.timeout_s)
            return QueryInterrupted(msg)
        return QueryInterrupted(tr("query cancelled"))
