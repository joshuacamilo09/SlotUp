// ===== LISTA DA CATEGORIA =====
// Mostra os recursos de uma categoria (categoria.html?cat=coworking) com o estado
// de cada um no dia e horário escolhidos nos filtros.

const utilizador = requireAuth();   // sem sessão, vai para o login

// ===== DADOS FICTÍCIOS (por agora) =====
// Tudo o que vai vir da API está neste objeto, para ser trocado depois por fetch.
// Os nomes dos campos são provisórios: vão ser alinhados com o booking-service.
// "ocupados" repete-se todos os dias; "dia" em minhas/fila = dias a partir de hoje (0 = hoje).
const DADOS_FALSOS = {
  categorias: {
    coworking:      { name: "Coworking",      icon: "desk",          description: "Mesas individuais e salas de reunião" },
    estacionamento: { name: "Estacionamento", icon: "local_parking", description: "Vagas nos pisos -1 e -2" },
    desporto:       { name: "Desporto",       icon: "sports_tennis", description: "Ginásio, personal trainer, pilates e padel" },
  },
  recursos: [
    { id: 1,  category: "coworking", type: "Salas de reunião",  icon: "groups", name: "Sala Atlântico",    location: "Piso 2", capacity: "até 8 pessoas",  tags: ["Ecrã", "Videoconferência"],       ocupados: [["09:00", "10:30"], ["13:00", "14:30"], ["18:00", "19:00"]] },
    { id: 2,  category: "coworking", type: "Salas de reunião",  icon: "groups", name: "Sala Índico",       location: "Piso 2", capacity: "até 8 pessoas",  tags: ["Videoconferência", "Quadro"],     ocupados: [["08:30", "10:00"], ["14:00", "16:00"]] },
    { id: 3,  category: "coworking", type: "Salas de reunião",  icon: "groups", name: "Sala Báltico",      location: "Piso 3", capacity: "até 6 pessoas",  tags: ["Ecrã"],                           ocupados: [["09:00", "12:00"], ["13:00", "17:30"]] },
    { id: 4,  category: "coworking", type: "Salas de reunião",  icon: "groups", name: "Sala Mediterrâneo", location: "Piso 3", capacity: "até 12 pessoas", tags: ["Ecrã duplo", "Videoconferência"], ocupados: [["15:00", "18:00"]] },
    { id: 5,  category: "coworking", type: "Salas de reunião",  icon: "groups", name: "Sala Cáspio",       location: "Piso 4", capacity: "até 10 pessoas", tags: ["Ecrã", "Videoconferência"],       ocupados: [["12:00", "13:00"]] },
    { id: 6,  category: "coworking", type: "Mesas individuais", icon: "desk",   name: "Mesa 2.14", location: "Piso 2 · open space",      capacity: "1 pessoa", tags: ["Monitor"],           ocupados: [["08:00", "13:00"]] },
    { id: 7,  category: "coworking", type: "Mesas individuais", icon: "desk",   name: "Mesa 2.15", location: "Piso 2 · open space",      capacity: "1 pessoa", tags: ["Monitor", "Janela"], ocupados: [["14:00", "18:00"]] },
    { id: 8,  category: "coworking", type: "Mesas individuais", icon: "desk",   name: "Mesa 3.01", location: "Piso 3 · zona silenciosa", capacity: "1 pessoa", tags: ["Monitor"],           ocupados: [] },

    { id: 9,  category: "estacionamento", type: "Piso -1", icon: "directions_car", name: "Vaga P-012", location: "Piso -1", capacity: "Ligeiro", tags: ["Junto ao elevador"], ocupados: [["08:00", "18:00"]] },
    { id: 10, category: "estacionamento", type: "Piso -1", icon: "directions_car", name: "Vaga P-114", location: "Piso -1", capacity: "Ligeiro", tags: [],                    ocupados: [["08:00", "12:00"]] },
    { id: 11, category: "estacionamento", type: "Piso -1", icon: "ev_station",     name: "Vaga P-115", location: "Piso -1", capacity: "Ligeiro", tags: ["Carregador EV"],     ocupados: [] },
    { id: 12, category: "estacionamento", type: "Piso -2", icon: "ev_station",     name: "Vaga P-203", location: "Piso -2", capacity: "Ligeiro", tags: ["Carregador EV"],     ocupados: [["09:00", "17:00"]] },
    { id: 13, category: "estacionamento", type: "Piso -2", icon: "two_wheeler",    name: "Vaga P-204", location: "Piso -2", capacity: "Mota",    tags: [],                    ocupados: [["13:00", "19:00"]] },

    { id: 14, category: "desporto", type: "Padel",   icon: "sports_tennis",    name: "Quadra de padel 1",       location: "Exterior",            capacity: "4 jogadores",       tags: ["Iluminação"],            ocupados: [["12:00", "13:00"], ["18:00", "20:00"]] },
    { id: 15, category: "desporto", type: "Padel",   icon: "sports_tennis",    name: "Quadra de padel 2",       location: "Exterior",            capacity: "4 jogadores",       tags: ["Iluminação", "Coberta"], ocupados: [["17:00", "18:30"]] },
    { id: 16, category: "desporto", type: "Ginásio", icon: "fitness_center",   name: "Personal trainer · Rui",  location: "Ginásio",             capacity: "Sessão individual", tags: ["Força", "Mobilidade"],   ocupados: [["08:00", "10:00"], ["17:00", "19:00"]] },
    { id: 17, category: "desporto", type: "Ginásio", icon: "fitness_center",   name: "Personal trainer · Inês", location: "Ginásio",             capacity: "Sessão individual", tags: ["Cardio"],                ocupados: [["12:00", "14:00"]] },
    { id: 18, category: "desporto", type: "Pilates", icon: "self_improvement", name: "Pilates · Sofia",         location: "Ginásio · estúdio 1", capacity: "Sessão individual", tags: ["Reformer"],              ocupados: [["09:00", "10:00"], ["18:00", "19:00"]] },
  ],
  minhas: [
    { resource_id: 1,  dia: 0, start: "11:00", end: "12:00" },
    { resource_id: 11, dia: 1, start: "08:30", end: "18:00" },
    { resource_id: 15, dia: 3, start: "09:00", end: "10:30" },
  ],
  fila: [
    { resource_id: 16, dia: 1, start: "08:00", end: "09:00" },
  ],
};

