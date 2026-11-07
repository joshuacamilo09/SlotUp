// ===== NOVO RECURSO (administração) =====
// Formulário em 3 partes (categoria, detalhes, horário) com pré-visualização ao lado.
// Grava com POST /api/reservas/recursos. Textos dos códigos em js/catalogo.js.

const utilizador = requireAuth();
if (utilizador && utilizador.role !== "ADMIN") location.replace("index.html");   // só administradores

// Exemplos que aparecem dentro dos campos vazios: [nome, localização]
const EXEMPLOS = {
  coworking:      ["Ex.: Sala de Reunião D", "Ex.: Piso 4, ala sul"],
  estacionamento: ["Ex.: Vaga Carro 3", "Ex.: Piso -1, zona B"],
  desporto:       ["Ex.: Quadra de Padel 2", "Ex.: Exterior"],
};
// Texto do campo da capacidade e valor inicial
const CAPACIDADE = {
  coworking:      ["Capacidade (pessoas)", 8],
  estacionamento: ["Lugares", 1],
  desporto:       ["Participantes máx.", 4],
};
const DIAS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];   // índice = weekday do backend (0 = segunda)
const PASSO_HORARIO = 30;      // abre/fecha andam de 30 em 30 minutos
const FIM_DO_DIA = 24 * 60;    // 24:00

// ===== AJUDANTES =====
// 570 → "09:30"
function paraHora(minutos) {
  return String(Math.floor(minutos / 60)).padStart(2, "0") + ":" + String(minutos % 60).padStart(2, "0");
}
// Para o backend: a coluna é "time", que não aceita 24:00. Fechar à meia-noite vira 23:59 (como no seed)
function horaParaApi(minutos) {
  return minutos >= FIM_DO_DIA ? "23:59" : paraHora(minutos);
}

// ===== ESTADO =====
// Categorias vindas da API, já com o id curto: [{ id: "coworking", uuid: "…", name: "Coworking" }, …]
let categorias = [];
let estado = null;

// Valores iniciais de uma categoria. Ao trocar de categoria, o nome e a localização ficam.
function estadoInicial(categoria, anterior = {}) {
  return {
    categoria,
    tipo: Object.keys(TIPOS_UI[categoria])[0],   // primeiro código do dicionário (ex.: "sala")
    nome: anterior.nome ?? "",
    local: anterior.local ?? "",
    capacidade: CAPACIDADE[categoria][1],
    atributos: [],                               // chaves escolhidas (ex.: ["monitor", "janela"])
    dias: [true, true, true, true, true, false, false],
    abre: 8 * 60,
    fecha: 20 * 60,
    erros: {},
    aEnviar: false,
  };
}

