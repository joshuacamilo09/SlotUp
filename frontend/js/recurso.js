// =====================================================================
// SlotUp – tela "Detalhe do recurso" (recurso.html)
// URL: recurso.html?id=<id>&dia=AAAA-MM-DD&inicio=HH:MM&fim=HH:MM
// Por agora usa dados fictícios (DADOS_FALSOS); depois liga-se à API.
// =====================================================================

// Sem sessão, requireAuth() manda para o login.
const utilizador = requireAuth();
const emailUtilizador = (utilizador && utilizador.email) || "";

// ---------------------------------------------------------------------
// Dados fictícios: tudo o que vem de "fora" fica aqui, para ser trocado
// depois por chamadas à API.
// ---------------------------------------------------------------------
const DADOS_FALSOS = {
  recurso: { id: 1, name: "Sala Atlântico", category: "coworking", type: "Salas de reunião",
             location: "Piso 2", capacity: "até 8 pessoas", tags: ["Ecrã", "Videoconferência"], icon: "groups" },
  ocupados:   [{ start: "09:00", end: "10:30" }, { start: "13:00", end: "14:30" }],
  minhas:     [{ start: "11:00", end: "12:00" }],
  naFila:     [],
  sugestoes:  [{ name: "Sala Índico", tag: "Mesmo horário", sub: "Piso 2 · até 8 pessoas", time: "09:00–10:30" }],
};
const dados = DADOS_FALSOS;

// ---------------------------------------------------------------------
// Constantes e regras de horário (iguais às do backend)
// ---------------------------------------------------------------------
const ABERTURA = 8 * 60;  // 08:00, em minutos desde a meia-noite
const FECHO = 20 * 60;    // 20:00
const PASSO = 15;         // horários de 15 em 15 minutos (também a duração mínima)
const PX_HORA = 48;       // altura de cada hora na grelha
const MAX_DIAS = 30;      // no máximo 30 dias à frente

const SEMANA = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];
const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const CATEGORIAS = {
  coworking: "Coworking",
  estacionamento: "Estacionamento",
  desporto: "Desporto",
};

// ---------------------------------------------------------------------
// Funções auxiliares de horas e datas
// ---------------------------------------------------------------------
// "09:30" -> 570
function paraMin(hhmm) {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + m;
}
// 570 -> "09:30"
function paraHora(min) {
  return String(Math.floor(min / 60)).padStart(2, "0") + ":" + String(min % 60).padStart(2, "0");
}
// 90 -> "1h30", 60 -> "1h", 45 -> "45min"
function duracaoTexto(min) {
  const h = Math.floor(min / 60);
  const m = min % 60;
  if (!h) return m + "min";
  return m ? h + "h" + String(m).padStart(2, "0") : h + "h";
}
// Date -> "AAAA-MM-DD" (em hora local)
function paraISO(d) {
  return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
}
// "AAAA-MM-DD" -> Date (meia-noite local)
function deISO(iso) {
  const [a, m, d] = iso.split("-").map(Number);
  return new Date(a, m - 1, d);
}
// "Qui, 22 out"
function textoDia(iso) {
  const d = deISO(iso);
  return SEMANA[d.getDay()] + ", " + d.getDate() + " " + MESES[d.getMonth()];
}
// Dois intervalos [a1,a2) e [b1,b2) sobrepõem-se?
function sobrepoe(a1, a2, b1, b2) {
  return a1 < b2 && b1 < a2;
}
function agoraMin() {
  const n = new Date();
  return n.getHours() * 60 + n.getMinutes();
}

// ---------------------------------------------------------------------
// Parâmetros da URL: dia, inicio e fim
// ---------------------------------------------------------------------
const params = new URLSearchParams(location.search);
const hoje = new Date();
hoje.setHours(0, 0, 0, 0);

// O dia da URL só vale se for hoje ou até daqui a 30 dias
function diaValido(iso) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(iso || "")) return false;
  const d = deISO(iso);
  const diff = Math.round((d - hoje) / 86400000);
  return paraISO(d) === iso && diff >= 0 && diff <= MAX_DIAS;
}

// "HH:MM" válido = múltiplo de 15 minutos dentro do horário de abertura; senão null
function horaValida(txt) {
  if (!/^\d{2}:\d{2}$/.test(txt || "")) return null;
  const m = paraMin(txt);
  if (m % PASSO !== 0 || m < ABERTURA || m > FECHO) return null;
  return m;
}