// ===== REGRAS DE HORÁRIO (iguais às do backend) =====
// Trabalhamos em minutos desde a meia-noite: 09:30 → 570. Facilita somar e comparar.
const ABRE = 8 * 60;          // 08:00
const FECHA = 20 * 60;        // 20:00
const PASSO = 15;             // os horários andam de 15 em 15 minutos
const DURACAO_MINIMA = 15;
const NUM_DIAS = 7;           // chips de hoje até daqui a 6 dias (o backend aceita até 30)

const DIAS_SEMANA = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];
const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

// "09:30" → 570
function paraMinutos(hora) {
  const [h, m] = hora.split(":").map(Number);
  return h * 60 + m;
}

// 570 → "09:30"
function paraHora(minutos) {
  const h = String(Math.floor(minutos / 60)).padStart(2, "0");
  const m = String(minutos % 60).padStart(2, "0");
  return `${h}:${m}`;
}

// Data do dia "offset" a partir de hoje (0 = hoje, 1 = amanhã...)
function dataDoDia(offset) {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() + offset);
  return d;
}

// Os intervalos [a, b) e [c, d) sobrepõem-se? (b igual a c não conta: 10:00–11:00 e 11:00–12:00 não chocam)
function sobrepoe(a, b, c, d) {
  return a < d && c < b;
}

// Primeiro horário de início permitido no dia escolhido: hoje não se pode reservar no passado
function inicioMinimo(dia) {
  if (dia !== 0) return ABRE;
  const agora = new Date();
  const minutosAgora = agora.getHours() * 60 + agora.getMinutes();
  const arredondado = Math.ceil(minutosAgora / PASSO) * PASSO;   // 10:07 → 10:15
  return Math.max(ABRE, arredondado);
}

// ===== CATEGORIA DA URL =====
const idCategoria = new URLSearchParams(location.search).get("cat");
const categoria = DADOS_FALSOS.categorias[idCategoria];
if (!categoria) location.replace("index.html");   // categoria inválida: volta para a home

// ===== ESTADO DA TELA =====
// Tudo o que o utilizador escolhe fica aqui; render() redesenha a tela a partir deste objeto.
const estado = { tipo: "Todos", dia: 0, inicio: 0, fim: 0, soLivres: false };

// Horário inicial: a próxima hora cheia, com 1 hora de duração.
// Se já não couber hoje (depois das 19:00), começa amanhã às 08:00.
(function horarioInicial() {
  const proximaHora = (new Date().getHours() + 1) * 60;
  estado.inicio = Math.max(ABRE, proximaHora);
  if (estado.inicio + 60 > FECHA) {
    estado.dia = 1;
    estado.inicio = ABRE;
  }
  estado.fim = estado.inicio + 60;
})();

