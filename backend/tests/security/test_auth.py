"""Authentication (ADR 0010): local passwords, OIDC (Entra-style claims) against a mock provider, the
studio's author role, CSRF origin check, server-side revocation."""

import base64
import hashlib
import io
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient
from joserfc import jwt
from joserfc.jwk import RSAKey

from data2html.api.main import app, get_settings
from data2html.auth import oidc, session
from data2html.auth.config import DbUserRule
from data2html.auth.local import hash_password, verify_password
from data2html.auth.local import main as local_cli
from data2html.auth.sessions import SessionStore
from data2html.settings import Settings
from data2html.sources.base import Identity

pytestmark = pytest.mark.real_auth

ISSUER = "https://login.example.com/tenant-1/v2.0"
CLIENT_ID = "d2h-client"
PASSWORD = "correct horse battery"  # noqa: S105 - test fixture
PASSWORD_HASH = hash_password(PASSWORD)  # once: scrypt is slow on purpose


@pytest.fixture
def settings(tmp_path, monkeypatch):
    users = {
        "users": {
            "ana": {"email": "ana@example.com", "groups": ["Norte"], "author": True, "db_user": "ANA",
                    "password_hash": PASSWORD_HASH},
            "beto": {"email": "beto@example.com", "groups": ["Sur"],
                     "password_hash": PASSWORD_HASH},
        }
    }
    (tmp_path / "users.yaml").write_text(yaml.safe_dump(users), encoding="utf-8")
    auth = {"local": True, "oidc": {"issuer": ISSUER, "client_id": CLIENT_ID,
                                    "client_secret_env": "D2H_TEST_OIDC_SECRET"}}
    (tmp_path / "auth.yaml").write_text(yaml.safe_dump(auth), encoding="utf-8")
    monkeypatch.setenv("D2H_TEST_OIDC_SECRET", "s3cret")
    s = Settings(data_dir=tmp_path, users_file=tmp_path / "users.yaml", auth_file=tmp_path / "auth.yaml")
    app.dependency_overrides[get_settings] = lambda: s
    yield s
    app.dependency_overrides.clear()


def sign_in(user: str, password: str = PASSWORD, **kw) -> tuple[TestClient, httpx.Response]:
    c = TestClient(app)
    form = {"user_id": user, "password": password, "next": "/"}
    r = c.post("/login", data=form, follow_redirects=False, **kw)
    return c, r


# ------------------------------------------------------------------ local sign-in and the author role


def test_studio_requires_an_author_session(settings):
    anon = TestClient(app)
    assert anon.get("/api/catalog").status_code == 401
    assert anon.get("/api/compat").status_code == 401
    assert anon.get("/api/me").status_code == 401
    reader, r = sign_in("beto")
    assert r.status_code == 303
    assert reader.get("/api/catalog").status_code == 403  # signed in, but not the author
    assert reader.get("/api/me").json()["author"] is False
    author, _ = sign_in("ana")
    assert author.get("/api/catalog").status_code == 200
    me = author.get("/api/me").json()
    assert me == {"user_id": "ana", "email": "ana@example.com", "provider": "local", "groups": ["Norte"],
                  "author": True}
    assert anon.get("/health").status_code == 200


def test_session_cookie_flags(settings):
    _, r = sign_in("ana")
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "path=/" in cookie
    assert "ana" not in r.headers["set-cookie"]  # only a random id travels


def test_wrong_password_and_unknown_user(settings):
    for user, pw in [("ana", "nope"), ("nadie", PASSWORD), ("ANA", "x" * 20)]:
        c, r = sign_in(user, pw)
        assert r.status_code == 401 and session.COOKIE not in r.cookies
        assert c.get("/api/me").status_code == 401


def test_login_throttle_is_shared_between_workers(settings):
    for _ in range(5):
        assert sign_in("ana", "wrong")[1].status_code == 401
    assert sign_in("ana")[1].status_code == 429  # even the right password, for a while
    # another worker process opens its own connection to the same database: still blocked
    from data2html.auth.sessions import SessionStore

    other = SessionStore(settings.sessions_path)
    assert other.failures(("user:ana",), 900) == 5
    raw = settings.sessions_path.read_bytes()
    assert b"user:ana" not in raw  # keys are hashed at rest


def test_logout_revokes_the_session_server_side(settings):
    c, _ = sign_in("ana")
    stolen = c.cookies.get(session.COOKIE)
    assert c.post("/logout", follow_redirects=False).status_code == 303
    replay = TestClient(app)
    replay.cookies.set(session.COOKIE, stolen)
    assert replay.get("/api/me").status_code == 401


def test_removing_a_user_revokes_access(settings):
    c, _ = sign_in("ana")
    data = yaml.safe_load(settings.users_file.read_text(encoding="utf-8"))
    del data["users"]["ana"]
    time.sleep(0.05)
    settings.users_file.write_text(yaml.safe_dump(data), encoding="utf-8")
    assert c.get("/api/me").status_code == 401


