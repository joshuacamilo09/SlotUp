"""Regras rígidas do CSP, uma classe por regra.

Cada regra tem um identificador (id), um nome e uma mensagem próprios, e
implementa só o "gancho" (hook) do seu tipo:

- tipo "pedido":  verificar_pedido(problema)                      -> antes da busca, olha o pedido inteiro
- tipo "unaria":  permite(problema, pedido, recurso, inicio, fim) -> monta os domínios (consistência de nó)
- tipo "binaria": compativeis(problema, a, b)                     -> durante a busca (forward checking)
- tipo "global":  vaga_valida(problema, vaga, atribuicao)         -> durante a busca, com todas as atividades

Ligar ou desligar uma regra é tirá-la ou pô-la na lista do modo, em ATIVAS_POR_MODO.
O booking NÃO escolhe regras no pedido: a lista fica no código.
"""
from app.csp.modelo import FOLGA_DESLOCAMENTO_MIN, PASSO_MIN, duracao_permitida, livre_com_folga, sobrepoe
from app.csp.restricoes import intervalo_estacionamento

ANTECEDENCIA_MAX_DIAS = 30  # igual ao booking


class Regra:
    """Base de todas as regras. Cada regra muda só o que precisa."""

    id = ""        # identificador estável: vai no failure.rule_id do contrato
    nome = ""      # nome curto, para pessoas
    mensagem = ""  # frase usada quando é esta regra que impede o plano
    tipo = ""      # "pedido", "unaria", "binaria" ou "global"

    def explicar(self, pedido) -> str:
        """Mensagem para o failure. As regras podem mostrar dados do pedido."""
        return f"{self.nome}: {self.mensagem}"


# --------------------------------------------------------------------------- unárias
# A ORDEM conta: o diagnóstico diz que a culpa é da ÚLTIMA regra desta lista que
# eliminou alguma opção. As regras "estruturais" vêm primeiro e as que dependem da
# ocupação vêm no fim.
class Capacidade(Regra):
    id = "CAPACIDADE"
    nome = "Capacidade"
    mensagem = "nenhum recurso deste tipo comporta todas as pessoas."
    tipo = "unaria"

    def permite(self, problema, pedido, recurso, inicio, fim) -> bool:
        return recurso["capacity"] >= pedido.people

    def explicar(self, pedido) -> str:
        return f"{self.nome}: nenhum recurso do tipo '{pedido.resource_type}' comporta {pedido.people} pessoas."


class Duracao(Regra):
    id = "DURACAO"
    nome = "Duração mínima e máxima"
    mensagem = "nenhum recurso deste tipo aceita esta duração."
    tipo = "unaria"

    def permite(self, problema, pedido, recurso, inicio, fim) -> bool:
        if inicio is None:
            return True  # a vaga não tem duração própria
        minimo, maximo = duracao_permitida(recurso)
        return minimo <= fim - inicio <= maximo

    def explicar(self, pedido) -> str:
        return f"{self.nome}: nenhum recurso do tipo '{pedido.resource_type}' aceita {pedido.duration_min} min."


class Multiplo15(Regra):
    id = "MULTIPLO_15"
    nome = "Múltiplos de 15 minutos"
    mensagem = "o início e a duração têm de ser múltiplos de 15 minutos."
    tipo = "unaria"

    def permite(self, problema, pedido, recurso, inicio, fim) -> bool:
        if inicio is None:
            return True
        # % é o resto da divisão: 0 quer dizer que é múltiplo
        return inicio % PASSO_MIN == 0 and (fim - inicio) % PASSO_MIN == 0


class HorarioAbertura(Regra):
    id = "HORARIO_ABERTURA"
    nome = "Horário de abertura"
    mensagem = "o recurso está fechado nesse dia ou a atividade não cabe no horário de abertura."
    tipo = "unaria"

    def permite(self, problema, pedido, recurso, inicio, fim) -> bool:
        if inicio is None:
            return True  # a vaga é verificada na VAGA_COBRE_O_DIA
        # As janelas DAQUELE dia (o modelo já as tirou do horário semanal)
        return any(abre <= inicio and fim <= fecha for abre, fecha in problema.aberturas[recurso["id"]])


class SemPassado(Regra):
    id = "SEM_PASSADO"
    nome = "Sem passado"
    mensagem = "o dia ou o horário pedido já passou."
    tipo = "unaria"

    def permite(self, problema, pedido, recurso, inicio, fim) -> bool:
        hoje = problema.agora.date()
        if problema.day != hoje:
            return problema.day > hoje  # outro dia: só vale se for no futuro
        if inicio is None:
            return True  # a vaga para hoje: o horário dela vem das atividades
        agora_min = problema.agora.hour * 60 + problema.agora.minute
        return inicio >= agora_min


