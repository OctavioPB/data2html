"""Remove server paths from messages before they reach a browser (DuckDB errors quote files:
`No files found that match the pattern "C:\\srv\\d2h\\data\\csv\\x.parquet"`).

Known directories become short markers that keep the useful tail (`<data>/csv/x.parquet`); any other
absolute path becomes `<path>`. Dates (`13/04/2026`) and URL paths (`/r/report`) are left alone.
"""

from __future__ import annotations

import re
import tempfile
from collections.abc import Iterable
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_WINDOWS_PATH = re.compile(r"\b[A-Za-z]:[\\/][^\s'\"<>|]*")
# Two or more directories, not glued to a word, digit or another path (keeps 13/04/2026 and /r/x)
_POSIX_PATH = re.compile(r"(?<![\w.:/\\>])/(?:[\w.-]+/){2,}[\w.-]*")
_MARKER_TAIL = re.compile(r"(<(?:data|content|app|tmp|home)>)([^\s'\"<>|]*)")

_extra: list[tuple[str, str]] = []


def register(directory: Path, marker: str) -> None:
    """Add a server directory (data_dir, content_dir…) to be shown as `marker`."""
    entry = (str(directory.resolve()), marker)
    if entry not in _extra:
        _extra.append(entry)


def _prefixes() -> Iterable[tuple[str, str]]:
    known = [*_extra, (str(_REPO_ROOT), "<app>"), (tempfile.gettempdir(), "<tmp>"),
             (str(Path.home()), "<home>")]
    # longest first: data_dir usually lives inside the repo or the home directory
    for path, marker in sorted(known, key=lambda x: -len(x[0])):
        for variant in {path, path.replace("\\", "/"), path.replace("/", "\\")}:
            yield variant, marker


def scrub(message: str) -> str:
    for prefix, marker in _prefixes():
        if prefix and prefix in message:
            message = message.replace(prefix, marker)
    # `<data>\csv\x.parquet` → `<data>/csv/x.parquet` (only the tail of a marker; other text is untouched)
    message = _MARKER_TAIL.sub(lambda m: m.group(1) + m.group(2).replace("\\", "/"), message)
    message = _WINDOWS_PATH.sub("<path>", message)
    return _POSIX_PATH.sub("<path>", message)
