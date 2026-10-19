import base64
import json

import pytest

from tests.conftest import bearer, make_token


def test_valid_user_token_is_accepted(client):
    r = client.get("/api/reservas/me", headers=bearer(make_token()))
    assert r.status_code == 200
    assert r.json()["email"] == "ana@slotup.pt" and r.json()["role"] == "USER"


def test_no_token_is_401(client):
    assert client.get("/api/reservas/me").status_code == 401


@pytest.mark.parametrize(
    "kwargs",
    [
        {"typ": "pre_auth"},  # 2FA incompleto
        {"exp_in": -10},  # expirado
        {"signer": "attacker"},  # assinado por outra chave
        {"aud": "outro-sistema"},
        {"iss": "outro-emissor"},
        {"alg": "HS256"},  # confusão de algoritmo
    ],
    ids=["pre_auth", "expirado", "assinatura_falsa", "audiencia", "emissor", "hs256_com_chave_publica"],
)
def test_bad_tokens_are_rejected(client, kwargs):
    token = make_token(**kwargs)
    assert client.get("/api/reservas/me", headers=bearer(token)).status_code == 401


def test_alg_none_is_rejected(client):
    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()

    token = f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64({'sub': 'x', 'typ': 'access', 'role': 'ADMIN'})}."
    assert client.get("/api/reservas/me", headers=bearer(token)).status_code == 401


def test_roles(client):
    assert client.get("/api/reservas/admin/check", headers=bearer(make_token(role="USER"))).status_code == 403
    r = client.get("/api/reservas/admin/check", headers=bearer(make_token(role="ADMIN")))
    assert r.status_code == 200 and r.json()["ok"] is True


def test_health(client):
    assert client.get("/health/live").json() == {"status": "ok"}
    assert client.get("/health/ready").json() == {"status": "ok"}
    assert client.get("/whoami").json()["service"] == "booking-service"
