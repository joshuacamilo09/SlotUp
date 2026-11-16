"""Benchmark do CSP: compara backtracking puro, com FC, com MRV e com os dois.

Gera cenários aleatórios REPRODUZÍVEIS (a mesma semente dá sempre o mesmo cenário)
e mede quantos nós a busca visita e quanto tempo demora.

Uso:
    python3 benchmark.py                      # grava em resultados/benchmark.csv
    python3 benchmark.py --saida outro.csv
"""
import argparse
import csv  # para gravar os resultados numa tabela que abre no Excel
import random
import statistics  # para a média
from datetime import datetime
from pathlib import Path

from app.csp.modelo import montar_problema
from app.csp.solver import resolver

DIA = "2026-11-18"
AGORA = datetime(2026, 11, 17, 9, 0)  # fixo: o benchmark dá o mesmo resultado em qualquer dia
SEMENTES = range(20)                  # 20 cenários por tamanho

# (nome no relatório, usar_fc, usar_mrv)
CONFIGS = [("BT", False, False), ("BT+FC", True, False), ("BT+MRV", False, True), ("BT+FC+MRV", True, True)]

# tipo: (quantidade de recursos, abre às, fecha às, capacidade)
TIPOS = {"mesa": (6, 8, 20, 1), "sala": (4, 8, 20, 8), "padel": (2, 7, 22, 4), "personal": (2, 7, 22, 1), "vaga": (3, 0, 24, 1)}

# Os pedidos vão sendo tirados desta lista, por ordem: (tipo, duração em min)
MODELOS_PEDIDO = [("mesa", 240), ("sala", 60), ("padel", 90), ("personal", 60),
                  ("sala", 30), ("mesa", 120), ("sala", 45), ("padel", 60)]


def hhmm(minutos: int) -> str:
    """Minutos -> 'HH:MM' (24:00 vira 23:59, porque a coluna time não aceita 24:00)."""
    minutos = min(minutos, 23 * 60 + 59)
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def gerar_cenario(semente: int, n_pedidos: int, ocupacao: float, ocupacao_vagas: float) -> dict:
    """Cria um cenário no mesmo formato de dados/cenario_basico.json.

    ocupacao: probabilidade de cada bloco de tempo de um recurso já estar reservado.
    """
    rng = random.Random(semente)  # gerador próprio: não depende do resto do programa
    recursos, busy = [], []

    for tipo, (quantidade, abre, fecha, capacidade) in TIPOS.items():
        for i in range(1, quantidade + 1):
            rid = f"{tipo}-{i}"
            recursos.append({
                "id": rid, "name": rid, "resource_type": tipo, "capacity": capacidade,
                "schedule": [{"open_time": hhmm(abre * 60), "close_time": hhmm(fecha * 60)}],
            })
            # Percorre o dia em blocos de 30 a 120 min e "reserva" alguns ao acaso
            prob = ocupacao_vagas if tipo == "vaga" else ocupacao
            t = abre * 60
            while t < fecha * 60 - 60:
                duracao = rng.choice([30, 60, 90, 120])
                if rng.random() < prob:  # rng.random() dá um número entre 0 e 1
                    busy.append({"resource_id": rid, "start": hhmm(t), "end": hhmm(min(t + duracao, fecha * 60))})
                t += duracao

    pedidos = [{"id": "estacionamento", "resource_type": "vaga", "covers_day": True}]
    for i in range(n_pedidos):
        tipo, duracao = MODELOS_PEDIDO[i % len(MODELOS_PEDIDO)]  # % volta ao início da lista
        inicio = rng.randrange(9 * 60, 18 * 60, 15)  # horário pedido entre 9h e 18h, de 15 em 15
        pedidos.append({"id": f"p{i + 1}-{tipo}", "resource_type": tipo,
                        "duration_min": duracao, "desired_start": hhmm(inicio)})

    return {"day": DIA, "requests": pedidos, "resources": recursos, "busy": busy}


def experimento(nome: str, tamanhos, ocupacao_vagas: float, otimizar: bool, escritor) -> None:
    """Corre as 4 configurações em todos os tamanhos e imprime uma tabela."""
    print(f"\n{nome}")
    print(f"{'pedidos':>7} | " + " | ".join(f"{c[0]:>24}" for c in CONFIGS))

    for n in tamanhos:
        colunas = []
        for config, fc, mrv in CONFIGS:
            nos, tempos, limites, com_solucao = [], [], 0, 0
            for semente in SEMENTES:
                cenario = gerar_cenario(semente, n, 0.5, ocupacao_vagas)
                problema = montar_problema(cenario, agora=AGORA)
                solucao, _, stats = resolver(problema, usar_fc=fc, usar_mrv=mrv, otimizar=otimizar)
                nos.append(stats.nos)
                tempos.append(stats.tempo_ms)
                limites += stats.limite_atingido  # True conta como 1, False como 0
                com_solucao += solucao is not None

            media_nos, media_ms = statistics.mean(nos), statistics.mean(tempos)
            marca = f"*{limites}" if limites else ""
            colunas.append(f"{media_nos:>10.0f} nós {media_ms:>7.1f} ms{marca:>3}")
            escritor.writerow([nome, n + 1, config, round(media_nos), round(media_ms, 2),
                               limites, com_solucao, len(SEMENTES)])

        # n + 1 porque o estacionamento também é um pedido
        print(f"{n + 1:>7} | " + " | ".join(colunas), flush=True)  # flush: mostra já, sem esperar


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark do CSP do SlotUp")
    parser.add_argument("--saida", default="resultados/benchmark.csv")
    args = parser.parse_args()

    # Cria a pasta resultados/ se ainda não existir
    Path(args.saida).parent.mkdir(parents=True, exist_ok=True)

    # with: fecha o arquivo sozinho no fim, mesmo se der erro
    with open(args.saida, "w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.writer(arquivo)
        escritor.writerow(["experimento", "pedidos", "config", "media_nos", "media_ms",
                           "limite_atingido", "com_solucao", "cenarios"])
        experimento("A) Melhor solução (branch and bound), cenários com solução",
                    range(2, 8), ocupacao_vagas=0.1, otimizar=True, escritor=escritor)
        experimento("B) Provar que não há solução (vagas muito ocupadas)",
                    range(2, 7), ocupacao_vagas=0.6, otimizar=False, escritor=escritor)

    print(f"\n* = nº de cenários (em 20) que atingiram o limite de nós: a média está subestimada")
    print(f"CSV gravado em {args.saida}")


if __name__ == "__main__":
    main()