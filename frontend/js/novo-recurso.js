// ===== NOVO RECURSO (administração) =====
// Formulário em 3 partes (categoria, detalhes, regras) com pré-visualização ao lado.
// Por agora não grava nada: mostra no Console o pedido que vai ser enviado à API.

const utilizador = requireAuth();
if (utilizador && utilizador.role !== "ADMIN") location.replace("index.html");   // só administradores

// ===== OPÇÕES DE CADA CATEGORIA (do design) =====
const CATEGORIAS = {
  coworking:      { name: "Coworking",      icon: "desk",          description: "Mesas e salas de reunião" },
  estacionamento: { name: "Estacionamento", icon: "local_parking", description: "Vagas nos pisos -1 e -2" },
  desporto:       { name: "Desporto",       icon: "sports_tennis", description: "Ginásio, pilates e padel" },
};
// [nome do tipo, ícone]
const TIPOS = {
  coworking:      [["Salas de reunião", "groups"], ["Mesas individuais", "desk"]],
  estacionamento: [["Piso -1", "directions_car"], ["Piso -2", "directions_car"]],
  desporto:       [["Padel", "sports_tennis"], ["Ginásio", "fitness_center"], ["Pilates", "self_improvement"]],
};
// [nome do atributo, ícone]
const ATRIBUTOS = {
  coworking:      [["Ecrã", "tv"], ["Videoconferência", "videocam"], ["Quadro", "edit_note"], ["Monitor", "desktop_windows"], ["Janela", "window"], ["Acessível", "accessible"]],
  estacionamento: [["Carregador EV", "ev_station"], ["Junto ao elevador", "elevator"], ["Coberta", "roofing"], ["Mota", "two_wheeler"], ["Acessível", "accessible"]],
  desporto:       [["Iluminação", "light_mode"], ["Coberta", "roofing"], ["Balneário", "shower"], ["Equipamento incluído", "sports"], ["Acessível", "accessible"]],
};
// [texto do campo, valor inicial]
const CAPACIDADE = {
  coworking:      ["Capacidade (pessoas)", 8],
  estacionamento: ["Lugares", 1],
  desporto:       ["Participantes máx.", 4],
};
// Exemplos que aparecem dentro dos campos vazios: [nome, localização]
const EXEMPLOS = {
  coworking:      ["Ex.: Sala Pacífico", "Ex.: Piso 4, ala sul"],
  estacionamento: ["Ex.: Vaga P-120", "Ex.: Piso -1, zona B"],
  desporto:       ["Ex.: Quadra de padel 3", "Ex.: Exterior"],
};
const DIAS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];
// Durações em minutos: [valor, texto]
const DURACOES_MIN = [[15, "15 min"], [30, "30 min"], [60, "1 h"]];
const DURACOES_MAX = [[60, "1 h"], [120, "2 h"], [240, "4 h"], [720, "Dia todo"]];

const PASSO_HORARIO = 30;   // abre/fecha andam de 30 em 30 minutos

// ===== AJUDANTES =====
// 570 → "09:30"
function paraHora(minutos) {
  return String(Math.floor(minutos / 60)).padStart(2, "0") + ":" + String(minutos % 60).padStart(2, "0");
}
// 90 → "1h30", 720 → "dia todo"
function textoDuracao(minutos) {
  if (minutos >= 720) return "dia todo";
  if (minutos < 60) return minutos + " min";
  return minutos % 60 ? `${Math.floor(minutos / 60)}h${minutos % 60}` : `${minutos / 60} h`;
}
// Capacidade em texto, como aparece nos cartões ("até 8 pessoas", "1 lugar"...)
function textoCapacidade(categoria, n) {
  if (categoria === "coworking") return n > 1 ? `até ${n} pessoas` : "1 pessoa";
  if (categoria === "estacionamento") return n > 1 ? `${n} lugares` : "1 lugar";
  return `até ${n} participantes`;
}

// ===== ESTADO DO FORMULÁRIO =====
// Valores iniciais de cada categoria. Ao trocar de categoria, o nome e a localização ficam.
function estadoInicial(categoria, anterior = {}) {
  return {
    categoria,
    tipo: TIPOS[categoria][0][0],
    nome: anterior.nome ?? "",
    local: anterior.local ?? "",
    capacidade: CAPACIDADE[categoria][1],
    atributos: [],
    dias: [true, true, true, true, true, false, false],      // seg a sex
    abre: 8 * 60,
    fecha: 20 * 60,
    minimo: categoria === "estacionamento" ? null : 15,      // estacionamento não tem duração mínima
    maximo: categoria === "estacionamento" ? 720 : 240,
    fila: true,
    erros: {},
  };
}
let estado = estadoInicial("coworking");

