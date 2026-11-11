// ===== LISTA DA CATEGORIA =====
// Mostra os recursos de uma categoria (categoria.html?cat=coworking) com o estado
// de cada um no dia e horário escolhidos nos filtros. Dados reais do booking-service.

const utilizador = requireAuth();   // sem sessão, vai para o login

// ===== REGRAS DE HORÁRIO (iguais às do backend) =====
// Trabalhamos em minutos desde a meia-noite: 09:30 → 570. Facilita somar e comparar.
const ABRE = 8 * 60;          // a lista mostra das 08:00...
const FECHA = 20 * 60;        // ...às 20:00
const PASSO = 15;             // os horários andam de 15 em 15 minutos
const DURACAO_MINIMA = 15;
const NUM_DIAS = 7;           // chips de hoje até daqui a 6 dias (o backend aceita até 30)

const DIAS_SEMANA = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];
const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

// 570 → "09:30"
function paraHora(minutos) {
  const h = String(Math.floor(minutos / 60)).padStart(2, "0");
  const m = String(minutos % 60).padStart(2, "0");
  return `${h}:${m}`;
}

// Data do dia "offset" a partir de hoje, à meia-noite (0 = hoje, 1 = amanhã...)
function dataDoDia(offset) {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() + offset);
  return d;
}

// Um intervalo da API ({start, end} em ISO com fuso) → [início, fim] em minutos desse dia
function emMinutos(intervalo, meiaNoite) {
  return [
    Math.round((new Date(intervalo.start) - meiaNoite) / 60000),
    Math.round((new Date(intervalo.end) - meiaNoite) / 60000),
  ];
}

// Os intervalos [a, b) e [c, d) sobrepõem-se? (b igual a c não conta: 10:00–11:00 e 11:00–12:00 não chocam)
function sobrepoe(a, b, c, d) {
  return a < d && c < b;
}

// Primeiro horário de início permitido no dia escolhido: hoje não se pode reservar no passado
function inicioMinimo(dia) {
  if (dia !== 0) return ABRE;
  const agora = new Date();
  const minutosAgora = agora.getHours() * 60 + agora.getMinutes();
  const arredondado = Math.ceil(minutosAgora / PASSO) * PASSO;   // 10:07 → 10:15
  return Math.max(ABRE, arredondado);
}

// ===== ESTADO DA TELA =====
const idCat = new URLSearchParams(location.search).get("cat");   // "coworking", "desporto"...
const estado = { tipo: "Todos", dia: 0, inicio: 0, fim: 0, soLivres: false };

// Dados da API
let categoria = null;     // { id, name, ... } do backend
let recursos = [];        // recursos desta categoria
let minhas = [];          // as minhas reservas confirmadas (futuras)
let naFila = [];          // os meus pedidos ativos na fila
let disps = {};           // disponibilidade do dia escolhido: { idDoRecurso: {opening, busy} }
let pedidoAtual = 0;      // para ignorar respostas antigas quando se troca de dia depressa
let aCarregar = true;     // enquanto a disponibilidade do dia não chega, mostra "A carregar…"

// Horário inicial: a próxima hora cheia, com 1 hora de duração.
// Se já não couber hoje (depois das 19:00), começa amanhã às 08:00.
(function horarioInicial() {
  const proximaHora = (new Date().getHours() + 1) * 60;
  estado.inicio = Math.max(ABRE, proximaHora);
  if (estado.inicio + 60 > FECHA) {
    estado.dia = 1;
    estado.inicio = ABRE;
  }
  estado.fim = estado.inicio + 60;
})();

// ===== ESTADO DE UM RECURSO =====
// Devolve "fechado", "minha", "fila", "ocupado" ou "livre" para o intervalo [inicio, fim) do dia.
function estadoDoRecurso(recurso, inicio, fim) {
  const disp = disps[recurso.id];
  if (!disp) return "fechado";   // erro ao carregar: não deixa reservar
  const meiaNoite = dataDoDia(estado.dia);

  // Tem de caber inteiro num intervalo de abertura (a mesma regra do backend)
  const aberto = disp.opening.some((i) => {
    const [a, b] = emMinutos(i, meiaNoite);
    return a <= inicio && fim <= b;
  });
  if (!aberto) return "fechado";

  // As minhas reservas e pedidos na fila deste recurso que tocam no intervalo
  const toca = (r, ini, fi) => {
    const [a, b] = emMinutos({ start: ini, end: fi }, meiaNoite);
    return r === recurso.id && sobrepoe(inicio, fim, a, b);
  };
  if (minhas.some((m) => toca(m.resource_id, m.start_at, m.end_at))) return "minha";
  if (naFila.some((f) => toca(f.resource_id, f.desired_start, f.desired_end))) return "fila";

  const ocupado = disp.busy.some((i) => {
    const [a, b] = emMinutos(i, meiaNoite);
    return sobrepoe(inicio, fim, a, b);
  });
  return ocupado ? "ocupado" : "livre";
}

