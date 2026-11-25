"""Testes do booking-service.

Não precisam do auth-service a correr: geramos um par de chaves RSA e criamos os
tokens aqui, exatamente como o auth faria.
Para o teste de /health/ready é preciso a BD:  docker compose up -d db
"""
import base64
import hashlib
import hmac
import json
import os
import tempfile
import time
import uuid
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

_tmp = Path(tempfile.mkdtemp(prefix="slotup-booking-tests-"))


def _make_pair(name: str) -> rsa.RSAPrivateKey:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    (_tmp / f"{name}_private.pem").write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    (_tmp / f"{name}_public.pem").write_bytes(
        key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    )
    return key


_make_pair("auth")  # o par "legítimo" do auth-service
_make_pair("attacker")  # um par que não é o do auth-service
os.environ["JWT_PUBLIC_KEY_FILE"] = str(_tmp / "auth_public.pem")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5436")
os.environ.setdefault("DB_PASSWORD", os.environ.get("BOOKING_DB_PASSWORD", "troque-me"))

# ===== Configuração própria dos testes =====
# Os testes usam o seu .env só para a senha do banco. O resto é fixo aqui, para os
# resultados não dependerem do ambiente de quem corre os testes.

# Banco só dos testes: o site e o booking-worker usam o booking_db e nunca veem estes dados
os.environ["DB_NAME"] = "booking_test"

# SMTP: sempre os valores padrão do Mailpit, mesmo que o .env tenha o Gmail. As variáveis
# ficam VAZIAS, e não apagadas: o load_dotenv() do alembic/env.py nunca substitui uma
# variável que já existe, e o config.py trata o vazio como "use o valor padrão".
for variavel in ("SMTP_HOST", "SMTP_PORT", "SMTP_STARTTLS", "SMTP_USER", "SMTP_PASSWORD", "MAIL_FROM", "MAIL_SKIP_DOMAINS"):
    os.environ[variavel] = ""

# ===== Migrações no banco de teste, antes do primeiro teste =====
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

from app.config import get_settings  # noqa: E402

# O alembic/env.py usa primeiro a BOOKING_DATABASE_URL: definida aqui com o endereço
# do banco de teste, as migrações nunca podem ir para o booking_db
os.environ["BOOKING_DATABASE_URL"] = get_settings().database_url.render_as_string(hide_password=False)

_alembic = Config()  # sem o alembic.ini: assim o Alembic não mexe na configuração dos logs
_alembic.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
command.upgrade(_alembic, "head")  # só aplica as migrações que faltam: rápido a partir da 2.ª vez
import jwt  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def make_token(*, role="USER", typ="access", signer="auth", exp_in=1800, aud="slotup", iss="slotup-auth", alg="RS256", **extra):
    now = int(time.time())
    payload = {
        "iss": iss, "aud": aud, "sub": str(uuid.uuid4()), "typ": typ, "iat": now, "exp": now + exp_in,
        "email": "ana@slotup.pt", "role": role, **extra,
    }
    if alg == "RS256":
        return jwt.encode(payload, (_tmp / f"{signer}_private.pem").read_text(), algorithm="RS256")
    # Ataque clássico: assinar com HS256 usando a chave PÚBLICA como segredo.
    # A biblioteca PyJWT recusa criar este token, por isso montamos à mão.
    return _forge_hs256(payload, (_tmp / "auth_public.pem").read_bytes())


def _forge_hs256(payload: dict, secret: bytes) -> str:
    def b64(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    head = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = b64(json.dumps(payload).encode())
    sig = hmac.new(secret, f"{head}.{body}".encode(), hashlib.sha256).digest()
    return f"{head}.{body}.{b64(sig)}"


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c

@pytest.fixture(autouse=True)
def scheduling_em_baixo(monkeypatch):
    """Por omissão os testes correm SEM o scheduling (como no plano B).

    autouse=True: vale para todos os testes. Os que precisam de respostas do CSP
    trocam a função outra vez (fixture "scheduling" do test_planner.py).
    """
    from app import scheduling_client

    def em_baixo(pedido):
        raise scheduling_client.SchedulingIndisponivel

    monkeypatch.setattr(scheduling_client, "planear", em_baixo)