// ===== DESENHO =====
// Os campos de texto (nome e localização) não são redesenhados, para não perderem o foco.
function render() {
  const c = estado.categoria;

  // ----- 1. Categoria (cartões) e tipo -----
  document.getElementById("escolha-categoria").innerHTML = Object.entries(CATEGORIAS).map(([id, cat]) => `
    <button type="button" class="opcao-categoria${id === c ? " ativo" : ""}" data-categoria="${id}"
            aria-pressed="${id === c}" style="--cor-cat: var(--${id}); --cor-cat-suave: var(--${id}-suave)">
      <div class="opcao-categoria-topo">
        <div class="icone-caixa"><span class="icone">${cat.icon}</span></div>
        <span class="opcao-radio"></span>
      </div>
      <div>
        <div class="opcao-categoria-nome">${cat.name}</div>
        <div class="opcao-categoria-descricao">${cat.description}</div>
      </div>
    </button>`).join("");

  document.getElementById("escolha-tipo").innerHTML = TIPOS[c].map(([tipo, icone]) => `
    <button type="button" class="opcao-tipo${tipo === estado.tipo ? " ativo" : ""}" data-tipo="${tipo}" aria-pressed="${tipo === estado.tipo}">
      <span class="icone">${icone}</span>${tipo}
    </button>`).join("");

  // ----- 2. Detalhes -----
  document.getElementById("nome").placeholder = EXEMPLOS[c][0];
  document.getElementById("local").placeholder = EXEMPLOS[c][1];
  document.getElementById("nome").classList.toggle("com-erro", !!estado.erros.nome);
  document.getElementById("erro-nome").hidden = !estado.erros.nome;

  document.getElementById("capacidade-titulo").textContent = CAPACIDADE[c][0];
  document.getElementById("capacidade-valor").textContent = estado.capacidade;
  document.getElementById("capacidade-menos").disabled = estado.capacidade <= 1;
  document.getElementById("capacidade-mais").disabled = estado.capacidade >= 50;

  document.getElementById("escolha-atributos").innerHTML = ATRIBUTOS[c].map(([atributo, icone]) => {
    const ativo = estado.atributos.includes(atributo);
    return `<button type="button" class="opcao-atributo${ativo ? " ativo" : ""}" data-atributo="${atributo}" aria-pressed="${ativo}">
              <span class="icone">${icone}</span>${atributo}
            </button>`;
  }).join("");

  // ----- 3. Regras -----
  document.getElementById("escolha-dias").innerHTML = DIAS.map((dia, i) => `
    <button type="button" class="opcao-dia${estado.dias[i] ? " ativo" : ""}" data-dia="${i}" aria-pressed="${estado.dias[i]}">${dia}</button>`).join("");
  document.getElementById("erro-dias").hidden = !estado.erros.dias;

  document.getElementById("abre-valor").textContent = paraHora(estado.abre);
  document.getElementById("fecha-valor").textContent = paraHora(estado.fecha);
  // Tem de ficar aberto pelo menos 1 hora; o dia vai das 00:00 às 24:00
  document.getElementById("abre-menos").disabled = estado.abre - PASSO_HORARIO < 0;
  document.getElementById("abre-mais").disabled = estado.abre + PASSO_HORARIO > estado.fecha - 60;
  document.getElementById("fecha-menos").disabled = estado.fecha - PASSO_HORARIO < estado.abre + 60;
  document.getElementById("fecha-mais").disabled = estado.fecha + PASSO_HORARIO > 24 * 60;

  // Duração mínima: escondida no estacionamento
  document.getElementById("bloco-minimo").hidden = estado.minimo === null;
  document.getElementById("escolha-minimo").innerHTML = DURACOES_MIN.map(([v, t]) =>
    `<button type="button" class="${v === estado.minimo ? "ativo" : ""}" data-minimo="${v}" aria-pressed="${v === estado.minimo}">${t}</button>`).join("");
  document.getElementById("escolha-maximo").innerHTML = DURACOES_MAX.map(([v, t]) =>
    `<button type="button" class="${v === estado.maximo ? "ativo" : ""}" data-maximo="${v}" aria-pressed="${v === estado.maximo}">${t}</button>`).join("");

  document.getElementById("permitir-fila").setAttribute("aria-checked", estado.fila);

  renderPreview();
}

