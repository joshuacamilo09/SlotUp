// =====================================================================
// SlotUp – tela "Detalhe do recurso" (recurso.html)
// URL: recurso.html?id=<uuid>&dia=AAAA-MM-DD&inicio=HH:MM&fim=HH:MM
// Dados reais do booking-service (js/api.js); textos dos códigos em js/catalogo.js.
// =====================================================================

// Sem sessão, requireAuth() manda para o login.
const utilizador = requireAuth();
const emailUtilizador = (utilizador && utilizador.email) || "";

// ---------------------------------------------------------------------
// Dados da API. Os intervalos ficam em minutos do dia escolhido: { ini: 600, fim: 660 } = 10:00–11:00
// ---------------------------------------------------------------------
const dados = {
  recurso: null,      // o recurso, como vem da API
  cat: "coworking",   // id curto da categoria (para cores e textos)
  abertura: [],       // quando o recurso está aberto neste dia
  ocupados: [],       // reservas (de qualquer pessoa) neste dia
  minhas: [],         // as minhas reservas confirmadas neste recurso, neste dia
  naFila: [],         // os meus pedidos ativos na fila deste recurso, neste dia
};
let todasMinhas = [];  // as minhas reservas neste recurso (todas as datas), como vêm da API
let todaFila = [];     // os meus pedidos na fila deste recurso (todas as datas)
let pedidoAtual = 0;   // para ignorar respostas antigas quando se troca de dia depressa
let aEnviar = false;   // enquanto espera a resposta de "Reservar": botão desativado

// ---------------------------------------------------------------------
// Constantes e regras de horário (iguais às do backend)
// ---------------------------------------------------------------------
const ABERTURA = 8 * 60;  // a grelha mostra das 08:00...
const FECHO = 20 * 60;    // ...às 20:00
const PASSO = 15;         // horários de 15 em 15 minutos (também a duração mínima)
const PX_HORA = 48;       // altura de cada hora na grelha
const MAX_DIAS = 30;      // no máximo 30 dias à frente

const SEMANA = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];
const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

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
// Horas da API (ISO com fuso) -> { ini, fim } em minutos desde a meia-noite do dia escolhido
function emMinutos(inicioIso, fimIso) {
  const meiaNoite = deISO(estado.dia);
  return {
    ini: Math.round((new Date(inicioIso) - meiaNoite) / 60000),
    fim: Math.round((new Date(fimIso) - meiaNoite) / 60000),
  };
}
// Só os intervalos que tocam neste dia (0 a 24h)
const doDia = (i) => i.fim > 0 && i.ini < 24 * 60;

// ---------------------------------------------------------------------
// Parâmetros da URL: id, dia, inicio e fim
// ---------------------------------------------------------------------
const params = new URLSearchParams(location.search);
const idRecurso = params.get("id");
if (!idRecurso) location.replace("index.html");   // sem recurso: volta à home
const hoje = new Date();
hoje.setHours(0, 0, 0, 0);

// O dia da URL só vale se for hoje ou até daqui a 30 dias
function diaValido(iso) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(iso || "")) return false;
  const d = deISO(iso);
  const diff = Math.round((d - hoje) / 86400000);
  return paraISO(d) === iso && diff >= 0 && diff <= MAX_DIAS;
}

// "HH:MM" válido = múltiplo de 15 minutos dentro da grelha; senão null
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

// Estado da seleção: passado, fechado, minha, fila, ocupado ou livre
function calcularEstado() {
  const { inicio, fim } = estado;
  const cruza = (b) => sobrepoe(inicio, fim, b.ini, b.fim);
  if (inicio < minInicio()) return "passado";
  // Tem de caber inteira num intervalo de abertura (a mesma regra do backend)
  if (!dados.abertura.some((a) => a.ini <= inicio && fim <= a.fim)) return "fechado";
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
  caixaFila: $("caixa-fila"),
  botaoFila: $("botao-fila"),
  botaoSugestao: $("botao-sugestao"),
};

// ---------------------------------------------------------------------
// Desenho: caminho e cabeçalho do recurso (textos de dados passam por esc())
// ---------------------------------------------------------------------
function desenharCaminho() {
  const r = dados.recurso;
  el.caminho.innerHTML =
    `<a href="index.html">Início</a> / ` +
    `<a href="categoria.html?cat=${encodeURIComponent(dados.cat)}">${esc(r.category_name)}</a> / ` +
    `<strong>${esc(r.name)}</strong>`;
}

