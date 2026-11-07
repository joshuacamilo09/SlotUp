"""Testes dos fluxos de reserva: o caminho completo, passo a passo, como na aplicação.

Cada teste conta uma história (criar, conflitar, cancelar, listar, fila de espera)
e confirma, a cada passo, o que cada pessoa vê. As regras isoladas estão nos outros
ficheiros; aqui interessa que as peças funcionem juntas, incluindo a regra de
permissão entre usuário comum e administrador.
"""
from datetime import datetime, timezone

from sqlalchemy import text

from app import waitlist
from app.database import SessionLocal
from tests.test_reservations import (  # noqa: F401  (fixtures do pytest)
    admin,
    at,
    book,
    category,
    create_resource,
    helpers,
    next_monday,
)
from tests.test_reservations_manage import Person, ana, cancel, rui  # noqa: F401
from tests.test_waitlist import entry, eva, join  # noqa: F401

RESERVAS = "/api/reservas/reservas"
FILA = "/api/reservas/fila"
AVAILABILITY = "/api/reservas/recursos/{rid}/disponibilidade"


def busy(client, headers, rid, day) -> list[tuple[str, str]]:
    data = client.get(AVAILABILITY.format(rid=rid), params={"day": str(day)}, headers=headers).json()
    return [(b["start"][11:16], b["end"][11:16]) for b in data["busy"]]


def mine(client, person, **params) -> list[dict]:
    return client.get(f"{RESERVAS}/minhas", params=params, headers=person.headers).json()


def emails(person) -> list[str]:
    """Os tipos de email pendentes (outbox) para esta pessoa, por ordem."""
    with SessionLocal() as db:
        return list(db.scalars(
            text("SELECT type FROM notifications WHERE recipient_email = :email ORDER BY created_at, type"),
            {"email": person.email},
        ).all())


# --------------------------------------------------------------------------- 1. criar, conflitar, cancelar, listar
def test_fluxo_reservar_conflito_cancelar_e_outro_reserva(client, admin, category, ana, rui):
    day = next_monday()
    rid = create_resource(client, admin, category)

    # A Ana vê o horário livre e reserva
    assert busy(client, ana.headers, rid, day) == []
    created = book(client, ana.headers, rid, at(day, 10), at(day, 11))
    assert created.status_code == 201
    reservation = created.json()["id"]

    # O horário aparece ocupado para todos e nas futuras da Ana
    assert busy(client, rui.headers, rid, day) == [("10:00", "11:00")]
    assert [r["id"] for r in mine(client, ana, periodo="futuras")] == [reservation]

    # O Rui tenta o mesmo horário, e um que se sobrepõe: conflito nos dois
    assert book(client, rui.headers, rid, at(day, 10), at(day, 11)).status_code == 409
    assert book(client, rui.headers, rid, at(day, 10, 30), at(day, 11, 30)).status_code == 409
    # Mas o horário seguinte está livre
    assert book(client, rui.headers, rid, at(day, 11), at(day, 12)).status_code == 201

    # A Ana cancela: o horário fica livre e o Rui reserva-o
    assert cancel(client, ana.headers, reservation).status_code == 200
    assert busy(client, rui.headers, rid, day) == [("11:00", "12:00")]
    assert book(client, rui.headers, rid, at(day, 10), at(day, 11)).status_code == 201

    # Cada um vê só as suas
    assert [r["status"] for r in mine(client, ana)] == ["CANCELLED"]
    assert sorted(r["start_at"][11:16] for r in mine(client, rui)) == ["10:00", "11:00"]
    assert emails(ana) == ["RESERVATION_CREATED", "RESERVATION_CANCELLED"]
    assert emails(rui) == ["RESERVATION_CREATED", "RESERVATION_CREATED"]


# --------------------------------------------------------------------------- 2. permissões: usuário comum x administrador
def test_fluxo_permissoes_usuario_comum_e_administrador(client, admin, category, ana, rui):
    day = next_monday()
    rid = create_resource(client, admin, category)
    reservation = book(client, ana.headers, rid, at(day, 9), at(day, 10)).json()["id"]

    # O Rui (usuário comum) não vê, não cancela e não lista as reservas dos outros
    assert client.get(f"{RESERVAS}/{reservation}", headers=rui.headers).status_code == 404
    assert cancel(client, rui.headers, reservation).status_code == 404
    assert client.get(RESERVAS, headers=rui.headers).status_code == 403
    assert mine(client, rui) == []
    # Nem cria recursos
    assert client.post("/api/reservas/recursos", json={}, headers=rui.headers).status_code == 403

    # O administrador vê todas, com o id de quem reservou, e cancela a da Ana
    listed = client.get(RESERVAS, params={"resource_id": rid}, headers=admin).json()
    assert [(r["id"], r["user_id"]) for r in listed] == [(reservation, str(ana.id))]
    assert cancel(client, admin, reservation).status_code == 200

    # A Ana vê a reserva cancelada e recebe o email a dizer que foi o administrador
    assert [r["status"] for r in mine(client, ana)] == ["CANCELLED"]
    with SessionLocal() as db:
        cancelled_by = db.scalar(text(
            "SELECT payload->>'cancelled_by' FROM notifications"
            " WHERE reservation_id = :id AND type = 'RESERVATION_CANCELLED'"), {"id": reservation})
    assert cancelled_by == "ADMIN"


