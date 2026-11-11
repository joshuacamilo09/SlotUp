// ===== HOME =====
// Banner da vaga (fila de espera), saudação, categorias, próximas reservas e fila.
// Dados reais do booking-service (js/api.js); textos e ícones em js/catalogo.js.

const utilizador = requireAuth();

// ===== AJUDANTES DE DATAS =====
// As horas vêm da API em ISO com fuso ("2026-11-12T09:00:00+00:00").
// new Date(iso) converte para a hora local do navegador (Lisboa).
const DIAS_CURTOS = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];
const MESES_CURTOS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

// Date → "09:00"
function hora(d) {
  return String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
}
// Date → "Sex, 13 nov"
function diaCurto(d) {
  return `${DIAS_CURTOS[d.getDay()]}, ${d.getDate()} ${MESES_CURTOS[d.getMonth()]}`;
}
// A data é hoje?
function eHoje(d) {
  return d.toDateString() === new Date().toDateString();
}

// ===== SAUDAÇÃO =====
function saudacaoPorHora() {
  const h = new Date().getHours();
  if (h < 12) return "Bom dia";
  if (h < 20) return "Boa tarde";
  return "Boa noite";
}
const primeiroNome = utilizador?.name?.split(" ")[0] ?? "";
const hojeTexto = new Date().toLocaleDateString("pt-PT", { weekday: "long", day: "numeric", month: "long" });
document.getElementById("saudacao-titulo").textContent = `${saudacaoPorHora()}, ${primeiroNome}`;
document.getElementById("saudacao-data").textContent = hojeTexto.charAt(0).toUpperCase() + hojeTexto.slice(1);

// ===== CATEGORIAS: "N livres agora" =====
// Livre agora = o recurso está aberto neste momento e não tem nenhuma reserva a decorrer
function livreAgora(disp, agora) {
  if (!disp) return false;
  const dentro = (i) => new Date(i.start) <= agora && agora < new Date(i.end);
  return disp.opening.some(dentro) && !disp.busy.some(dentro);
}

async function carregarCategorias() {
  const lista = document.getElementById("lista-categorias");
  try {
    const [categorias, recursos] = await Promise.all([api.categories(), api.resources()]);
    // Disponibilidade de hoje de cada recurso, em paralelo (se uma falhar, conta como não livre)
    const hoje = toISODate(new Date());
    const disps = await Promise.all(recursos.map((r) => api.availability(r.id, hoje).catch(() => null)));
    const agora = new Date();

    lista.innerHTML = categorias.map((c) => {
      const id = idCategoria(c.name);
      const ui = CATEGORIAS_UI[id] ?? { icon: "category", description: c.description ?? "" };
      const daCategoria = recursos.map((r, i) => ({ r, disp: disps[i] })).filter((x) => x.r.category_id === c.id);
      const livres = daCategoria.filter((x) => livreAgora(x.disp, agora)).length;
      return `
        <a class="card-categoria" href="categoria.html?cat=${id}"
           style="--cor-cat: var(--${id}, var(--cor-primaria)); --cor-cat-suave: var(--${id}-suave, var(--cor-chip))">
          <div class="card-topo">
            <div class="icone-caixa"><span class="icone">${ui.icon}</span></div>
            <span class="icone">arrow_forward</span>
          </div>
          <div>
            <div class="card-nome">${esc(c.name)}</div>
            <div class="card-descricao">${esc(ui.description)}</div>
          </div>
          <div class="card-rodape">
            <i class="ponto-livre"></i>
            <b>${livres} ${livres === 1 ? "livre" : "livres"} agora</b>
            <span>de ${daCategoria.length}</span>
          </div>
        </a>`;
    }).join("");
  } catch (err) {
    lista.innerHTML = `<p class="painel-vazio">${esc(err.message)}</p>`;
  }
}

// ===== PRÓXIMAS RESERVAS =====
async function carregarReservas() {
  const lista = document.getElementById("lista-reservas");
  try {
    // Só as confirmadas: as ofertas da fila (HELD) aparecem no banner
    const reservas = await api.myReservations("futuras", 3, "CONFIRMED");
    if (reservas.length === 0) {
      lista.innerHTML = '<p class="painel-vazio">Sem reservas. Escolha uma categoria acima para começar.</p>';
      return;
    }
    lista.innerHTML = reservas.map((r) => {
      const inicio = new Date(r.start_at);
      const fim = new Date(r.end_at);
      const cat = idCategoria(r.category_name);
      return `
        <div class="reserva">
          <div class="reserva-data">
            <div class="reserva-dia-semana">${eHoje(inicio) ? "Hoje" : DIAS_CURTOS[inicio.getDay()]}</div>
            <div class="reserva-dia">${inicio.getDate()}</div>
          </div>
          <div class="reserva-icone" style="--cor-cat: var(--${cat}, var(--cor-primaria)); --cor-cat-suave: var(--${cat}-suave, var(--cor-chip))">
            <span class="icone">${CATEGORIAS_UI[cat]?.icon ?? "event"}</span>
          </div>
          <div class="reserva-info">
            <div class="reserva-nome">${esc(r.resource_name)}</div>
            <div class="reserva-local">${esc(r.category_name)}</div>
          </div>
          <div class="reserva-hora">${hora(inicio)}–${hora(fim)}</div>
          <!-- O dono só pode cancelar antes de começar: depois disso o botão não aparece -->
          ${inicio > new Date() ? `<button class="botao-cancelar" data-id="${r.id}">Cancelar</button>` : ""}
        </div>`;
    }).join("");
  } catch (err) {
    lista.innerHTML = `<p class="painel-vazio">${esc(err.message)}</p>`;
  }
}

