"""Dados de exemplo do booking-service (SÓ para desenvolvimento e demo).

Deixa o booking_db sempre no mesmo ponto de partida:
  1. apaga TODAS as reservas, a fila de espera, as notificações e os recursos;
  2. deixa só as 3 categorias base (Coworking, Estacionamento, Desporto), ativas;
  3. recria os recursos de exemplo, com ids FIXOS (iguais em todas as execuções).

Rodar:  docker compose exec booking python -m app.seed
"""
import os
import sys
import uuid
from datetime import time

from sqlalchemy import delete, select, text, update

from app.database import SessionLocal
from app.models import AvailabilityRule, Category, Resource

SEED_NAMESPACE = uuid.UUID("5e1f0d2a-7c3b-4b8e-9a61-2d4c8f0b3a17")

BASE_CATEGORIES = ("Coworking", "Estacionamento", "Desporto")

SEG_A_SEX = range(0, 5)
SEG_A_SAB = range(0, 6)
TODOS_OS_DIAS = range(0, 7)

def schedule(days, open_time: time, close_time: time) -> list[tuple[int, time, time]]:
    return [(day, open_time, close_time) for day in days]

# (categoria, nome, tipo, capacidade, atributos, horário)
RESOURCES = [
    # --- Coworking: mesas (1 pessoa) e salas (o grupo reserva a sala inteira)
    ("Coworking", "Mesa 1", "mesa", 1, {"monitor": True}, schedule(SEG_A_SEX, time(8), time(20))),
    ("Coworking", "Mesa 2", "mesa", 1, {"monitor": True}, schedule(SEG_A_SEX, time(8), time(20))),
    ("Coworking", "Mesa 3", "mesa", 1, {"monitor": False}, schedule(SEG_A_SEX, time(8), time(20))),
    ("Coworking", "Sala de Reunião A", "sala", 4, {"tem_projetor": False}, schedule(SEG_A_SEX, time(8), time(20))),
    ("Coworking", "Sala de Reunião B", "sala", 8, {"tem_projetor": True}, schedule(SEG_A_SEX, time(8), time(20))),
    ("Coworking", "Sala de Reunião C", "sala", 12, {"tem_projetor": True}, schedule(SEG_A_SEX, time(8), time(20))),
    # --- Desporto
    ("Desporto", "Quadra de Padel 1", "quadra", 4, {"coberta": True}, schedule(TODOS_OS_DIAS, time(7), time(22))),
    ("Desporto", "Personal Trainer 1", "personal", 1, {}, schedule(SEG_A_SAB, time(7), time(21))),
    ("Desporto", "Personal Trainer 2", "personal", 1, {}, schedule(SEG_A_SAB, time(7), time(21))),
    # Aulas: só abrem nos horários da aula (capacidade com várias pessoas: ver tarefa "Criar reserva")
    ("Desporto", "Yoga Manhã", "aula", 15, {}, schedule((0, 2, 4), time(7), time(8))),          # seg, qua, sex
    ("Desporto", "Yoga Fim de Tarde", "aula", 15, {}, schedule((1, 3), time(18, 30), time(19, 30))),  # ter, qui
    # --- Estacionamento: abertas o dia todo (23:59 porque o fecho tem de ser depois da abertura)
    ("Estacionamento", "Vaga Carro 1", "vaga_carro", 1, {"eletrico": False}, schedule(TODOS_OS_DIAS, time(0), time(23, 59))),
    ("Estacionamento", "Vaga Carro 2", "vaga_carro", 1, {"eletrico": True}, schedule(TODOS_OS_DIAS, time(0), time(23, 59))),
    ("Estacionamento", "Vaga Mota 1", "vaga_mota", 1, {}, schedule(TODOS_OS_DIAS, time(0), time(23, 59))),
    ("Estacionamento", "Vaga Mota 2", "vaga_mota", 1, {}, schedule(TODOS_OS_DIAS, time(0), time(23, 59))),
]

def main() -> None:
    if os.environ.get("SEED_ENABLED", "").lower() != "true":
        sys.exit("SEED_ENABLED não está ativo: o seed só roda em desenvolvimento.")

    with SessionLocal() as db:
        db.execute(text("TRUNCATE reservations, waitlist_entries, notifications, availability_rules, resources CASCADE"))

        found ={c.name: c for c in db.scalars(select(Category))}
        missing = set(BASE_CATEGORIES) - found.keys()
        if missing:
            sys.exit(f"Faltam categorias {sorted(missing)}: rode as migrações (booking-migrate) primeiro.")
        db.execute(delete(Category).where(Category.name.not_in(BASE_CATEGORIES)))
        db.execute(update(Category).values(is_active=True))

        for category, name, resource_type, capacity, attributes, rules in RESOURCES:
            db.add(
                Resource(
                    id=uuid.uuid5(SEED_NAMESPACE, name),
                    category_id=found[category].id,
                    name=name,
                    resource_type=resource_type,
                    capacity=capacity,
                    attributes=attributes,
                    rules=[AvailabilityRule(weekday=d, open_time=o, close_time=c) for d, o, c in rules],
                )
            )

        db.commit()

    print(f"OK: {len(RESOURCES)} recursos criados em {len(BASE_CATEGORIES)} categorias. Reservas e fila de espera vazias.")

if __name__ == "__main__":
    main()