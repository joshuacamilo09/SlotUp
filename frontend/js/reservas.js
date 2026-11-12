// ===== MINHAS RESERVAS =====
// Duas abas: "Próximas" (reservas confirmadas) e "Fila de espera".
// Em cima, o banner da vaga aberta (igual ao da página inicial).
// Dados reais do booking-service (js/api.js); ícones em js/catalogo.js.

const utilizador = requireAuth();

// ===== AJUDANTES DE DATAS (iguais aos do home.js) =====
const DIAS_CURTOS = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];
const MESES_CURTOS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const hora = (d) => String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
const diaCurto = (d) => `${DIAS_CURTOS[d.getDay()]}, ${d.getDate()} ${MESES_CURTOS[d.getMonth()]}`;

// ===== ESTADO =====
// Tudo o que a página mostra sai daqui; desenhar() lê o estado e monta o HTML
const estado = {
  aba: new URLSearchParams(location.search).get("aba") === "fila" ? "fila" : "proximas",
  reservas: [],
  fila: [],
};

// ===== CATEGORIA → ícone e cores =====
// Devolve o atributo style com as variáveis que o CSS usa (.linha-icone)
function corCategoria(nome) {
  const id = idCategoria(nome ?? "");
  return `--cor-cat: var(--${id}, var(--cor-primaria)); --cor-cat-suave: var(--${id}-suave, var(--cor-chip))`;
}
function iconeCategoria(nome) {
  return CATEGORIAS_UI[idCategoria(nome ?? "")]?.icon ?? "event";
}

// Primeira coluna das duas listas: ícone + nome do recurso + categoria
function colunaRecurso(nome, categoria) {
  return `
    <div class="linha-recurso">
      <span class="linha-icone" style="${corCategoria(categoria)}"><span class="icone">${iconeCategoria(categoria)}</span></span>
      <div>
        <div class="linha-nome">${esc(nome)}</div>
        <div class="linha-cat">${esc(categoria)}</div>
      </div>
    </div>`;
}

// ===== LINHAS =====
function linhaReserva(r) {
  const inicio = new Date(r.start_at);
  const fim = new Date(r.end_at);
  return `
    <div class="linha">
      ${colunaRecurso(r.resource_name, r.category_name)}
      <div class="linha-data">${diaCurto(inicio)}</div>
      <div class="linha-hora">${hora(inicio)}–${hora(fim)}</div>
      <span class="selo reservada">Reservado por si</span>
      ${inicio > new Date()
        ? `<button class="botao-perigo" data-cancelar="${r.id}">Cancelar</button>`
        : "<span></span>"  /* já começou: não se pode cancelar, mas a coluna fica ocupada */}
    </div>`;
}

function linhaFila(f) {
  const inicio = new Date(f.desired_start);
  const fim = new Date(f.desired_end);
  const selo = f.status === "OFFERED"
    ? '<span class="selo aberta">Vaga aberta</span>'
    : `<span class="selo espera">${f.position}.º na fila</span>`;
  return `
    <div class="linha fila">
      ${colunaRecurso(f.resource_name, f.category_name)}
      <div class="linha-hora">${diaCurto(inicio)} · ${hora(inicio)}–${hora(fim)}</div>
      ${selo}
      <button class="botao-perigo" data-sair="${f.id}">Sair da fila</button>
    </div>`;
}

// Caixa da lista: as linhas, ou uma frase quando está vazia
function caixa(linhas, textoVazio) {
  return `<div class="lista">${linhas.length ? linhas.join("") : `<p class="lista-vazia">${esc(textoVazio)}</p>`}</div>`;
}

// ===== DESENHAR =====
function desenhar() {
  document.getElementById("painel-proximas").innerHTML = caixa(
    estado.reservas.map(linhaReserva),
    "Ainda não tem reservas. Escolha uma categoria na página inicial para começar.");
  document.getElementById("painel-fila").innerHTML = caixa(
    estado.fila.map(linhaFila),
    "Não está em nenhuma fila. Quando um horário estiver ocupado, pode entrar na fila e avisamos por email.");

  document.getElementById("conta-proximas").textContent = estado.reservas.length;
  document.getElementById("conta-fila").textContent = estado.fila.length;

  // Badge laranja do cabeçalho (criado pelo layout.js)
  const badge = document.getElementById("badge-fila");
  if (badge) {
    badge.textContent = estado.fila.length;
    badge.hidden = estado.fila.length === 0;
  }

  // Abas: marca a ativa e mostra só o painel dela
  document.querySelectorAll(".aba").forEach((aba) => {
    const ativa = aba.dataset.aba === estado.aba;
    aba.classList.toggle("ativo", ativa);
    aba.setAttribute("aria-selected", ativa);
  });
  document.getElementById("painel-proximas").hidden = estado.aba !== "proximas";
  document.getElementById("painel-fila").hidden = estado.aba !== "fila";

  // Banner: a oferta que expira primeiro
  const ofertas = estado.fila.filter((f) => f.status === "OFFERED" && f.hold_expires_at)
    .sort((a, b) => new Date(a.hold_expires_at) - new Date(b.hold_expires_at));
  mostrarBanner(ofertas[0] ?? null);
}

