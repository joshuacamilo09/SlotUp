"""Demonstração do CSP do SlotUp pelo terminal (para a discussão do Milestone 2).

Uso:
    python3 demo.py                              # usa dados/cenario_basico.json
    python3 demo.py dados/outro_cenario.json     # usa outro cenário
"""
import argparse  # lê os argumentos da linha de comando
import json
from datetime import date, datetime, time, timedelta
from pathlib import Path

from app.csp.custo import detalhar_custo
from app.csp.modelo import Problema, montar_problema, para_hhmm
from app.csp.solver import formatar_solucao, resolver

LINHA = "─" * 64  # multiplicar uma string repete-a 64 vezes


def titulo(texto: str) -> None:
    print(f"\n{LINHA}\n {texto}\n{LINHA}")


def mostrar(problema: Problema, solucao: dict, nomes: dict) -> None:
    """Imprime a solução, uma linha por serviço, por ordem de início."""
    for item in formatar_solucao(problema, solucao):
        # :<15 alinha o texto à esquerda numa coluna de 15 caracteres
        print(f"  {item['start']}–{item['end']}  {item['request_id']:<15} {nomes[item['resource_id']]}")


def main() -> None:
    # nargs="?": o argumento é opcional; sem ele, usa o default
    parser = argparse.ArgumentParser(description="Demonstração do CSP do SlotUp")
    parser.add_argument("cenario", nargs="?", default="dados/cenario_basico.json")
    args = parser.parse_args()

    dados = json.loads(Path(args.cenario).read_text(encoding="utf-8"))
    dia = date.fromisoformat(dados["day"])
    # Na demo fingimos que "agora" é a véspera às 09:00. Assim o cenário funciona
    # em qualquer dia em que a demo for corrida (a R3 continua a valer na API).
    agora = datetime.combine(dia - timedelta(days=1), time(9, 0))
    problema = montar_problema(dados, agora=agora)
    nomes = {r["id"]: r["name"] for r in dados["resources"]}  # id -> nome legível

    # ---------------------------------------------------------------- 0. pedidos
    titulo(f"SlotUp · Planear o meu dia · {dia.strftime('%d/%m/%Y')}")
    for pid, p in problema.pedidos.items():
        if p.covers_day:
            print(f"  • {pid:<15} {p.resource_type:<6} o dia todo (R7)")
        else:
            hora = para_hhmm(p.desired_start) if p.desired_start is not None else "--:--"
            extra = f", {p.people} pessoas" if p.people > 1 else ""
            fav = f", favorito: {nomes.get(p.favorite_resource_id, p.favorite_resource_id)}" if p.favorite_resource_id else ""
            print(f"  • {pid:<15} {p.resource_type:<6} às {hora}, {p.duration_min} min{extra}{fav}")

    # ---------------------------------------------------------------- 1. domínios
    titulo("1. Domínios depois das restrições unárias (R1-R5, R9)")
    for pid, dominio in problema.dominios.items():
        print(f"  {pid:<15} {len(dominio):>4} opções")  # :>4 alinha à direita

    # ---------------------------------------------------------------- 2. primeira solução
    titulo("2. Primeira solução válida (só regras rígidas)")
    solucao, custo, stats = resolver(problema, otimizar=False)
    if solucao is None:
        print("  Sem solução: nenhuma combinação respeita todas as regras rígidas.")
        return  # não há mais nada para mostrar
    mostrar(problema, solucao, nomes)
    print(f"\n  Custo: {custo:.1f}  |  {stats.nos} nós")  # :.1f = 1 casa decimal

    # ---------------------------------------------------------------- 3. melhor solução
    titulo("3. Melhor solução (branch and bound com F1-F3)")
    solucao, custo, stats = resolver(problema)
    mostrar(problema, solucao, nomes)

    detalhe = detalhar_custo(problema, solucao)
    print("\n  Custo:")
    for pid, f1, f3 in detalhe["pedidos"]:  # desempacota cada tupla em 3 variáveis
        if f1 or f3:  # só mostra os pedidos que custaram alguma coisa
            print(f"    {pid:<15} F1 = {f1:>5.1f}   F3 = {f3:>5.1f}")
    print(f"    {'buracos no dia':<15} F2 = {detalhe['f2']:>5.1f}")
    print(f"    {'TOTAL':<15}      {detalhe['total']:>5.1f}")
    print(f"\n  {stats.nos} nós · {stats.solucoes} soluções · {stats.podas} podas · {stats.tempo_ms:.2f} ms")


# Só corre main() quando o arquivo é executado diretamente (python3 demo.py),
# e não quando é importado por outro arquivo
if __name__ == "__main__":
    main()