# --------------------------------------------------------------------------- 3. fila de espera
def test_fluxo_fila_de_espera_recusa_e_aceita(client, admin, category, ana, rui, eva):
    day = next_monday()
    rid = create_resource(client, admin, category)
    reservation = book(client, ana.headers, rid, at(day, 10), at(day, 11)).json()["id"]

    # O Rui e a Eva querem o mesmo horário: conflito, por isso entram na fila
    assert book(client, rui.headers, rid, at(day, 10), at(day, 11)).status_code == 409
    rui_entry = join(client, rui, rid, at(day, 10), at(day, 11)).json()["id"]
    eva_entry = join(client, eva, rid, at(day, 10), at(day, 11)).json()["id"]
    assert (entry(client, rui, rui_entry)["position"], entry(client, eva, eva_entry)["position"]) == (1, 2)

    # A Ana cancela: o Rui (1.º) recebe a oferta; o horário continua ocupado para os outros
    cancel(client, ana.headers, reservation)
    assert entry(client, rui, rui_entry)["status"] == "OFFERED"
    assert busy(client, eva.headers, rid, day) == [("10:00", "11:00")]
    assert book(client, eva.headers, rid, at(day, 10), at(day, 11)).status_code == 409
    # A oferta aparece nas reservas do Rui como HELD
    assert [r["status"] for r in mine(client, rui)] == ["HELD"]

    # O Rui recusa: a oferta passa à Eva
    client.post(f"{FILA}/{rui_entry}/sair", headers=rui.headers)
    assert entry(client, eva, eva_entry)["status"] == "OFFERED"

    # A Eva aceita: fica com a reserva confirmada
    accepted = client.post(f"{FILA}/{eva_entry}/aceitar", headers=eva.headers)
    assert accepted.status_code == 200 and accepted.json()["status"] == "CONFIRMED"
    assert [r["status"] for r in mine(client, eva)] == ["CONFIRMED"]

    # O administrador vê a história completa deste horário
    statuses = sorted(r["status"] for r in client.get(RESERVAS, params={"resource_id": rid}, headers=admin).json())
    assert statuses == ["CANCELLED", "CANCELLED", "CONFIRMED"]  # Ana, oferta do Rui, Eva

    # Emails pendentes de cada um, pela ordem em que aconteceram
    assert emails(rui) == ["WAITLIST_JOINED", "WAITLIST_OFFERED"]
    assert emails(eva) == ["WAITLIST_JOINED", "WAITLIST_OFFERED", "RESERVATION_CREATED"]


def test_fluxo_oferta_sem_resposta_expira_e_passa_ao_seguinte(client, admin, category, ana, rui, eva):
    day = next_monday()
    rid = create_resource(client, admin, category)
    reservation = book(client, ana.headers, rid, at(day, 10), at(day, 11)).json()["id"]
    rui_entry = join(client, rui, rid, at(day, 10), at(day, 11)).json()["id"]
    eva_entry = join(client, eva, rid, at(day, 10), at(day, 11)).json()["id"]
    cancel(client, ana.headers, reservation)

    # O Rui não responde a tempo: o job de expiração corre (no Kubernetes, um CronJob)
    rui_hold = entry(client, rui, rui_entry)["reservation_id"]
    with SessionLocal() as db:
        db.execute(text("UPDATE reservations SET hold_expires_at = now() - interval '1 minute' WHERE id = :id"),
                   {"id": rui_hold})
        db.commit()
        waitlist.expire(db, datetime.now(timezone.utc))
        db.commit()

    assert entry(client, rui, rui_entry)["status"] == "EXPIRED"
    assert client.post(f"{FILA}/{rui_entry}/aceitar", headers=rui.headers).status_code == 409
    assert entry(client, eva, eva_entry)["status"] == "OFFERED"
    assert client.post(f"{FILA}/{eva_entry}/aceitar", headers=eva.headers).status_code == 200
    assert busy(client, rui.headers, rid, day) == [("10:00", "11:00")]