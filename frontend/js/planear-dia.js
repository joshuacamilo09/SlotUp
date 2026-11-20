// ===== PLANEAR O MEU DIA =====
// O utilizador diz o que quer fazer; o CSP (scheduling) monta o plano e o booking
// devolve-o. Esta tela só monta o pedido e mostra a resposta: não resolve nada sozinha.
// Todas as horas aqui são minutos desde a meia-noite (09:00 = 540).

requireAuth();   // sem sessão vai para o login (o layout.js também verifica)

// ===== 1. CONSTANTES =====
const PASSO = 15;               // duração e hora andam de 15 em 15 min (a grelha do booking)
const DUR_MIN = 15;
const DUR_MAX = 8 * 60;
const HORA_MIN = 7 * 60;        // "hora específica" entre as 07:00...
const HORA_MAX = 22 * 60;       // ...e as 22:00 (o horário mais largo dos recursos)
const MAX_ATIVIDADES = 5;       // como no mockup
const PESSOAS_MAX = 20;
// Janelas de "manhã" e "tarde": vão no pedido como preferred_start e preferred_end
const TURNOS = {
  manha: { texto: "Manhã", janela: [8 * 60, 13 * 60] },
  tarde: { texto: "Tarde", janela: [13 * 60, 20 * 60] },
  hora:  { texto: "Hora específica" },
};
// Tipos em que o número de pessoas muda o recurso possível (capacidade); nos outros vai 1
const TIPOS_COM_PESSOAS = ["sala", "quadra"];
const DIAS = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];   // getDay() do JS: 0 = domingo
const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

// Sugestões quando não há plano, pela regra que o impediu (failure.rule_id do contrato)
const SUGESTOES = {
  CAPACIDADE:        ["Reduzir o número de pessoas", "Escolher outro tipo de recurso"],
  DURACAO:           ["Mudar a duração da atividade"],
  HORARIO_ABERTURA:  ["Mudar o horário preferido", "Escolher outro dia"],
  RECURSO_LIVRE:     ["Mudar o horário preferido, por exemplo de hora específica para manhã ou tarde", "Escolher outro dia"],
  INTERVALO_RECURSO: ["Mudar o horário preferido", "Escolher outro dia"],
  SEM_SOBREPOSICAO:  ["Reduzir a duração de uma atividade", "Mudar o horário preferido, por exemplo de hora específica para manhã ou tarde", "Escolher outro dia"],
  VAGA_COBRE_O_DIA:  ["Tirar o estacionamento do plano", "Escolher outro dia"],
  SEM_PASSADO:       ["Escolher outro dia"],
  ANTECEDENCIA:      ["Escolher um dia mais próximo"],
};
const SUGESTOES_PADRAO = ["Reduzir a duração de uma atividade", "Mudar o horário preferido", "Escolher outro dia"];

// ===== 2. LIGAÇÃO AO BACKEND =====
// O confirmar ainda devolve uma resposta de exemplo, NO FORMATO DO CONTRATO
// (documentacao/contrato-scheduling.md). Na tarefa "Planear o meu dia (rota)" passam a
// chamar o booking, e o resto da tela não muda.
//
// planear(pedido)  pedido: { day, activities: [{ id, resource_type, people, duration_min,
//                  preferred_start, preferred_end, covers_day }] }
//                  devolve: { status: "OK" | "NO_SOLUTION", plan, failure }
// confirmar(dia, itens)  cria as reservas do plano, tudo ou nada; 409 se um horário foi ocupado
async function planear(pedido) {
  // Os erros (422, 503 do plano B...) chegam como ApiError e o gerarPlano mostra-os num toast
  return api.planDay(pedido.day, pedido.activities);
}

async function confirmar(dia, itens) {
  // A API só aceita estes 4 campos (extra="forbid"): tiramos o resource_name de cada item
  const items = itens.map(({ activity_id, resource_id, start, end }) => ({ activity_id, resource_id, start, end }));
  await api.confirmPlan(dia, items);
  return itens;   // a tela mostra os itens do plano (já têm o nome do recurso e a atividade)
}

// ===== 3. AJUDANTES =====
const pad = (n) => String(n).padStart(2, "0");
const hhmm = (m) => `${pad(Math.floor(m / 60))}:${pad(m % 60)}`;
const paraMinutos = (texto) => Number(texto.slice(0, 2)) * 60 + Number(texto.slice(3, 5));   // "09:30" → 570