// Intervalo inicial: o da URL, ou a próxima hora cheia com 1 hora de duração
function intervaloInicial() {
  const ini = horaValida(params.get("inicio"));
  const fim = horaValida(params.get("fim"));
  if (ini !== null && fim !== null && fim > ini) return { inicio: ini, duracao: fim - ini };
  return { inicio: (Math.floor(agoraMin() / 60) + 1) * 60, duracao: 60 };
}

// ---------------------------------------------------------------------
// Estado da tela
// ---------------------------------------------------------------------
const inicial = intervaloInicial();
const estado = {
  dia: diaValido(params.get("dia")) ? params.get("dia") : paraISO(hoje),
  inicio: inicial.inicio,
  fim: inicial.inicio + inicial.duracao,
  sugestao: 0, // índice da sugestão escolhida na janela de conflito
};

const eHoje = () => estado.dia === paraISO(hoje);

// Primeiro início permitido: 08:00, ou "agora" (arredondado) se o dia for hoje
function minInicio() {
  if (!eHoje()) return ABERTURA;
  return Math.max(ABERTURA, Math.ceil(agoraMin() / PASSO) * PASSO);
}

// Põe a seleção num sítio válido, mantendo a duração sempre que possível
function posicionar(inicio, duracao) {
  const minimo = minInicio();
  const dur = Math.min(duracao, Math.max(PASSO, FECHO - minimo));
  let i = Math.max(inicio, minimo);
  i = Math.min(i, FECHO - dur);
  estado.inicio = i;
  estado.fim = i + dur;
}

// Estado da seleção: passado, minha, fila, ocupado ou livre
function calcularEstado() {
  const { inicio, fim } = estado;
  const cruza = (b) => sobrepoe(inicio, fim, paraMin(b.start), paraMin(b.end));
  if (inicio < minInicio()) return "passado";
  if (dados.minhas.some(cruza)) return "minha";
  if (dados.naFila.some(cruza)) return "fila";
  if (dados.ocupados.some(cruza)) return "ocupado";
  return "livre";
}

// ---------------------------------------------------------------------
// Elementos da página
// ---------------------------------------------------------------------
const $ = (id) => document.getElementById(id);
const el = {
  caminho: $("caminho"),
  cabecalho: $("recurso-cab"),
  chipsDias: $("chips-dias"),
  grelha: $("grelha"),
  grelhaHoras: $("grelha-horas"),
  grelhaBlocos: $("grelha-blocos"),
  selecao: $("selecao"),
  linhaAgora: $("linha-agora"),
  painelDia: $("painel-dia"),
  inicioValor: $("inicio-valor"),
  fimValor: $("fim-valor"),
  inicioMenos: $("inicio-menos"),
  inicioMais: $("inicio-mais"),
  fimMenos: $("fim-menos"),
  fimMais: $("fim-mais"),
  estado: $("estado"),
  botaoPrincipal: $("botao-principal"),
  emailUtilizador: $("email-utilizador"),
  modalConfirmacao: $("modal-confirmacao"),
  modalConflito: $("modal-conflito"),
  blocoSugestoes: $("bloco-sugestoes"),
  listaSugestoes: $("sugestoes-lista"),
  caixaFila: $("caixa-fila"),
  botaoFila: $("botao-fila"),
  botaoSugestao: $("botao-sugestao"),
};

// ---------------------------------------------------------------------
// Desenho: caminho e cabeçalho do recurso (textos de dados passam por esc())
// ---------------------------------------------------------------------
function chaveCategoria() {
  return CATEGORIAS[dados.recurso.category] ? dados.recurso.category : "coworking";
}

function desenharCaminho() {
  const r = dados.recurso;
  const chave = chaveCategoria();
  el.caminho.innerHTML =
    `<a href="index.html">Início</a> / ` +
    `<a href="categoria.html?cat=${encodeURIComponent(chave)}">${esc(CATEGORIAS[chave])}</a> / ` +
    `<strong>${esc(r.name)}</strong>`;
}

