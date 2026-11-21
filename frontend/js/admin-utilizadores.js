/* =====================================================================
   SlotUp · Administração · Utilizadores
   Só as duas funções da secção 1 falam com o backend.
   ===================================================================== */
"use strict";

(() => {
  /* ===== 1. LIGAÇÃO AO BACKEND (o colega substitui só estas funções) =====
     Por agora devolvem dados de exemplo para a página funcionar sozinha.

     listarUtilizadores()
       devolve: Promise<[{
         id,                    // qualquer identificador
         nome, email,
         papel,                 // "ADMIN" | "USER"
         fa,                    // "ATIVO" | "POR_CONFIGURAR"
         registo,               // "AAAA-MM-DD"
         eu                     // true só na conta de quem está com a sessão iniciada
       }]>

     reporDoisFA(id)
       Repõe o 2FA desse utilizador (passa a "POR_CONFIGURAR").
       Rejeitar com Error("mensagem") se falhar (a mensagem aparece na janela). */
  const UTILIZADORES_EXEMPLO = [
    { id: 1, nome: "Marta Sousa", email: "marta.sousa@empresa.pt", papel: "ADMIN", fa: "ATIVO", registo: "2025-03-03", eu: true },
    { id: 2, nome: "Carlos Mendes", email: "carlos.mendes@empresa.pt", papel: "ADMIN", fa: "ATIVO", registo: "2025-03-03", eu: false },
    { id: 3, nome: "Ana Costa", email: "ana.costa@empresa.pt", papel: "USER", fa: "ATIVO", registo: "2025-04-14", eu: false },
    { id: 4, nome: "João Ferreira", email: "joao.ferreira@empresa.pt", papel: "USER", fa: "ATIVO", registo: "2025-06-02", eu: false },
    { id: 5, nome: "Tiago Martins", email: "tiago.martins@empresa.pt", papel: "USER", fa: "ATIVO", registo: "2025-09-09", eu: false },
    { id: 6, nome: "Inês Rocha", email: "ines.rocha@empresa.pt", papel: "USER", fa: "ATIVO", registo: "2026-01-17", eu: false },
    { id: 7, nome: "Sara Pinto", email: "sara.pinto@empresa.pt", papel: "USER", fa: "ATIVO", registo: "2026-05-05", eu: false },
    { id: 8, nome: "Miguel Oliveira", email: "miguel.oliveira@empresa.pt", papel: "USER", fa: "ATIVO", registo: "2026-07-30", eu: false },
    { id: 9, nome: "Beatriz Lopes", email: "beatriz.lopes@empresa.pt", papel: "USER", fa: "POR_CONFIGURAR", registo: "2026-10-20", eu: false },
    { id: 10, nome: "Pedro Santos", email: "pedro.santos@empresa.pt", papel: "USER", fa: "POR_CONFIGURAR", registo: "2026-10-21", eu: false },
  ];

  async function listarUtilizadores() {
    await esperar(300);
    return UTILIZADORES_EXEMPLO.map((u) => ({ ...u }));
  }

  async function reporDoisFA(id) {
    await esperar(500);
  }

  /* ===== 2. Utilitários ===== */
  const DIAS_SEMANA = ["domingo", "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado"];
  const MESES_LONGOS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];
  const MESES_CURTOS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

  const $ = (seletor, raiz = document) => raiz.querySelector(seletor);
  const esperar = (ms) => new Promise((r) => setTimeout(r, ms));
  const pad = (n) => String(n).padStart(2, "0");
  const esc = (t) => String(t).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const normalizar = (t) => t.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

  function iniciais(nome) {
    const p = nome.trim().split(/\s+/);
    return ((p[0][0] || "") + (p.length > 1 ? p[p.length - 1][0] : "")).toUpperCase();
  }
  function dataCurta(iso) {
    const [a, m, d] = iso.split("-").map(Number);
    return `${d} ${MESES_CURTOS[m - 1]} ${a}`;
  }

  /* ===== 3. Elementos e estado ===== */
  const corpo = $("#tabela-corpo");
  const rodape = $("#rodape");
  const modal = $("#modal-repor");
  const confirmarBtn = $("#modal-confirmar");
  const confirmarTxt = $("#modal-confirmar-txt");
  const modalErro = $("#modal-erro");

  let utilizadores = [];
  let alvo = null; // utilizador que está na janela de confirmação

  /* ===== 4. Data de hoje no cabeçalho ===== */
  function atualizarData() {
    const d = new Date();
    $("#admin-data").textContent =
      `Hoje, ${DIAS_SEMANA[d.getDay()]} ${d.getDate()} de ${MESES_LONGOS[d.getMonth()]} · ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  /* ===== 5. Tabela ===== */
  function filtros() {
    return {
      busca: normalizar($("#busca").value.trim()),
      papel: $('input[name="papel"]:checked').value, // todos | admin | utilizador
      fa: $('input[name="fa"]:checked').value,       // todos | ativo | pendente
    };
  }

  function linha(u) {
    const papel = u.papel === "ADMIN"
      ? `<span class="papel papel--admin"><span class="icone" aria-hidden="true">admin_panel_settings</span>Administrador</span>`
      : `<span class="papel"><span class="icone" aria-hidden="true">person</span>Utilizador</span>`;
    const fa = u.fa === "ATIVO"
      ? `<span class="fa fa--ativo">Ativo</span>`
      : `<span class="fa fa--pendente">Por configurar</span>`;

    let acao;
    if (u.eu) {
      acao = `<button class="repor" type="button" disabled aria-describedby="nota-eu"><span class="icone" aria-hidden="true">lock_reset</span>Repor 2FA</button>` +
        `<p class="repor-nota" id="nota-eu"><span class="icone" aria-hidden="true">info</span>Só outro administrador pode repor o seu</p>`;
    } else if (u.fa === "ATIVO") {
      acao = `<button class="repor" type="button" data-repor="${esc(u.id)}" aria-label="Repor o 2FA de ${esc(u.nome)}"><span class="icone" aria-hidden="true">lock_reset</span>Repor 2FA</button>`;
    } else {
      acao = `<span class="sem-acao">Sem ação</span>`;
    }

    return `<tr>
      <td><div class="nome"><span class="nome__av" aria-hidden="true">${esc(iniciais(u.nome))}</span><span class="nome__txt" title="${esc(u.nome)}">${esc(u.nome)}</span>${u.eu ? `<span class="nome__eu">A sua conta</span>` : ""}</div></td>
      <td><div class="celula-texto" title="${esc(u.email)}">${esc(u.email)}</div></td>
      <td>${papel}</td>
      <td>${fa}</td>
      <td class="celula-data">${esc(dataCurta(u.registo))}</td>
      <td>${acao}</td>
    </tr>`;
  }

  function desenhar() {
    const f = filtros();
    const visiveis = utilizadores.filter((u) => {
      const papelOk = f.papel === "todos" || (f.papel === "admin" ? u.papel === "ADMIN" : u.papel === "USER");
      const faOk = f.fa === "todos" || (f.fa === "ativo" ? u.fa === "ATIVO" : u.fa === "POR_CONFIGURAR");
      const buscaOk = !f.busca || normalizar(`${u.nome} ${u.email}`).includes(f.busca);
      return papelOk && faOk && buscaOk;
    });

    corpo.innerHTML = visiveis.length
      ? visiveis.map(linha).join("")
      : `<tr><td class="tabela__aviso" colspan="6">Nenhum utilizador corresponde aos filtros.</td></tr>`;

    const pendentes = utilizadores.filter((u) => u.fa === "POR_CONFIGURAR").length;
    $("#tab-total").textContent = utilizadores.length;
    rodape.textContent = `A mostrar ${visiveis.length} de ${utilizadores.length} utilizadores · ${pendentes} com o 2FA por configurar`;
  }

  document.querySelector(".filtros").addEventListener("input", desenhar);

  /* ===== 6. Janela de confirmação ===== */
  corpo.addEventListener("click", (e) => {
    const botao = e.target.closest("[data-repor]");
    if (!botao) return;
    alvo = utilizadores.find((u) => String(u.id) === botao.dataset.repor);
    if (!alvo) return;

    $("#modal-nome").textContent = alvo.nome;
    $("#modal-email").textContent = alvo.email;
    $("#modal-primeiro").textContent = alvo.nome.split(/\s+/)[0];
    modalErro.hidden = true;
    confirmarBtn.disabled = false;
    confirmarTxt.textContent = "Repor 2FA";
    modal.showModal();
  });

  $("#modal-fechar").addEventListener("click", () => modal.close());
  $("#modal-cancelar").addEventListener("click", () => modal.close());
  modal.addEventListener("click", (e) => { if (e.target === modal) modal.close(); }); // clique fora

  confirmarBtn.addEventListener("click", async () => {
    if (!alvo) return;
    confirmarBtn.disabled = true;
    confirmarTxt.textContent = "A repor…";
    modalErro.hidden = true;
    try {
      await reporDoisFA(alvo.id);
      alvo.fa = "POR_CONFIGURAR";
      const nome = alvo.nome;
      modal.close();
      desenhar();
      avisar("2FA reposto", `${nome} vai configurar o 2FA na próxima entrada.`);
    } catch (erro) {
      modalErro.textContent = erro.message || "Não foi possível repor o 2FA. Tente outra vez.";
      modalErro.hidden = false;
      confirmarBtn.disabled = false;
      confirmarTxt.textContent = "Repor 2FA";
    }
  });

  /* ===== 7. Aviso em baixo à direita ===== */
  let temporizador = null;
  function avisar(titulo, mensagem, erro = false) {
    $(".aviso-cartao")?.remove();
    clearTimeout(temporizador);
    const el = document.createElement("div");
    el.className = "aviso-cartao" + (erro ? " aviso-cartao--erro" : "");
    el.setAttribute("role", "status");
    el.innerHTML =
      `<span class="aviso-cartao__icone" aria-hidden="true"><span class="icone">${erro ? "error" : "check"}</span></span>` +
      `<div class="aviso-cartao__texto"><p class="aviso-cartao__titulo">${esc(titulo)}</p><p class="aviso-cartao__msg">${esc(mensagem)}</p></div>` +
      `<button class="aviso-cartao__fechar" type="button" aria-label="Fechar aviso"><span class="icone" aria-hidden="true">close</span></button>`;
    el.querySelector("button").addEventListener("click", () => el.remove());
    document.body.append(el);
    temporizador = setTimeout(() => el.remove(), 5000);
  }

  /* ===== 8. Arranque ===== */
  atualizarData();
  setInterval(atualizarData, 30000);

  listarUtilizadores()
    .then((lista) => { utilizadores = lista; desenhar(); })
    .catch((erro) => {
      corpo.innerHTML = `<tr><td class="tabela__aviso" colspan="6">${esc(erro.message || "Não foi possível carregar os utilizadores.")}</td></tr>`;
    });
})();