function desenharCabecalho() {
  const r = dados.recurso;
  const c = dados.cat;
  // "Salas de reunião · Piso 2 · até 8 pessoas" (a localização está na description)
  const sub = [textoTipo(c, r.resource_type), r.description, textoCapacidade(c, r.capacity)]
    .filter(Boolean).map(esc).join(" · ");
  const tags = atributosEmTexto(c, r.attributes).map((t) => `<span class="recurso-tag">${esc(t)}</span>`).join("");

  el.cabecalho.classList.add("cat-" + c);
  el.cabecalho.innerHTML =
    `<div class="recurso-icone"><span class="material-symbols-rounded" aria-hidden="true">${esc(iconeTipo(c, r.resource_type))}</span></div>` +
    `<div>` +
      `<div class="recurso-titulo"><h1>${esc(r.name)}</h1><span class="pilula-cat">${esc(r.category_name)}</span></div>` +
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
  if (!botao || botao.dataset.dia === estado.dia) return;
  estado.dia = botao.dataset.dia;
  // guarda o dia na URL, para se poder partilhar/recarregar
  params.set("dia", estado.dia);
  history.replaceState(null, "", location.pathname + "?" + params.toString());
  posicionar(estado.inicio, estado.fim - estado.inicio);
  desenharDias();
  carregarDia();   // a disponibilidade muda de dia para dia
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

// Um bloco (fechado, ocupado, em fila ou minha reserva) posicionado pela hora.
// Corta o que fica fora da grelha (ex.: estacionamento ocupado das 07:00 às 09:00 → 08:00–09:00)
function htmlBloco(b, classe, titulo) {
  const ini = Math.max(b.ini, ABERTURA);
  const fim = Math.min(b.fim, FECHO);
  if (fim <= ini) return "";   // fora da grelha
  const topo = ((ini - ABERTURA) / 60) * PX_HORA + 1;
  const altura = ((fim - ini) / 60) * PX_HORA - 2;
  return (
    `<div class="bloco ${classe}${altura < 30 ? " curto" : ""}" style="top:${topo}px;height:${altura}px">` +
    `<span>${esc(titulo)}</span><span class="bloco-hora">${paraHora(ini)}–${paraHora(fim)}</span></div>`
  );
}

// Partes da grelha (08:00–20:00) em que o recurso está fechado = o que sobra da abertura
function intervalosFechados() {
  const fechados = [];
  let cursor = ABERTURA;
  for (const a of [...dados.abertura].sort((x, y) => x.ini - y.ini)) {
    if (a.ini > cursor) fechados.push({ ini: cursor, fim: a.ini });
    cursor = Math.max(cursor, a.fim);
  }
  if (cursor < FECHO) fechados.push({ ini: cursor, fim: FECHO });
  return fechados;
}

function desenharBlocos() {
  const igual = (a, b) => a.ini === b.ini && a.fim === b.fim;
  const cruzaFila = (o) => dados.naFila.some((f) => sobrepoe(o.ini, o.fim, f.ini, f.fim));

  const fechados = intervalosFechados().map((f) => htmlBloco(f, "fechado", "Fechado"));
  // O "busy" da API também inclui as minhas reservas: essas desenham-se à parte, como "A sua reserva"
  const ocupados = dados.ocupados
    .filter((o) => !dados.minhas.some((m) => igual(m, o)))
    .map((o) => (cruzaFila(o) ? htmlBloco(o, "fila", "Ocupado · está na fila") : htmlBloco(o, "ocupado", "Ocupado")));
  const minhas = dados.minhas.map((m) => htmlBloco(m, "minha", "A sua reserva"));
  el.grelhaBlocos.innerHTML = fechados.join("") + ocupados.join("") + minhas.join("");
}

// A seleção é um único elemento, para o top/height poderem animar
function desenharSelecao() {
  const altura = ((estado.fim - estado.inicio) / 60) * PX_HORA;
  el.selecao.style.top = ((estado.inicio - ABERTURA) / 60) * PX_HORA + "px";
  el.selecao.style.height = altura + "px";
  el.selecao.classList.toggle("curto", altura < 34);
  el.selecao.classList.toggle("curto", altura < 34);

  // A seleção toca num bloco (ocupado, em fila, minha reserva ou fechado)?
  const cruza = (b) => sobrepoe(estado.inicio, estado.fim, b.ini, b.fim);
  const sobreBloco = [...dados.ocupados, ...dados.minhas, ...intervalosFechados()].some(cruza);
  // Por cima de um bloco: só o contorno, sem fundo nem texto, para o texto do bloco continuar legível
  el.selecao.classList.toggle("sobre-bloco", sobreBloco);
  // Contorno vermelho quando não se pode reservar ali (ocupado, em fila, fechado ou passado)
  el.selecao.classList.toggle("conflito", ["ocupado", "fila", "fechado", "passado"].includes(calcularEstado()));
  el.selecao.innerHTML = sobreBloco
    ? ""
    : `<span>Seleção</span><span class="bloco-hora">${paraHora(estado.inicio)}–${paraHora(estado.fim)}</span>`;
}

// Linha vermelha de "agora" (só se o dia for hoje e estivermos dentro da grelha)
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
  fechado: { icone: "block",           texto: "Fechado neste horário" },
};

