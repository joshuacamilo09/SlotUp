"""Gráficos do benchmark para o relatório (lê resultados/benchmark.csv).

Uso:  python graficos.py   ->  resultados/benchmark_nos.png e resultados/benchmark_tempo.png
Precisa do matplotlib (pip install -r requirements-dev.txt); a API não precisa dele.
"""
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # desenha direto para arquivo, sem abrir janela
import matplotlib.pyplot as plt  # noqa: E402 (tem de vir depois do use)

PASTA = Path("resultados")
TITULOS = {"A": "A) Melhor solução", "B": "B) Provar que não há solução"}
# Mesmas cores e marcadores em todos os gráficos; a busca completa (FC+MRV) em destaque
ESTILO = {"BT": ("#9aa0a6", "o"), "BT+FC": ("#e8710a", "s"), "BT+MRV": ("#1a73e8", "^"), "BT+FC+MRV": ("#188038", "D")}


def ler() -> list[dict]:
    with open(PASTA / "benchmark.csv", encoding="utf-8") as arquivo:
        return list(csv.DictReader(arquivo))  # cada linha vira um dict {coluna: valor}


def grafico(linhas: list[dict], coluna: str, rotulo: str, arquivo: str):
    """Um painel por experimento; eixo y em escala log, porque a busca simples cresce muito depressa."""
    fig, paineis = plt.subplots(1, len(TITULOS), figsize=(11, 4.2), sharey=True)
    for painel, (exp_id, titulo) in zip(paineis, TITULOS.items()):
        for config, (cor, marcador) in ESTILO.items():
            pontos = [l for l in linhas if l["experimento"] == exp_id and l["config"] == config]
            x = [int(l["atividades"]) for l in pontos]
            y = [max(float(l[coluna]), 0.01) for l in pontos]  # log não aceita 0
            painel.plot(x, y, color=cor, marker=marcador, linewidth=2.2 if config == "BT+FC+MRV" else 1.5, label=config)
        painel.set_xticks(x)  # só números inteiros no eixo x (não existe "3,5 atividades")
        painel.set_title(titulo)
        painel.set_xlabel("Atividades no pedido (com a vaga)")
        painel.set_yscale("log")
        painel.grid(True, which="major", alpha=0.3)
    paineis[0].set_ylabel(rotulo)
    paineis[0].legend(frameon=False)
    fig.tight_layout()
    fig.savefig(PASTA / arquivo, dpi=200)
    plt.close(fig)
    print(f"Gravado {PASTA / arquivo}")


if __name__ == "__main__":
    linhas = ler()
    grafico(linhas, "media_nos", "Nós explorados (média, escala log)", "benchmark_nos.png")
    grafico(linhas, "media_ms", "Tempo da busca em ms (média, escala log)", "benchmark_tempo.png")