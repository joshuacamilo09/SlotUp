"""Categorias: listar (qualquer utilizador), criar e editar (só ADMIN).

Precisam da BD com as migrações aplicadas (ver backend/README.md, secção 6).
Cada teste cria categorias com nome "teste-<aleatório>", apagadas no fim.
"""
import threading
import uuid

import pytest
from sqlalchemy import text

from app.database import SessionLocal
from tests.conftest import bearer, make_token

URL = "/api/reservas/categorias"
USER = bearer(make_token(role="USER"))
ADMIN = bearer(make_token(role="ADMIN"))


@pytest.fixture(scope="module", autouse=True)
def _cleanup():
    yield
    with SessionLocal() as db:
        db.execute(text("DELETE FROM categories WHERE name ILIKE 'teste-%'"))
        db.commit()


def new_name() -> str:
    return f"teste-{uuid.uuid4().hex[:10]}"


def create(client, **body) -> dict:
    body.setdefault("name", new_name())
    r = client.post(URL, json=body, headers=ADMIN)
    assert r.status_code == 201, r.text
    return r.json()


# ---------- listar e consultar ----------

def test_list_requires_token(client):
    assert client.get(URL).status_code == 401


def test_user_lists_the_three_initial_categories_sorted(client):
    r = client.get(URL, headers=USER)
    assert r.status_code == 200
    names = [c["name"] for c in r.json()]
    assert {"Coworking", "Estacionamento", "Desporto"} <= set(names)
    assert names == sorted(names)


def test_get_one_category(client):
    cat = create(client, description="Para testes")
    r = client.get(f"{URL}/{cat['id']}", headers=USER)
    assert r.status_code == 200 and r.json()["description"] == "Para testes"


def test_unknown_and_invalid_ids(client):
    assert client.get(f"{URL}/{uuid.uuid4()}", headers=USER).status_code == 404
    assert client.get(f"{URL}/nao-e-um-uuid", headers=USER).status_code == 422


# ---------- só o ADMIN escreve ----------

def test_user_cannot_create_or_edit(client):
    cat = create(client)
    assert client.post(URL, json={"name": new_name()}, headers=USER).status_code == 403
    assert client.patch(f"{URL}/{cat['id']}", json={"name": new_name()}, headers=USER).status_code == 403
    assert client.post(URL, json={"name": new_name()}).status_code == 401


def test_admin_creates_and_it_appears_in_the_list(client):
    cat = create(client, name=f"  {new_name()}  ", description="Salas de estudo")
    assert cat["name"] == cat["name"].strip()  # espaços à volta são removidos
    assert cat["is_active"] is True and cat["created_at"] and cat["updated_at"]
    ids = [c["id"] for c in client.get(URL, headers=USER).json()]
    assert cat["id"] in ids


@pytest.mark.parametrize(
    "body",
    [{}, {"name": ""}, {"name": " a "}, {"name": "x" * 101}, {"name": "ok-nome", "description": "x" * 501},
     {"name": "ok-nome", "is_admin": True}],
    ids=["vazio", "nome_vazio", "nome_curto", "nome_longo", "descricao_longa", "campo_desconhecido"],
)
def test_create_validation(client, body):
    assert client.post(URL, json=body, headers=ADMIN).status_code == 422


def test_duplicate_name_is_409_ignoring_case(client):
    name = new_name()
    create(client, name=name)
    assert client.post(URL, json={"name": name.upper()}, headers=ADMIN).status_code == 409
    assert client.post(URL, json={"name": "coworking"}, headers=ADMIN).status_code == 409


def test_concurrent_creates_of_the_same_name_only_one_wins(client):
    """Dois admins (ou duas réplicas) a criar o mesmo nome ao mesmo tempo."""
    name = new_name()
    statuses: list[int] = []
    start = threading.Barrier(8)

    def worker():
        start.wait()
        statuses.append(client.post(URL, json={"name": name}, headers=ADMIN).status_code)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(statuses) == [201] + [409] * 7


# ---------- editar ----------

def test_admin_edits_name_and_description(client):
    cat = create(client, description="antiga")
    new = new_name()
    r = client.patch(f"{URL}/{cat['id']}", json={"name": new, "description": None}, headers=ADMIN)
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == new and body["description"] is None
    assert body["updated_at"] > cat["updated_at"]


def test_edit_only_changes_the_fields_sent(client):
    cat = create(client, description="fica igual")
    r = client.patch(f"{URL}/{cat['id']}", json={"name": new_name()}, headers=ADMIN)
    assert r.json()["description"] == "fica igual"


def test_edit_to_an_existing_name_is_409(client):
    a, b = create(client), create(client)
    r = client.patch(f"{URL}/{b['id']}", json={"name": a["name"].upper()}, headers=ADMIN)
    assert r.status_code == 409
    # a categoria b não mudou
    assert client.get(f"{URL}/{b['id']}", headers=USER).json()["name"] == b["name"]


@pytest.mark.parametrize(
    "body", [{}, {"name": None}, {"is_active": None}, {"id": str(uuid.uuid4())}],
    ids=["vazio", "nome_null", "is_active_null", "mudar_id"],
)
def test_edit_validation(client, body):
    cat = create(client)
    assert client.patch(f"{URL}/{cat['id']}", json=body, headers=ADMIN).status_code == 422


def test_edit_unknown_category_is_404(client):
    assert client.patch(f"{URL}/{uuid.uuid4()}", json={"name": new_name()}, headers=ADMIN).status_code == 404


# ---------- desativar (em vez de apagar) ----------

def test_deactivated_category_is_hidden_from_users_but_not_from_admin(client):
    cat = create(client)
    r = client.patch(f"{URL}/{cat['id']}", json={"is_active": False}, headers=ADMIN)
    assert r.status_code == 200 and r.json()["is_active"] is False

    assert cat["id"] not in [c["id"] for c in client.get(URL, headers=USER).json()]
    assert client.get(f"{URL}/{cat['id']}", headers=USER).status_code == 404

    assert cat["id"] not in [c["id"] for c in client.get(URL, headers=ADMIN).json()]
    all_ids = [c["id"] for c in client.get(URL, params={"include_inactive": True}, headers=ADMIN).json()]
    assert cat["id"] in all_ids
    assert client.get(f"{URL}/{cat['id']}", headers=ADMIN).status_code == 200

    # reativar
    client.patch(f"{URL}/{cat['id']}", json={"is_active": True}, headers=ADMIN)
    assert client.get(f"{URL}/{cat['id']}", headers=USER).status_code == 200


def test_user_cannot_ask_for_inactive_categories(client):
    assert client.get(URL, params={"include_inactive": True}, headers=USER).status_code == 403


def test_there_is_no_delete(client):
    cat = create(client)
    assert client.delete(f"{URL}/{cat['id']}", headers=ADMIN).status_code == 405