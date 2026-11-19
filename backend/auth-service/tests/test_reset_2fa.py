"""Reset do 2FA pelo admin, para quem perdeu a app autenticadora.

POST /api/auth/users/{id}/2fa/reset (só ADMIN). O utilizador volta a configurar o 2FA
no próximo login, com um segredo novo.
"""
from tests.conftest import PASSWORD, bearer, get_user, totp_code
from tests.test_roles_and_health import _make_admin


def _reset(client, admin_token, email):
    return client.post(f"/api/auth/users/{get_user(email).id}/2fa/reset", headers=bearer(admin_token))


def test_depois_do_reset_configura_um_2fa_novo(client, user_with_2fa):
    _, admin_token, _ = _make_admin(client)
    email, segredo_antigo = user_with_2fa["email"], user_with_2fa["secret"]
    assert _reset(client, admin_token, email).status_code == 204
    user = get_user(email)
    assert not user.two_fa_enabled and user.totp_secret_encrypted is None

    pre = client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).json()
    assert pre["status"] == "MFA_SETUP_REQUIRED"
    novo = client.post("/api/auth/2fa/setup", headers=bearer(pre["pre_auth_token"])).json()["secret"]
    assert novo != segredo_antigo
    # os códigos da app perdida já não servem; os da nova sim
    h = bearer(pre["pre_auth_token"])
    assert client.post("/api/auth/2fa/enable", json={"code": totp_code(segredo_antigo, 30)}, headers=h).status_code == 401
    assert client.post("/api/auth/2fa/enable", json={"code": totp_code(novo, 30)}, headers=h).status_code == 200


def test_o_reset_termina_as_sessoes_abertas(client, user_with_2fa):
    _, admin_token, _ = _make_admin(client)
    assert client.get("/api/auth/me", headers=bearer(user_with_2fa["token"])).status_code == 200
    _reset(client, admin_token, user_with_2fa["email"])
    assert client.get("/api/auth/me", headers=bearer(user_with_2fa["token"])).status_code == 401


def test_o_reset_desbloqueia_a_conta(client, user_with_2fa):
    _, admin_token, _ = _make_admin(client)
    email = user_with_2fa["email"]
    for _ in range(5):
        client.post("/api/auth/login", json={"email": email, "password": "errada-errada-1"})
    assert client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).status_code == 429
    _reset(client, admin_token, email)
    assert client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).status_code == 200


def test_o_admin_nao_repoe_o_proprio_2fa(client):
    admin_email, admin_token, _ = _make_admin(client)
    r = _reset(client, admin_token, admin_email)
    assert r.status_code == 400
    assert get_user(admin_email).two_fa_enabled


def test_so_o_admin_pode_repor(client, user_with_2fa, registered):
    assert _reset(client, user_with_2fa["token"], registered).status_code == 403
    assert client.post(f"/api/auth/users/{get_user(registered).id}/2fa/reset").status_code == 401


def test_utilizador_inexistente_da_404(client):
    _, admin_token, _ = _make_admin(client)
    r = client.post("/api/auth/users/00000000-0000-0000-0000-000000000000/2fa/reset", headers=bearer(admin_token))
    assert r.status_code == 404