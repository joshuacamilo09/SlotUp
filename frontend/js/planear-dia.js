/* =====================================================================
   SlotUp · Planear o meu dia
   Todas as horas aqui dentro são "minutos desde a meia-noite"
   (09:00 = 540). Só as duas funções da secção 2 falam com o backend.
   ===================================================================== */
"use strict";

(() => {
  /* ===== 1. Constantes ===== */
  const ABRE = 8 * 60;        // 08:00
  const FECHA = 20 * 60;      // 20:00
  const MEIO_DIA = 13 * 60;   // a manhã acaba às 13:00 e a tarde começa aí
  const PASSO = 30;           // os botões − e + andam de 30 em 30 minutos
  const DUR_MIN = 30;
  const DUR_MAX = 8 * 60;
  const MAX_ATIVIDADES = 6;

  const CATEGORIAS = {
    coworking: { nome: "Coworking", icone: "desk" },
    estacionamento: { nome: "Estacionamento", icone: "local_parking" },
    desporto: { nome: "Desporto", icone: "sports_tennis" },
  };
  const DIAS = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];
  const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

  /* ===== 2. LIGAÇÃO AO BACKEND (o colega substitui só estas duas funções) =====
     Por agora devolvem dados de exemplo para a página funcionar sozinha.

     obterLivres(categoria, dia)
       categoria: "coworking" | "estacionamento" | "desporto"
       dia:       "AAAA-MM-DD"
       devolve:   Promise<[{ id, nome, local, livres: [{ ini, fim }] }]>
                  (um item por recurso; ini/fim em minutos desde a meia-noite)

     reservarPlano(dia, itens)
       itens:     [{ recursoId, categoria, ini, fim }]
       devolve:   Promise (rejeitar com Error("mensagem") se falhar)         */
  const RECURSOS_EXEMPLO = {
    coworking: [
      { id: "c1", nome: "Sala Atlântico", local: "Piso 2" },
      { id: "c2", nome: "Mesa 04", local: "Piso 1" },
    ],
    estacionamento: [{ id: "e1", nome: "Vaga P-115", local: "Piso -1" }],
    desporto: [{ id: "d1", nome: "Quadra de padel 2", local: "Exterior" }],
  };

  async function obterLivres(categoria, dia) {
    await esperar(400);
    const n = Number(dia.slice(-2));
    return RECURSOS_EXEMPLO[categoria].map((r, i) => {
      const ocupadoIni = 9 * 60 + ((n + i * 3) % 6) * 60; // um bloco ocupado de 2h
      const ocupadoFim = ocupadoIni + 2 * 60;
      return { ...r, livres: [{ ini: ABRE, fim: ocupadoIni }, { ini: ocupadoFim, fim: FECHA }] };
    });
  }

  async function reservarPlano(dia, itens) {
    await esperar(500);
    console.log("reservarPlano", dia, itens);
  }

  /* ===== 3. Utilitários ===== */
  const $ = (seletor, raiz = document) => raiz.querySelector(seletor);
  const $$ = (seletor, raiz = document) => [...raiz.querySelectorAll(seletor)];
  const esperar = (ms) => new Promise((r) => setTimeout(r, ms));
  const pad = (n) => String(n).padStart(2, "0");
  const hhmm = (m) => `${pad(Math.floor(m / 60))}:${pad(m % 60)}`;
  const esc = (t) => String(t).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

  function duracaoTxt(m) {
    const h = Math.floor(m / 60);
    const r = m % 60;
    if (!h) return `${r}min`;
    return r ? `${h}h${pad(r)}` : `${h}h`;
  }
  function dataIso(d) {
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }
  function dataCurta(iso) {
    const d = new Date(`${iso}T12:00:00`);
    return `${DIAS[d.getDay()]}, ${d.getDate()} ${MESES[d.getMonth()]}`;
  }
  function avisar(texto, erro = false) {
    const t = document.createElement("div");
    t.className = "toast" + (erro ? " error" : "");
    t.textContent = texto;
    document.body.append(t);
    setTimeout(() => t.remove(), 3500);
  }

  /* ===== 4. Elementos ===== */
  const datasEl = $("#datas");
  const listaEl = $("#atv-lista");
  const totalEl = $("#atv-total");
  const dataPlanoEl = $("#plano-data");
  const resultadoEl = $("#plano-resultado");
  const gerarBtn = $("#gerar-plano");
  const modelo = $("#tpl-atv");

  const vazioClasse = resultadoEl.className;
  const vazioHtml = resultadoEl.innerHTML;
  let contador = 0;

  /* ===== 5. Datas: hoje + 6 dias ===== */
  function desenharDatas() {
    const hoje = new Date();
    hoje.setHours(12, 0, 0, 0);
    datasEl.innerHTML = Array.from({ length: 7 }, (_, i) => {
      const d = new Date(hoje);
      d.setDate(hoje.getDate() + i);
      return `<label class="data"><input type="radio" name="dia" value="${dataIso(d)}"${i === 1 ? " checked" : ""}>` +
        `<span class="data__dia">${i === 0 ? "Hoje" : DIAS[d.getDay()]}</span><span class="data__num">${d.getDate()}</span></label>`;
    }).join("");
    atualizarDataPlano();
  }
  function diaEscolhido() {
    return $('input[name="dia"]:checked').value;
  }
  function atualizarDataPlano() {
    dataPlanoEl.textContent = dataCurta(diaEscolhido());
  }

  /* ===== 6. Atividades ===== */
  function adicionar({ categoria = "coworking", duracao = 60, turno = "manha", inicio = 9 * 60 } = {}) {
    if ($$(".atv", listaEl).length >= MAX_ATIVIDADES) {
      avisar(`No máximo ${MAX_ATIVIDADES} atividades por dia.`, true);
      return;
    }
    const n = ++contador;
    listaEl.insertAdjacentHTML("beforeend", modelo.innerHTML.replaceAll("{n}", n));
    const li = listaEl.lastElementChild;
    $(`input[name="cat-${n}"][value="${categoria}"]`, li).checked = true;
    $(`input[name="turno-${n}"][value="${turno}"]`, li).checked = true;
    li.dataset.dur = duracao;
    li.dataset.ini = inicio;
    pintar(li);
    atualizarLista();
  }

  function pintar(li) {
    const dur = Number(li.dataset.dur);
    const ini = Number(li.dataset.ini);
    $('[data-mostra="dur"]', li).textContent = duracaoTxt(dur);
    $('[data-mostra="ini"]', li).textContent = hhmm(ini);
    $('[data-mostra="fim"]', li).textContent = hhmm(ini + dur);
  }

  function atualizarLista() {
    const atividades = $$(".atv", listaEl);
    atividades.forEach((li, i) => {
      $(".atv__titulo", li).textContent = `Atividade ${i + 1}`;
      $(".atv__lixo", li).setAttribute("aria-label", `Remover a atividade ${i + 1}`);
      $(".atv__lixo", li).disabled = atividades.length === 1;
    });
    const total = atividades.reduce((soma, li) => soma + Number(li.dataset.dur), 0);
    const n = atividades.length;
    totalEl.textContent = `${n} ${n === 1 ? "atividade" : "atividades"} · ${duracaoTxt(total)} no total`;
  }

  listaEl.addEventListener("click", (e) => {
    const botao = e.target.closest("[data-acao]");
    if (!botao) return;
    const li = botao.closest(".atv");
    const acao = botao.dataset.acao;
    limparPlano();

    if (acao === "remover") {
      li.remove();
      atualizarLista();
      return;
    }
    let dur = Number(li.dataset.dur);
    let ini = Number(li.dataset.ini);
    if (acao === "dur-") dur = Math.max(DUR_MIN, dur - PASSO);
    if (acao === "dur+") dur = Math.min(DUR_MAX, dur + PASSO);
    if (acao === "ini-") ini = Math.max(ABRE, ini - PASSO);
    if (acao === "ini+") ini = Math.min(FECHA - dur, ini + PASSO);
    ini = Math.min(ini, FECHA - dur); // a atividade nunca passa das 20:00
    li.dataset.dur = dur;
    li.dataset.ini = ini;
    pintar(li);
    atualizarLista();
  });

  $("#atv-add").addEventListener("click", () => {
    limparPlano();
    adicionar();
  });

  // Mudar o dia, a categoria ou o horário preferido invalida o plano que estava à vista
  $("#pedido").addEventListener("change", (e) => {
    if (e.target.name === "dia") atualizarDataPlano();
    limparPlano();
  });

  /* ===== 7. Ler o pedido ===== */
  function lerPedido() {
    return {
      dia: diaEscolhido(),
      atividades: $$(".atv", listaEl).map((li, i) => ({
        numero: i + 1,
        categoria: $(".atv__cats input:checked", li).value,
        duracao: Number(li.dataset.dur),
        turno: $(".turnos input:checked", li).value, // "manha" | "tarde" | "hora"
        inicio: Number(li.dataset.ini),
      })),
    };
  }

  /* ===== 8. Montar o plano (sem sobreposições) ===== */
  function janela(a) {
    if (a.turno === "hora") return [a.inicio, a.inicio + a.duracao];
    return a.turno === "manha" ? [ABRE, MEIO_DIA] : [MEIO_DIA, FECHA];
  }

  function resolver(atividades, livresPorCategoria) {
    // Primeiro as de hora marcada, depois as mais compridas (são as mais difíceis de encaixar)
    const ordem = [...atividades].sort((a, b) => (b.turno === "hora") - (a.turno === "hora") || b.duracao - a.duracao);
    const colocados = [];

    function tentar(k) {
      if (k === ordem.length) return true;
      const a = ordem[k];
      const [de, ate] = janela(a);
      for (let ini = de; ini + a.duracao <= ate; ini += PASSO) {
        const fim = ini + a.duracao;
        if (colocados.some((c) => ini < c.fim && fim > c.ini)) continue; // sobrepõe outra atividade
        const recurso = livresPorCategoria[a.categoria].find((r) => r.livres.some((l) => l.ini <= ini && l.fim >= fim));
        if (!recurso) continue;
        colocados.push({ atividade: a.numero, categoria: a.categoria, recursoId: recurso.id, recurso: recurso.nome, local: recurso.local, ini, fim });
        if (tentar(k + 1)) return true;
        colocados.pop();
      }
      return false;
    }
    return tentar(0) ? colocados.sort((x, y) => x.ini - y.ini) : null;
  }

  /* ===== 9. Mostrar o resultado ===== */
  function limparPlano() {
    resultadoEl.className = vazioClasse;
    resultadoEl.innerHTML = vazioHtml;
  }

  function mostrarPlano(dia, itens) {
    resultadoEl.className = "plano-lista";
    resultadoEl.innerHTML =
      `<ol class="plano-itens">` +
      itens.map((i) => `
        <li class="plano-item cat--${i.categoria}">
          <span class="plano-item__hora">${hhmm(i.ini)}–${hhmm(i.fim)}</span>
          <span class="plano-item__icone"><span class="icone" aria-hidden="true">${CATEGORIAS[i.categoria].icone}</span></span>
          <div>
            <p class="plano-item__nome">${esc(i.recurso)}</p>
            <p class="plano-item__meta">${CATEGORIAS[i.categoria].nome} · ${esc(i.local)}</p>
          </div>
          <span class="plano-item__dur">${duracaoTxt(i.fim - i.ini)}</span>
        </li>`).join("") +
      `</ol><button class="gerar" type="button" id="reservar-plano"><span class="icone" aria-hidden="true">event_available</span><span class="gerar__txt">Reservar plano</span></button>`;

    $("#reservar-plano").addEventListener("click", async (e) => {
      const btn = e.currentTarget;
      btn.disabled = true;
      $(".gerar__txt", btn).textContent = "A reservar…";
      try {
        await reservarPlano(dia, itens.map(({ recursoId, categoria, ini, fim }) => ({ recursoId, categoria, ini, fim })));
        avisar("Plano reservado.");
      } catch (erro) {
        avisar(erro.message || "Não foi possível reservar o plano.", true);
      } finally {
        btn.disabled = false;
        $(".gerar__txt", btn).textContent = "Reservar plano";
      }
    });
  }

  function mostrarSemPlano(texto) {
    resultadoEl.className = "plano-vazio plano-vazio--erro";
    resultadoEl.innerHTML =
      `<span class="icone" aria-hidden="true">event_busy</span>` +
      `<p class="plano-vazio__titulo">Não foi possível montar o plano</p>` +
      `<p class="plano-vazio__texto">${esc(texto)}</p>`;
  }

  /* ===== 10. Gerar plano ===== */
  gerarBtn.addEventListener("click", async () => {
    const pedido = lerPedido();
    const txt = $(".gerar__txt", gerarBtn);
    gerarBtn.disabled = true;
    txt.textContent = "A gerar…";

    try {
      const categorias = [...new Set(pedido.atividades.map((a) => a.categoria))];
      const livresPorCategoria = {};
      await Promise.all(categorias.map(async (c) => {
        livresPorCategoria[c] = await obterLivres(c, pedido.dia);
      }));

      const plano = resolver(pedido.atividades, livresPorCategoria);
      if (plano) {
        mostrarPlano(pedido.dia, plano);
      } else {
        const sozinhas = pedido.atividades.filter((a) => !resolver([a], livresPorCategoria)).map((a) => a.numero);
        mostrarSemPlano(sozinhas.length
          ? `Não há recurso livre para a atividade ${sozinhas.join(", ")} nesse horário. Mude o horário ou a duração.`
          : "Cada atividade tem lugar, mas não cabem todas sem se sobreporem. Tente outro horário ou outro dia.");
      }
    } catch (erro) {
      avisar(erro.message || "Não foi possível obter os horários.", true);
    } finally {
      gerarBtn.disabled = false;
      txt.textContent = "Gerar plano";
    }
  });

  /* ===== 11. Arranque: as três atividades do desenho ===== */
  desenharDatas();
  adicionar({ categoria: "coworking", duracao: 180, turno: "manha", inicio: 9 * 60 });
  adicionar({ categoria: "desporto", duracao: 60, turno: "tarde", inicio: 14 * 60 });
  adicionar({ categoria: "coworking", duracao: 60, turno: "hora", inicio: 16 * 60 });
})();