const TEXTO_PILULA = { livre: "Livre", ocupado: "Ocupado", minha: "Reservado por si", fila: "Em fila", fechado: "Fechado" };

// ===== DESENHO DA TELA =====
function render() {
  renderAbas();
  renderDias();
  renderHorario();

  // Recursos do tipo escolhido, cada um com o seu estado no horário do filtro
  const doTipo = recursos
    .filter((r) => estado.tipo === "Todos" || r.resource_type === estado.tipo)
    .map((r) => ({ recurso: r, situacao: estadoDoRecurso(r, estado.inicio, estado.fim) }));

  const livres = doTipo.filter((x) => x.situacao === "livre").length;
  const visiveis = estado.soLivres ? doTipo.filter((x) => x.situacao === "livre") : doTipo;

  // Resumo: "6 de 8 livres · Qui, 22 out, 09:00–10:00"
  const data = dataDoDia(estado.dia);
  const quando = `${DIAS_SEMANA[data.getDay()]}, ${data.getDate()} ${MESES[data.getMonth()]}, ${paraHora(estado.inicio)}–${paraHora(estado.fim)}`;
  document.getElementById("resumo").innerHTML = `<b>${livres} de ${doTipo.length} livres</b> · ${quando}`;

  if (aCarregar) {
    document.getElementById("resumo").textContent = `A carregar · ${quando}`;
    document.getElementById("grelha-recursos").innerHTML = "";
    document.getElementById("lista-vazia").hidden = true;
    return;
  }
  document.getElementById("grelha-recursos").innerHTML = visiveis.map(cartaoHtml).join("");
  document.getElementById("lista-vazia").hidden = visiveis.length > 0;
}

// Abas: "Todos · 6", depois uma por tipo (texto do catalogo.js)
function renderAbas() {
  const tipos = ["Todos", ...new Set(recursos.map((r) => r.resource_type))];   // Set remove os repetidos
  document.getElementById("abas-tipo").innerHTML = tipos.map((tipo) => {
    const total = tipo === "Todos" ? recursos.length : recursos.filter((r) => r.resource_type === tipo).length;
    const ativo = tipo === estado.tipo;
    const texto = tipo === "Todos" ? "Todos" : textoTipo(idCat, tipo);
    return `<button type="button" class="aba${ativo ? " ativo" : ""}" role="tab" aria-selected="${ativo}"
              data-tipo="${esc(tipo)}">${esc(texto)} · ${total}</button>`;
  }).join("");
}

// Chips dos 7 dias: o primeiro diz "Hoje"
function renderDias() {
  let html = "";
  for (let i = 0; i < NUM_DIAS; i++) {
    const data = dataDoDia(i);
    const nome = i === 0 ? "Hoje" : DIAS_SEMANA[data.getDay()];
    // Hoje fica desativado quando já não cabe nenhuma reserva (perto ou depois das 20:00)
    const semHorario = i === 0 && inicioMinimo(0) > FECHA - DURACAO_MINIMA;
    html += `<button type="button" class="chip-dia${i === estado.dia ? " ativo" : ""}" data-dia="${i}"${semHorario ? " disabled" : ""}>
               <span class="chip-dia-semana">${nome}</span>
               <span class="chip-dia-numero">${data.getDate()}</span>
             </button>`;
  }
  document.getElementById("chips-dias").innerHTML = html;
}