function desenharCabecalho() {
  const r = dados.recurso;
  const chave = chaveCategoria();
  const sub = [r.type, r.location, r.capacity].filter(Boolean).map(esc).join(" · ");
  const tags = (r.tags || []).map((t) => `<span class="recurso-tag">${esc(t)}</span>`).join("");

  el.cabecalho.classList.add("cat-" + chave);
  el.cabecalho.innerHTML =
    `<div class="recurso-icone"><span class="material-symbols-rounded" aria-hidden="true">${esc(r.icon)}</span></div>` +
    `<div>` +
      `<div class="recurso-titulo"><h1>${esc(r.name)}</h1><span class="pilula-cat">${esc(CATEGORIAS[chave])}</span></div>` +
      `<p class="recurso-sub">${sub}</p>` +
      `<div class="recurso-tags">${tags}</div>` +
    `</div>`;
  document.title = r.name + " – SlotUp";
}

// ---------------------------------------------------------------------
// Desenho: os 7 dias (de hoje até daqui a 6 dias)
// ---------------------------------------------------------------------
function desenharDias() {
  let html = "";
  for (let i = 0; i < 7; i++) {
    const d = new Date(hoje);
    d.setDate(hoje.getDate() + i);
    const iso = paraISO(d);
    const ativo = iso === estado.dia;
    html +=
      `<button type="button" class="chip-dia${ativo ? " ativo" : ""}" data-dia="${iso}" aria-pressed="${ativo}">` +
      `<span class="cd-semana">${i === 0 ? "Hoje" : SEMANA[d.getDay()]}</span>` +
      `<span class="cd-numero">${d.getDate()}</span></button>`;
  }
  el.chipsDias.innerHTML = html;
}

el.chipsDias.addEventListener("click", (e) => {
  const botao = e.target.closest(".chip-dia");
  if (!botao) return;
  estado.dia = botao.dataset.dia;
  // guarda o dia na URL, para se poder partilhar/recarregar
  params.set("dia", estado.dia);
  history.replaceState(null, "", location.pathname + "?" + params.toString());
  posicionar(estado.inicio, estado.fim - estado.inicio);
  desenharDias();
  atualizar();
});

// ---------------------------------------------------------------------
// Desenho: grelha do dia (08:00 a 20:00, 48px por hora)
// ---------------------------------------------------------------------
// As linhas e as horas desenham-se uma só vez
function desenharHoras() {
  let html = "";
  for (let h = 8; h <= 20; h++) {
    html += `<div class="grelha-hora" style="top:${(h - 8) * PX_HORA}px"><span>${paraHora(h * 60)}</span></div>`;
  }
  el.grelhaHoras.innerHTML = html;
}

// Um bloco (ocupado, em fila ou minha reserva) posicionado pela hora
function htmlBloco(b, classe, titulo) {
  const ini = paraMin(b.start);
  const fim = paraMin(b.end);
  const topo = ((ini - ABERTURA) / 60) * PX_HORA + 1;
  const altura = ((fim - ini) / 60) * PX_HORA - 2;
  return (
    `<div class="bloco ${classe}${altura < 30 ? " curto" : ""}" style="top:${topo}px;height:${altura}px">` +
    `<span>${esc(titulo)}</span><span class="bloco-hora">${esc(b.start)}–${esc(b.end)}</span></div>`
  );
}

function desenharBlocos() {
  const cruzaFila = (o) =>
    dados.naFila.some((f) => sobrepoe(paraMin(o.start), paraMin(o.end), paraMin(f.start), paraMin(f.end)));

  const ocupados = dados.ocupados.map((o) =>
    cruzaFila(o) ? htmlBloco(o, "fila", "Ocupado · está na fila") : htmlBloco(o, "ocupado", "Ocupado")
  );
  const minhas = dados.minhas.map((m) => htmlBloco(m, "minha", "A sua reserva"));
  el.grelhaBlocos.innerHTML = ocupados.join("") + minhas.join("");
}

// A seleção é um único elemento, para o top/height poderem animar
function desenharSelecao() {
  const altura = ((estado.fim - estado.inicio) / 60) * PX_HORA;
  el.selecao.style.top = ((estado.inicio - ABERTURA) / 60) * PX_HORA + "px";
  el.selecao.style.height = altura + "px";
  el.selecao.classList.toggle("curto", altura < 34);
  el.selecao.innerHTML =
    `<span>Seleção</span><span class="bloco-hora">${paraHora(estado.inicio)}–${paraHora(estado.fim)}</span>`;
}