function duracaoTxt(m) {
  const h = Math.floor(m / 60);
  const r = m % 60;
  if (!h) return `${r} min`;
  return r ? `${h}h${pad(r)}` : `${h}h`;
}
function dataCurta(iso) {
  const d = new Date(`${iso}T12:00:00`);   // meio-dia: evita mudar de dia por causa do fuso
  return `${DIAS[d.getDay()]}, ${d.getDate()} ${MESES[d.getMonth()]}`;
}
const categoriaDoTipo = (tipo) => Object.keys(TIPOS_UI).find((c) => TIPOS_UI[c][tipo]);

// ===== 4. ESTADO =====
// fase: "vazio" | "carregando" | "plano" | "sem-plano" | "confirmando" | "confirmado"
let contador = 0;
const estado = {
  dia: null,
  atividades: [],
  fase: "vazio",
  plano: null,       // resposta.plan
  falha: null,       // resposta.failure
  criadas: [],
};

function novaAtividade({ tipo = "mesa", duracao = 60, turno = "manha", inicio = 9 * 60, pessoas = 1 } = {}) {
  return { id: `a${++contador}`, categoria: categoriaDoTipo(tipo), tipo, duracao, turno, inicio, pessoas };
}
const temVaga = (exceto) => estado.atividades.some((a) => a !== exceto && a.categoria === "estacionamento");

// ===== 5. DESENHO =====
function render() {
  renderDatas();
  renderAtividades();
  renderResultado();
}

function renderDatas() {
  const hoje = new Date();
  hoje.setHours(12, 0, 0, 0);
  document.getElementById("datas").innerHTML = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(hoje);
    d.setDate(hoje.getDate() + i);
    const iso = toISODate(d);   // toISODate vem do api.js
    const ativo = iso === estado.dia;
    return `<button type="button" class="data${ativo ? " ativo" : ""}" data-acao="dia" data-dia="${iso}" aria-pressed="${ativo}">
              <span class="data__dia">${i === 0 ? "Hoje" : DIAS[d.getDay()]}</span><span class="data__num">${d.getDate()}</span>
            </button>`;
  }).join("");
  document.getElementById("plano-data").textContent = dataCurta(estado.dia);
}

