"""Testes do módulo de recursos (/api/reservas/recursos).

Correm contra o PostgreSQL real, com as migrações aplicadas (ver backend/README.md, secção 6).
As categorias são criadas diretamente na base de dados, para estes testes não dependerem do
router das categorias, e são apagadas no fim.
"""
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import text

from app.database import SessionLocal

URL = "/api/reservas/recursos"


@pytest.fixture(scope="session")
def helpers(request):
    """O módulo conftest.py (make_token e bearer), tal como o pytest já o carregou.

    Não o importamos à mão: um segundo import voltava a correr o conftest e a gerar outro par
    de chaves RSA, e os tokens deixavam de ser aceites pela app.
    """
    for plugin in request.config.pluginmanager.get_plugins():
        if hasattr(plugin, "make_token") and hasattr(plugin, "bearer"):
            return plugin
    raise RuntimeError("Não encontrei o conftest.py com make_token e bearer")


@pytest.fixture
def admin(helpers):
    return helpers.bearer(helpers.make_token(role="ADMIN"))


@pytest.fixture
def user(helpers):
    return helpers.bearer(helpers.make_token(role="USER"))


@pytest.fixture
def make_category():
    """Cria categorias de teste na BD; no fim apaga-as, com os recursos que ficaram nelas."""
    created: list[uuid.UUID] = []

    def _make(active: bool = True) -> str:
        category_id = uuid.uuid4()
        with SessionLocal() as db:
            db.execute(
                text("INSERT INTO categories (id, name, is_active) VALUES (:id, :name, :active)"),
                {"id": category_id, "name": f"teste-{category_id.hex[:12]}", "active": active},
            )
            db.commit()
        created.append(category_id)
        return str(category_id)

    yield _make

    with SessionLocal() as db:
        for category_id in created:
            of_category = "SELECT id FROM resources WHERE category_id = :id"
            # ordem: fila de espera (aponta para reservas) -> reservas -> recursos -> categoria
            db.execute(text(f"DELETE FROM waitlist_entries WHERE resource_id IN ({of_category})"), {"id": category_id})
            db.execute(text(f"DELETE FROM reservations WHERE resource_id IN ({of_category})"), {"id": category_id})
            db.execute(text("DELETE FROM resources WHERE category_id = :id"), {"id": category_id})
            db.execute(text("DELETE FROM categories WHERE id = :id"), {"id": category_id})
        db.commit()


@pytest.fixture
def category(make_category) -> str:
    return make_category()


def body(category_id: str, **extra) -> dict:
    return {"category_id": category_id, "name": f"Mesa {uuid.uuid4().hex[:8]}", "resource_type": "mesa", **extra}


def create(client, admin, category_id: str, **extra) -> dict:
    response = client.post(URL, json=body(category_id, **extra), headers=admin)
    assert response.status_code == 201, response.text
    return response.json()


def hours(resource: dict) -> set[tuple[int, str, str]]:
    return {(r["weekday"], r["open_time"], r["close_time"]) for r in resource["schedule"]}


# --------------------------------------------------------------------------- autenticação e papéis
def test_sem_token_da_401(client):
    assert client.get(URL).status_code == 401


def test_utilizador_normal_nao_cria_edita_nem_remove(client, admin, user, category):
    resource = create(client, admin, category)
    rid = resource["id"]
    assert client.post(URL, json=body(category), headers=user).status_code == 403
    assert client.patch(f"{URL}/{rid}", json={"name": "Outro"}, headers=user).status_code == 403
    assert client.put(f"{URL}/{rid}/horarios", json={"rules": []}, headers=user).status_code == 403
    assert client.delete(f"{URL}/{rid}", headers=user).status_code == 403
    # nada mudou
    assert client.get(f"{URL}/{rid}", headers=admin).json()["name"] == resource["name"]


def test_token_pre_auth_nao_serve(client, helpers):
    token = helpers.make_token(role="ADMIN", typ="pre_auth")
    assert client.get(URL, headers=helpers.bearer(token)).status_code == 401


# --------------------------------------------------------------------------- criar
def test_recurso_novo_abre_todos_os_dias_das_8_as_20(client, admin, category):
    resource = create(client, admin, category, capacity=4, attributes={"tem_projetor": True})
    assert resource["is_active"] is True
    assert resource["capacity"] == 4
    assert resource["attributes"] == {"tem_projetor": True}
    assert resource["category_id"] == category
    assert resource["category_name"].startswith("teste-")
    assert hours(resource) == {(day, "08:00:00", "20:00:00") for day in range(7)}


