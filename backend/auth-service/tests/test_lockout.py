"""Limite de tentativas: 5 erros bloqueiam a conta durante 15 min.

Contam os erros de password e os de código 2FA, somados. O contador fica no banco
(users.failed_login_attempts), por isso vale para todas as réplicas do auth.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from sqlalchemy import update

from app.config import get_settings
from app.database import SessionLocal
from app.models import User
from tests.conftest import PASSWORD, bearer, full_login, get_user, totp_code

WRONG = "errada-errada-1"


def _login(client, email, password):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def test_a_regra_e_5_erros_e_15_minutos():
    s = get_settings()
    assert (s.max_failed_attempts, s.lock_minutes) == (5, 15)


def test_4_erros_ainda_nao_bloqueiam(client, registered):
    for _ in range(4):
        assert _login(client, registered, WRONG).status_code == 401
    assert _login(client, registered, PASSWORD).status_code == 200


def test_o_5o_erro_bloqueia_por_15_minutos(client, registered):
    for _ in range(5):
        assert _login(client, registered, WRONG).status_code == 401
    r = _login(client, registered, PASSWORD)  # até a password certa é recusada
    assert r.status_code == 429
    assert 14 * 60 < int(r.headers["Retry-After"]) <= 15 * 60
    assert "15 min" in r.json()["detail"]
    locked = get_user(registered).locked_until
    assert timedelta(minutes=14) < locked - datetime.now(timezone.utc) <= timedelta(minutes=15)


def test_erros_de_password_e_de_codigo_contam_juntos(client, user_with_2fa):
    email = user_with_2fa["email"]
    for _ in range(3):
        assert _login(client, email, WRONG).status_code == 401
    pre = _login(client, email, PASSWORD).json()["pre_auth_token"]
    for _ in range(2):
        assert client.post("/api/auth/2fa/verify", json={"code": "000000"}, headers=bearer(pre)).status_code == 401
    # 3 + 2 = 5: bloqueada, mesmo com o código certo
    right = client.post("/api/auth/2fa/verify", json={"code": totp_code(user_with_2fa["secret"], 30)}, headers=bearer(pre))
    assert right.status_code == 429


def test_passados_os_15_minutos_volta_a_entrar(client, user_with_2fa):
    email = user_with_2fa["email"]
    for _ in range(5):
        _login(client, email, WRONG)
    assert _login(client, email, PASSWORD).status_code == 429
    # Simula a passagem do tempo: o bloqueio acabou há 1 segundo
    with SessionLocal() as db:
        db.execute(update(User).where(User.email == email)
                   .values(locked_until=datetime.now(timezone.utc) - timedelta(seconds=1)))
        db.commit()
    full_login(client, email, secret=user_with_2fa["secret"], offset=30)
    user = get_user(email)
    assert user.failed_login_attempts == 0 and user.locked_until is None


def test_pedidos_ao_mesmo_tempo_tambem_bloqueiam(client, registered):
    # 8 passwords erradas em simultâneo (como se viessem pelas 2 réplicas): o contador
    # sobe no próprio banco, sem se perder nenhuma, e a conta fica bloqueada
    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(lambda _: _login(client, registered, WRONG).status_code, range(8)))
    assert all(c in (401, 429) for c in codes)
    assert _login(client, registered, PASSWORD).status_code == 429