function renderAtividades() {
  const n = estado.atividades.length;
  const total = estado.atividades.filter((a) => a.categoria !== "estacionamento").reduce((s, a) => s + a.duracao, 0);
  document.getElementById("atv-total").textContent = `${n} ${n === 1 ? "atividade" : "atividades"} · ${duracaoTxt(total)} no total`;
  document.getElementById("atv-add").hidden = n >= MAX_ATIVIDADES;
  document.getElementById("atv-max").hidden = n < MAX_ATIVIDADES;

  document.getElementById("atv-lista").innerHTML = estado.atividades.map((a, i) => {
    const vaga = a.categoria === "estacionamento";
    const categorias = Object.entries(CATEGORIAS_UI).map(([id, c]) => {
      const bloqueada = id === "estacionamento" && temVaga(a);   // no máximo 1 vaga por dia
      return `<button type="button" class="cat cat--${id}${id === a.categoria ? " ativo" : ""}" data-acao="categoria" data-valor="${id}"
                aria-pressed="${id === a.categoria}"${bloqueada ? ' disabled title="Já há uma vaga de estacionamento no plano"' : ""}>
                <span class="icone" aria-hidden="true">${c.icon}</span>${esc(nomeCategoria(id))}</button>`;
    }).join("");
    const tipos = Object.entries(TIPOS_UI[a.categoria]).map(([codigo, [texto, icone]]) => `
      <button type="button" class="tipo${codigo === a.tipo ? " ativo" : ""}" data-acao="tipo" data-valor="${codigo}" aria-pressed="${codigo === a.tipo}">
        <span class="icone" aria-hidden="true">${icone}</span>${esc(texto)}</button>`).join("");

    // Estacionamento: sem duração nem horário, porque a vaga cobre o dia (VAGA_COBRE_O_DIA)
    const detalhes = vaga
      ? `<p class="atv__nota"><span class="icone" aria-hidden="true">info</span>A vaga fica reservada da primeira à última atividade do dia. Máximo de 1 vaga de estacionamento por dia.</p>`
      : `
        <div class="atv__linha">
          <div class="atv__campo">
            <span class="atv__rotulo" id="duracao-${a.id}">Duração</span>
            <div class="passo" role="group" aria-labelledby="duracao-${a.id}">
              <button class="passo__btn" type="button" data-acao="dur-" aria-label="Menos 15 minutos"${a.duracao <= DUR_MIN ? " disabled" : ""}><span class="icone" aria-hidden="true">remove</span></button>
              <output class="passo__valor">${duracaoTxt(a.duracao)}</output>
              <button class="passo__btn" type="button" data-acao="dur+" aria-label="Mais 15 minutos"${a.duracao >= DUR_MAX ? " disabled" : ""}><span class="icone" aria-hidden="true">add</span></button>
            </div>
          </div>
          <div class="atv__campo">
            <span class="atv__rotulo" id="turno-${a.id}">Horário preferido</span>
            <div class="turnos" role="group" aria-labelledby="turno-${a.id}">
              ${Object.entries(TURNOS).map(([id, t]) => `
                <button type="button" class="turno${id === a.turno ? " ativo" : ""}" data-acao="turno" data-valor="${id}" aria-pressed="${id === a.turno}">${t.texto}</button>`).join("")}
            </div>
          </div>
        </div>
        ${a.turno === "hora" ? `
        <div class="atv__hora">
          <span class="atv__rotulo">Começa às</span>
          <div class="passo" role="group" aria-label="Hora de início">
            <button class="passo__btn" type="button" data-acao="ini-" aria-label="Mais cedo 15 minutos"${a.inicio <= HORA_MIN ? " disabled" : ""}><span class="icone" aria-hidden="true">remove</span></button>
            <output class="passo__valor">${hhmm(a.inicio)}</output>
            <button class="passo__btn" type="button" data-acao="ini+" aria-label="Mais tarde 15 minutos"${a.inicio + a.duracao >= HORA_MAX ? " disabled" : ""}><span class="icone" aria-hidden="true">add</span></button>
          </div>
          <span class="atv__fim">termina às <b>${hhmm(a.inicio + a.duracao)}</b></span>
        </div>` : ""}
        ${TIPOS_COM_PESSOAS.includes(a.tipo) ? `
        <div class="atv__hora">
          <span class="atv__rotulo" id="pessoas-${a.id}">Pessoas</span>
          <div class="passo" role="group" aria-labelledby="pessoas-${a.id}">
            <button class="passo__btn" type="button" data-acao="pes-" aria-label="Menos uma pessoa"${a.pessoas <= 1 ? " disabled" : ""}><span class="icone" aria-hidden="true">remove</span></button>
            <output class="passo__valor">${a.pessoas}</output>
            <button class="passo__btn" type="button" data-acao="pes+" aria-label="Mais uma pessoa"${a.pessoas >= PESSOAS_MAX ? " disabled" : ""}><span class="icone" aria-hidden="true">add</span></button>
          </div>
        </div>` : ""}`;

    return `
      <li class="atv" data-id="${a.id}">
        <div class="atv__cab">
          <h4 class="atv__titulo">Atividade ${i + 1}</h4>
          <button class="atv__lixo" type="button" data-acao="remover" aria-label="Remover a atividade ${i + 1}"${n === 1 ? " disabled" : ""}>
            <span class="icone" aria-hidden="true">delete</span></button>
        </div>
        <div class="atv__cats" role="group" aria-label="Categoria">${categorias}</div>
        <div class="atv__tipos" role="group" aria-label="Tipo">${tipos}</div>
        ${detalhes}
      </li>`;
  }).join("");

  const gerar = document.getElementById("gerar-plano");
  gerar.disabled = estado.fase === "carregando" || !estado.atividades.some((a) => a.categoria !== "estacionamento");
  gerar.querySelector(".gerar__txt").textContent = estado.fase === "carregando" ? "A gerar…" : "Gerar plano";
}