def test_admin_define_horario_proprio_na_criacao(client, admin, category):
    schedule = [{"weekday": d, "open_time": "09:00", "close_time": "18:00"} for d in range(5)]
    resource = create(client, admin, category, schedule=schedule)
    assert hours(resource) == {(d, "09:00:00", "18:00:00") for d in range(5)}


def test_dois_intervalos_no_mesmo_dia(client, admin, category):
    schedule = [
        {"weekday": 0, "open_time": "09:00", "close_time": "13:00"},
        {"weekday": 0, "open_time": "14:00", "close_time": "18:00"},
    ]
    resource = create(client, admin, category, schedule=schedule)
    assert [(r["open_time"], r["close_time"]) for r in resource["schedule"]] == [
        ("09:00:00", "13:00:00"),
        ("14:00:00", "18:00:00"),
    ]


def test_tipo_fica_em_minusculas_e_nome_sem_espacos(client, admin, category):
    resource = create(client, admin, category, name="  Sala Azul  ", resource_type=" SALA ")
    assert resource["name"] == "Sala Azul"
    assert resource["resource_type"] == "sala"


@pytest.mark.parametrize(
    "extra",
    [
        {"capacity": 0},
        {"capacity": -3},
        {"name": "x"},
        {"resource_type": ""},
        {"is_admin": True},  # campo desconhecido
        {"schedule": [{"weekday": 7, "open_time": "08:00", "close_time": "20:00"}]},
        {"schedule": [{"weekday": 0, "open_time": "20:00", "close_time": "08:00"}]},
        {"schedule": [{"weekday": 0, "open_time": "08:00", "close_time": "08:00"}]},
        {"schedule": [{"weekday": 0, "open_time": "08:00+01:00", "close_time": "20:00"}]},
        {
            "schedule": [
                {"weekday": 2, "open_time": "08:00", "close_time": "12:00"},
                {"weekday": 2, "open_time": "11:00", "close_time": "15:00"},
            ]
        },
    ],
)
def test_pedidos_invalidos_dao_422(client, admin, category, extra):
    assert client.post(URL, json=body(category, **extra), headers=admin).status_code == 422


def test_categoria_inexistente_da_422(client, admin):
    assert client.post(URL, json=body(str(uuid.uuid4())), headers=admin).status_code == 422


def test_categoria_desativada_da_409(client, admin, make_category):
    inactive = make_category(active=False)
    assert client.post(URL, json=body(inactive), headers=admin).status_code == 409


def test_nome_repetido_na_mesma_categoria_da_409_mas_noutra_nao(client, admin, make_category):
    first, second = make_category(), make_category()
    payload = body(first)
    assert client.post(URL, json=payload, headers=admin).status_code == 201
    assert client.post(URL, json=payload, headers=admin).status_code == 409
    assert client.post(URL, json={**payload, "category_id": second}, headers=admin).status_code == 201


def test_criacoes_simultaneas_com_o_mesmo_nome_so_uma_passa(client, admin, category):
    payload = body(category)
    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(lambda _: client.post(URL, json=payload, headers=admin).status_code, range(8)))
    assert sorted(codes) == [201] + [409] * 7


# --------------------------------------------------------------------------- listar e filtrar
def test_utilizador_lista_e_filtra_por_categoria(client, admin, user, make_category):
    first, second = make_category(), make_category()
    in_first = create(client, admin, first)
    in_second = create(client, admin, second)

    ids_of_first = {r["id"] for r in client.get(URL, params={"category_id": first}, headers=user).json()}
    ids_of_second = {r["id"] for r in client.get(URL, params={"category_id": second}, headers=user).json()}
    assert ids_of_first == {in_first["id"]}
    assert ids_of_second == {in_second["id"]}

    everything = {r["id"] for r in client.get(URL, headers=user).json()}
    assert {in_first["id"], in_second["id"]} <= everything


def test_lista_ordenada_por_categoria_e_nome(client, admin, category):
    for name in ("Mesa C", "Mesa A", "Mesa B"):
        create(client, admin, category, name=name)
    names = [r["name"] for r in client.get(URL, params={"category_id": category}, headers=admin).json()]
    assert names == ["Mesa A", "Mesa B", "Mesa C"]


def test_filtro_com_id_invalido_da_422(client, user):
    assert client.get(URL, params={"category_id": "abc"}, headers=user).status_code == 422


