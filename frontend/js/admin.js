// ===== ADMINISTRAÇÃO =====
// Indicadores do dia, ocupação por categoria e lista de recursos com ativar/desativar.
// Usa os dados de js/dados-falsos.js (carregado antes deste arquivo).

const utilizador = requireAuth();
// Só administradores. A proteção a sério é no backend (require_admin);
// aqui é só para não mostrar a tela a quem não tem acesso.
if (utilizador && utilizador.role !== "ADMIN") location.replace("index.html");

// ===== HORÁRIO E CONTAS =====
const ABRE = 8 * 60;      // 08:00, em minutos desde a meia-noite
const FECHA = 20 * 60;    // 20:00

// "09:30" → 570
function paraMinutos(hora) {
  const [h, m] = hora.split(":").map(Number);
  return h * 60 + m;
}

// Minutos de agora (ex.: 14:07 → 847)
function minutosAgora() {
  const d = new Date();
  return d.getHours() * 60 + d.getMinutes();
}

// O recurso está ocupado neste minuto de hoje? (reserva de outra pessoa ou sua)
function ocupadoAgora(recurso, agora) {
  if (agora < ABRE || agora >= FECHA) return false;   // fora do horário: nada está ocupado
  const dentro = ([a, b]) => paraMinutos(a) <= agora && agora < paraMinutos(b);
  const minhasHoje = DADOS_FALSOS.minhas
    .filter((m) => m.resource_id === recurso.id && m.dia === 0)
    .map((m) => [m.start, m.end]);
  return recurso.ocupados.some(dentro) || minhasHoje.some(dentro);
}

// Número de reservas de hoje num recurso
function reservasHoje(recurso) {
  const minhas = DADOS_FALSOS.minhas.filter((m) => m.resource_id === recurso.id && m.dia === 0).length;
  return recurso.ocupados.length + minhas;
}

// ===== ESTADO =====
// Recursos desativados (por id). Por agora só vive na memória da página.
const desativados = new Set();

// ===== DESENHO =====
function render() {
  const agora = minutosAgora();
  const todos = DADOS_FALSOS.recursos;
  const ativos = todos.filter((r) => !desativados.has(r.id));

  // ----- Data no topo: "Hoje, sexta-feira 6 de novembro · 14:07" -----
  const hoje = new Date();
  const data = hoje.toLocaleDateString("pt-PT", { weekday: "long", day: "numeric", month: "long" }).replace(",", "");
  const hora = hoje.toLocaleTimeString("pt-PT", { hour: "2-digit", minute: "2-digit" });
  document.getElementById("admin-data").textContent = `Hoje, ${data} · ${hora}`;

  // ----- Indicadores (KPIs) -----
  const ocupadosAgora = ativos.filter((r) => ocupadoAgora(r, agora)).length;
  const kpis = [
    { titulo: "Reservas hoje",   valor: ativos.reduce((soma, r) => soma + reservasHoje(r), 0) },   // reduce soma tudo
    { titulo: "Ocupação agora",  valor: Math.round((100 * ocupadosAgora) / Math.max(1, ativos.length)) + "%" },
    { titulo: "Pessoas em fila", valor: DADOS_FALSOS.fila.length },
    { titulo: "Recursos ativos", valor: `${ativos.length} / ${todos.length}` },
  ];
  document.getElementById("kpis").innerHTML = kpis.map((k) => `
    <div class="kpi">
      <div class="kpi-titulo">${k.titulo}</div>
      <div class="kpi-valor">${k.valor}</div>
    </div>`).join("");

  // ----- Ocupação agora, por categoria -----
  document.getElementById("ocupacao").innerHTML = Object.entries(DADOS_FALSOS.categorias).map(([id, cat]) => {
    const daCategoria = ativos.filter((r) => r.category === id);
    const ocupados = daCategoria.filter((r) => ocupadoAgora(r, agora)).length;
    const pct = daCategoria.length ? Math.round((100 * ocupados) / daCategoria.length) : 0;
    return `
      <div class="ocupacao-linha">
        <div class="ocupacao-texto"><span>${esc(cat.name)}</span><span>${ocupados} / ${daCategoria.length}</span></div>
        <div class="ocupacao-barra"><div style="width: ${pct}%; background: var(--${id})"></div></div>
      </div>`;
  }).join("");

  // ----- Tabela de recursos -----
  document.getElementById("lista-recursos").innerHTML = todos.map((r) => {
    const ativo = !desativados.has(r.id);
    const n = reservasHoje(r);
    const hojeTexto = ativo ? `${n} ${n === 1 ? "reserva" : "reservas"} hoje` : "Desativado";
    return `
      <div class="recurso-linha${ativo ? "" : " inativo"}">
        <div class="recurso-nome">
          <b>${esc(r.name)}</b>
          <div>${esc(r.location)} · ${esc(r.capacity)}</div>
        </div>
        <div class="recurso-tipo"><i style="background: var(--${r.category})"></i>${esc(r.type)}</div>
        <div class="recurso-hoje">${hojeTexto}</div>
        <button type="button" class="interruptor" role="switch" aria-checked="${ativo}"
                aria-label="Ativo: ${esc(r.name)}" data-id="${r.id}">
          <span class="interruptor-trilho"><i></i></span>
        </button>
      </div>`;
  }).join("");
}

// ===== EVENTOS =====
// Ativar/desativar: delegação de eventos na lista (as linhas são redesenhadas)
document.getElementById("lista-recursos").addEventListener("click", (e) => {
  const botao = e.target.closest(".interruptor");
  if (!botao) return;
  const id = Number(botao.dataset.id);
  const recurso = DADOS_FALSOS.recursos.find((r) => r.id === id);

  if (desativados.has(id)) {
    desativados.delete(id);
    toast(`${recurso.name} voltou a estar disponível.`);
  } else {
    desativados.add(id);
    toast(`${recurso.name} deixou de aparecer aos utilizadores.`);
  }
  render();
});

// ===== ARRANQUE =====
// Aviso deixado por outra página (ex.: depois de criar um recurso): mostra uma vez e apaga
try {
  const aviso = sessionStorage.getItem("slotup_aviso");
  if (aviso) {
    toast(aviso);
    sessionStorage.removeItem("slotup_aviso");
  }
} catch (e) { /* sem acesso ao sessionStorage: ignora */ }
render();
setInterval(render, 60 * 1000);   // atualiza a hora e a "ocupação agora" a cada minuto