// ===== DESENHO =====
// Os campos de texto (nome e localização) não são redesenhados, para não perderem o foco.
function render() {
  const c = estado.categoria;

  // ----- 1. Categoria (cartões) e tipo -----
  document.getElementById("escolha-categoria").innerHTML = categorias.map((cat) => `
    <button type="button" class="opcao-categoria${cat.id === c ? " ativo" : ""}" data-categoria="${cat.id}"
            aria-pressed="${cat.id === c}" style="--cor-cat: var(--${cat.id}); --cor-cat-suave: var(--${cat.id}-suave)">
      <div class="opcao-categoria-topo">
        <div class="icone-caixa"><span class="icone">${CATEGORIAS_UI[cat.id].icon}</span></div>
        <span class="opcao-radio"></span>
      </div>
      <div>
        <div class="opcao-categoria-nome">${esc(cat.name)}</div>
        <div class="opcao-categoria-descricao">${CATEGORIAS_UI[cat.id].description}</div>
      </div>
    </button>`).join("");

  document.getElementById("escolha-tipo").innerHTML = Object.entries(TIPOS_UI[c]).map(([codigo, [texto, icone]]) => `
    <button type="button" class="opcao-tipo${codigo === estado.tipo ? " ativo" : ""}" data-tipo="${codigo}" aria-pressed="${codigo === estado.tipo}">
      <span class="icone">${icone}</span>${texto}
    </button>`).join("");

  // ----- 2. Detalhes -----
  document.getElementById("nome").placeholder = EXEMPLOS[c][0];
  document.getElementById("local").placeholder = EXEMPLOS[c][1];
  document.getElementById("nome").classList.toggle("com-erro", !!estado.erros.nome);
  document.getElementById("erro-nome").hidden = !estado.erros.nome;
  document.getElementById("erro-nome").textContent = estado.erros.nome || "";

  document.getElementById("capacidade-titulo").textContent = CAPACIDADE[c][0];
  document.getElementById("capacidade-valor").textContent = estado.capacidade;
  document.getElementById("capacidade-menos").disabled = estado.capacidade <= 1;
  document.getElementById("capacidade-mais").disabled = estado.capacidade >= 1000;   // limite do backend

  document.getElementById("escolha-atributos").innerHTML = Object.entries(ATRIBUTOS_UI[c]).map(([chave, [texto, icone]]) => {
    const ativo = estado.atributos.includes(chave);
    return `<button type="button" class="opcao-atributo${ativo ? " ativo" : ""}" data-atributo="${chave}" aria-pressed="${ativo}">
              <span class="icone">${icone}</span>${texto}
            </button>`;
  }).join("");

  // ----- 3. Horário -----
  document.getElementById("escolha-dias").innerHTML = DIAS.map((dia, i) => `
    <button type="button" class="opcao-dia${estado.dias[i] ? " ativo" : ""}" data-dia="${i}" aria-pressed="${estado.dias[i]}">${dia}</button>`).join("");
  document.getElementById("erro-dias").hidden = !estado.erros.dias;

  document.getElementById("abre-valor").textContent = paraHora(estado.abre);
  document.getElementById("fecha-valor").textContent = paraHora(estado.fecha);
  // Tem de ficar aberto pelo menos 1 hora; o dia vai das 00:00 às 24:00
  document.getElementById("abre-menos").disabled = estado.abre - PASSO_HORARIO < 0;
  document.getElementById("abre-mais").disabled = estado.abre + PASSO_HORARIO > estado.fecha - 60;
  document.getElementById("fecha-menos").disabled = estado.fecha - PASSO_HORARIO < estado.abre + 60;
  document.getElementById("fecha-mais").disabled = estado.fecha + PASSO_HORARIO > FIM_DO_DIA;

  // Botão de enviar: desativado enquanto espera a resposta
  const enviar = document.getElementById("criar-btn");
  enviar.disabled = estado.aEnviar;
  enviar.textContent = estado.aEnviar ? "A criar…" : "Criar recurso";

  renderPreview();
}

// Pré-visualização: o cartão como vai aparecer na lista da categoria
function renderPreview() {
  const c = estado.categoria;
  const nome = estado.nome.trim() || EXEMPLOS[c][0].replace("Ex.: ", "");
  const local = estado.local.trim();
  const tags = estado.atributos.map((chave) => ATRIBUTOS_UI[c][chave][0]);

  // 12 barrinhas das 08h às 20h: livres dentro do horário de abertura, cinza fora
  let barras = "";
  for (let h = 8 * 60; h < 20 * 60; h += 60) {
    const aberto = h >= estado.abre && h + 60 <= estado.fecha;
    barras += `<i class="${aberto ? "" : "fechado"}"></i>`;
  }

  // Resumo do horário: "Seg, Ter, Qua, Qui, Sex · 08:00–20:00"
  const diasOn = DIAS.filter((_, i) => estado.dias[i]);
  const dias = diasOn.length === 7 ? "Todos os dias" : diasOn.join(", ") || "Sem dias";

  const preview = document.getElementById("preview");
  preview.style.setProperty("--cor-cat", `var(--${c})`);
  preview.style.setProperty("--cor-cat-suave", `var(--${c}-suave)`);
  preview.innerHTML = `
    <article class="cartao-recurso">
      <div class="cartao-topo">
        <div class="preview-titulo">
          <div class="icone-caixa"><span class="icone">${iconeTipo(c, estado.tipo)}</span></div>
          <div>
            <div class="cartao-nome">${esc(nome)}</div>
            <div class="cartao-local">${local ? esc(local) + " · " : ""}${textoCapacidade(c, estado.capacidade)}</div>
          </div>
        </div>
        <span class="pilula livre">Livre</span>
      </div>
      <div class="cartao-tags">${tags.map((t) => `<span>${esc(t)}</span>`).join("")}</div>
      <div class="linha-dia">
        <div class="linha-dia-barras">${barras}</div>
        <div class="linha-dia-horas"><span>08</span><span>14</span><span>20</span></div>
      </div>
      <div class="botao botao-primario">Reservar</div>
    </article>
    <p class="preview-regras">${dias} · ${paraHora(estado.abre)}–${paraHora(estado.fecha)} · reservas de 15 em 15 min</p>`;
}