// Preenche uma lista (<select>) com as horas de 15 em 15 min, de "de" até "ate", e escolhe "valor"
function preencherHoras(lista, de, ate, valor) {
  let html = "";
  for (let m = de; m <= ate; m += PASSO) {
    html += `<option value="${m}"${m === valor ? " selected" : ""}>${paraHora(m)}</option>`;
  }
  lista.innerHTML = html;
}

function desenharPainel() {
  el.painelDia.textContent = textoDia(estado.dia);
  // Listas de horas: o início vai do mínimo do dia até 19:45; o fim, de início + 15 min até 20:00
  preencherHoras(el.inicioValor, Math.min(minInicio(), estado.inicio), FECHO - PASSO, estado.inicio);
  preencherHoras(el.fimValor, estado.inicio + PASSO, FECHO, estado.fim);

  // Os botões + / − não deixam passar dos limites
  el.inicioMenos.disabled = estado.inicio - PASSO < minInicio();
  el.inicioMais.disabled = estado.inicio + PASSO > estado.fim - PASSO;
  el.fimMenos.disabled = estado.fim - PASSO < estado.inicio + PASSO;
  el.fimMais.disabled = estado.fim + PASSO > FECHO;

  const tipo = calcularEstado();
  const info = TEXTOS_ESTADO[tipo];
  const texto = tipo === "livre" ? "Disponível · " + duracaoTexto(estado.fim - estado.inicio) : info.texto;
  el.estado.className = "estado " + (tipo === "passado" || tipo === "fechado" ? "ocupado" : tipo);
  el.estado.innerHTML = `<span class="material-symbols-rounded" aria-hidden="true">${info.icone}</span><span>${texto}</span>`;

  // O botão principal muda conforme o estado
  const intervalo = paraHora(estado.inicio) + "–" + paraHora(estado.fim);
  el.botaoPrincipal.disabled = aEnviar || tipo === "passado" || tipo === "fechado";
  if (aEnviar) el.botaoPrincipal.textContent = "A reservar…";
  else if (tipo === "livre") el.botaoPrincipal.textContent = "Reservar " + intervalo;
  else if (tipo === "ocupado" || tipo === "fila") el.botaoPrincipal.textContent = "Ver alternativas";
  else if (tipo === "minha") el.botaoPrincipal.textContent = "Ver as minhas reservas";
  else if (tipo === "fechado") el.botaoPrincipal.textContent = "Fechado";
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

// Listas de horas: ao mudar o início, a duração mantém-se (como num calendário)
el.inicioValor.addEventListener("change", () => {
  posicionar(Number(el.inicioValor.value), estado.fim - estado.inicio);
  atualizar();
});
el.fimValor.addEventListener("change", () => {
  estado.fim = Number(el.fimValor.value);
  atualizar();
});

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
// Hora para a API: sem fuso ("2026-11-12T10:00") = hora local do complexo
const paraApi = (min) => `${estado.dia}T${paraHora(min)}`;

async function reservar() {
  aEnviar = true;
  desenharPainel();
  try {
    const reserva = await api.createReservation(dados.recurso.id, paraApi(estado.inicio), paraApi(estado.fim));
    aEnviar = false;
    await carregarMeus();   // a nova reserva passa a aparecer como "A sua reserva"
    await carregarDia();
    abrirConfirmacao(reserva);
  } catch (err) {
    aEnviar = false;
    toast(err.message, true);   // ex.: 409 "Este horário já está reservado" (alguém foi mais rápido)
    carregarDia();              // atualiza a grelha com o que está ocupado agora
  }
}

function abrirConfirmacao(reserva) {
  const inicio = new Date(reserva.start_at);
  const fim = new Date(reserva.end_at);
  const hhmm = (d) => String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
  $("conf-email").textContent = emailUtilizador;
  $("conf-recurso").textContent = reserva.resource_name;
  $("conf-data").textContent = textoDia(estado.dia) + " " + deISO(estado.dia).getFullYear();
  $("conf-horario").textContent = hhmm(inicio) + "–" + hhmm(fim);
  // Código curto a partir do id da reserva (UUID): "SU-5E1F0D2A"
  $("conf-codigo").textContent = "SU-" + reserva.id.slice(0, 8).toUpperCase();
  fecharModal();
  abrirModal(el.modalConfirmacao);
}

// ---------------------------------------------------------------------
// Janela "Este horário já está ocupado"
// As sugestões vêm do CSP (scheduling), na 3.ª entrega: por agora ficam escondidas.
// ---------------------------------------------------------------------
el.blocoSugestoes.hidden = true;
el.botaoSugestao.hidden = true;

function abrirConflito() {
  const intervalo = paraHora(estado.inicio) + "–" + paraHora(estado.fim);
  $("conflito-sub").textContent = dados.recurso.name + " · " + textoDia(estado.dia) + " · " + intervalo;
  el.caixaFila.hidden = calcularEstado() === "fila"; // já está na fila: não mostra outra vez
  abrirModal(el.modalConflito);
}

// "Entrar na fila": POST /fila com o mesmo horário
el.botaoFila.addEventListener("click", async () => {
  el.botaoFila.disabled = true;
  try {
    const pedido = await api.joinWaitlist(dados.recurso.id, paraApi(estado.inicio), paraApi(estado.fim));
    fecharModal();
    toast(pedido.position
      ? `Está na fila (${pedido.position}.º). Avisamos por email quando a vaga abrir.`
      : "A vaga abriu entretanto: veja o aviso na página inicial.");   // raro: alguém cancelou no mesmo instante
    await carregarMeus();
    await carregarDia();
  } catch (err) {
    toast(err.message, true);   // ex.: 409 "O horário está livre: faça a reserva diretamente"
  } finally {
    el.botaoFila.disabled = false;
  }
});

// ---------------------------------------------------------------------
// Carregar da API
// ---------------------------------------------------------------------
// As minhas reservas e pedidos na fila deste recurso (todas as datas)
async function carregarMeus() {
  const [reservas, fila] = await Promise.all([
    api.myReservations("futuras", 200, "CONFIRMED"),
    api.myWaitlist(),
  ]);
  todasMinhas = reservas.filter((r) => r.resource_id === idRecurso);
  todaFila = fila.filter((f) => f.resource_id === idRecurso && (f.status === "WAITING" || f.status === "OFFERED"));
}

// Disponibilidade do dia escolhido, convertida para minutos desse dia
async function carregarDia() {
  const meu = ++pedidoAtual;
  try {
    const disp = await api.availability(idRecurso, estado.dia);
    if (meu !== pedidoAtual) return;   // entretanto escolheu outro dia: esta resposta já não interessa
    dados.abertura = disp.opening.map((i) => emMinutos(i.start, i.end));
    dados.ocupados = disp.busy.map((i) => emMinutos(i.start, i.end));
    dados.minhas = todasMinhas.map((r) => emMinutos(r.start_at, r.end_at)).filter(doDia);
    dados.naFila = todaFila.map((f) => emMinutos(f.desired_start, f.desired_end)).filter(doDia);
  } catch (err) {
    toast(err.message, true);
  }
  atualizar();
}

// ---------------------------------------------------------------------
// Arranque
// ---------------------------------------------------------------------
async function iniciar() {
  el.emailUtilizador.textContent = emailUtilizador;
  desenharDias();
  desenharHoras();
  posicionar(inicial.inicio, inicial.duracao);
  try {
    // O recurso e as minhas reservas/fila ao mesmo tempo
    const [recurso] = await Promise.all([api.resource(idRecurso), carregarMeus()]);
    dados.recurso = recurso;
    dados.cat = idCategoria(recurso.category_name);
    desenharCaminho();
    desenharCabecalho();
    await carregarDia();
  } catch (err) {
    // Ex.: 404 (recurso desativado ou id errado)
    el.cabecalho.innerHTML = `<p class="recurso-sub">${esc(err.message)} · <a href="index.html">Voltar ao início</a></p>`;
    el.botaoPrincipal.disabled = true;
  }
}
iniciar();
setInterval(() => { if (dados.recurso) carregarDia(); }, 60000); // mantém a grelha, a linha de "agora" e as regras do passado em dia