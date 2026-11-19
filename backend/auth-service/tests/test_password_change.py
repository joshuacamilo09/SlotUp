"""Validade do token e troca da palavra-passe.

* O token de acesso vale 30 min (ACCESS_TOKEN_MINUTES, dentro dos 30 a 60 pedidos).
* Quem tem sessão troca a palavra-passe com a atual + a nova.
* A troca (e a redefinição pelo admin) termina as outras sessões no auth: os tokens
  antigos deixam de valer. No booking, um token antigo vale até expirar.
"""
import jwt

from app.config import get_settings
from tests.conftest import PASSWORD, bearer, full_login, get_user, totp_code
from tests.test_roles_and_health import _make_admin

CHANGE = "/api/auth/password/change"
NEW_PASSWORD = "uma-password-nova-456"


def _change(client, token, current=PASSWORD, new=NEW_PASSWORD):
    return client.post(CHANGE, json={"current_password": current, "new_password": new}, headers=bearer(token))


def test_o_token_de_acesso_vale_30_minutos(user_with_2fa):
    claims = jwt.decode(user_with_2fa["token"], options={"verify_signature": False})
    assert claims["exp"] - claims["iat"] == 30 * 60
    assert 30 <= get_settings().access_token_minutes <= 60


def test_trocar_a_palavra_passe_e_continuar_com_o_token_novo(client, user_with_2fa):
    r = _change(client, user_with_2fa["token"])
    assert r.status_code == 200
    novo = r.json()["access_token"]
    assert client.get("/api/auth/me", headers=bearer(novo)).status_code == 200
    # a nova entra, a antiga já não
    assert client.post("/api/auth/login", json={"email": user_with_2fa["email"], "password": NEW_PASSWORD}).status_code == 200
    assert client.post("/api/auth/login", json={"email": user_with_2fa["email"], "password": PASSWORD}).status_code == 401


def test_a_troca_termina_as_outras_sessoes(client, user_with_2fa):
    email, secret = user_with_2fa["email"], user_with_2fa["secret"]
    outra_sessao, _ = full_login(client, email, secret=secret, offset=30)  # p. ex. noutro computador
    r = _change(client, user_with_2fa["token"])
    assert r.status_code == 200
    me = client.get("/api/auth/me", headers=bearer(outra_sessao))
    assert me.status_code == 401
    assert me.json()["detail"] == "Sessão terminada. Entre outra vez."
    assert client.get("/api/auth/me", headers=bearer(user_with_2fa["token"])).status_code == 401
    assert get_user(email).session_version == 1


def test_palavra_passe_atual_errada_da_401_e_conta_para_o_bloqueio(client, user_with_2fa):
    r = _change(client, user_with_2fa["token"], current="nao-e-esta-123")
    assert r.status_code == 401
    assert get_user(user_with_2fa["email"]).failed_login_attempts == 1
    for _ in range(4):
        _change(client, user_with_2fa["token"], current="nao-e-esta-123")
    assert _change(client, user_with_2fa["token"]).status_code == 429  # bloqueada: nem a certa passa


def test_a_nova_tem_de_ser_diferente_e_ter_10_caracteres(client, user_with_2fa):
    assert _change(client, user_with_2fa["token"], new=PASSWORD).status_code == 400
    assert _change(client, user_with_2fa["token"], new="curta").status_code == 422


def test_so_com_sessao_iniciada(client, registered):
    assert client.post(CHANGE, json={"current_password": PASSWORD, "new_password": NEW_PASSWORD}).status_code == 401
    pre = client.post("/api/auth/login", json={"email": registered, "password": PASSWORD}).json()["pre_auth_token"]
    assert _change(client, pre).status_code == 401  # o token temporário do 2FA não serve


def test_a_redefinicao_pelo_admin_tambem_termina_as_sessoes(client, user_with_2fa):
    _, admin_token, _ = _make_admin(client)
    uid = get_user(user_with_2fa["email"]).id
    reset = client.post(f"/api/auth/users/{uid}/password/reset", headers=bearer(admin_token)).json()["token"]
    r = client.post("/api/auth/password/reset", json={"token": reset, "new_password": NEW_PASSWORD})
    assert r.status_code == 204
    assert client.get("/api/auth/me", headers=bearer(user_with_2fa["token"])).status_code == 401
    # e com a palavra-passe nova volta a entrar normalmente
    pre = client.post("/api/auth/login", json={"email": user_with_2fa["email"], "password": NEW_PASSWORD}).json()["pre_auth_token"]
    ok = client.post("/api/auth/2fa/verify", json={"code": totp_code(user_with_2fa["secret"], 30)}, headers=bearer(pre))
    assert ok.status_code == 200
    assert client.get("/api/auth/me", headers=bearer(ok.json()["access_token"])).status_code == 200