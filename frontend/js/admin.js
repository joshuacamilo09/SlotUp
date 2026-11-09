// ===== ADMINISTRAÇÃO =====
// Indicadores do dia, ocupação por categoria e lista de recursos com ativar/desativar.
// Dados reais do booking-service (via js/api.js); textos dos códigos em js/catalogo.js.

const utilizador = requireAuth();
// Só administradores. A proteção a sério é no backend (require_admin);
// aqui é só para não mostrar a tela a quem não tem acesso.
if (utilizador && utilizador.role !== "ADMIN") location.replace("index.html");

// Dados vindos da API. Ficam aqui para o render() não ter de pedir de novo.
let dados = { categorias: [], recursos: [] };

// ===== CARREGAR DA API =====
async function carregar() {
  try {
    // Categorias e recursos (incluindo os desativados) ao mesmo tempo: Promise.all espera pelos dois
    const [categorias, recursos] = await Promise.all([
      api.categories(true),
      api.resources({ includeInactive: true }),
    ]);

    // Disponibilidade de hoje de cada recurso ativo, em paralelo.
    // .catch(() => null): se um falhar, a tela mostra o resto em vez de ficar vazia
    const hoje = toISODate(new Date());
    const disponibilidades = await Promise.all(
      recursos.map((r) => (r.is_active ? api.availability(r.id, hoje).catch(() => null) : null))
    );

    dados = {
      categorias,
      recursos: recursos.map((r, i) => ({ ...r, hoje: disponibilidades[i] })),   // junta a disponibilidade ao recurso
    };
    render();
  } catch (err) {
    document.getElementById("lista-recursos").innerHTML = `<p class="admin-erro">${esc(err.message)}</p>`;
  }
}

// ===== CONTAS =====
// O recurso está ocupado agora? (há uma reserva no "busy" que começou e ainda não acabou)
function ocupadoAgora(recurso, agora) {
  return (recurso.hoje?.busy ?? []).some((b) => new Date(b.start) <= agora && agora < new Date(b.end));
}

// Número de reservas de hoje (cada reserva é um intervalo no "busy")
function reservasHoje(recurso) {
  return recurso.hoje?.busy.length ?? 0;
}

// ===== DESENHO =====
function render() {
  const agora = new Date();
  const todos = dados.recursos;
  const ativos = todos.filter((r) => r.is_active);

  // ----- Data no topo: "Hoje, sábado 7 de novembro · 10:52" -----
  const data = agora.toLocaleDateString("pt-PT", { weekday: "long", day: "numeric", month: "long" }).replace(",", "");
  const hora = agora.toLocaleTimeString("pt-PT", { hour: "2-digit", minute: "2-digit" });
  document.getElementById("admin-data").textContent = `Hoje, ${data} · ${hora}`;

  // ----- Indicadores (KPIs) -----
  const ocupados = ativos.filter((r) => ocupadoAgora(r, agora)).length;
  const kpis = [
    { titulo: "Reservas hoje",   valor: ativos.reduce((soma, r) => soma + reservasHoje(r), 0) },   // reduce soma tudo
    { titulo: "Ocupação agora",  valor: Math.round((100 * ocupados) / Math.max(1, ativos.length)) + "%" },
    // Ainda não há rota de admin para contar a fila de espera
    { titulo: "Pessoas em fila", valor: "—", dica: "Falta uma rota de admin no booking para contar a fila" },
    { titulo: "Recursos ativos", valor: `${ativos.length} / ${todos.length}` },
  ];
  document.getElementById("kpis").innerHTML = kpis.map((k) => `
    <div class="kpi"${k.dica ? ` title="${k.dica}"` : ""}>
      <div class="kpi-titulo">${k.titulo}</div>
      <div class="kpi-valor">${k.valor}</div>
    </div>`).join("");

  // ----- Ocupação agora, por categoria (só as categorias ativas) -----
  document.getElementById("ocupacao").innerHTML = dados.categorias.filter((c) => c.is_active).map((c) => {
    const id = idCategoria(c.name);
    const daCategoria = ativos.filter((r) => r.category_id === c.id);
    const n = daCategoria.filter((r) => ocupadoAgora(r, agora)).length;
    const pct = daCategoria.length ? Math.round((100 * n) / daCategoria.length) : 0;
    return `
      <div class="ocupacao-linha">
        <div class="ocupacao-texto"><span>${esc(c.name)}</span><span>${n} / ${daCategoria.length}</span></div>
        <!-- var(--x, var(--cor-primaria)): se a categoria não tiver cor própria no CSS, usa a primária -->
        <div class="ocupacao-barra"><div style="width: ${pct}%; background: var(--${id}, var(--cor-primaria))"></div></div>
      </div>`;
  }).join("");

  // ----- Tabela de recursos -----
  document.getElementById("lista-recursos").innerHTML = todos.map((r) => {
    const cat = idCategoria(r.category_name);
    const n = reservasHoje(r);
    const hojeTexto = r.is_active ? `${n} ${n === 1 ? "reserva" : "reservas"} hoje` : "Desativado";
    // A localização fica guardada na description
    const local = r.description ? `${esc(r.description)} · ` : "";
    return `
      <div class="recurso-linha${r.is_active ? "" : " inativo"}">
        <div class="recurso-nome">
          <b>${esc(r.name)}</b>
          <div>${local}${textoCapacidade(cat, r.capacity)}</div>
        </div>
        <div class="recurso-tipo"><i style="background: var(--${cat}, var(--cor-primaria))"></i>${esc(textoTipo(cat, r.resource_type))}</div>
        <div class="recurso-hoje">${hojeTexto}</div>
        <button type="button" class="interruptor" role="switch" aria-checked="${r.is_active}"
                aria-label="Ativo: ${esc(r.name)}" data-id="${r.id}">
          <span class="interruptor-trilho"><i></i></span>
        </button>
      </div>`;
  }).join("");
}

// ===== EVENTOS =====
// Ativar/desativar: PATCH {is_active} e volta a carregar (os números de cima também mudam)
document.getElementById("lista-recursos").addEventListener("click", async (e) => {
  const botao = e.target.closest(".interruptor");
  if (!botao) return;
  const recurso = dados.recursos.find((r) => r.id === botao.dataset.id);   // os ids são UUID (texto)
  const ativar = !recurso.is_active;

  botao.disabled = true;   // evita clique duplo enquanto espera a resposta
  try {
    await api.updateResource(recurso.id, { is_active: ativar });
    toast(ativar ? `${recurso.name} voltou a estar disponível.` : `${recurso.name} deixou de aparecer aos utilizadores.`);
    await carregar();
  } catch (err) {
    toast(err.message, true);
    botao.disabled = false;
  }
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

document.getElementById("lista-recursos").innerHTML = '<p class="admin-erro">A carregar…</p>';
carregar();
setInterval(carregar, 60 * 1000);   // atualiza a "ocupação agora" a cada minuto