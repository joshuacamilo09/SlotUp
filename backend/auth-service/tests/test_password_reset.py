"""Recuperação de palavra-passe: o admin gera o token e o utilizador redefine com ele."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.database import SessionLocal
from tests.conftest import PASSWORD, bearer, get_user, totp_code
from tests.test_roles_and_health import _make_admin

NEW_PASSWORD = "outra-password-segura-456"
RESET = "/api/auth/password/reset"


@pytest.fixture
def admin(client):
    _, token, _ = _make_admin(client)
    return bearer(token)


def ask_reset(client, admin_headers, email):
    return client.post(f"/api/auth/users/{get_user(email).id}/password/reset", headers=admin_headers)


def login_status(client, email, password):
    """Passo 1 do login: devolve o código HTTP e o status (MFA_REQUIRED / MFA_SETUP_REQUIRED)."""
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    return r.status_code, r.json().get("status")


def stored_hashes(email) -> list[str]:
    with SessionLocal() as db:
        return list(db.scalars(
            text("SELECT token_hash FROM password_reset_tokens WHERE user_id = :id"), {"id": get_user(email).id}
        ))


# --------------------------------------------------------------------------- o admin pede
def test_admin_gera_um_token_que_so_aparece_uma_vez(client, admin, registered):
    r = ask_reset(client, admin, registered)
    assert r.status_code == 201, r.text
    body = r.json()
    assert len(body["token"]) >= 40
    assert r.headers["Cache-Control"] == "no-store"

    expires = datetime.fromisoformat(body["expires_at"])
    assert timedelta(minutes=29) < expires - datetime.now(timezone.utc) <= timedelta(minutes=30)

    # Na base de dados fica só o hash, nunca o token
    [stored] = stored_hashes(registered)
    assert len(stored) == 64 and stored != body["token"]


def test_so_o_admin_pede_a_redefinicao(client, user_with_2fa, registered):
    uid = get_user(registered).id
    assert client.post(f"/api/auth/users/{uid}/password/reset", headers=bearer(user_with_2fa["token"])).status_code == 403
    assert client.post(f"/api/auth/users/{uid}/password/reset").status_code == 401


def test_utilizador_inexistente_da_404(client, admin):
    r = client.post("/api/auth/users/00000000-0000-0000-0000-000000000000/password/reset", headers=admin)
    assert r.status_code == 404


# --------------------------------------------------------------------------- o utilizador redefine
def test_redefinir_troca_a_palavra_passe_e_o_2fa_continua_obrigatorio(client, admin, user_with_2fa):
    email = user_with_2fa["email"]
    token = ask_reset(client, admin, email).json()["token"]

    r = client.post(RESET, json={"token": token, "new_password": NEW_PASSWORD})
    assert r.status_code == 204, r.text

    assert login_status(client, email, PASSWORD)[0] == 401  # a antiga deixa de servir
    assert login_status(client, email, NEW_PASSWORD) == (200, "MFA_REQUIRED")  # o 2FA continua a ser pedido

    # E o login completo funciona com a nova palavra-passe + código 2FA
    pre = client.post("/api/auth/login", json={"email": email, "password": NEW_PASSWORD}).json()["pre_auth_token"]
    done = client.post("/api/auth/2fa/verify", json={"code": totp_code(user_with_2fa["secret"], 30)},
                       headers=bearer(pre))
    assert done.status_code == 200 and done.json()["access_token"]


def test_quem_ainda_nao_tinha_2fa_tem_de_o_configurar(client, admin, registered):
    token = ask_reset(client, admin, registered).json()["token"]
    client.post(RESET, json={"token": token, "new_password": NEW_PASSWORD})
    assert login_status(client, registered, NEW_PASSWORD) == (200, "MFA_SETUP_REQUIRED")


def test_a_palavra_passe_antiga_funciona_ate_o_token_ser_usado(client, admin, registered):
    ask_reset(client, admin, registered)
    assert login_status(client, registered, PASSWORD)[0] == 200


def test_o_token_so_serve_uma_vez(client, admin, registered):
    token = ask_reset(client, admin, registered).json()["token"]
    assert client.post(RESET, json={"token": token, "new_password": NEW_PASSWORD}).status_code == 204
    second = client.post(RESET, json={"token": token, "new_password": "mais-uma-password-789"})
    assert second.status_code == 400 and second.json()["detail"] == "Token inválido ou expirado"
    assert login_status(client, registered, NEW_PASSWORD)[0] == 200


def test_token_errado_da_400(client):
    r = client.post(RESET, json={"token": "x" * 43, "new_password": NEW_PASSWORD})
    assert r.status_code == 400 and r.json()["detail"] == "Token inválido ou expirado"


def test_token_expirado_da_400(client, admin, registered):
    token = ask_reset(client, admin, registered).json()["token"]
    with SessionLocal() as db:
        db.execute(text("UPDATE password_reset_tokens SET created_at = now() - interval '1 hour',"
                        " expires_at = now() - interval '1 minute' WHERE user_id = :id"),
                   {"id": get_user(registered).id})
        db.commit()
    r = client.post(RESET, json={"token": token, "new_password": NEW_PASSWORD})
    assert r.status_code == 400 and r.json()["detail"] == "Token inválido ou expirado"
    assert login_status(client, registered, PASSWORD)[0] == 200  # nada mudou


def test_novo_pedido_anula_o_token_anterior(client, admin, registered):
    first = ask_reset(client, admin, registered).json()["token"]
    second = ask_reset(client, admin, registered).json()["token"]
    assert len(stored_hashes(registered)) == 1
    assert client.post(RESET, json={"token": first, "new_password": NEW_PASSWORD}).status_code == 400
    assert client.post(RESET, json={"token": second, "new_password": NEW_PASSWORD}).status_code == 204


def test_redefinir_desbloqueia_a_conta(client, admin, registered):
    for _ in range(3):  # nos testes, MAX_FAILED_ATTEMPTS = 3
        client.post("/api/auth/login", json={"email": registered, "password": "errada-errada"})
    assert login_status(client, registered, PASSWORD)[0] == 429  # bloqueada

    token = ask_reset(client, admin, registered).json()["token"]
    assert client.post(RESET, json={"token": token, "new_password": NEW_PASSWORD}).status_code == 204
    assert login_status(client, registered, NEW_PASSWORD)[0] == 200


@pytest.mark.parametrize(
    "body",
    [{"token": "curto", "new_password": NEW_PASSWORD}, {"token": "x" * 43, "new_password": "curta"},
     {"token": "x" * 43}, {}],
    ids=["token_curto", "password_curta", "sem_password", "vazio"],
)
def test_validacao_da_422(client, body):
    assert client.post(RESET, json=body).status_code == 422


def test_dois_pedidos_ao_mesmo_tempo_com_o_mesmo_token_so_um_passa(client, admin, registered):
    """O UPDATE ... WHERE used_at IS NULL é atómico: com 8 pedidos simultâneos, só um gasta o token."""
    token = ask_reset(client, admin, registered).json()["token"]
    passwords = [f"password-paralela-{i:02d}" for i in range(8)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(
            lambda pw: client.post(RESET, json={"token": token, "new_password": pw}).status_code, passwords
        ))
    assert sorted(codes) == [204] + [400] * 7
    winner = passwords[codes.index(204)]
    assert login_status(client, registered, winner)[0] == 200