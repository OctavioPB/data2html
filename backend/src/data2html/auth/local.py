"""Local users (`config/users.yaml`, ignored by git): username/password with scrypt hashes.

    python -m data2html.auth add-user ana --email ana@example.com --groups Norte,Sur --author
    python -m data2html.auth add-user ana ... --password-stdin < secret.txt

The file holds hashes, never passwords. Users are re-read on every request (cached by mtime), so
removing one revokes their sessions at once.
"""

from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import hmac
import secrets
import sys
import time
from functools import lru_cache
from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, ConfigDict, Field

from data2html.auth.config import DB_USER
from data2html.sources.base import Identity

USER_ID = r"^[a-z][a-z0-9_.-]{0,62}$"
_N, _R, _P = 2**15, 8, 1  # scrypt cost: ~32 MB, tens of ms
_MAXMEM = 64 * 1024 * 1024


class LocalUser(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    email: str = ""
    groups: tuple[str, ...] = ()
    author: bool = False
    db_user: Annotated[str, Field(pattern=DB_USER.pattern)] | None = None
    password_hash: Annotated[str, Field(pattern=r"^scrypt\$\d+\$\d+\$\d+\$[A-Za-z0-9+/=]+\$[A-Za-z0-9+/=]+$")]


class UsersFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    users: dict[Annotated[str, Field(pattern=USER_ID)], LocalUser] = Field(default_factory=dict)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, maxmem=_MAXMEM, dklen=32)
    b64 = base64.b64encode
    return f"scrypt${_N}${_R}${_P}${b64(salt).decode()}${b64(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, digest = stored.split("$")
        expected = base64.b64decode(digest)
        got = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
                             maxmem=_MAXMEM, dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got, expected)


# Same cost as a real check, so an unknown user takes as long as a wrong password
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


@lru_cache
def _load(path: Path, mtime: float) -> UsersFile:
    return UsersFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


def load_users(path: Path | None) -> dict[str, LocalUser]:
    if path is None or not path.exists():
        return {}
    return _load(path, path.stat().st_mtime).users


def to_identity(user_id: str, u: LocalUser) -> Identity:
    return Identity(user_id=user_id, email=u.email, provider="local", groups=u.groups, author=u.author,
                    db_user=u.db_user)


def authenticate(path: Path | None, user_id: str, password: str) -> Identity | None:
    user = load_users(path).get(user_id)
    ok = verify_password(password, user.password_hash if user else _DUMMY_HASH)
    return to_identity(user_id, user) if user and ok else None


# ------------------------------------------------------------------ CLI


def _add_user(args: argparse.Namespace) -> int:
    path = Path(args.file)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None
    users = UsersFile.model_validate(data or {})
    if args.password_stdin:
        password = sys.stdin.readline().rstrip("\n")
    else:
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Repeat: "):
            print("passwords do not match", file=sys.stderr)
            return 1
    if len(password) < 12:
        print("use at least 12 characters", file=sys.stderr)
        return 1
    groups = tuple(g.strip() for g in (args.groups or "").split(",") if g.strip())
    users.users[args.user_id] = LocalUser(email=args.email or "", groups=groups, author=args.author,
                                          db_user=args.db_user, password_hash=hash_password(password))
    data = users.model_dump(mode="json", exclude_none=True)
    body = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Local users (data2html). Hashes only; this file is ignored by git.\n" + body,
                    encoding="utf-8", newline="\n")
    print(f"user {args.user_id} saved in {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    from data2html.settings import Settings

    default_file = Settings.from_env().users_file
    parser = argparse.ArgumentParser(prog="python -m data2html.auth")
    sub = parser.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add-user", help="add or replace a local user")
    add.add_argument("user_id")
    add.add_argument("--email")
    add.add_argument("--groups", help="comma-separated (report access and RLS)")
    add.add_argument("--author", action="store_true", help="may use the studio")
    add.add_argument("--db-user", help="Teradata PROXYUSER")
    add.add_argument("--password-stdin", action="store_true")
    add.add_argument("--file", default=str(default_file))
    tok = sub.add_parser("token", help="personal access tokens of local users (ADR 0014)")
    tsub = tok.add_subparsers(dest="action", required=True)
    create = tsub.add_parser("create", help="new token for a local user; printed once")
    create.add_argument("user_id")
    create.add_argument("--name", default="")
    create.add_argument("--days", type=int, default=30)
    create.add_argument("--file", default=str(default_file))
    lst = tsub.add_parser("list", help="active tokens of a local user")
    lst.add_argument("user_id")
    rev = tsub.add_parser("revoke", help="revoke a token by id (any user)")
    rev.add_argument("token_id")
    args = parser.parse_args(argv)
    if args.cmd == "token":
        return _token(args)
    return _add_user(args)


def _token(args: argparse.Namespace) -> int:
    from data2html.auth.tokens import get_tokens
    from data2html.settings import Settings

    store = get_tokens(Settings.from_env().sessions_path)
    if args.action == "revoke":
        found = store.revoke(args.token_id)
        print(f"token {args.token_id} revoked" if found else f"unknown token {args.token_id}",
              file=sys.stdout if found else sys.stderr)
        return 0 if found else 1
    if args.action == "list":
        for t in store.list("local", args.user_id):
            print(f"{t.id}  {t.name}  expires {time.strftime('%Y-%m-%d', time.gmtime(t.expires))}")
        return 0
    user = load_users(Path(args.file)).get(args.user_id)
    if user is None:
        print(f"unknown local user {args.user_id}", file=sys.stderr)
        return 1
    try:
        token_id, secret = store.create(to_identity(args.user_id, user), args.name, args.days)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(f"token {token_id} for {args.user_id} (copy it now, it is not stored):\n{secret}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
