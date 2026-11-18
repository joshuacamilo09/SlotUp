"""Worker: envio dos emails da tabela notifications e expiração das ofertas da fila.

O envio por SMTP é trocado por um "carteiro falso" que guarda os emails numa lista,
ou que falha de propósito. Assim os testes não precisam de servidor de email.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app import emails, worker
from app.config import get_settings
from app.database import SessionLocal
from tests.test_reservations import admin, at, book, category, create_resource, helpers, next_monday  # noqa: F401
from tests.test_reservations_manage import Person, ana, cancel, rui  # noqa: F401
from tests.test_waitlist import busy_slot, entry, eva, join, reservation_status  # noqa: F401


class Carteiro:
    """Guarda os emails em vez de os enviar. Com falhar=True, falha sempre."""

    def __init__(self, falhar=False):
        self.enviados, self.falhar = [], falhar

    def __call__(self, message):
        if self.falhar:
            raise ConnectionRefusedError("servidor de email em baixo")
        self.enviados.append(message)


def ids_of(where: str, **params) -> list:
    with SessionLocal() as db:
        return list(db.scalars(text(f"SELECT id FROM notifications WHERE {where}"), params).all())


def notification(nid) -> dict:
    with SessionLocal() as db:
        row = db.execute(text("SELECT status, attempts, last_error, next_attempt_at, sent_at FROM notifications "
                              "WHERE id = :id"), {"id": nid}).mappings().one()
        return dict(row)


def send(ids, carteiro, now=None):
    with SessionLocal() as db:
        return emails.send_pending(db, now or datetime.now(timezone.utc), get_settings(), carteiro, only_ids=ids)


@pytest.fixture
def quatro_eventos(client, busy_slot, ana, eva):
    """Gera os 4 eventos: reserva criada (busy_slot), fila, cancelamento e oferta."""
    entry_id = join(client, eva, busy_slot["rid"], busy_slot["start"], busy_slot["end"]).json()["id"]
    assert cancel(client, ana.headers, busy_slot["reservation"]).status_code == 200  # oferta para a Eva
    return ids_of("reservation_id = :r OR waitlist_entry_id = :e", r=busy_slot["reservation"], e=entry_id)


# --------------------------------------------------------------------------- envio
def test_envia_os_quatro_eventos(quatro_eventos, ana, eva):
    carteiro = Carteiro()
    assert send(quatro_eventos, carteiro) == (4, 0)

    por_destino = {(m["To"], m["Subject"].split(":")[0]) for m in carteiro.enviados}
    assert por_destino == {
        (ana.email, "Reserva confirmada"),
        (ana.email, "Reserva cancelada"),
        (eva.email, "Está na fila de espera"),
        (eva.email, "O horário ficou livre"),
    }
    for nid in quatro_eventos:
        estado = notification(nid)
        assert estado["status"] == "SENT" and estado["sent_at"] is not None and estado["attempts"] == 1


def test_email_usa_a_hora_local(client, admin, category, ana):
    day = next_monday()
    rid = create_resource(client, admin, category)
    reservation = book(client, ana.headers, rid, at(day, 10), at(day, 11, 30)).json()["id"]
    carteiro = Carteiro()
    send(ids_of("reservation_id = :r", r=reservation), carteiro)

    corpo = carteiro.enviados[0].get_content()
    assert "10:00 – 11:30" in corpo and day.strftime("%d/%m/%Y") in corpo


def test_ja_enviado_nao_volta_a_ser_enviado(quatro_eventos):
    send(quatro_eventos, Carteiro())
    segundo = Carteiro()
    assert send(quatro_eventos, segundo) == (0, 0)
    assert segundo.enviados == []


# --------------------------------------------------------------------------- falhas
def test_falha_fica_pendente_e_tenta_mais_tarde(quatro_eventos):
    now = datetime.now(timezone.utc)
    assert send(quatro_eventos, Carteiro(falhar=True), now) == (0, 4)

    estado = notification(quatro_eventos[0])
    assert estado["status"] == "PENDING" and estado["attempts"] == 1
    assert "ConnectionRefusedError" in estado["last_error"]
    assert estado["next_attempt_at"] >= now + timedelta(seconds=29)

    # Antes da hora da nova tentativa, não tenta outra vez
    assert send(quatro_eventos, Carteiro(), now + timedelta(seconds=5)) == (0, 0)
    # Quando a hora chega, envia
    assert send(quatro_eventos, Carteiro(), now + timedelta(seconds=31)) == (4, 0)


def test_depois_do_maximo_de_tentativas_fica_failed(quatro_eventos):
    nid = quatro_eventos[:1]
    now = datetime.now(timezone.utc)
    for tentativa in range(get_settings().email_max_attempts):
        send(nid, Carteiro(falhar=True), now + timedelta(hours=2 * tentativa))
    assert notification(nid[0])["status"] == "FAILED"
    # FAILED não volta a ser tentado
    assert send(nid, Carteiro(), now + timedelta(days=1)) == (0, 0)


def test_tipo_desconhecido_nao_rebenta_o_worker():
    with pytest.raises(ValueError):
        emails.build_message(type("N", (), {"type": "OUTRO", "payload": {}, "recipient_email": "x@y.pt"})(),
                             get_settings())


# --------------------------------------------------------------------------- vagas seguradas na fila
def test_worker_faz_expirar_a_oferta_e_passa_ao_seguinte(client, busy_slot, ana, eva, rui, monkeypatch):
    """A Eva e o Rui estão na fila. A oferta da Eva expira: o worker cancela-a e oferece ao Rui."""
    e_eva = join(client, eva, busy_slot["rid"], busy_slot["start"], busy_slot["end"]).json()["id"]
    e_rui = join(client, rui, busy_slot["rid"], busy_slot["start"], busy_slot["end"]).json()["id"]
    cancel(client, ana.headers, busy_slot["reservation"])
    oferta_eva = entry(client, eva, e_eva)["reservation_id"]
    assert entry(client, rui, e_rui)["status"] == "WAITING"

    with SessionLocal() as db:   # os 15 minutos da Eva passaram
        db.execute(text("UPDATE reservations SET hold_expires_at = now() - interval '1 minute' WHERE id = :id"),
                   {"id": oferta_eva})
        db.commit()

    # Só interessa a parte da fila: o envio dos emails fica de fora deste teste
    monkeypatch.setattr(worker.emails, "send_pending", lambda *a, **k: (0, 0))
    feito = worker.tick(get_settings(), Carteiro())

    assert feito["ofertas_expiradas"] >= 1
    assert reservation_status(oferta_eva) == "CANCELLED"
    assert entry(client, eva, e_eva)["status"] == "EXPIRED"
    assert entry(client, rui, e_rui)["status"] == "OFFERED"