function renderResultado() {
  const el = document.getElementById("plano-resultado");
  const f = estado.fase;

  if (f === "vazio") {
    el.className = "plano-vazio";
    el.innerHTML = `
      <span class="icone" aria-hidden="true">view_timeline</span>
      <p class="plano-vazio__titulo">O plano aparece aqui</p>
      <p class="plano-vazio__texto">Adicione as atividades e carregue em “Gerar plano”.</p>`;
  } else if (f === "carregando") {
    el.className = "plano-vazio";
    el.innerHTML = `
      <span class="plano-roda" aria-hidden="true"></span>
      <p class="plano-vazio__titulo">A procurar horários que encaixem tudo…</p>
      <p class="plano-vazio__texto">Só com recursos livres e sem sobreposições.</p>`;
  } else if (f === "plano" || f === "confirmando") {
    el.className = "plano-lista";
    el.innerHTML = `
      <p class="plano-resumo"><span class="icone" aria-hidden="true">check_circle</span>Sem sobreposições · só recursos livres</p>
      ${listaItens(estado.plano.items)}
      <p class="plano-nota"><span class="icone" aria-hidden="true">info</span>O plano só usa recursos livres, sem fila de espera.</p>
      <div class="plano-acoes">
        <button class="plano-secundario" type="button" data-acao="alterar">Alterar o pedido</button>
        <button class="gerar" type="button" data-acao="confirmar"${f === "confirmando" ? " disabled" : ""}>
          <span class="icone" aria-hidden="true">event_available</span>
          <span class="gerar__txt">${f === "confirmando" ? "A reservar…" : "Confirmar e reservar tudo"}</span>
        </button>
      </div>`;
  } else if (f === "sem-plano") {
    const sugestoes = SUGESTOES[estado.falha?.rule_id] ?? SUGESTOES_PADRAO;
    el.className = "plano-vazio plano-vazio--erro";
    el.innerHTML = `
      <span class="icone" aria-hidden="true">event_busy</span>
      <p class="plano-vazio__titulo">Não há horários que encaixem tudo</p>
      <p class="plano-vazio__texto">${esc(estado.falha?.message ?? `Em ${dataCurta(estado.dia)}, não encontrámos recursos livres para todas as atividades.`)}</p>
      <p class="plano-sugestoes__titulo">Experimente</p>
      <ul class="plano-sugestoes">${sugestoes.map((s) => `<li>${esc(s)}</li>`).join("")}</ul>`;
  } else if (f === "confirmado") {
    el.className = "plano-lista";
    el.innerHTML = `
      <p class="plano-resumo"><span class="icone" aria-hidden="true">check</span>Plano confirmado: ${estado.criadas.length} reservas para ${dataCurta(estado.dia)}</p>
      ${listaItens(estado.criadas)}
      <div class="plano-acoes">
        <button class="plano-secundario" type="button" data-acao="novo-dia">Planear outro dia</button>
        <a class="gerar" href="reservas.html"><span class="gerar__txt">Ver as minhas reservas</span><span class="icone" aria-hidden="true">arrow_forward</span></a>
      </div>`;
  }
}

// Lista dos itens do plano (itens no formato do contrato: activity_id, resource_name, start, end)
function listaItens(itens) {
  const porId = Object.fromEntries(estado.atividades.map((a) => [a.id, a]));   // id → atividade
  const ordenados = [...itens].sort((x, y) => x.start.localeCompare(y.start));
  return `<ol class="plano-itens">${ordenados.map((item) => {
    const a = porId[item.activity_id];
    const minutos = paraMinutos(item.end) - paraMinutos(item.start);
    return `
      <li class="plano-item cat--${a.categoria}">
        <span class="plano-item__hora">${item.start.slice(0, 5)}–${item.end.slice(0, 5)}</span>
        <span class="plano-item__icone"><span class="icone" aria-hidden="true">${iconeTipo(a.categoria, a.tipo)}</span></span>
        <div>
          <p class="plano-item__nome">${esc(item.resource_name)}</p>
          <p class="plano-item__meta">${esc(textoTipo(a.categoria, a.tipo))}${TIPOS_COM_PESSOAS.includes(a.tipo) && a.pessoas > 1 ? ` · ${a.pessoas} pessoas` : ""}</p>
        </div>
        <span class="plano-item__dur">${duracaoTxt(minutos)}</span>
      </li>`;
  }).join("")}</ol>`;
}

// O nome que o booking dá à categoria ("Coworking"); aqui só temos o id curto
const nomeCategoria = (id) => ({ coworking: "Coworking", estacionamento: "Estacionamento", desporto: "Desporto" })[id] ?? id;

// ===== 6. PEDIDO (formato das atividades do contrato) =====
function montarPedido() {
  return {
    day: estado.dia,
    activities: estado.atividades.map((a) => {
      if (a.categoria === "estacionamento") {
        return { id: a.id, resource_type: a.tipo, people: 1, covers_day: true };
      }
      const atividade = { id: a.id, resource_type: a.tipo, duration_min: a.duracao,
                          people: TIPOS_COM_PESSOAS.includes(a.tipo) ? a.pessoas : 1 };
      if (a.turno === "hora") {
        atividade.preferred_start = hhmm(a.inicio);           // hora específica: sem preferred_end
      } else {
        const [inicio, fim] = TURNOS[a.turno].janela;          // manhã ou tarde: uma janela
        atividade.preferred_start = hhmm(inicio);
        atividade.preferred_end = hhmm(fim);
      }
      return atividade;
    }),
  };
}