// ===== ESTADO DE UM RECURSO =====
// Devolve "minha", "fila", "ocupado" ou "livre" para o intervalo [inicio, fim) do dia.
// A ordem importa: a sua reserva aparece antes de "ocupado".
function estadoDoRecurso(recurso, dia, inicio, fim) {
  const toca = (item) => item.resource_id === recurso.id && item.dia === dia &&
    sobrepoe(inicio, fim, paraMinutos(item.start), paraMinutos(item.end));

  if (DADOS_FALSOS.minhas.some(toca)) return "minha";
  if (DADOS_FALSOS.fila.some(toca)) return "fila";
  const ocupado = recurso.ocupados.some(([a, b]) => sobrepoe(inicio, fim, paraMinutos(a), paraMinutos(b)));
  return ocupado ? "ocupado" : "livre";
}

// Texto da pílula para cada estado
const TEXTOS = {
  livre:   { pilula: "Livre" },
  ocupado: { pilula: "Ocupado" },
  minha:   { pilula: "Reservado por si" },
  fila:    { pilula: "Em fila" },
};

// ===== DESENHO DA TELA =====
function render() {
  const recursosDaCategoria = DADOS_FALSOS.recursos.filter((r) => r.category === idCategoria);
  renderAbas(recursosDaCategoria);
  renderDias();
  renderHorario();

  // Recursos do tipo escolhido, cada um com o seu estado no horário do filtro
  const doTipo = recursosDaCategoria
    .filter((r) => estado.tipo === "Todos" || r.type === estado.tipo)
    .map((r) => ({ recurso: r, situacao: estadoDoRecurso(r, estado.dia, estado.inicio, estado.fim) }));

  const livres = doTipo.filter((x) => x.situacao === "livre").length;
  const visiveis = estado.soLivres ? doTipo.filter((x) => x.situacao === "livre") : doTipo;

  // Resumo: "6 de 8 livres · Qui, 22 out, 09:00–10:00"
  const data = dataDoDia(estado.dia);
  const quando = `${DIAS_SEMANA[data.getDay()]}, ${data.getDate()} ${MESES[data.getMonth()]}, ${paraHora(estado.inicio)}–${paraHora(estado.fim)}`;
  document.getElementById("resumo").innerHTML = `<b>${livres} de ${doTipo.length} livres</b> · ${quando}`;

  document.getElementById("grelha-recursos").innerHTML = visiveis.map(cartaoHtml).join("");
  document.getElementById("lista-vazia").hidden = visiveis.length > 0;
}

// Abas: "Todos · 8", depois um por tipo, pela ordem em que aparecem nos dados
function renderAbas(recursos) {
  const tipos = ["Todos", ...new Set(recursos.map((r) => r.type))];   // Set remove os repetidos
  document.getElementById("abas-tipo").innerHTML = tipos.map((tipo) => {
    const total = tipo === "Todos" ? recursos.length : recursos.filter((r) => r.type === tipo).length;
    const ativo = tipo === estado.tipo;
    return `<button type="button" class="aba${ativo ? " ativo" : ""}" role="tab" aria-selected="${ativo}"
              data-tipo="${esc(tipo)}">${esc(tipo)} · ${total}</button>`;
  }).join("");
}

// Chips dos 7 dias: o primeiro diz "Hoje"
function renderDias() {
  let html = "";
  for (let i = 0; i < NUM_DIAS; i++) {
    const data = dataDoDia(i);
    const nome = i === 0 ? "Hoje" : DIAS_SEMANA[data.getDay()];
    // Hoje fica desativado quando já não cabe nenhuma reserva (perto ou depois do fecho)
    const semHorario = i === 0 && inicioMinimo(0) > FECHA - DURACAO_MINIMA;
    html += `<button type="button" class="chip-dia${i === estado.dia ? " ativo" : ""}" data-dia="${i}"${semHorario ? " disabled" : ""}>
               <span class="chip-dia-semana">${nome}</span>
               <span class="chip-dia-numero">${data.getDate()}</span>
             </button>`;
  }
  document.getElementById("chips-dias").innerHTML = html;
}

// Valores dos seletores e botões desativados quando chegam ao limite
function renderHorario() {
  document.getElementById("inicio-valor").textContent = paraHora(estado.inicio);
  document.getElementById("fim-valor").textContent = paraHora(estado.fim);

  document.getElementById("inicio-menos").disabled = estado.inicio - PASSO < inicioMinimo(estado.dia);
  document.getElementById("inicio-mais").disabled = estado.inicio + PASSO > FECHA - DURACAO_MINIMA;
  document.getElementById("fim-menos").disabled = estado.fim - PASSO < estado.inicio + DURACAO_MINIMA;
  document.getElementById("fim-mais").disabled = estado.fim + PASSO > FECHA;

  document.getElementById("so-livres").setAttribute("aria-checked", estado.soLivres);
}

