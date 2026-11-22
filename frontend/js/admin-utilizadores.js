// ===== ADMINISTRAÇÃO · UTILIZADORES (design do Dario) =====
// Lista as contas, repõe o 2FA e gera o código para redefinir a palavra-passe.
// Dados reais do auth-service (js/api.js). Todas as rotas exigem ADMIN no backend.

const utilizador = requireAuth();
// A proteção a sério é o require_admin do backend; isto só evita mostrar a tela a quem não é admin
if (utilizador && utilizador.role !== "ADMIN") location.replace("index.html");

// ===== AJUDANTES =====
const DIAS_SEMANA = ["domingo", "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado"];
const MESES_LONGOS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];
const MESES_CURTOS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const $ = (seletor) => document.querySelector(seletor);
const pad = (n) => String(n).padStart(2, "0");
// Tira os acentos e põe em minúsculas: "Inês" e "ines" passam a ser iguais na pesquisa
const normalizar = (t) => t.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

function iniciais(nome) {
  const p = nome.trim().split(/\s+/);
  return ((p[0]?.[0] ?? "") + (p.length > 1 ? p.at(-1)[0] : "")).toUpperCase();
}
// created_at vem em ISO ("2026-10-20T09:12:00+00:00") → "20 out 2026"
function dataCurta(iso) {
  const d = new Date(iso);
  return `${d.getDate()} ${MESES_CURTOS[d.getMonth()]} ${d.getFullYear()}`;
}
const horaDe = (iso) => { const d = new Date(iso); return `${pad(d.getHours())}:${pad(d.getMinutes())}`; };

// ===== ESTADO =====
let utilizadores = [];   // a lista que veio do GET /api/auth/users
let alvo = null;         // a conta que está aberta numa das janelas