def test_recurso_inexistente_da_404(client, user):
    assert client.get(f"{URL}/{uuid.uuid4()}", headers=user).status_code == 404


# --------------------------------------------------------------------------- editar
def test_patch_altera_so_o_que_foi_enviado(client, admin, category):
    resource = create(client, admin, category, description="original", capacity=2)
    response = client.patch(f"{URL}/{resource['id']}", json={"name": "Novo nome", "capacity": 6}, headers=admin)
    assert response.status_code == 200
    data = response.json()
    assert (data["name"], data["capacity"], data["description"]) == ("Novo nome", 6, "original")
    assert hours(data) == hours(resource)  # o horário não é tocado pelo PATCH


def test_patch_pode_apagar_a_descricao(client, admin, category):
    resource = create(client, admin, category, description="algo")
    response = client.patch(f"{URL}/{resource['id']}", json={"description": None}, headers=admin)
    assert response.json()["description"] is None


@pytest.mark.parametrize("payload", [{}, {"name": None}, {"capacity": None}, {"is_active": None}, {"capacity": 0}])
def test_patch_invalido_da_422(client, admin, category, payload):
    resource = create(client, admin, category)
    assert client.patch(f"{URL}/{resource['id']}", json=payload, headers=admin).status_code == 422


def test_patch_mudar_para_nome_ja_usado_da_409(client, admin, category):
    taken = create(client, admin, category)
    other = create(client, admin, category)
    response = client.patch(f"{URL}/{other['id']}", json={"name": taken["name"]}, headers=admin)
    assert response.status_code == 409


def test_patch_muda_de_categoria(client, admin, make_category):
    first, second = make_category(), make_category()
    resource = create(client, admin, first)
    response = client.patch(f"{URL}/{resource['id']}", json={"category_id": second}, headers=admin)
    assert response.status_code == 200
    assert response.json()["category_id"] == second
    assert response.json()["category_name"].startswith("teste-")


def test_patch_para_categoria_inexistente_da_422(client, admin, category):
    resource = create(client, admin, category)
    response = client.patch(f"{URL}/{resource['id']}", json={"category_id": str(uuid.uuid4())}, headers=admin)
    assert response.status_code == 422


def test_desativar_esconde_dos_utilizadores_mas_nao_do_admin(client, admin, user, category):
    resource = create(client, admin, category)
    rid = resource["id"]
    assert client.patch(f"{URL}/{rid}", json={"is_active": False}, headers=admin).json()["is_active"] is False

    assert client.get(f"{URL}/{rid}", headers=user).status_code == 404
    assert rid not in {r["id"] for r in client.get(URL, params={"category_id": category}, headers=user).json()}

    assert client.get(f"{URL}/{rid}", headers=admin).status_code == 200
    listed = client.get(URL, params={"category_id": category, "include_inactive": True}, headers=admin).json()
    assert rid in {r["id"] for r in listed}

    # reativar
    client.patch(f"{URL}/{rid}", json={"is_active": True}, headers=admin)
    assert client.get(f"{URL}/{rid}", headers=user).status_code == 200


def test_include_inactive_e_so_para_admin(client, user):
    assert client.get(URL, params={"include_inactive": True}, headers=user).status_code == 403


def test_recursos_de_categoria_desativada_ficam_escondidos(client, admin, user, category):
    resource = create(client, admin, category)
    with SessionLocal() as db:
        db.execute(text("UPDATE categories SET is_active = false WHERE id = :id"), {"id": category})
        db.commit()
    assert client.get(f"{URL}/{resource['id']}", headers=user).status_code == 404
    assert client.get(URL, params={"category_id": category}, headers=user).json() == []
    assert client.get(f"{URL}/{resource['id']}", headers=admin).status_code == 200


# --------------------------------------------------------------------------- horário
def test_put_horarios_substitui_dias_e_horas(client, admin, category):
    resource = create(client, admin, category)  # começa 7 dias, 08:00-20:00
    rules = [
        {"weekday": 0, "open_time": "08:00", "close_time": "20:00"},  # igual a uma regra antiga
        {"weekday": 5, "open_time": "10:00", "close_time": "14:00"},
    ]
    response = client.put(f"{URL}/{resource['id']}/horarios", json={"rules": rules}, headers=admin)
    assert response.status_code == 200
    assert hours(response.json()) == {(0, "08:00:00", "20:00:00"), (5, "10:00:00", "14:00:00")}
    # e fica gravado
    assert hours(client.get(f"{URL}/{resource['id']}", headers=admin).json()) == hours(response.json())