// HTML de um cartão de recurso
function cartaoHtml({ recurso, situacao }) {
  // Link para o detalhe já com o dia e o horário do filtro
  const link = `recurso.html?id=${recurso.id}&dia=${toISODate(dataDoDia(estado.dia))}` +
               `&inicio=${paraHora(estado.inicio)}&fim=${paraHora(estado.fim)}`;

  // 12 barrinhas, uma por hora das 08h às 20h
  let barras = "";
  for (let h = ABRE; h < FECHA; h += 60) {
    const s = estadoDoRecurso(recurso, estado.dia, h, h + 60);
    const classes = [s === "livre" ? "" : s, sobrepoe(h, h + 60, estado.inicio, estado.fim) ? "no-filtro" : ""];
    barras += `<i class="${classes.join(" ").trim()}"></i>`;
  }

  // Botão conforme o estado (o ✨ marca as sugestões, que vão vir do scheduling)
  const horario = `${paraHora(estado.inicio)}–${paraHora(estado.fim)}`;
  const botoes = {
    livre:   `<a class="botao botao-primario" href="${link}">Reservar ${horario}</a>`,
    ocupado: `<a class="botao botao-secundario" href="${link}"><span class="icone">auto_awesome</span>Ver alternativas</a>`,
    minha:   `<a class="botao botao-secundario" href="reservas.html">Ver a minha reserva</a>`,
    fila:    `<a class="botao botao-secundario" href="${link}">Em fila · ver horários</a>`,
  };

  return `
    <article class="cartao-recurso">
      <div class="cartao-topo">
        <a href="${link}" class="cartao-link">
          <div class="cartao-nome">${esc(recurso.name)}</div>
          <div class="cartao-local">${esc(recurso.location)} · ${esc(recurso.capacity)}</div>
        </a>
        <span class="pilula ${situacao}">${TEXTOS[situacao].pilula}</span>
      </div>
      <div class="cartao-tags">${recurso.tags.map((t) => `<span>${esc(t)}</span>`).join("")}</div>
      <div class="linha-dia" title="Ocupação das 08:00 às 20:00">
        <div class="linha-dia-barras">${barras}</div>
        <div class="linha-dia-horas"><span>08</span><span>14</span><span>20</span></div>
      </div>
      ${botoes[situacao]}
    </article>`;
}

// ===== EVENTOS =====
// Abas: um único "ouvinte" no contentor (delegação), porque os botões são redesenhados
document.getElementById("abas-tipo").addEventListener("click", (e) => {
  const aba = e.target.closest(".aba");
  if (!aba) return;
  estado.tipo = aba.dataset.tipo;
  render();
});

// Dias: ao trocar, garante que o horário não fica no passado (mantendo a duração)
document.getElementById("chips-dias").addEventListener("click", (e) => {
  const chip = e.target.closest(".chip-dia");
  if (!chip) return;
  estado.dia = Number(chip.dataset.dia);

  const minimo = inicioMinimo(estado.dia);
  if (estado.inicio < minimo) {
    const duracao = estado.fim - estado.inicio;
    estado.inicio = minimo;
    estado.fim = Math.min(FECHA, minimo + duracao);
    if (estado.fim - estado.inicio < DURACAO_MINIMA) estado.inicio = estado.fim - DURACAO_MINIMA;
  }
  render();
});

// Seletores de hora. Os botões ficam desativados nos limites, por isso aqui basta somar.
document.getElementById("inicio-menos").addEventListener("click", () => {
  estado.inicio -= PASSO;
  render();
});
document.getElementById("inicio-mais").addEventListener("click", () => {
  estado.inicio += PASSO;
  // Se o início encostar no fim, empurra o fim junto (mantém a duração mínima)
  if (estado.fim - estado.inicio < DURACAO_MINIMA) estado.fim = estado.inicio + DURACAO_MINIMA;
  render();
});
document.getElementById("fim-menos").addEventListener("click", () => {
  estado.fim -= PASSO;
  render();
});
document.getElementById("fim-mais").addEventListener("click", () => {
  estado.fim += PASSO;
  render();
});

// Interruptor "Só disponíveis"
document.getElementById("so-livres").addEventListener("click", () => {
  estado.soLivres = !estado.soLivres;
  render();
});

// ===== ARRANQUE =====
if (categoria) {
  // Título, ícone e cores da categoria (as variáveis --coworking, --coworking-suave... estão no style.css)
  document.title = `SlotUp · ${categoria.name}`;
  document.getElementById("caminho-atual").textContent = categoria.name;
  document.getElementById("cat-nome").textContent = categoria.name;
  document.getElementById("cat-descricao").textContent = categoria.description;
  document.getElementById("cat-icone").textContent = categoria.icon;
  const topo = document.getElementById("cat-topo");
  topo.style.setProperty("--cor-cat", `var(--${idCategoria})`);
  topo.style.setProperty("--cor-cat-suave", `var(--${idCategoria}-suave)`);

  render();
}