/* =====================================================================
   SlotUp · Minhas reservas · comportamento da página
   Tudo o que fala com o backend está no objeto `dados` (secção 1).
   O resto da página só usa essas funções.
   ===================================================================== */
(() => {
  "use strict";

  /* ===== 0. Configuração ===== */
  const USAR_DADOS_DE_EXEMPLO = false; // true = dados de exemplo, sem backend; false = exige sessão e usa o backend
  const HOLD_TOTAL_S = 15 * 60;       // duração de uma vaga guardada (anel do banner)
  const CIRCUNFERENCIA = 194.8;       // 2 * pi * 31, o raio do anel no HTML

  /* ===== 1. Dados =====
     Formato que o resto da página espera (datas em ISO ou Date):
       reserva: { id, recurso, categoria, local, inicio, fim,
                  estado: "CONFIRMED" | "HELD", expiraEm?, codigo? }
       fila:    { id, recurso, categoria, local, inicio, fim,
                  estado: "WAITING" | "OFFERED", posicao, reservaId? }
     Correspondência com a base de dados (migração 0002):
       estado    <- reservations.status / waitlist_entries.status
       expiraEm  <- reservations.hold_expires_at
       inicio/fim<- start_at/end_at (reservas) ou desired_start/desired_end (fila)
       reservaId <- waitlist_entries.reservation_id (a reserva HELD da oferta) */
  function criarDadosDeExemplo() {
    const atraso = (valor) => new Promise((ok) => setTimeout(() => ok(valor), 120));
    const em = (dias, h, m = 0) => {
      const d = new Date();
      d.setDate(d.getDate() + dias);
      d.setHours(h, m, 0, 0);
      return d.toISOString();
    };
    let reservas = [
      { id: "r1", recurso: "Sala Atlântico", categoria: "Coworking", local: "Piso 2", inicio: em(1, 11), fim: em(1, 12), estado: "CONFIRMED" },
      { id: "r2", recurso: "Vaga P-115", categoria: "Estacionamento", local: "Piso -1", inicio: em(2, 8, 30), fim: em(2, 18), estado: "CONFIRMED" },
      { id: "r3", recurso: "Quadra de padel 2", categoria: "Desporto", local: "Exterior", inicio: em(5, 9), fim: em(5, 10, 30), estado: "CONFIRMED" },
      {
        id: "h1", recurso: "Personal trainer · Rui", categoria: "Desporto", local: "", inicio: em(3, 8), fim: em(3, 9),
        estado: "HELD", expiraEm: new Date(Date.now() + (HOLD_TOTAL_S - 32) * 1000).toISOString(),
      },
    ];
    let fila = [
      { id: "f1", recurso: "Personal trainer · Rui", categoria: "Desporto", local: "", inicio: em(3, 8), fim: em(3, 9), estado: "OFFERED", posicao: 1, reservaId: "h1" },
    ];
    const copia = (x) => JSON.parse(JSON.stringify(x));

    return {
      listarReservas: () => atraso(copia(reservas)),
      listarFila: () => atraso(copia(fila)),
      async cancelarReserva(id) {
        if (!reservas.some((r) => r.id === id)) throw new Error("Reserva não encontrada.");
        reservas = reservas.filter((r) => r.id !== id);
        return atraso();
      },
      async sairDaFila(id) {
        fila = fila.filter((f) => f.id !== id);
        return atraso();
      },
      async confirmarVaga(reservaId) {
        const r = reservas.find((x) => x.id === reservaId && x.estado === "HELD");
        if (!r || Date.parse(r.expiraEm) <= Date.now()) throw new Error("A vaga já expirou.");
        r.estado = "CONFIRMED";
        r.expiraEm = null;
        r.codigo = "SU-" + String(Math.floor(10000 + Math.random() * 90000));
        fila = fila.filter((f) => f.reservaId !== reservaId);
        return atraso(copia(r));
      },
      async recusarVaga(reservaId) {
        reservas = reservas.filter((r) => r.id !== reservaId);
        fila = fila.filter((f) => f.reservaId !== reservaId);
        return atraso();
      },
    };
  }

  function criarDadosReais() {
    // `request` vem do api.js, que tem de ser carregado antes deste ficheiro
    if (typeof request !== "function") {
      throw new Error("O api.js não foi carregado antes do minhas-reservas.js.");
    }
    const paraReserva = (r) => ({
      id: r.id, recurso: r.resource_name, categoria: r.category_name, local: "",
      inicio: r.start_at, fim: r.end_at, estado: r.status,
      expiraEm: r.hold_expires_at, codigo: null,
    });
    const aindaNao = () => { throw new Error("Esta função ainda não existe no backend."); };
    return {
      async listarReservas() { return (await request("GET", "/reservas/reservas/minhas")).map(paraReserva); },
      cancelarReserva: (id) => request("DELETE", `/reservas/reservas/${id}`),
      // Fila de espera, confirmar e recusar a vaga: ligar quando o backend tiver estas rotas
      listarFila: async () => [],
      sairDaFila: aindaNao,
      confirmarVaga: aindaNao,
      recusarVaga: aindaNao,
    };
  }

  const dados = USAR_DADOS_DE_EXEMPLO ? criarDadosDeExemplo() : criarDadosReais();

  /* ===== 2. Utilitários ===== */
  const $ = (seletor, raiz = document) => raiz.querySelector(seletor);
  const $$ = (seletor, raiz = document) => Array.from(raiz.querySelectorAll(seletor));
  const dois = (n) => String(n).padStart(2, "0");
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const DIAS = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];
  const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
  const fmtDia = (v) => { const d = new Date(v); return `${DIAS[d.getDay()]}, ${d.getDate()} ${MESES[d.getMonth()]}`; };
  const fmtHora = (v) => { const d = new Date(v); return `${dois(d.getHours())}:${dois(d.getMinutes())}`; };
  const fmtIntervalo = (a, b) => `${fmtHora(a)}–${fmtHora(b)}`;
  const fmtContagem = (s) => `${dois(Math.floor(s / 60))}:${dois(s % 60)}`;
  // O desenho mostra um código (SU-50345), mas a tabela reservations ainda não tem essa coluna:
  // enquanto não existir, deriva-se do id da reserva.
  const codigoDe = (r) => r.codigo || "SU-" + String(r.id).replace(/-/g, "").slice(0, 5).toUpperCase();

  function aviso(mensagem, erro = false) {
    const el = document.createElement("div");
    el.className = "toast" + (erro ? " error" : "");
    el.setAttribute("role", erro ? "alert" : "status");
    el.textContent = mensagem;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 3500);
  }

  /* ===== 3. Utilizador ===== */
  function lerUtilizador() {
    try {
      const u = JSON.parse(localStorage.getItem("slotup_user"));
      if (u && u.email) return { nome: u.name || u.nome || u.email, email: u.email };
    } catch (_) { /* sem sessão guardada */ }
    return USAR_DADOS_DE_EXEMPLO ? { nome: "Marta Sousa", email: "marta.sousa@empresa.pt" } : null;
  }
  const utilizador = lerUtilizador();
  if (!utilizador) {
    location.replace("login.html");
    return;
  }
  $("#avatar").textContent = utilizador.nome.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join("");

  /* ===== 4. Ícones por categoria ===== */
  const ICONES = {
    coworking: {
      classe: "tile--teal",
      svg: '<svg viewBox="0 0 24 24"><circle cx="12" cy="9" r="2.6"/><circle cx="5.5" cy="10" r="1.8"/><circle cx="18.5" cy="10" r="1.8"/><path d="M7.5 18c.4-2.6 2.2-4 4.5-4s4.1 1.4 4.5 4M2.5 17c.2-1.7 1.3-2.8 3-2.8M21.5 17c-.2-1.7-1.3-2.8-3-2.8"/></svg>',
    },
    estacionamento: {
      classe: "tile--violet",
      svg: '<svg viewBox="0 0 24 24"><rect x="4" y="3" width="12" height="18" rx="2"/><path d="M8 17v-6h3a2 2 0 0 1 0 4H8M19 8v7a1.5 1.5 0 0 0 3 0v-4l-2-2"/></svg>',
    },
    desporto: {
      classe: "tile--pink",
      svg: '<svg viewBox="0 0 24 24"><circle cx="11" cy="9" r="5.5"/><path d="M7 13.5 3.5 20M17 17.5a1.8 1.8 0 1 0 .01 0"/></svg>',
    },
  };
  const ICONE_OUTRO = { classe: "tile--teal", svg: '<svg viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="3"/></svg>' };
  const iconeDe = (categoria) => ICONES[String(categoria || "").toLowerCase()] || ICONE_OUTRO;

  /* ===== 5. Estado e desenho ===== */
  const estado = { reservas: [], fila: [], hold: null, assinatura: "" };

  function meta(item) {
    return [item.categoria, item.local].filter(Boolean).join(" · ");
  }

  function linhaReserva(r) {
    const ic = iconeDe(r.categoria);
    return `<li class="row">
      <div class="row__what">
        <span class="tile ${ic.classe}" aria-hidden="true">${ic.svg}</span>
        <div><p class="row__name">${esc(r.recurso)}</p><p class="row__meta">${esc(meta(r))}</p></div>
      </div>
      <p class="row__date">${esc(fmtDia(r.inicio))}</p>
      <p class="row__time">${esc(fmtIntervalo(r.inicio, r.fim))}</p>
      <span class="badge badge--ok">Reservado por si</span>
      <button class="link-danger" type="button" data-cancel="${esc(r.id)}">Cancelar</button>
    </li>`;
  }

  function linhaFila(f) {
    const ic = iconeDe(f.categoria);
    const aberta = f.estado === "OFFERED";
    const selo = aberta
      ? '<span class="badge badge--wait">Vaga aberta</span>'
      : `<span class="badge badge--muted">Posição ${esc(f.posicao)}</span>`;
    return `<li class="row row--wait">
      <div class="row__what">
        <span class="tile ${ic.classe}" aria-hidden="true">${ic.svg}</span>
        <div><p class="row__name">${esc(f.recurso)}</p>${meta(f) ? `<p class="row__meta">${esc(meta(f))}</p>` : ""}</div>
      </div>
      <p class="row__when">${esc(fmtDia(f.inicio))} · ${esc(fmtIntervalo(f.inicio, f.fim))}</p>
      ${selo}
      <button class="link-danger" type="button" data-leave="${esc(f.id)}">Sair da fila</button>
    </li>`;
  }

  const caixaVazia = (texto) => `<div class="list"><p class="empty">${esc(texto)}</p></div>`;

  function desenharPainel(painel, itens, fabricaLinha, textoVazio) {
    painel.innerHTML = itens.length
      ? `<ul class="list">${itens.map(fabricaLinha).join("")}</ul>`
      : caixaVazia(textoVazio);
  }

  function desenhar() {
    const agora = Date.now();
    const proximas = estado.reservas
      .filter((r) => r.estado === "CONFIRMED" && Date.parse(r.fim) > agora)
      .sort((a, b) => Date.parse(a.inicio) - Date.parse(b.inicio));
    const holds = estado.reservas
      .filter((r) => r.estado === "HELD" && Date.parse(r.expiraEm) > agora)
      .sort((a, b) => Date.parse(a.expiraEm) - Date.parse(b.expiraEm));
    const fila = estado.fila.slice().sort((a, b) => Date.parse(a.inicio) - Date.parse(b.inicio));

    desenharPainel($("#panel-upcoming"), proximas, linhaReserva, "Ainda não tem reservas próximas.");
    desenharPainel($("#panel-waitlist"), fila, linhaFila, "Não está em nenhuma fila de espera.");
    $("#count-upcoming").textContent = proximas.length;
    $("#count-waitlist").textContent = fila.length;

    estado.hold = holds[0] || null;
    $("#nav-count").textContent = holds.length;
    $("#nav-count").hidden = holds.length === 0;
    desenharBanner();
  }

  /* ===== 6. Banner da vaga aberta e contagem decrescente ===== */
  let relogio = null;
  const pararRelogio = () => { clearInterval(relogio); relogio = null; };

  function desenharBanner() {
    const banner = $("#hold");
    const h = estado.hold;
    banner.hidden = !h;
    if (!h) { pararRelogio(); return; }
    $(".hold__title", banner).textContent =
      `Abriu uma vaga para si: ${h.recurso}, ${fmtDia(h.inicio).toLowerCase()} ${fmtIntervalo(h.inicio, h.fim)}`;
    pararRelogio();
    tique();
    relogio = setInterval(tique, 1000);
  }

  function tique() {
    const h = estado.hold;
    if (!h) return;
    // Calcula sempre a partir da hora de expiração (e não a contar segundos), para ser certo
    // mesmo quando o separador esteve em segundo plano.
    const restante = Math.max(0, Math.round((Date.parse(h.expiraEm) - Date.now()) / 1000));
    $("#hold-time").textContent = fmtContagem(restante);
    $(".ring__bar", $("#hold")).style.strokeDashoffset =
      (CIRCUNFERENCIA * (1 - Math.min(1, restante / HOLD_TOTAL_S))).toFixed(1);
    if (restante === 0) {
      pararRelogio();
      aviso("A vaga expirou e passou para o próximo da fila.");
      carregar(true);
    }
  }

  /* ===== 7. Carregar ===== */
  async function carregar(forcar = false) {
    let reservas, fila;
    try {
      [reservas, fila] = await Promise.all([dados.listarReservas(), dados.listarFila()]);
    } catch (erro) {
      const msg = caixaVazia(erro.message || "Não foi possível carregar as reservas.");
      $("#panel-upcoming").innerHTML = msg;
      $("#panel-waitlist").innerHTML = msg;
      return;
    }
    const assinatura = JSON.stringify([reservas, fila]);
    if (!forcar && assinatura === estado.assinatura) return; // nada mudou: não redesenha
    estado.assinatura = assinatura;
    estado.reservas = reservas;
    estado.fila = fila;
    desenhar();
  }

  /* ===== 8. Separadores (com teclado) ===== */
  const tabs = $$('[role="tab"]');

  function selecionarTab(tab, focar = false) {
    tabs.forEach((t) => {
      const ativo = t === tab;
      t.setAttribute("aria-selected", String(ativo));
      t.tabIndex = ativo ? 0 : -1;
      $("#" + t.getAttribute("aria-controls")).hidden = !ativo;
    });
    if (focar) tab.focus();
  }
  tabs.forEach((t) => t.addEventListener("click", () => selecionarTab(t)));
  $(".tabs").addEventListener("keydown", (e) => {
    const i = tabs.indexOf(document.activeElement);
    if (i < 0) return;
    const destino = { ArrowRight: tabs[(i + 1) % tabs.length], ArrowLeft: tabs[(i - 1 + tabs.length) % tabs.length], Home: tabs[0], End: tabs[tabs.length - 1] }[e.key];
    if (destino) { e.preventDefault(); selecionarTab(destino, true); }
  });
  selecionarTab(tabs.find((t) => t.getAttribute("aria-selected") === "true") || tabs[0]);

  /* ===== 9. Ações ===== */
  async function executar(botao, acao, mensagemOk) {
    botao.disabled = true;
    try {
      await acao();
      if (mensagemOk) aviso(mensagemOk);
    } catch (erro) {
      aviso(erro.message || "Não foi possível concluir a ação.", true);
    } finally {
      botao.disabled = false;
    }
    await carregar(true);
  }

  document.addEventListener("click", (e) => {
    const cancelar = e.target.closest("[data-cancel]");
    if (cancelar) {
      const r = estado.reservas.find((x) => x.id === cancelar.dataset.cancel);
      if (!r) return;
      if (!window.confirm(`Cancelar a reserva de ${r.recurso}, ${fmtDia(r.inicio)}, ${fmtIntervalo(r.inicio, r.fim)}?`)) return;
      executar(cancelar, () => dados.cancelarReserva(r.id), "Reserva cancelada.");
      return;
    }
    const sair = e.target.closest("[data-leave]");
    if (sair) {
      const f = estado.fila.find((x) => x.id === sair.dataset.leave);
      if (!f) return;
      if (!window.confirm(`Sair da fila de espera de ${f.recurso}?`)) return;
      executar(sair, () => dados.sairDaFila(f.id), "Saiu da fila de espera.");
    }
  });

  $("#hold-confirm").addEventListener("click", async (e) => {
    const h = estado.hold;
    if (!h) return;
    const botao = e.currentTarget;
    botao.disabled = true;
    try {
      const reserva = await dados.confirmarVaga(h.id);
      await carregar(true);
      abrirModal(reserva);
    } catch (erro) {
      aviso(erro.message || "Não foi possível confirmar a vaga.", true);
      await carregar(true);
    } finally {
      botao.disabled = false;
    }
  });

  $("#hold-decline").addEventListener("click", (e) => {
    const h = estado.hold;
    if (!h) return;
    if (!window.confirm("Recusar a vaga? Passa para o próximo na fila.")) return;
    executar(e.currentTarget, () => dados.recusarVaga(h.id), "Vaga recusada.");
  });

  /* ===== 10. Modal: reserva confirmada ===== */
  const modal = $("#modal-ok");

  function abrirModal(reserva) {
    $("#modal-email").textContent = utilizador.email;
    $("#modal-resource").textContent = reserva.recurso;
    $("#modal-date").textContent = fmtDia(reserva.inicio);
    $("#modal-time").textContent = fmtIntervalo(reserva.inicio, reserva.fim);
    $("#modal-code").textContent = codigoDe(reserva);
    modal.showModal();
  }
  $("#modal-close").addEventListener("click", () => modal.close());
  $("#modal-view").addEventListener("click", (e) => {
    e.preventDefault(); // já estamos nesta página: fecha o modal e mostra as próximas
    modal.close();
    selecionarTab($("#tab-upcoming"), true);
  });
  modal.addEventListener("click", (e) => { if (e.target === modal) modal.close(); }); // clique no fundo

  /* ===== 11. Arranque ===== */
  $("#panel-upcoming").innerHTML = caixaVazia("A carregar…");
  $("#panel-waitlist").innerHTML = caixaVazia("A carregar…");
  carregar(true);
  // Vai buscar novidades (por exemplo, uma vaga que abriu) sem o utilizador recarregar a página
  setInterval(() => { if (!document.hidden) carregar(); }, 30000);
})();