// ===== CARREGAR =====
async function carregar() {
  try {
    // As duas chamadas em paralelo
    const [reservas, fila] = await Promise.all([
      api.myReservations("futuras", 50, "CONFIRMED"),   // só confirmadas: as ofertas (HELD) vão para o banner
      api.myWaitlist(),
    ]);
    // A API já devolve por ordem de início; da fila ficam só os pedidos ativos
    estado.reservas = reservas;
    estado.fila = fila
      .filter((f) => f.status === "WAITING" || f.status === "OFFERED")
      .sort((a, b) => new Date(a.desired_start) - new Date(b.desired_start));
    desenhar();
  } catch (err) {
    const erro = caixa([], err.message);
    document.getElementById("painel-proximas").innerHTML = erro;
    document.getElementById("painel-fila").innerHTML = erro;
  }
}

// ===== ABAS =====
// Delegação: um só "ouvinte" na barra de abas
document.querySelector(".abas").addEventListener("click", (e) => {
  const aba = e.target.closest(".aba");
  if (!aba) return;
  mudarAba(aba.dataset.aba);
});
function mudarAba(nome) {
  estado.aba = nome;
  // Guarda a aba no endereço (?aba=fila): ao recarregar, a página abre na mesma aba
  history.replaceState(null, "", nome === "fila" ? "?aba=fila" : location.pathname);
  desenhar();
}

// ===== CANCELAR E SAIR DA FILA =====
// Delegação no <main>: as linhas são redesenhadas, por isso não se põe ouvinte em cada botão
document.querySelector("main").addEventListener("click", async (e) => {
  const cancelar = e.target.closest("[data-cancelar]");
  const sair = e.target.closest("[data-sair]");
  if (!cancelar && !sair) return;

  const botao = cancelar || sair;
  const pergunta = cancelar ? "Cancelar esta reserva?" : "Sair desta fila de espera?";
  if (!confirm(pergunta)) return;

  botao.disabled = true;
  try {
    if (cancelar) {
      await api.cancelReservation(botao.dataset.cancelar);
      toast("Reserva cancelada.");
    } else {
      await api.leaveWaitlist(botao.dataset.sair);
      toast("Saiu da fila de espera.");
    }
  } catch (err) {
    toast(err.message, true);   // ex.: 409 "A reserva já começou e não pode ser cancelada"
  }
  carregar();   // a linha sai da lista (e o botão volta a existir, já ativo)
});

// ===== BANNER DA VAGA (igual ao do home.js) =====
const TEMPO_OFERTA = 15 * 60;   // segundos que o backend guarda a vaga
const banner = document.getElementById("banner-vaga");
let contador = null;

function mostrarBanner(oferta) {
  clearInterval(contador);
  banner.hidden = !oferta;
  if (!oferta) return;

  const inicio = new Date(oferta.desired_start);
  const fim = new Date(oferta.desired_end);
  document.getElementById("vaga-nome").textContent = oferta.resource_name;
  document.getElementById("vaga-quando").textContent = `${diaCurto(inicio).toLowerCase()} ${hora(inicio)}–${hora(fim)}`;
  banner.dataset.id = oferta.id;

  const expira = new Date(oferta.hold_expires_at).getTime();
  function atualizarContador() {
    const restante = Math.max(0, Math.round((expira - Date.now()) / 1000));
    document.getElementById("vaga-tempo").textContent = `${Math.floor(restante / 60)}:${String(restante % 60).padStart(2, "0")}`;
    const pct = Math.min(100, (restante / TEMPO_OFERTA) * 100);
    document.getElementById("vaga-anel").style.setProperty("--progresso", pct + "%");
    if (restante === 0) {
      clearInterval(contador);
      banner.hidden = true;
      carregar();   // a vaga passou ao seguinte
    }
  }
  atualizarContador();
  contador = setInterval(atualizarContador, 1000);
}

async function responderOferta(aceitar) {
  const id = banner.dataset.id;
  const botoes = banner.querySelectorAll("button");
  botoes.forEach((b) => (b.disabled = true));
  try {
    if (aceitar) {
      await api.acceptOffer(id);
      toast("Vaga confirmada! Já está nas suas próximas reservas.");
      estado.aba = "proximas";   // mostra logo a nova reserva
    } else {
      await api.leaveWaitlist(id);
      toast("Vaga recusada. Passou para o próximo da fila.");
    }
  } catch (err) {
    toast(err.message, true);   // ex.: 409 "A oferta expirou"
  } finally {
    botoes.forEach((b) => (b.disabled = false));
    carregar();
  }
}
document.getElementById("vaga-confirmar").addEventListener("click", () => responderOferta(true));
document.getElementById("vaga-recusar").addEventListener("click", () => responderOferta(false));

// ===== ARRANQUE =====
carregar();
setInterval(carregar, 30 * 1000);   // a cada 30 s: apanha uma vaga que abriu sem recarregar