// ===== EVENTOS =====
// Todos os botões de opção do formulário: um só "ouvinte" (delegação)
document.getElementById("form-recurso").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b || !estado || b.type === "submit") return;
  const d = b.dataset;   // atributos data-*: data-tipo → d.tipo, data-dia → d.dia...

  if (d.categoria) estado = estadoInicial(d.categoria, estado);   // nova categoria: valores iniciais dela
  else if (d.tipo) estado.tipo = d.tipo;
  else if (d.atributo) {
    // Liga/desliga o atributo
    estado.atributos = estado.atributos.includes(d.atributo)
      ? estado.atributos.filter((a) => a !== d.atributo)
      : [...estado.atributos, d.atributo];
  }
  else if (d.dia) {
    estado.dias[Number(d.dia)] = !estado.dias[Number(d.dia)];
    estado.erros.dias = false;
  }
  else if (b.id === "capacidade-menos") estado.capacidade--;
  else if (b.id === "capacidade-mais") estado.capacidade++;
  else if (b.id === "abre-menos") estado.abre -= PASSO_HORARIO;
  else if (b.id === "abre-mais") estado.abre += PASSO_HORARIO;
  else if (b.id === "fecha-menos") estado.fecha -= PASSO_HORARIO;
  else if (b.id === "fecha-mais") estado.fecha += PASSO_HORARIO;
  else return;

  render();
});

// Campos de texto: só atualizam o estado e a pré-visualização
document.getElementById("nome").addEventListener("input", (e) => {
  estado.nome = e.target.value;
  if (estado.erros.nome) {               // começou a escrever: tira o erro
    estado.erros.nome = "";
    render();
  } else {
    renderPreview();
  }
});
document.getElementById("local").addEventListener("input", (e) => {
  estado.local = e.target.value;
  renderPreview();
});

// ----- Criar recurso -----
document.getElementById("form-recurso").addEventListener("submit", async (e) => {
  e.preventDefault();   // impede o formulário de recarregar a página
  if (!estado || estado.aEnviar) return;

  // Validação no frontend (o backend volta a validar tudo)
  const nome = estado.nome.trim();
  estado.erros = {
    nome: nome.length < 2 ? "Dê um nome ao recurso (mínimo 2 letras)." : "",
    dias: !estado.dias.some(Boolean),
  };
  if (estado.erros.nome || estado.erros.dias) {
    render();
    if (estado.erros.nome) document.getElementById("nome").focus();
    return;
  }

  // Pedido no formato do ResourceCreate do backend
  const pedido = {
    category_id: categorias.find((c) => c.id === estado.categoria).uuid,
    name: nome,
    resource_type: estado.tipo,
    description: estado.local.trim() || null,                                  // a localização vai na description
    capacity: estado.capacidade,
    attributes: Object.fromEntries(estado.atributos.map((chave) => [chave, true])),   // ["monitor"] → {monitor: true}
    // Um intervalo por dia escolhido (weekday: 0 = segunda ... 6 = domingo)
    schedule: DIAS.map((_, i) => i).filter((i) => estado.dias[i]).map((i) => ({
      weekday: i,
      open_time: horaParaApi(estado.abre),
      close_time: horaParaApi(estado.fecha),
    })),
  };

  estado.aEnviar = true;
  render();
  try {
    const criado = await api.createResource(pedido);
    try {
      sessionStorage.setItem("slotup_aviso", `${criado.name} já está disponível para reserva.`);
    } catch (err) { /* sem acesso ao sessionStorage: segue sem aviso */ }
    location.href = "admin.html";
  } catch (err) {
    estado.aEnviar = false;
    if (err.status === 409) {
      estado.erros.nome = err.message;       // "Já existe um recurso com esse nome nesta categoria"
      render();
      document.getElementById("nome").focus();
    } else {
      render();
      toast(err.message, true);              // outros erros (422, 503...) num aviso em baixo
    }
  }
});

// ===== ARRANQUE =====
// Busca as categorias ativas e fica só com as que o frontend conhece (estão no catalogo.js)
async function iniciar() {
  try {
    const daApi = await api.categories();
    categorias = daApi
      .map((c) => ({ id: idCategoria(c.name), uuid: c.id, name: c.name }))
      .filter((c) => TIPOS_UI[c.id]);
    if (categorias.length === 0) throw new Error("Não há categorias ativas.");
    estado = estadoInicial(categorias[0].id);
    render();
  } catch (err) {
    document.getElementById("escolha-categoria").innerHTML = `<p class="campo-erro">${esc(err.message)}</p>`;
  }
}
iniciar();