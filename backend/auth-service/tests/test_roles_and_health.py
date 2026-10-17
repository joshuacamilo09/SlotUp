from tests.conftest import PASSWORD, bearer, full_login, get_user, new_email, set_role


def _make_admin(client):
    email = new_email()
    client.post("/api/auth/register", json={"name": "Admin", "email": email, "password": PASSWORD})
    set_role(email, "ADMIN")  # no auth real, o 1º admin vem do ADMIN_EMAIL; nos testes promovemos na BD
    token, secret = full_login(client, email)
    return email, token, secret


def test_new_users_are_regular_users_and_cannot_use_admin_endpoints(client, user_with_2fa):
    h = bearer(user_with_2fa["token"])
    assert client.get("/api/auth/users", headers=h).status_code == 403
    assert client.patch(f"/api/auth/users/{get_user(user_with_2fa['email']).id}/role", json={"role": "ADMIN"}, headers=h).status_code == 403


def test_admin_can_list_users(client, user_with_2fa):
    _, token, _ = _make_admin(client)
    r = client.get("/api/auth/users", headers=bearer(token))
    assert r.status_code == 200
    emails = [u["email"] for u in r.json()]
    assert user_with_2fa["email"] in emails
    assert all("password" not in u and "totp" not in str(u) for u in r.json())


def test_admin_can_change_roles_but_not_their_own(client, registered):
    admin_email, token, _ = _make_admin(client)
    h = bearer(token)
    target = get_user(registered).id
    r = client.patch(f"/api/auth/users/{target}/role", json={"role": "ADMIN"}, headers=h)
    assert r.status_code == 200 and r.json()["role"] == "ADMIN"
    own = get_user(admin_email).id
    assert client.patch(f"/api/auth/users/{own}/role", json={"role": "USER"}, headers=h).status_code == 400
    assert client.patch(f"/api/auth/users/{target}/role", json={"role": "SUPERUSER"}, headers=h).status_code == 422


def test_admin_can_reset_2fa_and_user_must_set_it_up_again(client, user_with_2fa):
    _, token, _ = _make_admin(client)
    uid = get_user(user_with_2fa["email"]).id
    assert client.post(f"/api/auth/users/{uid}/2fa/reset", headers=bearer(token)).status_code == 204
    r = client.post("/api/auth/login", json={"email": user_with_2fa["email"], "password": PASSWORD})
    assert r.json()["status"] == "MFA_SETUP_REQUIRED"


def test_unknown_user_is_404(client):
    _, token, _ = _make_admin(client)
    r = client.patch("/api/auth/users/00000000-0000-0000-0000-000000000000/role", json={"role": "USER"}, headers=bearer(token))
    assert r.status_code == 404


def test_health_endpoints(client):
    assert client.get("/health/live").json() == {"status": "ok"}
    assert client.get("/health/ready").json() == {"status": "ok"}
    who = client.get("/whoami").json()
    assert who["service"] == "auth-service" and who["instance"]


def test_database_outage_returns_503_not_500(client):
    from sqlalchemy.exc import OperationalError

    from app.database import get_db
    from app.main import app

    def broken_db():
        raise OperationalError("SELECT 1", {}, Exception("ligação recusada"))
        yield  # pragma: no cover

    app.dependency_overrides[get_db] = broken_db
    try:
        r = client.post("/api/auth/login", json={"email": "a@slotup.pt", "password": "qualquer"})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 503
    assert r.headers["Retry-After"] == "5"