def test_put_horarios_vazio_deixa_o_recurso_sem_horario(client, admin, category):
    resource = create(client, admin, category)
    response = client.put(f"{URL}/{resource['id']}/horarios", json={"rules": []}, headers=admin)
    assert response.status_code == 200
    assert response.json()["schedule"] == []


@pytest.mark.parametrize(
    "rules",
    [
        [{"weekday": 8, "open_time": "08:00", "close_time": "20:00"}],
        [{"weekday": 1, "open_time": "20:00", "close_time": "08:00"}],
        [
            {"weekday": 1, "open_time": "08:00", "close_time": "12:00"},
            {"weekday": 1, "open_time": "08:00", "close_time": "12:00"},
        ],
    ],
)
def test_put_horarios_invalido_da_422_e_nao_mexe_no_horario(client, admin, category, rules):
    resource = create(client, admin, category)
    response = client.put(f"{URL}/{resource['id']}/horarios", json={"rules": rules}, headers=admin)
    assert response.status_code == 422
    assert hours(client.get(f"{URL}/{resource['id']}", headers=admin).json()) == hours(resource)


def test_put_horarios_de_recurso_inexistente_da_404(client, admin):
    assert client.put(f"{URL}/{uuid.uuid4()}/horarios", json={"rules": []}, headers=admin).status_code == 404


# --------------------------------------------------------------------------- remover
def test_delete_sem_reservas_apaga_de_vez(client, admin, category):
    resource = create(client, admin, category)
    response = client.delete(f"{URL}/{resource['id']}", headers=admin)
    assert response.status_code == 200
    assert response.json() == {"action": "deleted", "resource_id": resource["id"]}
    assert client.get(f"{URL}/{resource['id']}", headers=admin).status_code == 404
    with SessionLocal() as db:  # as regras de horário foram apagadas em cascata
        left = db.scalar(
            text("SELECT count(*) FROM availability_rules WHERE resource_id = :id"), {"id": resource["id"]}
        )
    assert left == 0


def _add_reservation(resource_id: str) -> None:
    with SessionLocal() as db:
        db.execute(
            text(
                "INSERT INTO reservations (user_id, user_email, resource_id, start_at, end_at, status) "
                "VALUES (:user, 'ana@slotup.pt', :resource, now() + interval '1 day', "
                "now() + interval '1 day 1 hour', 'CONFIRMED')"
            ),
            {"user": uuid.uuid4(), "resource": resource_id},
        )
        db.commit()


def _add_waitlist_entry(resource_id: str) -> None:
    with SessionLocal() as db:
        db.execute(
            text(
                "INSERT INTO waitlist_entries (user_id, user_email, resource_id, desired_start, desired_end) "
                "VALUES (:user, 'rui@slotup.pt', :resource, now() + interval '1 day', now() + interval '1 day 1 hour')"
            ),
            {"user": uuid.uuid4(), "resource": resource_id},
        )
        db.commit()


def _count(table_name: str, resource_id: str) -> int:
    with SessionLocal() as db:
        return db.scalar(text(f"SELECT count(*) FROM {table_name} WHERE resource_id = :id"), {"id": resource_id})


@pytest.mark.parametrize("add_history, table_name", [(_add_reservation, "reservations"), (_add_waitlist_entry, "waitlist_entries")])
def test_delete_com_historico_desativa_em_vez_de_apagar(client, admin, user, category, add_history, table_name):
    resource = create(client, admin, category)
    rid = resource["id"]
    add_history(rid)

    response = client.delete(f"{URL}/{rid}", headers=admin)
    assert response.status_code == 200
    assert response.json() == {"action": "deactivated", "resource_id": rid}

    # o admin continua a vê-lo, inativo; o utilizador deixa de o ver; o histórico fica intacto
    assert client.get(f"{URL}/{rid}", headers=admin).json()["is_active"] is False
    assert client.get(f"{URL}/{rid}", headers=user).status_code == 404
    assert _count(table_name, rid) == 1
    # apagar outra vez continua a dar "desativado" (idempotente)
    assert client.delete(f"{URL}/{rid}", headers=admin).json()["action"] == "deactivated"


def test_delete_de_recurso_inexistente_da_404(client, admin):
    assert client.delete(f"{URL}/{uuid.uuid4()}", headers=admin).status_code == 404