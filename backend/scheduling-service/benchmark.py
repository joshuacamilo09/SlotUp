"""Benchmark do CSP: busca simples (BT) contra a busca com heurísticas (FC, MRV).

Corre os MESMOS cenários com as 4 combinações e mede, em média, quantos nós a busca
explorou e quanto tempo levou. Grava:
  resultados/benchmark.csv  os números (o graficos.py lê daqui)
  resultados/benchmark.md   as tabelas prontas para o relatório

Uso:  python benchmark.py         (demora alguns minutos: a busca simples é lenta)
"""
import argparse
import csv
import math
import random
import statistics  # statistics.mean = média
from datetime import datetime
from pathlib import Path

from app.csp.modelo import montar_problema
from app.csp.solver import LIMITE_NOS_PADRAO, resolver

DIA = "2026-11-18"
AGORA = datetime(2026, 11, 17, 9, 0)
SEMENTES = range(20)  # 20 cenários aleatórios por tamanho (sempre os mesmos: a semente fixa o sorteio)
# (nome, usar_fc, usar_mrv)
CONFIGS = [("BT", False, False), ("BT+FC", True, False), ("BT+MRV", False, True), ("BT+FC+MRV", True, True)]
# tipo: (quantos recursos, abre, fecha, capacidade)
TIPOS = {"mesa": (6, 8, 20, 1), "sala": (4, 8, 20, 8), "quadra": (2, 7, 22, 4), "personal": (2, 7, 22, 1), "vaga_carro": (3, 0, 24, 1)}
# (mínima, máxima) de cada tipo, como no seed do booking
LIMITES = {"mesa": (15, 720), "sala": (15, 240), "quadra": (60, 90), "personal": (60, 60), "vaga_carro": (15, 1440)}
# As atividades de cada cenário saem desta lista, por ordem: (tipo, duração)
MODELOS_PEDIDO = [("mesa", 240), ("sala", 60), ("quadra", 90), ("personal", 60), ("sala", 30), ("mesa", 120), ("sala", 45), ("quadra", 60)]

EXPERIMENTOS = [
    # (id, título, tamanhos, ocupação das vagas, otimizar)
    ("A", "Melhor solução (branch and bound), cenários com solução", range(2, 8), 0.1, True),
    ("B", "Provar que não há solução (vagas muito ocupadas)", range(2, 7), 0.6, False),
]


def hhmm(minutos):
    minutos = min(minutos, 23 * 60 + 59)
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def gerar_cenario(semente, n_pedidos, ocupacao, ocupacao_vagas):
    """Um cenário aleatório (mas repetível) no formato do contrato: recursos, ocupação e pedidos."""
    rng = random.Random(semente)  # gerador próprio: a mesma semente dá sempre o mesmo cenário
    recursos, busy = [], []
    for tipo, (quantidade, abre, fecha, capacidade) in TIPOS.items():
        for i in range(1, quantidade + 1):
            rid = f"{tipo}-{i}"
            minimo, maximo = LIMITES[tipo]
            recursos.append({"id": rid, "name": rid, "resource_type": tipo, "capacity": capacidade,
                             "schedule": [{"weekday": w, "open_time": hhmm(abre * 60), "close_time": hhmm(fecha * 60)}
                                          for w in range(7)],
                             "min_duration_min": minimo, "max_duration_min": maximo, "buffer_min": 10})
            # Ocupa blocos ao acaso ao longo do dia (prob = chance de cada bloco estar reservado)
            prob = ocupacao_vagas if tipo == "vaga_carro" else ocupacao
            t = abre * 60
            while t < fecha * 60 - 60:
                duracao = rng.choice([30, 60, 90, 120])
                if rng.random() < prob:
                    busy.append({"resource_id": rid, "start": hhmm(t), "end": hhmm(min(t + duracao, fecha * 60))})
                t += duracao
    pedidos = [{"id": "estacionamento", "resource_type": "vaga_carro", "covers_day": True, "people": 1}]
    for i in range(n_pedidos):
        tipo, duracao = MODELOS_PEDIDO[i % len(MODELOS_PEDIDO)]
        inicio = rng.randrange(9 * 60, 18 * 60, 15)
        pedidos.append({"id": f"p{i + 1}-{tipo}", "resource_type": tipo, "duration_min": duracao,
                        "preferred_start": hhmm(inicio), "people": 1})
    return {"mode": "plan", "day": DIA, "now": AGORA.isoformat(), "activities": pedidos, "resources": recursos, "busy": busy}