def test_cross_site_requests_are_refused(settings):
    c, _ = sign_in("ana")
    body = {"name": "x", "source": "csv", "table": "t", "dimensions": {}, "measures": {}}
    def check(origin):
        return c.post("/api/semantic/check", json=body, headers={"Origin": origin}).status_code

    assert check("https://evil.example") == 403
    assert check("http://testserver") == 200
    # login CSRF: a foreign page cannot sign the browser in either
    _, r = sign_in("ana", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_next_cannot_leave_the_site(settings):
    c = TestClient(app)
    for evil in ["https://evil.example", "//evil.example", "/\\evil", "/api/sql"]:
        form = {"user_id": "ana", "password": PASSWORD, "next": evil}
        r = c.post("/login", data=form, follow_redirects=False)
        assert r.headers["location"] == "/"
    assert 'value="/"' in c.get("/login", params={"next": "https://evil.example"}).text


# ------------------------------------------------------------------ passwords, sessions, CLI


def test_password_hashing():
    h = hash_password("a long passphrase")
    assert h.startswith("scrypt$") and "a long passphrase" not in h
    assert verify_password("a long passphrase", h)
    assert not verify_password("a long passphrasE", h)
    assert not verify_password("x", "scrypt$broken")
    assert hash_password("same") != hash_password("same")  # salted


def test_session_store(tmp_path):
    store = SessionStore(tmp_path / "s.sqlite")
    who = Identity(user_id="u", email="u@x", provider="oidc", groups=("A",), author=True, db_user="U")
    sid = store.create(who, ttl_s=60, now=1000)
    assert store.get(sid, now=1001) == who
    assert store.get(sid, now=1061) is None  # expired
    assert store.get("guess") is None
    state = store.put_pending({"nonce": "n"})
    assert store.pop_pending(state) == {"nonce": "n"}
    assert store.pop_pending(state) is None  # single use
    raw = (tmp_path / "s.sqlite").read_bytes()
    assert sid.encode() not in raw  # only its hash is stored


def test_cli_add_user(tmp_path, monkeypatch):
    f = tmp_path / "users.yaml"
    monkeypatch.setattr("sys.stdin", io.StringIO("a-very-long-password\n"))
    assert local_cli(["add-user", "carla", "--email", "c@x", "--groups", "Norte, Sur", "--author",
                      "--db-user", "CARLA", "--password-stdin", "--file", str(f)]) == 0
    data = yaml.safe_load(f.read_text(encoding="utf-8"))["users"]["carla"]
    assert data["groups"] == ["Norte", "Sur"] and data["author"] is True and data["db_user"] == "CARLA"
    assert verify_password("a-very-long-password", data["password_hash"])
    monkeypatch.setattr("sys.stdin", io.StringIO("short\n"))
    assert local_cli(["add-user", "dan", "--password-stdin", "--file", str(f)]) == 1


@pytest.mark.parametrize(("rule", "value", "expected"), [
    (DbUserRule(), "ana.perez@corp.com", None),            # '.' is not valid in a Teradata user
    (DbUserRule(), "aperez@corp.com", "APEREZ"),
    (DbUserRule(transform="none"), "APEREZ", "APEREZ"),
    (DbUserRule(transform="local_part"), "x'; DROP USER y;--@corp.com", None),
    (DbUserRule(), None, None),
])
def test_db_user_rule(rule, value, expected):
    assert rule.apply(value) == expected


# ------------------------------------------------------------------ OIDC against a mock provider


class FakeIdP:
    def __init__(self):
        self.key = RSAKey.generate_key(2048, parameters={"kid": "k1", "use": "sig"})
        self.challenges: dict[str, str] = {}
        self.claims: dict = {}
        self.sign_with = self.key
        self.alg = "RS256"
        self.last_nonce = ""

    def authorize(self, url: str) -> tuple[str, str]:
        q = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
        assert q["code_challenge_method"] == "S256" and q["response_type"] == "code"
        assert q["client_id"] == CLIENT_ID and "openid" in q["scope"].split()
        code = "code-" + q["state"][:8]
        self.challenges[code] = q["code_challenge"]
        self.last_nonce = q["nonce"]
        return q["state"], code

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == f"{ISSUER}/.well-known/openid-configuration":
            return httpx.Response(200, json={
                "issuer": ISSUER, "authorization_endpoint": f"{ISSUER}/authorize",
                "token_endpoint": f"{ISSUER}/token", "jwks_uri": f"{ISSUER}/keys"})
        if url == f"{ISSUER}/keys":
            return httpx.Response(200, json={"keys": [self.key.as_dict(private=False)]})
        if url == f"{ISSUER}/token":
            form = parse_qs(request.content.decode())
            code, verifier = form["code"][0], form["code_verifier"][0]
            sha = hashlib.sha256(verifier.encode()).digest()
            digest = base64.urlsafe_b64encode(sha).rstrip(b"=").decode()
            if form["client_secret"][0] != "s3cret" or self.challenges.get(code) != digest:
                return httpx.Response(400, json={"error": "invalid_grant"})
            now = int(time.time())
            claims = {"iss": ISSUER, "aud": CLIENT_ID, "iat": now, "nbf": now, "exp": now + 3600,
                      "nonce": self.last_nonce, "sub": "pairwise-sub", "oid": "oid-123",
                      "preferred_username": "aperez@corp.com", "roles": ["Norte", "data2html.author"]}
            claims.update(self.claims)
            header = {"alg": self.alg, "kid": "k1"}
            token = jwt.encode(header, claims, self.sign_with, algorithms=[self.alg])
            return httpx.Response(200, json={"id_token": token, "access_token": "x", "token_type": "Bearer"})
        return httpx.Response(404)


@pytest.fixture
def idp(settings, monkeypatch):
    fake = FakeIdP()
    monkeypatch.setattr(oidc, "TRANSPORT", httpx.MockTransport(fake.handler))
    oidc._clients.clear()
    yield fake
    oidc._clients.clear()


def oidc_sign_in(idp: FakeIdP, next_url: str = "/r/regional") -> tuple[TestClient, httpx.Response]:
    c = TestClient(app)
    r = c.get("/login/oidc", params={"next": next_url}, follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].startswith(f"{ISSUER}/authorize?")
    q = parse_qs(urlsplit(r.headers["location"]).query)
    assert q["redirect_uri"] == ["http://testserver/auth/callback"]
    state, code = idp.authorize(r.headers["location"])
    return c, c.get("/auth/callback", params={"state": state, "code": code}, follow_redirects=False)


def test_oidc_sign_in_builds_the_identity_from_claims(idp):
    c, r = oidc_sign_in(idp)
    assert r.status_code == 200 and 'content="0;url=/r/regional"' in r.text
    me = c.get("/api/me").json()
    assert me == {"user_id": "oid-123", "email": "aperez@corp.com", "provider": "oidc",
                  "groups": ["Norte", "data2html.author"], "author": True}
    assert c.get("/api/catalog").status_code == 200


def test_oidc_reader_without_author_role(idp):
    idp.claims = {"roles": ["Sur"]}
    c, r = oidc_sign_in(idp)
    assert r.status_code == 200
    assert c.get("/api/catalog").status_code == 403


@pytest.mark.parametrize("bad", [
    {"aud": "someone-else"},
    {"iss": "https://login.example.com/other/v2.0"},
    {"exp": 1000, "iat": 900, "nbf": 900},
    {"nonce": "replayed"},
])
def test_oidc_rejects_invalid_tokens(idp, bad):
    idp.claims = bad
    c, r = oidc_sign_in(idp)
    assert r.status_code == 401 and session.COOKIE not in r.cookies
    assert c.get("/api/me").status_code == 401


def test_oidc_rejects_tokens_signed_by_another_key(idp):
    idp.sign_with = RSAKey.generate_key(2048, parameters={"kid": "k1"})
    _, r = oidc_sign_in(idp)
    assert r.status_code == 401


def test_oidc_state_is_single_use_and_required(idp):
    c = TestClient(app)
    r = c.get("/login/oidc", follow_redirects=False)
    state, code = idp.authorize(r.headers["location"])
    assert c.get("/auth/callback", params={"state": "forged", "code": code}).status_code == 400
    assert c.get("/auth/callback", params={"state": state, "code": code}).status_code == 200
    assert c.get("/auth/callback", params={"state": state, "code": code}).status_code == 400  # replay


def test_oidc_provider_error_and_missing_secret(idp, monkeypatch):
    c = TestClient(app)
    r = c.get("/login/oidc", follow_redirects=False)
    state, _ = idp.authorize(r.headers["location"])
    assert c.get("/auth/callback", params={"state": state, "error": "access_denied"}).status_code == 401
    monkeypatch.delenv("D2H_TEST_OIDC_SECRET")
    _, r = oidc_sign_in(idp)
    assert r.status_code == 401


def test_pages_keep_origin_on_our_own_posts(settings):
    # `no-referrer` makes browsers send `Origin: null` on form POSTs, which check_origin refuses
    r = TestClient(app).get("/login")
    assert r.headers["referrer-policy"] == "same-origin"
    _, r = sign_in("ana", headers={"Origin": "null"})
    assert r.status_code == 403


def test_studio_dev_proxy_keeps_the_host_header():
    # Vite's proxy shorthand rewrites Host to the backend's, so Origin (localhost:5173) would never match
    from pathlib import Path

    config = (Path(__file__).resolve().parents[3] / "studio/vite.config.ts").read_text(encoding="utf-8")
    assert "changeOrigin: false" in config