class Antecedencia(Regra):
    id = "ANTECEDENCIA"
    nome = "Antecedência máxima"
    mensagem = f"só é possível planear até {ANTECEDENCIA_MAX_DIAS} dias à frente."
    tipo = "unaria"

    def permite(self, problema, pedido, recurso, inicio, fim) -> bool:
        # date - date dá um intervalo; .days é o número de dias dele
        return (problema.day - problema.agora.date()).days <= ANTECEDENCIA_MAX_DIAS


class RecursoLivre(Regra):
    id = "RECURSO_LIVRE"
    nome = "Recurso livre"
    mensagem = "o recurso já está reservado nesse horário."
    tipo = "unaria"

    def permite(self, problema, pedido, recurso, inicio, fim) -> bool:
        if inicio is None:
            return True
        # Ocupação "crua", sem folga: as reservas CONFIRMED e HELD
        return not any(sobrepoe(inicio, fim, b0, b1) for b0, b1 in problema.busy.get(recurso["id"], []))


class IntervaloRecurso(Regra):
    id = "INTERVALO_RECURSO"
    nome = "Intervalo entre reservas"
    mensagem = "falta o intervalo de limpeza ou preparação entre reservas seguidas do recurso."
    tipo = "unaria"

    def permite(self, problema, pedido, recurso, inicio, fim) -> bool:
        if inicio is None:
            return True
        return livre_com_folga(problema, recurso["id"], inicio, fim)


# --------------------------------------------------------------------------- pedido
class UmaVagaPorDia(Regra):
    id = "UMA_VAGA_POR_DIA"
    nome = "Uma vaga por dia"
    mensagem = "no máximo 1 vaga de estacionamento por dia."
    tipo = "pedido"

    def verificar_pedido(self, problema) -> bool:
        # sum() de booleanos conta os True
        return sum(p.covers_day for p in problema.pedidos.values()) <= 1


# --------------------------------------------------------------------------- binária
class SemSobreposicao(Regra):
    id = "SEM_SOBREPOSICAO"
    nome = "Sem sobreposição"
    mensagem = "as atividades não cabem todas no mesmo dia sem se sobreporem."
    tipo = "binaria"

    def compativeis(self, problema, a, b) -> bool:
        if a.inicio is None or b.inicio is None:
            return True  # a vaga fica "por baixo" das atividades
        # 10 min para o usuário ir de uma atividade para a outra
        return not sobrepoe(a.inicio, a.fim, b.inicio - FOLGA_DESLOCAMENTO_MIN, b.fim + FOLGA_DESLOCAMENTO_MIN)


# --------------------------------------------------------------------------- global
class VagaCobreODia(Regra):
    id = "VAGA_COBRE_O_DIA"
    nome = "Vaga cobre o dia"
    mensagem = "nenhuma vaga fica livre durante todo o dia planeado."
    tipo = "global"

    def vaga_valida(self, problema, vaga, atribuicao) -> bool:
        intervalo = intervalo_estacionamento(atribuicao)
        if intervalo is None:
            return True  # só pediu estacionamento: não há nada a cobrir
        inicio, fim = intervalo
        dentro = any(a <= inicio and fim <= f for a, f in problema.aberturas.get(vaga.resource_id, []))
        return dentro and livre_com_folga(problema, vaga.resource_id, inicio, fim)


# --------------------------------------------------------------------------- registro
# Todas as regras, pela ordem em que são aplicadas (ver o comentário das unárias)
TODAS = [
    Capacidade(), Duracao(), Multiplo15(), HorarioAbertura(), SemPassado(), Antecedencia(),
    RecursoLivre(), IntervaloRecurso(), UmaVagaPorDia(), SemSobreposicao(), VagaCobreODia(),
]
POR_ID = {r.id: r for r in TODAS}  # id -> regra

# Ligar ou desligar uma regra num modo = pôr ou tirar o id desta lista
ATIVAS_POR_MODO = {
    "plan": [r.id for r in TODAS],
    # suggest: uma só atividade, por isso as regras entre atividades não se aplicam
    "suggest": [r.id for r in TODAS if r.id not in {"SEM_SOBREPOSICAO", "UMA_VAGA_POR_DIA", "VAGA_COBRE_O_DIA"}],
}


def regras_ativas(modo: str, desligar: set[str] | None = None) -> list[Regra]:
    """As regras ligadas num modo. `desligar` serve aos testes e ao benchmark."""
    desligar = desligar or set()
    return [POR_ID[i] for i in ATIVAS_POR_MODO[modo] if i not in desligar]