// Linha vermelha de "agora" (só se o dia for hoje e estivermos em horário de abertura)
function desenharAgora() {
  const m = agoraMin();
  const visivel = eHoje() && m >= ABERTURA && m <= FECHO;
  el.linhaAgora.hidden = !visivel;
  if (visivel) el.linhaAgora.style.top = ((m - ABERTURA) / 60) * PX_HORA - 1 + "px";
}

// Clicar numa hora move a seleção para essa hora, mantendo a duração
el.grelha.addEventListener("click", (e) => {
  const y = e.clientY - el.grelha.getBoundingClientRect().top;
  const hora = Math.min(19, Math.max(8, 8 + Math.floor(y / PX_HORA)));
  posicionar(hora * 60, estado.fim - estado.inicio);
  atualizar();
});

// ---------------------------------------------------------------------
// Desenho: painel "Nova reserva"
// ---------------------------------------------------------------------
const TEXTOS_ESTADO = {
  livre:   { icone: "check_circle" },
  ocupado: { icone: "error",           texto: "Ocupado neste intervalo" },
  fila:    { icone: "hourglass_top",   texto: "Ocupado · já está na fila" },
  minha:   { icone: "event_available", texto: "Já tem uma reserva aqui" },
  passado: { icone: "schedule",        texto: "Este horário já passou" },
};

function desenharPainel() {
  el.painelDia.textContent = textoDia(estado.dia);
  el.inicioValor.textContent = paraHora(estado.inicio);
  el.fimValor.textContent = paraHora(estado.fim);

  // Os botões + / − não deixam passar dos limites
  el.inicioMenos.disabled = estado.inicio - PASSO < minInicio();
  el.inicioMais.disabled = estado.inicio + PASSO > estado.fim - PASSO;
  el.fimMenos.disabled = estado.fim - PASSO < estado.inicio + PASSO;
  el.fimMais.disabled = estado.fim + PASSO > FECHO;

  const tipo = calcularEstado();
  const info = TEXTOS_ESTADO[tipo];
  const texto = tipo === "livre" ? "Disponível · " + duracaoTexto(estado.fim - estado.inicio) : info.texto;
  el.estado.className = "estado " + (tipo === "passado" ? "ocupado" : tipo);
  el.estado.innerHTML = `<span class="material-symbols-rounded" aria-hidden="true">${info.icone}</span><span>${texto}</span>`;

  // O botão principal muda conforme o estado
  const intervalo = paraHora(estado.inicio) + "–" + paraHora(estado.fim);
  el.botaoPrincipal.disabled = tipo === "passado";
  if (tipo === "livre") el.botaoPrincipal.textContent = "Reservar " + intervalo;
  else if (tipo === "ocupado" || tipo === "fila") el.botaoPrincipal.textContent = "Ver alternativas";
  else if (tipo === "minha") el.botaoPrincipal.textContent = "Ver as minhas reservas";
  else el.botaoPrincipal.textContent = "Reservar";
}

// Redesenha tudo o que depende do dia, da seleção ou das reservas
function atualizar() {
  desenharBlocos();
  desenharSelecao();
  desenharAgora();
  desenharPainel();
}

// Seletores − / +
el.inicioMenos.addEventListener("click", () => mudarInicio(-PASSO));
el.inicioMais.addEventListener("click", () => mudarInicio(PASSO));
el.fimMenos.addEventListener("click", () => mudarFim(-PASSO));
el.fimMais.addEventListener("click", () => mudarFim(PASSO));

function mudarInicio(delta) {
  const novo = estado.inicio + delta;
  if (novo < minInicio() || novo > estado.fim - PASSO) return;
  estado.inicio = novo;
  atualizar();
}
function mudarFim(delta) {
  const novo = estado.fim + delta;
  if (novo < estado.inicio + PASSO || novo > FECHO) return;
  estado.fim = novo;
  atualizar();
}

// Botão principal
el.botaoPrincipal.addEventListener("click", () => {
  const tipo = calcularEstado();
  if (tipo === "livre") reservar();
  else if (tipo === "ocupado" || tipo === "fila") abrirConflito();
  else if (tipo === "minha") location.href = "reservas.html";
});

// ---------------------------------------------------------------------
// Janelas (modais): abrem/fecham com o X, com Esc e clicando fora
// ---------------------------------------------------------------------
let modalAberto = null;
let focoAnterior = null;