// Valores dos seletores e botões desativados quando chegam ao limite
function renderHorario() {
  // Listas de horas: o início vai do mínimo do dia até 19:45; o fim, de início + 15 min até 20:00
  preencherHoras("inicio-valor", inicioMinimo(estado.dia), FECHA - DURACAO_MINIMA, estado.inicio);
  preencherHoras("fim-valor", estado.inicio + DURACAO_MINIMA, FECHA, estado.fim);

  document.getElementById("inicio-menos").disabled = estado.inicio - PASSO < inicioMinimo(estado.dia);
  document.getElementById("inicio-mais").disabled = estado.inicio + PASSO > FECHA - DURACAO_MINIMA;
  document.getElementById("fim-menos").disabled = estado.fim - PASSO < estado.inicio + DURACAO_MINIMA;
  document.getElementById("fim-mais").disabled = estado.fim + PASSO > FECHA;

  document.getElementById("so-livres").setAttribute("aria-checked", estado.soLivres);
}

   // Preenche uma lista (<select>) com as horas de 15 em 15 min, de "de" até "ate", e escolhe "valor"
   function preencherHoras(id, de, ate, valor) {
     let html = "";
     for (let m = de; m <= ate; m += PASSO) {
       html += `<option value="${m}"${m === valor ? " selected" : ""}>${paraHora(m)}</option>`;
     }
     document.getElementById(id).innerHTML = html;
   }

// HTML de um cartão de recurso
function cartaoHtml({ recurso, situacao }) {
  // Link para o detalhe já com o dia e o horário do filtro
  const link = `recurso.html?id=${recurso.id}&dia=${toISODate(dataDoDia(estado.dia))}` +
               `&inicio=${paraHora(estado.inicio)}&fim=${paraHora(estado.fim)}`;

  // 12 barrinhas, uma por hora das 08h às 20h
  let barras = "";
  for (let h = ABRE; h < FECHA; h += 60) {
    const s = estadoDoRecurso(recurso, h, h + 60);
    const classes = [s === "livre" ? "" : s, sobrepoe(h, h + 60, estado.inicio, estado.fim) ? "no-filtro" : ""];
    barras += `<i class="${classes.join(" ").trim()}"></i>`;
  }

  // Botão conforme o estado (o ✨ marca as alternativas; as sugestões do CSP vêm depois)
  const horario = `${paraHora(estado.inicio)}–${paraHora(estado.fim)}`;
  const botoes = {
    livre:   `<a class="botao botao-primario" href="${link}">Reservar ${horario}</a>`,
    ocupado: `<a class="botao botao-secundario" href="${link}"><span class="icone">auto_awesome</span>Ver alternativas</a>`,
    minha:   `<a class="botao botao-secundario" href="reservas.html">Ver a minha reserva</a>`,
    fila:    `<a class="botao botao-secundario" href="${link}">Em fila · ver horários</a>`,
    fechado: `<a class="botao botao-secundario" href="${link}">Fechado neste horário · ver o dia</a>`,
  };

  // Subtítulo: localização (description) · capacidade
  const sub = [recurso.description ? esc(recurso.description) : "", textoCapacidade(idCat, recurso.capacity)]
    .filter(Boolean).join(" · ");
  const tags = atributosEmTexto(idCat, recurso.attributes);

  return `
    <article class="cartao-recurso">
      <div class="cartao-topo">
        <a href="${link}" class="cartao-link">
          <div class="cartao-nome">${esc(recurso.name)}</div>
          <div class="cartao-local">${sub}</div>
        </a>
        <span class="pilula ${situacao}">${TEXTO_PILULA[situacao]}</span>
      </div>
      <div class="cartao-tags">${tags.map((t) => `<span>${esc(t)}</span>`).join("")}</div>
      <div class="linha-dia" title="Ocupação das 08:00 às 20:00">
        <div class="linha-dia-barras">${barras}</div>
        <div class="linha-dia-horas"><span>08</span><span>14</span><span>20</span></div>
      </div>
      ${botoes[situacao]}
    </article>`;
}

// ===== CARREGAR DA API =====
// Disponibilidade do dia escolhido para todos os recursos (em paralelo)
async function carregarDia() {
  const meu = ++pedidoAtual;   // número deste pedido
  disps = {};
  aCarregar = true;
  render();

  const dia = toISODate(dataDoDia(estado.dia));
  const resultados = await Promise.all(recursos.map((r) => api.availability(r.id, dia).catch(() => null)));
  if (meu !== pedidoAtual) return;   // entretanto escolheu outro dia: esta resposta já não interessa

  recursos.forEach((r, i) => { if (resultados[i]) disps[r.id] = resultados[i]; });
  aCarregar = false;
  render();
}