// Pré-visualização: o cartão como vai aparecer na lista da categoria
function renderPreview() {
  const c = estado.categoria;
  const icone = TIPOS[c].find(([tipo]) => tipo === estado.tipo)[1];
  const nome = estado.nome.trim() || EXEMPLOS[c][0].replace("Ex.: ", "");
  const local = estado.local.trim() || estado.tipo;

  // 12 barrinhas das 08h às 20h: livres dentro do horário de abertura, cinza fora
  let barras = "";
  for (let h = 8 * 60; h < 20 * 60; h += 60) {
    const aberto = h >= estado.abre && h + 60 <= estado.fecha;
    barras += `<i class="${aberto ? "" : "fechado"}"></i>`;
  }

  // Resumo das regras: "Seg, Ter, Qua · 08:00–20:00 · reservas de 15 min a 4 h · com fila de espera"
  const diasOn = DIAS.filter((_, i) => estado.dias[i]);
  const dias = diasOn.length === 7 ? "Todos os dias" : diasOn.join(", ") || "Sem dias";
  const duracao = estado.minimo === null
    ? `reservas até ${textoDuracao(estado.maximo)}`
    : `reservas de ${textoDuracao(estado.minimo)} a ${textoDuracao(estado.maximo)}`;
  const regras = `${dias} · ${paraHora(estado.abre)}–${paraHora(estado.fecha)} · ${duracao} · ${estado.fila ? "com" : "sem"} fila de espera`;

  const preview = document.getElementById("preview");
  preview.style.setProperty("--cor-cat", `var(--${c})`);
  preview.style.setProperty("--cor-cat-suave", `var(--${c}-suave)`);
  preview.innerHTML = `
    <article class="cartao-recurso">
      <div class="cartao-topo">
        <div class="preview-titulo">
          <div class="icone-caixa"><span class="icone">${icone}</span></div>
          <div>
            <div class="cartao-nome">${esc(nome)}</div>
            <div class="cartao-local">${esc(local)} · ${textoCapacidade(c, estado.capacidade)}</div>
          </div>
        </div>
        <span class="pilula livre">Livre</span>
      </div>
      <div class="cartao-tags">${estado.atributos.map((t) => `<span>${esc(t)}</span>`).join("")}</div>
      <div class="linha-dia">
        <div class="linha-dia-barras">${barras}</div>
        <div class="linha-dia-horas"><span>08</span><span>14</span><span>20</span></div>
      </div>
      <div class="botao botao-primario">Reservar</div>
    </article>
    <p class="preview-regras">${regras}</p>`;
}

// ===== EVENTOS =====
// Todos os botões de opção do formulário: um só "ouvinte" (delegação)
document.getElementById("form-recurso").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
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
  else if (d.minimo) {
    estado.minimo = Number(d.minimo);
    estado.maximo = Math.max(estado.maximo, estado.minimo);      // o máximo nunca fica abaixo do mínimo
  }
  else if (d.maximo) {
    estado.maximo = Number(d.maximo);
    if (estado.minimo !== null) estado.minimo = Math.min(estado.minimo, estado.maximo);
  }
  else if (b.id === "capacidade-menos") estado.capacidade--;
  else if (b.id === "capacidade-mais") estado.capacidade++;
  else if (b.id === "abre-menos") estado.abre -= PASSO_HORARIO;
  else if (b.id === "abre-mais") estado.abre += PASSO_HORARIO;
  else if (b.id === "fecha-menos") estado.fecha -= PASSO_HORARIO;
  else if (b.id === "fecha-mais") estado.fecha += PASSO_HORARIO;
  else if (b.id === "permitir-fila") estado.fila = !estado.fila;
  else return;   // outro botão (ex.: "Criar recurso" é tratado no submit)

  render();
});

// Campos de texto: só atualizam o estado e a pré-visualização
document.getElementById("nome").addEventListener("input", (e) => {
  estado.nome = e.target.value;
  if (estado.erros.nome) {               // começou a escrever: tira o erro
    estado.erros.nome = false;
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
document.getElementById("form-recurso").addEventListener("submit", (e) => {
  e.preventDefault();   // impede o formulário de recarregar a página

  estado.erros = { nome: !estado.nome.trim(), dias: !estado.dias.some(Boolean) };
  if (estado.erros.nome || estado.erros.dias) {
    render();
    if (estado.erros.nome) document.getElementById("nome").focus();
    return;
  }

  // Pedido que vai para a API (nomes provisórios, a alinhar com o booking-service)
  const pedido = {
    category: estado.categoria,
    type: estado.tipo,
    name: estado.nome.trim(),
    location: estado.local.trim() || estado.tipo,
    capacity: estado.capacidade,
    tags: estado.atributos,
    available_days: DIAS.map((_, i) => i).filter((i) => estado.dias[i]),   // 0 = segunda ... 6 = domingo
    opens_at: paraHora(estado.abre),
    closes_at: paraHora(estado.fecha),
    min_duration_minutes: estado.minimo,
    max_duration_minutes: estado.maximo,
    waitlist_enabled: estado.fila,
  };
  console.log("Pedido que vai para a API:", pedido);

  // Deixa um aviso para a Administração mostrar quando abrir
  try {
    sessionStorage.setItem("slotup_aviso", `${pedido.name} já está disponível para reserva.`);
  } catch (err) { /* sem acesso ao sessionStorage: segue sem aviso */ }
  location.href = "admin.html";
});

// ===== ARRANQUE =====
render();