// ===== 7. EVENTOS =====
// Um só "ouvinte" para a página inteira (delegação): cada botão diz o que faz em data-acao
document.querySelector("main").addEventListener("click", async (e) => {
  const botao = e.target.closest("[data-acao]");
  if (!botao || botao.disabled) return;
  const acao = botao.dataset.acao;
  const li = botao.closest(".atv");
  const a = li && estado.atividades.find((x) => x.id === li.dataset.id);

  // Mudar o pedido invalida o plano que estava à vista
  const mudaPedido = ["dia", "categoria", "tipo", "turno", "remover", "dur-", "dur+", "ini-", "ini+", "pes-", "pes+", "adicionar"];
  if (mudaPedido.includes(acao) && estado.fase !== "carregando") {
    estado.fase = "vazio";
  }

  if (acao === "dia") estado.dia = botao.dataset.dia;
  else if (acao === "adicionar") estado.atividades.push(novaAtividade());
  else if (acao === "remover") estado.atividades = estado.atividades.filter((x) => x !== a);
  else if (acao === "categoria") {
    a.categoria = botao.dataset.valor;
    a.tipo = Object.keys(TIPOS_UI[a.categoria])[0];   // o primeiro tipo da categoria
  }
  else if (acao === "tipo") a.tipo = botao.dataset.valor;
  else if (acao === "turno") a.turno = botao.dataset.valor;
  else if (acao === "dur-") a.duracao = Math.max(DUR_MIN, a.duracao - PASSO);
  else if (acao === "dur+") a.duracao = Math.min(DUR_MAX, a.duracao + PASSO);
  else if (acao === "ini-") a.inicio = Math.max(HORA_MIN, a.inicio - PASSO);
  else if (acao === "ini+") a.inicio = Math.min(HORA_MAX - a.duracao, a.inicio + PASSO);
  else if (acao === "pes-") a.pessoas = Math.max(1, a.pessoas - 1);
  else if (acao === "pes+") a.pessoas = Math.min(PESSOAS_MAX, a.pessoas + 1);
  else if (acao === "alterar") estado.fase = "vazio";
  else if (acao === "novo-dia") { estado.fase = "vazio"; estado.criadas = []; }
  else if (acao === "confirmar") return confirmarPlano();
  else return;

  // Uma atividade com hora específica nunca passa das 22:00
  if (a && a.inicio + a.duracao > HORA_MAX) a.inicio = HORA_MAX - a.duracao;
  render();
});

document.getElementById("gerar-plano").addEventListener("click", gerarPlano);

async function gerarPlano() {
  estado.fase = "carregando";
  render();
  try {
    const resposta = await planear(montarPedido());
    if (resposta.status === "OK") {
      estado.plano = resposta.plan;
      estado.fase = "plano";
    } else {
      estado.falha = resposta.failure;
      estado.fase = "sem-plano";
    }
  } catch (err) {
    estado.fase = "vazio";
    toast(err.message || "Não foi possível gerar o plano.", true);
  }
  render();
}

async function confirmarPlano() {
  estado.fase = "confirmando";
  renderResultado();
  try {
    estado.criadas = await confirmar(estado.dia, estado.plano.items);
    estado.fase = "confirmado";
  } catch (err) {
    if (err.status === 409) {
      // Alguém reservou um dos horários entre o plano e a confirmação: nada foi criado
      estado.fase = "vazio";
      toast(err.message, true);
    } else {
      estado.fase = "plano";
      toast(err.message || "Não foi possível reservar o plano.", true);
    }
  }
  render();
}

// ===== 8. ARRANQUE =====
(function iniciar() {
  const amanha = new Date();
  amanha.setDate(amanha.getDate() + 1);
  estado.dia = toISODate(amanha);
  // As três atividades do mockup
  estado.atividades = [
    novaAtividade({ tipo: "mesa", duracao: 180, turno: "manha" }),
    novaAtividade({ tipo: "quadra", duracao: 60, turno: "tarde", pessoas: 4 }),
    novaAtividade({ tipo: "sala", duracao: 60, turno: "hora", inicio: 16 * 60, pessoas: 6 }),
  ];
  render();
})();