def medir(n, ocupacao_vagas, otimizar, fc, mrv) -> dict:
    """Corre os 20 cenários de um tamanho com UMA configuração e devolve as médias."""
    nos, tempos, limites, com_solucao = [], [], 0, 0
    for semente in SEMENTES:
        problema = montar_problema(gerar_cenario(semente, n, 0.5, ocupacao_vagas), agora=AGORA)
        # limite_ms=math.inf: sem limite de tempo, para medir a busca inteira. O limite
        # de nós continua: a busca simples pode explodir e não queremos esperar horas.
        solucao, _, stats = resolver(problema, usar_fc=fc, usar_mrv=mrv, otimizar=otimizar, limite_ms=math.inf)
        nos.append(stats.nos)
        tempos.append(stats.tempo_ms)
        limites += stats.limite_atingido  # True conta como 1
        com_solucao += solucao is not None
    return {"media_nos": round(statistics.mean(nos)), "media_ms": round(statistics.mean(tempos), 2),
            "limite_atingido": limites, "com_solucao": com_solucao}


def tabela_md(titulo: str, linhas: list[dict]) -> str:
    """Uma tabela em Markdown: uma linha por tamanho, uma coluna por configuração."""
    nomes = [c[0] for c in CONFIGS]
    md = [f"### {titulo}", "", "| Atividades | " + " | ".join(nomes) + " |", "|---:|" + "---:|" * len(nomes)]
    for atividades in sorted({l["atividades"] for l in linhas}):
        celulas = []
        for nome in nomes:
            l = next(x for x in linhas if x["atividades"] == atividades and x["config"] == nome)
            marca = " *" if l["limite_atingido"] else ""  # * = algum cenário bateu no limite de nós
            celulas.append(f"{l['media_nos']:,} nós · {l['media_ms']:.1f} ms{marca}".replace(",", " "))
        md.append(f"| {atividades} | " + " | ".join(celulas) + " |")
    return "\n".join(md)


def main():
    parser = argparse.ArgumentParser(description="Benchmark do CSP do SlotUp")
    parser.add_argument("--saida", default="resultados")
    args = parser.parse_args()
    pasta = Path(args.saida)
    pasta.mkdir(parents=True, exist_ok=True)

    linhas = []
    for exp_id, titulo, tamanhos, ocupacao_vagas, otimizar in EXPERIMENTOS:
        print(f"\n{exp_id}) {titulo}")
        for n in tamanhos:
            for config, fc, mrv in CONFIGS:
                # n atividades com horário + a vaga de estacionamento = n + 1 atividades
                linha = {"experimento": exp_id, "atividades": n + 1, "config": config,
                         **medir(n, ocupacao_vagas, otimizar, fc, mrv)}
                linhas.append(linha)
                print(f"  {n + 1} atividades  {config:<10} {linha['media_nos']:>9} nós  {linha['media_ms']:>9.1f} ms"
                      + (f"  (limite em {linha['limite_atingido']})" if linha["limite_atingido"] else ""), flush=True)

    with open(pasta / "benchmark.csv", "w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=list(linhas[0]))  # DictWriter: escreve dicts
        escritor.writeheader()
        escritor.writerows(linhas)

    partes = ["# Benchmark do CSP", "",
              f"Média de {len(SEMENTES)} cenários aleatórios por tamanho (sementes fixas). "
              "BT = backtracking simples; FC = forward checking; MRV = menor domínio primeiro.", ""]
    for exp_id, titulo, *_ in EXPERIMENTOS:
        partes += [tabela_md(f"{exp_id}) {titulo}", [l for l in linhas if l["experimento"] == exp_id]), ""]
    partes.append(f"\\* algum cenário atingiu o limite de {LIMITE_NOS_PADRAO:,} nós: a média real é maior.".replace(",", " "))
    (pasta / "benchmark.md").write_text("\n".join(partes) + "\n", encoding="utf-8")
    print(f"\nGravado em {pasta}/benchmark.csv e {pasta}/benchmark.md. Gráficos: python graficos.py")


if __name__ == "__main__":
    main()