// ===== DATA DE HOJE NO TOPO =====
function atualizarData() {
  const d = new Date();
  $("#admin-data").textContent =
    `Hoje, ${DIAS_SEMANA[d.getDay()]} ${d.getDate()} de ${MESES_LONGOS[d.getMonth()]} · ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

// ===== TABELA =====
function filtros() {
  return {
    busca: normalizar($("#busca").value.trim()),
    papel: document.querySelector('input[name="papel"]:checked').value,   // todos | admin | utilizador
    fa: document.querySelector('input[name="fa"]:checked').value,         // todos | ativo | pendente
  };
}

function linha(u) {
  const eu = u.id === utilizador.id;   // a conta de quem está com a sessão iniciada

  const cargo = u.role === "ADMIN"
    ? '<span class="cargo cargo--admin"><span class="icone" aria-hidden="true">admin_panel_settings</span>Administrador</span>'
    : '<span class="cargo"><span class="icone" aria-hidden="true">person</span>Utilizador</span>';
  const fa = u.two_fa_enabled
    ? '<span class="fa fa--ativo">Ativo</span>'
    : '<span class="fa fa--pendente">Por configurar</span>';

  // Ações: o backend não deixa um admin repor o próprio 2FA, por isso na sua conta não há botões
  let acao;
  if (eu) {
    acao = '<p class="repor-nota"><span class="icone" aria-hidden="true">info</span>Só outro administrador pode repor o seu 2FA</p>';
  } else {
    acao = '<div class="acoes">' +
      // Repor só faz sentido com o 2FA ativo
      (u.two_fa_enabled
        ? `<button class="repor" type="button" data-repor="${u.id}" aria-label="Repor o 2FA de ${esc(u.name)}"><span class="icone" aria-hidden="true">lock_reset</span>Repor 2FA</button>`
        : "") +
      `<button class="repor repor--neutro" type="button" data-codigo="${u.id}" aria-label="Gerar código de palavra-passe para ${esc(u.name)}"><span class="icone" aria-hidden="true">key</span>Palavra-passe</button>` +
      "</div>";
  }

  return `<tr>
    <td><div class="nome"><span class="nome__av" aria-hidden="true">${esc(iniciais(u.name))}</span><span class="nome__txt" title="${esc(u.name)}">${esc(u.name)}</span>${eu ? '<span class="nome__eu">A sua conta</span>' : ""}</div></td>
    <td><div class="celula-texto" title="${esc(u.email)}">${esc(u.email)}</div></td>
    <td>${cargo}</td>
    <td>${fa}</td>
    <td class="celula-data">${dataCurta(u.created_at)}</td>
    <td>${acao}</td>
  </tr>`;
}

function desenhar() {
  const f = filtros();
  const visiveis = utilizadores.filter((u) => {
    const papelOk = f.papel === "todos" || (f.papel === "admin" ? u.role === "ADMIN" : u.role !== "ADMIN");
    const faOk = f.fa === "todos" || (f.fa === "ativo" ? u.two_fa_enabled : !u.two_fa_enabled);
    const buscaOk = !f.busca || normalizar(`${u.name} ${u.email}`).includes(f.busca);
    return papelOk && faOk && buscaOk;
  });

  $("#tabela-corpo").innerHTML = visiveis.length
    ? visiveis.map(linha).join("")
    : '<tr><td class="tabela__aviso" colspan="6">Nenhum utilizador corresponde aos filtros.</td></tr>';

  const pendentes = utilizadores.filter((u) => !u.two_fa_enabled).length;
  $("#tab-total").textContent = utilizadores.length;
  $("#rodape").textContent = `A mostrar ${visiveis.length} de ${utilizadores.length} utilizadores · ${pendentes} com o 2FA por configurar`;
}

// Qualquer mudança nos filtros (escrever na pesquisa ou trocar um botão) redesenha
$(".filtros").addEventListener("input", desenhar);

async function carregar() {
  try {
    utilizadores = await api.users();
    desenhar();
  } catch (err) {
    $("#tabela-corpo").innerHTML = `<tr><td class="tabela__aviso" colspan="6">${esc(err.message)}</td></tr>`;
  }
}

// ===== CLIQUES NA TABELA (delegação: as linhas são redesenhadas) =====
$("#tabela-corpo").addEventListener("click", (e) => {
  const repor = e.target.closest("[data-repor]");
  const codigo = e.target.closest("[data-codigo]");
  if (repor) abrirRepor(repor.dataset.repor);
  if (codigo) abrirCodigo(codigo.dataset.codigo);
});

// Fechar as janelas: botões com data-fechar ou clique no fundo escuro
document.querySelectorAll("dialog").forEach((dialogo) => {
  dialogo.addEventListener("click", (e) => { if (e.target === dialogo) dialogo.close(); });
  dialogo.querySelectorAll("[data-fechar]").forEach((b) => b.addEventListener("click", () => dialogo.close()));
});

// ===== JANELA 1: REPOR O 2FA =====
const modalRepor = $("#modal-repor");

function abrirRepor(id) {
  alvo = utilizadores.find((u) => u.id === id);
  if (!alvo) return;
  $("#modal-nome").textContent = alvo.name;
  $("#modal-email").textContent = alvo.email;
  $("#modal-primeiro").textContent = alvo.name.split(/\s+/)[0];
  $("#modal-erro").hidden = true;
  $("#modal-confirmar").disabled = false;
  $("#modal-confirmar-txt").textContent = "Repor 2FA";
  modalRepor.showModal();
}

$("#modal-confirmar").addEventListener("click", async () => {
  if (!alvo) return;
  $("#modal-confirmar").disabled = true;
  $("#modal-confirmar-txt").textContent = "A repor…";
  $("#modal-erro").hidden = true;
  try {
    await api.reset2fa(alvo.id);   // 204: sem corpo na resposta
    modalRepor.close();
    avisar("2FA reposto", `${alvo.name} vai configurar o 2FA na próxima entrada.`);
    carregar();   // a linha passa a "Por configurar"
  } catch (err) {
    $("#modal-erro").textContent = err.message;
    $("#modal-erro").hidden = false;
    $("#modal-confirmar").disabled = false;
    $("#modal-confirmar-txt").textContent = "Repor 2FA";
  }
});

// ===== JANELA 2: CÓDIGO PARA REDEFINIR A PALAVRA-PASSE =====
// Duas partes na mesma janela: primeiro confirmar, depois mostrar o link com o código
const modalCodigo = $("#modal-codigo");

function abrirCodigo(id) {
  alvo = utilizadores.find((u) => u.id === id);
  if (!alvo) return;
  $("#codigo-nome").textContent = alvo.name;
  $("#codigo-email").textContent = alvo.email;
  $("#codigo-pedir").hidden = false;
  $("#codigo-resultado").hidden = true;
  $("#codigo-erro").hidden = true;
  $("#codigo-gerar").disabled = false;
  modalCodigo.showModal();
}

$("#codigo-gerar").addEventListener("click", async () => {
  if (!alvo) return;
  $("#codigo-gerar").disabled = true;
  $("#codigo-erro").hidden = true;
  try {
    const res = await api.createPasswordReset(alvo.id);   // { token, expires_at }
    // O token só existe nesta resposta (na base de dados fica só o hash): não se guarda em lado nenhum
    $("#codigo-link").value = `${location.origin}/recuperar-senha.html?token=${encodeURIComponent(res.token)}`;
    $("#codigo-validade").textContent = horaDe(res.expires_at);
    $("#codigo-pedir").hidden = true;
    $("#codigo-resultado").hidden = false;
  } catch (err) {
    $("#codigo-erro").textContent = err.message;
    $("#codigo-erro").hidden = false;
    $("#codigo-gerar").disabled = false;
  }
});

$("#codigo-copiar").addEventListener("click", async () => {
  const campo = $("#codigo-link");
  try {
    await navigator.clipboard.writeText(campo.value);   // só funciona em https ou localhost
  } catch {
    campo.select();                                      // plano B: seleciona para o admin copiar à mão
    return;
  }
  avisar("Link copiado", `Envie-o a ${alvo.name.split(/\s+/)[0]} por um canal de confiança.`);
});

// Ao fechar, apaga o link do campo: o código não fica à vista na página
modalCodigo.addEventListener("close", () => { $("#codigo-link").value = ""; });

// ===== AVISO EM BAIXO À DIREITA (do Dario) =====
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
    '<button class="aviso-cartao__fechar" type="button" aria-label="Fechar aviso"><span class="icone" aria-hidden="true">close</span></button>';
  el.querySelector("button").addEventListener("click", () => el.remove());
  document.body.append(el);
  temporizador = setTimeout(() => el.remove(), 5000);
}

// ===== ARRANQUE =====
atualizarData();
setInterval(atualizarData, 30000);
carregar();