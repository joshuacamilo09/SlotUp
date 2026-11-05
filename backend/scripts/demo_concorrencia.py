"""Demo de consistência: vários pedidos SIMULTÂNEOS para o mesmo horário; só um vence.

O que mostra: quem decide é o PostgreSQL (constraint reservations_no_overlap), por isso
o resultado é o mesmo com 1 ou com várias réplicas do booking.

Usa os dados do seed: a ana e o admin (2FA com SEED_TOTP_SECRET) e a "Sala de Reunião B".
Rodar em infra/docker, com o .env carregado:
    set -a; source .env; set +a
    python ../../backend/scripts/demo_concorrencia.py
Depois do Nginx, aponte para ele:  BOOKING_URL=http://localhost:8080 python ...
"""

import os
import sys
import threading
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

import httpx
import pyotp

AUTH = os.environ.get("AUTH_URL", "http://localhost:8001")
BOOKING = os.environ.get("BOOKING_URL", "http://localhost:8002")
REQUESTS = int(os.environ.get("DEMO_REQUESTS", "10"))

# Mesmo namespace do seed do booking: o mesmo nome dá sempre o mesmo id
SEED_NAMESPACE = uuid.UUID("5e1f0d2a-7c3b-4b8e-9a61-2d4c8f0b3a17")
RESOURCE_ID = str(uuid.uuid5(SEED_NAMESPACE, "Sala de Reunião B"))

def env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(f"Falta {name}: rode antes set -a; source .env; set +a")
    return value

def login(client: httpx.Client, email: str, password: str, totp_secret: str) -> str:
    """Login em dois passos, como um usuário real: senha e depois o código 2FA."""
    r = client.post(f"{AUTH}/api/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    pre_auth = {"Authorization": f"Bearer {r.json()['pre_auth_token']}"}

    for _ in range(2):
        r = client.post(f"{AUTH}/api/auth/2fa/verify", json={"code": pyotp.TOTP(totp_secret).now()}, headers=pre_auth)
        if r.status_code == 200:
            return r.json()["access_token"]
        time.sleep(31 - time.time() % 30)
    r.raise_for_status()

def next_monday() -> date:
    today = date.today()
    return today + timedelta(days=7 - today.weekday())

def main() -> None:
    with httpx.Client(timeout=10) as client:
        # 1) dois usuários reais, com login e 2fa
        tokens = [
            login(client, env("ADMIN_EMAIL"), env("ADMIN_PASSWORD"), env("SEED_TOTP_SECRET")),
            login(client, "ana@slotup.pt", env("SEED_USER_PASSWORD"), env("SEED_TOTP_SECRET")),
        ]
        headers = [{"Authorization": f"Bearer {t}"} for t in tokens]

        # 2) Escolhe um horário LIVRE (pela consulta de disponibilidade), para a demo poder repetir
        day = next_monday()
        r = client.get(f"{BOOKING}/api/reservas/recursos/{RESOURCE_ID}/disponibilidade",
                       params={"day": day.isoformat()}, headers=headers[0])
        r.raise_for_status()
        free = r.json()["free"]
        if not free:
            sys.exit("A sala não tem horário livre nesse dia: rode o seed do booking para recomeçar.")
        start = datetime.fromisoformat(free[0]["start"])
        end = start + timedelta(hours=1)
        body = {"resource_id": RESOURCE_ID, "start_at": start.isoformat(), "end_at": end.isoformat()}
        print(f"Sala de Reunião B, {start:%d/%m/ %H:%M}-{end:%H:%M}: {REQUESTS} pedidos ao mesmo tempo...")

        # 3) Todos os pedidos esperam na "barreira" e saem juntos, para ficarem mesmo simultaneos
        barrier = threading.Barrier(REQUESTS)

        def attempt(i: int) -> int:
            barrier.wait()
            response = client.post(f"{BOOKING}/api/reservas/reservas", json=body, headers=headers[i % 2])
            return response.status_code

        with ThreadPoolExecutor(max_workers=REQUESTS) as pool:
            codes = list(pool.map(attempt, range(REQUESTS)))

    # 4) Resultado
    summary = Counter(codes)
    for code, count in sorted(summary.items()):
        label = {201: "reservou", 409: "recusado: horário já ocupado"}.get(code, "inesperado")
        print(f" {code} ({label}): {count}")
    if summary == Counter({201: 1, 409: REQUESTS - 1}):
        print("OK: só um pedido ficou com o horário. Quem decidiu foi o PostgreSQL.")
    else:
        sys.exti("FALHOU: o resultado devia ser exatamente um 201 e o resto 409.")

if __name__ == "__main__":
    main()