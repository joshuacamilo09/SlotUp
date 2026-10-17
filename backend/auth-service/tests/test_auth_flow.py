import time

import jwt
import pytest

from app.config import get_settings
from app.security import _read_key
from tests.conftest import (
    PASSWORD,
    bearer,
    full_login,
    get_user,
    new_email,
    stored_secret,
    totp_code,
)


# ------------------------------------------------------------------ registo
def test_register_ok_and_email_is_lowercased(client):
    email = new_email()
    r = client.post("/api/auth/register", json={"name": "Ana", "email": email.upper(), "password": PASSWORD})
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == email
    assert body["role"] == "USER"
    assert body["two_fa_enabled"] is False
    assert "password" not in str(body).lower().replace("two_fa", "")


def test_register_duplicate_email_is_409_even_with_different_case(client, registered):
    r = client.post("/api/auth/register", json={"name": "Outro", "email": registered.upper(), "password": PASSWORD})
    assert r.status_code == 409


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "A", "email": "a@slotup.pt", "password": PASSWORD},  # nome curto
        {"name": "Ana", "email": "nao-e-email", "password": PASSWORD},
        {"name": "Ana", "email": "a@slotup.pt", "password": "curta"},
    ],
)
def test_register_validation(client, payload):
    assert client.post("/api/auth/register", json=payload).status_code == 422


def test_password_is_stored_as_argon2_hash(registered):
    assert get_user(registered).password_hash.startswith("$argon2id$")


# ------------------------------------------------------------------ login passo 1
def test_wrong_password_and_unknown_email_give_the_same_error(client, registered):
    a = client.post("/api/auth/login", json={"email": registered, "password": "errada-errada-1"})
    b = client.post("/api/auth/login", json={"email": new_email(), "password": "errada-errada-1"})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_first_login_requires_2fa_setup(client, registered):
    r = client.post("/api/auth/login", json={"email": registered, "password": PASSWORD})
    assert r.status_code == 200
    assert r.json()["status"] == "MFA_SETUP_REQUIRED"
    # ainda não há token de acesso
    assert "access_token" not in r.json()


# ------------------------------------------------------------------ 2FA
def test_full_flow_setup_enable_then_login_with_code(client, registered):
    token, secret = full_login(client, registered)  # setup + enable
    assert client.get("/api/auth/me", headers=bearer(token)).json()["two_fa_enabled"] is True

    # novo login: agora pede o código. Usa o passo seguinte (+30 s) porque o atual já foi usado no enable.
    token2, _ = full_login(client, registered, secret=secret, offset=30)
    me = client.get("/api/auth/me", headers=bearer(token2))
    assert me.status_code == 200 and me.json()["email"] == registered


def test_login_after_2fa_enabled_returns_mfa_required(client, user_with_2fa):
    r = client.post("/api/auth/login", json={"email": user_with_2fa["email"], "password": PASSWORD})
    assert r.json()["status"] == "MFA_REQUIRED"


def test_totp_code_cannot_be_reused(client, user_with_2fa):
    secret, email = user_with_2fa["secret"], user_with_2fa["email"]
    pre = client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).json()["pre_auth_token"]
    code = totp_code(secret, 30)
    first = client.post("/api/auth/2fa/verify", json={"code": code}, headers=bearer(pre))
    assert first.status_code == 200
    pre2 = client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).json()["pre_auth_token"]
    replay = client.post("/api/auth/2fa/verify", json={"code": code}, headers=bearer(pre2))
    assert replay.status_code == 401


def test_the_code_used_to_enable_2fa_cannot_be_reused_to_login(client, registered):
    pre = client.post("/api/auth/login", json={"email": registered, "password": PASSWORD}).json()["pre_auth_token"]
    secret = client.post("/api/auth/2fa/setup", headers=bearer(pre)).json()["secret"]
    code = totp_code(secret)
    assert client.post("/api/auth/2fa/enable", json={"code": code}, headers=bearer(pre)).status_code == 200
    pre2 = client.post("/api/auth/login", json={"email": registered, "password": PASSWORD}).json()["pre_auth_token"]
    assert client.post("/api/auth/2fa/verify", json={"code": code}, headers=bearer(pre2)).status_code == 401


def test_wrong_code_is_rejected_and_code_format_is_validated(client, registered):
    pre = client.post("/api/auth/login", json={"email": registered, "password": PASSWORD}).json()["pre_auth_token"]
    client.post("/api/auth/2fa/setup", headers=bearer(pre))
    assert client.post("/api/auth/2fa/enable", json={"code": "000000"}, headers=bearer(pre)).status_code == 401
    assert client.post("/api/auth/2fa/enable", json={"code": "12ab"}, headers=bearer(pre)).status_code == 422