async function iniciar() {
  try {
    // Categoria pelo id curto da URL ("coworking" ↔ "Coworking")
    const categorias = await api.categories();
    categoria = categorias.find((c) => idCategoria(c.name) === idCat);
    if (!categoria) {
      location.replace("index.html");   // categoria inexistente ou desativada: volta à home
      return;
    }

    // Título, ícone e cores da categoria
    const ui = CATEGORIAS_UI[idCat] ?? { icon: "category", description: categoria.description ?? "" };
    document.title = `SlotUp · ${categoria.name}`;
    document.getElementById("caminho-atual").textContent = categoria.name;
    document.getElementById("cat-nome").textContent = categoria.name;
    document.getElementById("cat-descricao").textContent = ui.description;
    document.getElementById("cat-icone").textContent = ui.icon;
    const topo = document.getElementById("cat-topo");
    topo.style.setProperty("--cor-cat", `var(--${idCat}, var(--cor-primaria))`);
    topo.style.setProperty("--cor-cat-suave", `var(--${idCat}-suave, var(--cor-chip))`);

    // Recursos, as minhas reservas e a minha fila, ao mesmo tempo
    const [lista, reservas, fila] = await Promise.all([
      api.resources({ categoryId: categoria.id }),
      api.myReservations("futuras", 200, "CONFIRMED"),
      api.myWaitlist(),
    ]);
    recursos = lista;
    minhas = reservas;
    naFila = fila.filter((f) => f.status === "WAITING" || f.status === "OFFERED");

    await carregarDia();
  } catch (err) {
    document.getElementById("grelha-recursos").innerHTML = `<p class="lista-vazia">${esc(err.message)}</p>`;
  }
}

// ===== EVENTOS =====
// Abas: um único "ouvinte" no contentor (delegação), porque os botões são redesenhados
document.getElementById("abas-tipo").addEventListener("click", (e) => {
  const aba = e.target.closest(".aba");
  if (!aba) return;
  estado.tipo = aba.dataset.tipo;
  render();
});

// Dias: ao trocar, garante que o horário não fica no passado e carrega a disponibilidade desse dia
document.getElementById("chips-dias").addEventListener("click", (e) => {
  const chip = e.target.closest(".chip-dia");
  if (!chip || Number(chip.dataset.dia) === estado.dia) return;
  estado.dia = Number(chip.dataset.dia);

  const minimo = inicioMinimo(estado.dia);
  if (estado.inicio < minimo) {
    const duracao = estado.fim - estado.inicio;
    estado.inicio = minimo;
    estado.fim = Math.min(FECHA, minimo + duracao);
    if (estado.fim - estado.inicio < DURACAO_MINIMA) estado.inicio = estado.fim - DURACAO_MINIMA;
  }
  carregarDia();
});

// Seletores de hora. Os botões ficam desativados nos limites, por isso aqui basta somar.
// Mudar a hora não pede nada à API: a disponibilidade do dia já está carregada.
document.getElementById("inicio-menos").addEventListener("click", () => {
  estado.inicio -= PASSO;
  render();
});
document.getElementById("inicio-mais").addEventListener("click", () => {
  estado.inicio += PASSO;
  // Se o início encostar no fim, empurra o fim junto (mantém a duração mínima)
  if (estado.fim - estado.inicio < DURACAO_MINIMA) estado.fim = estado.inicio + DURACAO_MINIMA;
  render();
});
document.getElementById("fim-menos").addEventListener("click", () => {
  estado.fim -= PASSO;
  render();
});
document.getElementById("fim-mais").addEventListener("click", () => {
  estado.fim += PASSO;
  render();
});

   // Escolher a hora na lista. Ao mudar o início, a duração mantém-se (como num calendário)
   document.getElementById("inicio-valor").addEventListener("change", (e) => {
     const duracao = estado.fim - estado.inicio;
     estado.inicio = Number(e.target.value);                      // o value vem como texto: "600" → 600
     estado.fim = Math.min(FECHA, estado.inicio + duracao);
     render();
   });
   document.getElementById("fim-valor").addEventListener("change", (e) => {
     estado.fim = Number(e.target.value);
     render();
   });

// Interruptor "Só disponíveis"
document.getElementById("so-livres").addEventListener("click", () => {
  estado.soLivres = !estado.soLivres;
  render();
});

// ===== ARRANQUE =====
iniciar();