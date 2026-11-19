"""Cifra do segredo do 2FA (AES-GCM) no auth_db.

O segredo TOTP de cada utilizador é guardado cifrado com AES-256-GCM:
  * a chave (32 bytes) vem de um Secret (Docker: /run/secrets/totp_encryption_key;
    Kubernetes: Secret totp-encryption-key), nunca do banco;
  * cada cifragem usa um nonce aleatório de 12 bytes, guardado à frente do texto cifrado;
  * o id do utilizador entra como dados associados: o segredo de um utilizador não
    serve se for copiado para a linha de outro.
"""
import base64
import os
import uuid

import pytest
from cryptography.exceptions import InvalidTag

from app.config import Settings, get_settings
from app.security import check_totp_key, decrypt_totp_secret, encrypt_totp_secret, new_totp_secret
from tests.conftest import PASSWORD, bearer, get_user


def _settings_with_key(key: bytes) -> Settings:
    return get_settings().model_copy(update={"totp_encryption_key": base64.urlsafe_b64encode(key).decode()})


def test_cada_cifragem_usa_um_nonce_aleatorio():
    settings, user_id, secret = get_settings(), uuid.uuid4(), new_totp_secret()
    a = encrypt_totp_secret(settings, secret, user_id)
    b = encrypt_totp_secret(settings, secret, user_id)
    assert a != b                # o mesmo segredo dá blobs diferentes
    assert a[:12] != b[:12]      # porque os 12 primeiros bytes (o nonce) mudam
    assert decrypt_totp_secret(settings, a, user_id) == decrypt_totp_secret(settings, b, user_id) == secret


def test_o_segredo_de_um_utilizador_nao_serve_na_linha_de_outro():
    settings, secret = get_settings(), new_totp_secret()
    blob = encrypt_totp_secret(settings, secret, uuid.uuid4())
    with pytest.raises(InvalidTag):
        decrypt_totp_secret(settings, blob, uuid.uuid4())


def test_sem_a_chave_certa_nao_se_decifra():
    user_id, secret = uuid.uuid4(), new_totp_secret()
    blob = encrypt_totp_secret(get_settings(), secret, user_id)
    with pytest.raises(InvalidTag):
        decrypt_totp_secret(_settings_with_key(os.urandom(32)), blob, user_id)


def test_um_byte_alterado_no_banco_e_detetado():
    settings, user_id = get_settings(), uuid.uuid4()
    blob = bytearray(encrypt_totp_secret(settings, new_totp_secret(), user_id))
    blob[-1] ^= 0x01
    with pytest.raises(InvalidTag):
        decrypt_totp_secret(settings, bytes(blob), user_id)


def test_chave_com_tamanho_errado_e_recusada_no_arranque():
    with pytest.raises(ValueError):
        check_totp_key(_settings_with_key(os.urandom(16)))
    check_totp_key(get_settings())  # a chave de 32 bytes dos testes passa


def test_no_banco_fica_nonce_mais_texto_cifrado(client, registered):
    pre = client.post("/api/auth/login", json={"email": registered, "password": PASSWORD}).json()["pre_auth_token"]
    secret = client.post("/api/auth/2fa/setup", headers=bearer(pre)).json()["secret"]
    blob = get_user(registered).totp_secret_encrypted
    assert secret.encode() not in blob
    # 12 bytes de nonce + o segredo cifrado (mesmo tamanho) + 16 bytes da etiqueta do GCM
    assert len(blob) == 12 + len(secret) + 16