def test_setup_is_idempotent_until_confirmed(client, registered):
    pre = client.post("/api/auth/login", json={"email": registered, "password": PASSWORD}).json()["pre_auth_token"]
    a = client.post("/api/auth/2fa/setup", headers=bearer(pre)).json()
    b = client.post("/api/auth/2fa/setup", headers=bearer(pre)).json()
    assert a["secret"] == b["secret"]
    assert a["otpauth_uri"].startswith("otpauth://totp/SlotUp:")


def test_totp_secret_is_encrypted_at_rest(client, registered):
    pre = client.post("/api/auth/login", json={"email": registered, "password": PASSWORD}).json()["pre_auth_token"]
    secret = client.post("/api/auth/2fa/setup", headers=bearer(pre)).json()["secret"]
    blob = get_user(registered).totp_secret_encrypted
    assert secret.encode() not in blob
    assert stored_secret(registered) == secret


# ------------------------------------------------------------------ tokens
def test_pre_auth_token_cannot_be_used_as_access_token(client, registered):
    pre = client.post("/api/auth/login", json={"email": registered, "password": PASSWORD}).json()["pre_auth_token"]
    assert client.get("/api/auth/me", headers=bearer(pre)).status_code == 401


def test_access_token_cannot_be_used_on_2fa_endpoints(client, user_with_2fa):
    r = client.post("/api/auth/2fa/verify", json={"code": "123456"}, headers=bearer(user_with_2fa["token"]))
    assert r.status_code == 401


def test_verify_stage_token_cannot_call_setup(client, user_with_2fa):
    pre = client.post(
        "/api/auth/login", json={"email": user_with_2fa["email"], "password": PASSWORD}
    ).json()["pre_auth_token"]
    assert client.post("/api/auth/2fa/setup", headers=bearer(pre)).status_code == 401


def test_missing_garbage_and_expired_tokens_are_401(client, user_with_2fa):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers=bearer("lixo")).status_code == 401
    s = get_settings()
    expired = jwt.encode(
        {
            "iss": s.jwt_issuer, "aud": s.jwt_audience, "sub": str(get_user(user_with_2fa["email"]).id),
            "typ": "access", "iat": int(time.time()) - 7200, "exp": int(time.time()) - 3600,
        },
        _read_key(s.jwt_private_key_file),
        algorithm="RS256",
    )
    assert client.get("/api/auth/me", headers=bearer(expired)).status_code == 401


def test_access_token_claims(user_with_2fa):
    s = get_settings()
    claims = jwt.decode(
        user_with_2fa["token"], _read_key(s.jwt_public_key_file),
        algorithms=["RS256"], audience=s.jwt_audience, issuer=s.jwt_issuer,
    )
    assert claims["typ"] == "access"
    assert claims["role"] == "USER"
    assert claims["email"] == user_with_2fa["email"]
    assert claims["exp"] > claims["iat"]


# ------------------------------------------------------------------ bloqueio de conta
def test_account_locks_after_failed_passwords_even_for_the_right_password(client, registered):
    for _ in range(get_settings().max_failed_attempts):
        assert client.post("/api/auth/login", json={"email": registered, "password": "errada-errada-1"}).status_code == 401
    r = client.post("/api/auth/login", json={"email": registered, "password": PASSWORD})
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) > 0


def test_wrong_totp_codes_also_lock_the_account(client, user_with_2fa):
    email = user_with_2fa["email"]
    pre = client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).json()["pre_auth_token"]
    for _ in range(get_settings().max_failed_attempts):
        assert client.post("/api/auth/2fa/verify", json={"code": "000000"}, headers=bearer(pre)).status_code == 401
    # mesmo com o código certo, a conta está bloqueada
    right = client.post("/api/auth/2fa/verify", json={"code": totp_code(user_with_2fa["secret"], 30)}, headers=bearer(pre))
    assert right.status_code == 429


def test_successful_login_resets_the_failure_counter(client, user_with_2fa):
    email = user_with_2fa["email"]
    client.post("/api/auth/login", json={"email": email, "password": "errada-errada-1"})
    assert get_user(email).failed_login_attempts == 1
    full_login(client, email, secret=user_with_2fa["secret"], offset=30)
    assert get_user(email).failed_login_attempts == 0
