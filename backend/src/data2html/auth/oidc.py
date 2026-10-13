"""OpenID Connect sign-in (authorization code + PKCE S256), e.g. Microsoft Entra ID (ADR 0010).

Flow: `/login/oidc` stores {nonce, PKCE verifier, next} under a random single-use `state` and redirects
to the provider; `/auth/callback` checks the state, exchanges the code (client secret from the
environment), and validates the `id_token`: RS256 only, signature against the provider's JWKS, `iss`,
`aud`, `exp`/`nbf`/`iat` (60 s leeway) and the `nonce`. Only then is an `Identity` built from its claims.
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import threading
import time
from typing import Any
from urllib.parse import urlencode

import httpx
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet

from data2html.auth.config import OidcConfig
from data2html.sources.base import Identity

METADATA_TTL_S = 3600
ALGORITHMS = ["RS256"]

# Tests replace this with an httpx.MockTransport that plays the provider
TRANSPORT: httpx.BaseTransport | None = None


class OidcError(Exception):
    """Sign-in failed. The message is for logs; users get a generic message."""


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    return verifier, _b64url(hashlib.sha256(verifier.encode()).digest())


class OidcClient:
    def __init__(self, cfg: OidcConfig) -> None:
        self.cfg = cfg
        self._lock = threading.Lock()
        self._metadata: dict[str, Any] | None = None
        self._metadata_at = 0.0
        self._jwks: KeySet | None = None

    def _http(self) -> httpx.Client:
        return httpx.Client(transport=TRANSPORT, timeout=10, follow_redirects=False)

    def metadata(self) -> dict[str, Any]:
        with self._lock:
            if self._metadata is None or time.monotonic() - self._metadata_at > METADATA_TTL_S:
                with self._http() as c:
                    r = c.get(f"{self.cfg.issuer}/.well-known/openid-configuration")
                    r.raise_for_status()
                    meta: dict[str, Any] = r.json()
                if meta.get("issuer", "").rstrip("/") != self.cfg.issuer:
                    raise OidcError("discovery issuer does not match the configured issuer")
                self._metadata, self._metadata_at, self._jwks = meta, time.monotonic(), None
            return self._metadata

    def _keys(self, refresh: bool = False) -> KeySet:
        with self._lock:
            jwks = self._jwks
        if jwks is None or refresh:
            with self._http() as c:
                r = c.get(self.metadata()["jwks_uri"])
                r.raise_for_status()
                jwks = KeySet.import_key_set(r.json())
            with self._lock:
                self._jwks = jwks
        return jwks

    def authorize_url(self, redirect_uri: str, state: str, nonce: str, challenge: str) -> str:
        query = {
            "response_type": "code", "client_id": self.cfg.client_id, "redirect_uri": redirect_uri,
            "scope": " ".join(self.cfg.scopes), "state": state, "nonce": nonce,
            "code_challenge": challenge, "code_challenge_method": "S256", "response_mode": "query",
        }
        return f"{self.metadata()['authorization_endpoint']}?{urlencode(query)}"

    def exchange(self, code: str, verifier: str, redirect_uri: str) -> str:
        """Authorization code → `id_token`."""
        secret = os.environ.get(self.cfg.client_secret_env)
        if not secret:
            raise OidcError(f"environment variable {self.cfg.client_secret_env} is not set")
        with self._http() as c:
            r = c.post(self.metadata()["token_endpoint"], data={
                "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
                "client_id": self.cfg.client_id, "client_secret": secret, "code_verifier": verifier,
            })
        if r.status_code != 200:
            raise OidcError(f"token endpoint answered {r.status_code}")
        token = r.json().get("id_token")
        if not isinstance(token, str):
            raise OidcError("no id_token in the token response")
        return token

    def validate(self, id_token: str, nonce: str) -> dict[str, Any]:
        def decode(keys: KeySet) -> jwt.Token:
            return jwt.decode(id_token, keys, algorithms=ALGORITHMS)

        try:
            try:
                token = decode(self._keys())
            except JoseError:
                token = decode(self._keys(refresh=True))  # the provider rotated its keys
            registry = jwt.JWTClaimsRegistry(
                leeway=60,
                iss={"essential": True, "value": self.cfg.issuer},
                aud={"essential": True, "value": self.cfg.client_id},
                exp={"essential": True},
                nonce={"essential": True, "value": nonce},
            )
            registry.validate(token.claims)
        except JoseError as e:
            raise OidcError(f"invalid id_token: {e}") from e
        return token.claims

    def identity(self, claims: dict[str, Any]) -> Identity:
        cfg = self.cfg
        user_id = claims.get(cfg.user_id_claim) or claims.get("sub")
        if not isinstance(user_id, str) or not user_id:
            raise OidcError(f"claim {cfg.user_id_claim} missing")
        raw_groups = claims.get(cfg.groups_claim) or []
        groups = tuple(g for g in raw_groups if isinstance(g, str)) if isinstance(raw_groups, list) else ()
        email = claims.get(cfg.email_claim) or claims.get("email") or ""
        db_user = cfg.db_user.apply(claims.get(cfg.db_user.claim)) if cfg.db_user else None
        return Identity(
            user_id=user_id, email=email if isinstance(email, str) else "", provider="oidc", groups=groups,
            author=cfg.author_role is not None and cfg.author_role in groups, db_user=db_user,
        )


_clients: dict[OidcConfig, OidcClient] = {}
_clients_lock = threading.Lock()


def get_client(cfg: OidcConfig) -> OidcClient:
    with _clients_lock:
        if cfg not in _clients:
            _clients[cfg] = OidcClient(cfg)
        return _clients[cfg]