// Cancelar: delegação de eventos na lista (as linhas são redesenhadas)
document.getElementById("lista-reservas").addEventListener("click", async (e) => {
  const botao = e.target.closest(".botao-cancelar");
  if (!botao || !confirm("Cancelar esta reserva?")) return;
  botao.disabled = true;
  try {
    await api.cancelReservation(botao.dataset.id);
    toast("Reserva cancelada.");
    carregarTudo();   // a reserva sai da lista e o "livres agora" pode mudar
  } catch (err) {
    toast(err.message, true);   // ex.: 409 "A reserva já começou e não pode ser cancelada"
    botao.disabled = false;
  }
});

// ===== FILA DE ESPERA + BANNER =====
let contador = null;   // o setInterval do banner

async function carregarFila() {
  const lista = document.getElementById("lista-fila");
  try {
    // A API devolve todos os pedidos (inclusive saídos e expirados): ficam só os ativos
    const fila = (await api.myWaitlist()).filter((f) => f.status === "WAITING" || f.status === "OFFERED");

    // Badge do cabeçalho (criado pelo layout.js): número de pedidos ativos
    const badge = document.getElementById("badge-fila");
    if (badge) {
      badge.textContent = fila.length;
      badge.hidden = fila.length === 0;
    }

    lista.innerHTML = fila.length === 0
      ? '<p class="painel-vazio">Não está em nenhuma fila. Quando um horário estiver ocupado, pode entrar na fila e avisamos por email.</p>'
      : fila.map((f) => {
          const inicio = new Date(f.desired_start);
          const fim = new Date(f.desired_end);
          return `
            <div class="fila-item">
              <div class="fila-topo">
                <b>${esc(f.resource_name)}</b>
                <span class="fila-estado">${f.status === "OFFERED" ? "Vaga aberta" : f.position + ".º na fila"}</span>
              </div>
              <div class="fila-quando">${diaCurto(inicio)} · ${hora(inicio)}–${hora(fim)}</div>
            </div>`;
        }).join("");

    // Banner: a oferta que expira primeiro
    const ofertas = fila.filter((f) => f.status === "OFFERED" && f.hold_expires_at)
      .sort((a, b) => new Date(a.hold_expires_at) - new Date(b.hold_expires_at));
    mostrarBanner(ofertas[0] ?? null);
  } catch (err) {
    lista.innerHTML = `<p class="painel-vazio">${esc(err.message)}</p>`;
  }
}

const TEMPO_OFERTA = 15 * 60;   // segundos que o backend guarda a vaga (HOLD_MINUTES)
const banner = document.getElementById("banner-vaga");

function mostrarBanner(oferta) {
  clearInterval(contador);
  banner.hidden = !oferta;
  if (!oferta) return;

  const inicio = new Date(oferta.desired_start);
  const fim = new Date(oferta.desired_end);
  document.getElementById("vaga-nome").textContent = oferta.resource_name;
  document.getElementById("vaga-quando").textContent = `${diaCurto(inicio).toLowerCase()} ${hora(inicio)}–${hora(fim)}`;
  banner.dataset.id = oferta.id;   // os botões sabem qual é o pedido

  const expira = new Date(oferta.hold_expires_at).getTime();
  function atualizarContador() {
    const restante = Math.max(0, Math.round((expira - Date.now()) / 1000));
    document.getElementById("vaga-tempo").textContent = `${Math.floor(restante / 60)}:${String(restante % 60).padStart(2, "0")}`;
    // O anel encolhe com o tempo; Math.min porque a oferta pode durar menos de 15 min
    const pct = Math.min(100, (restante / TEMPO_OFERTA) * 100);
    document.getElementById("vaga-anel").style.setProperty("--progresso", pct + "%");
    if (restante === 0) {
      clearInterval(contador);
      banner.hidden = true;
      carregarTudo();   // a vaga passou ao seguinte: atualiza a fila
    }
  }
  atualizarContador();
  contador = setInterval(atualizarContador, 1000);
}

// Confirmar ou recusar a vaga
async function responderOferta(aceitar) {
  const id = banner.dataset.id;
  const botoes = banner.querySelectorAll("button");
  botoes.forEach((b) => (b.disabled = true));
  try {
    if (aceitar) {
      await api.acceptOffer(id);
      toast("Vaga confirmada! A reserva está nas suas próximas reservas.");
    } else {
      await api.leaveWaitlist(id);
      toast("Vaga recusada. Passou para o próximo da fila.");
    }
  } catch (err) {
    toast(err.message, true);   // ex.: 409 "A oferta expirou..."
  } finally {
    botoes.forEach((b) => (b.disabled = false));
    carregarTudo();
  }
}
document.getElementById("vaga-confirmar").addEventListener("click", () => responderOferta(true));
document.getElementById("vaga-recusar").addEventListener("click", () => responderOferta(false));

// ===== ARRANQUE =====
function carregarTudo() {
  carregarCategorias();
  carregarReservas();
  carregarFila();
}
carregarTudo();
setInterval(carregarTudo, 60 * 1000);   // atualiza "livres agora", reservas e fila a cada minuto