function abrirModal(modal) {
  focoAnterior = document.activeElement;
  modal.hidden = false;
  modalAberto = modal;
  document.body.classList.add("modal-aberto");
  modal.querySelector(".modal-fechar").focus();
}
function fecharModal() {
  if (!modalAberto) return;
  modalAberto.hidden = true;
  modalAberto = null;
  document.body.classList.remove("modal-aberto");
  if (focoAnterior) focoAnterior.focus();
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") fecharModal();
});
document.querySelectorAll(".modal").forEach((modal) => {
  // clicar no fundo escuro (e não no cartão) fecha a janela
  modal.addEventListener("click", (e) => {
    if (e.target === modal) fecharModal();
  });
});
document.querySelectorAll("[data-fechar]").forEach((b) => b.addEventListener("click", fecharModal));

// ---------------------------------------------------------------------
// Reservar e janela "Reserva confirmada"
// ---------------------------------------------------------------------
function reservar() {
  const horario = paraHora(estado.inicio) + "–" + paraHora(estado.fim);
  dados.minhas.push({ start: paraHora(estado.inicio), end: paraHora(estado.fim) });
  atualizar();
  abrirConfirmacao(dados.recurso.name, horario);
}

function abrirConfirmacao(nomeRecurso, horario) {
  const codigo = "SU-" + Math.floor(10000 + Math.random() * 90000); // código fictício
  $("conf-email").textContent = emailUtilizador;
  $("conf-recurso").textContent = nomeRecurso;
  $("conf-data").textContent = textoDia(estado.dia) + " " + deISO(estado.dia).getFullYear();
  $("conf-horario").textContent = horario;
  $("conf-codigo").textContent = codigo;
  fecharModal();
  abrirModal(el.modalConfirmacao);
}

// ---------------------------------------------------------------------
// Janela "Este horário já está ocupado"
// ---------------------------------------------------------------------
function desenharSugestoes() {
  const lista = dados.sugestoes;
  el.blocoSugestoes.hidden = lista.length === 0;
  el.botaoSugestao.disabled = lista.length === 0;
  el.listaSugestoes.innerHTML = lista
    .map((s, i) => {
      const ativa = i === estado.sugestao;
      return (
        `<button type="button" class="sugestao${ativa ? " ativa" : ""}" data-i="${i}" role="radio" aria-checked="${ativa}">` +
        `<span><span class="sugestao-nome">${esc(s.name)} · <span class="sugestao-tag">${esc(s.tag)}</span></span>` +
        `<span class="sugestao-sub">${esc(s.sub)}</span></span>` +
        `<span class="sugestao-hora">${esc(s.time)}</span></button>`
      );
    })
    .join("");
}

el.listaSugestoes.addEventListener("click", (e) => {
  const botao = e.target.closest(".sugestao");
  if (!botao) return;
  estado.sugestao = Number(botao.dataset.i);
  desenharSugestoes();
});

function abrirConflito() {
  const intervalo = paraHora(estado.inicio) + "–" + paraHora(estado.fim);
  $("conflito-sub").textContent = dados.recurso.name + " · " + textoDia(estado.dia) + " · " + intervalo;
  el.caixaFila.hidden = calcularEstado() === "fila"; // já está na fila: não mostra outra vez
  estado.sugestao = 0;
  desenharSugestoes();
  abrirModal(el.modalConflito);
}

// "Entrar na fila": regista o pedido e pinta o bloco a laranja tracejado
el.botaoFila.addEventListener("click", () => {
  dados.naFila.push({ start: paraHora(estado.inicio), end: paraHora(estado.fim) });
  fecharModal();
  atualizar();
});

// "Reservar sugestão": confirma a sugestão escolhida (outro recurso, fictício)
el.botaoSugestao.addEventListener("click", () => {
  const s = dados.sugestoes[estado.sugestao];
  if (s) abrirConfirmacao(s.name, s.time);
});

// ---------------------------------------------------------------------
// Arranque
// ---------------------------------------------------------------------
el.emailUtilizador.textContent = emailUtilizador;
desenharCaminho();
desenharCabecalho();
desenharDias();
desenharHoras();
posicionar(inicial.inicio, inicial.duracao);
atualizar();
setInterval(atualizar, 60000); // mantém a linha de "agora" e as regras do passado em dia