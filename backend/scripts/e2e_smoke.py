"""Teste de fumo de ponta a ponta: percorre o fluxo real entre os 3 serviços.

Pré-requisito: os serviços a correr (docker compose up -d --build) e, no seu PC:
    pip install httpx pyotp
    python backend/scripts/e2e_smoke.py

Cria um utilizador novo a cada execução (não precisa de limpar nada).
"""
import os
import sys
import uuid

import httpx
import pyotp

AUTH = os.getenv("AUTH_URL", "http://localhost:8001")
BOOKING = os.getenv("BOOKING_URL", "http://localhost:8002")
SCHEDULING = os.getenv("SCHEDULING_URL", "http://localhost:8003")
PASSWORD = "uma-password-segura-123"
failures = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global failures
    print(f"  [{'OK' if condition else 'FALHOU'}] {label}" + (f"  ({detail})" if detail and not condition else ""))
    failures += 0 if condition else 1


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def main() -> int:
    c = httpx.Client(timeout=10)
    email = f"smoke-{uuid.uuid4().hex[:8]}@slotup.pt"

    print("1. Serviços vivos")
    for name, url in (("auth", AUTH), ("booking", BOOKING), ("scheduling", SCHEDULING)):
        r = c.get(f"{url}/health/ready")
        check(f"{name} /health/ready", r.status_code == 200, r.text)
        check(f"{name} /whoami", r.status_code == 200 and c.get(f"{url}/whoami").json()["instance"] != "")

    print("2. Registo e login em dois passos")
    r = c.post(f"{AUTH}/api/auth/register", json={"name": "Smoke Test", "email": email, "password": PASSWORD})
    check("registo (201)", r.status_code == 201, r.text)
    r = c.post(f"{AUTH}/api/auth/login", json={"email": email, "password": PASSWORD})
    check("login pede configurar o 2FA", r.json().get("status") == "MFA_SETUP_REQUIRED", r.text)
    pre = r.json()["pre_auth_token"]
    setup = c.post(f"{AUTH}/api/auth/2fa/setup", headers=bearer(pre)).json()
    check("setup devolve otpauth_uri", setup["otpauth_uri"].startswith("otpauth://totp/"))
    secret = setup["secret"]
    r = c.post(f"{AUTH}/api/auth/2fa/enable", json={"code": pyotp.TOTP(secret).now()}, headers=bearer(pre))
    check("2FA ativado e token recebido", r.status_code == 200 and "access_token" in r.json(), r.text)
    token = r.json()["access_token"]

    print("3. O booking-service valida o token sem falar com o auth")
    r = c.get(f"{BOOKING}/api/reservas/me", headers=bearer(token))
    check("token válido aceite", r.status_code == 200 and r.json()["email"] == email, r.text)
    check("sem token = 401", c.get(f"{BOOKING}/api/reservas/me").status_code == 401)
    check("pre_auth não serve como acesso", c.get(f"{BOOKING}/api/reservas/me", headers=bearer(pre)).status_code == 401)

    print("4. Papéis")
    check("utilizador normal não entra em rota de admin (403)",
          c.get(f"{BOOKING}/api/reservas/admin/check", headers=bearer(token)).status_code == 403)
    check("utilizador normal não lista utilizadores (403)",
          c.get(f"{AUTH}/api/auth/users", headers=bearer(token)).status_code == 403)

    print("\nTudo certo." if failures == 0 else f"\n{failures} verificação(ões) falharam.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
