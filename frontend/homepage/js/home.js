// ===== BANNER DA VAGA (dados fictícios por enquanto) =====

// Tempo que a vaga fica guardada, em segundos.
// Depois isto virá do backend (momento em que o HELD expira).
const TEMPO_TOTAL = 5 * 60;
const expiraEm = Date.now() + TEMPO_TOTAL * 1000;   // Date.now() = agora, em milissegundos

// Pegamos os elementos do HTML pelo id
const banner = document.getElementById('banner-vaga');
const textoTempo = document.getElementById('vaga-tempo');
const anel = document.getElementById('vaga-anel');

// Esconde o banner e para o contador
function fecharBanner() {
    clearInterval(intervalo);
    banner.hidden = true;
}

//  Roda a cada segundo: calcula o tempo restante e atualiza a tela
function atualizarContador() {
    const restante = Math.max(0, Math.round((expiraEm - Date.now()) / 1000));
    const min = Math.floor(restante / 60);
    const seg = String(restante % 60).padStart(2, '0');
    textoTempo.textContent = `${min}:${seg}`;

    // Porcentagem que ainda resta → o CSS usa isso para desenhar o anel
    anel.style.setProperty('--progresso', (restante / TEMPO_TOTAL) * 100 + '%');

    if (restante === 0) fecharBanner(); // tempo acabou: a vaga passa para o próximo
}

atualizarContador();// primeira atualização imediata
const intervalo = setInterval(atualizarContador, 1000);// depois, a cada 1000 ms

// Botões: por enquanto só fecham o banner.
// Depois vão chamar a API (confirmar ou recusar a vaga na fila).
document.getElementById('vaga-recusar').addEventListener('click', fecharBanner);
document.getElementById('vaga-confirmar').addEventListener('click', fecharBanner);

// ===== UTILITÁRIO DE SEGURANÇA =====
// Converte < > & " em texto seguro antes de pôr no HTML.
// Importante quando os dados vierem da API, para evitar XSS.
function escapar(texto) {
    const div = document.createElement('div');
    div.textContent = texto;
    return div.innerHTML;
}

// ===== SAUDAÇÃO =====
const NOME_UTILIZADOR = 'Marta'; 

function saudacaoPorHora() {
    const hora = new Date().getHours();
    if (hora < 12) return 'Bom dia';
    if (hora < 20) return 'Boa tarde';
    return 'Boa noite';
}

// toLocaleDateString formata a data no idioma pedido: "sábado, 24 de outubro"
const hoje = new Date().toLocaleDateString('pt-PT', { weekday: 'long', day: 'numeric', month: 'long' });
document.getElementById('saudacao-titulo').textContent = `${saudacaoPorHora()}, ${NOME_UTILIZADOR}`;
document.getElementById('saudacao-data').textContent = hoje.charAt(0).toUpperCase() + hoje.slice(1);

// ===== CATEGORIAS (dados fictícios) =====
// O "id" tem o mesmo nome das variáveis de cor do CSS (--coworking, --estacionamento...)
const CATEGORIAS = [
    { id: 'coworking',      nome: 'Coworking',      icone: 'desk',          descricao: 'Mesas individuais e salas de reunião',       livres: 6, total: 8 },
    { id: 'estacionamento', nome: 'Estacionamento', icone: 'local_parking', descricao: 'Vagas nos pisos -1 e -2',                    livres: 2, total: 5 },
    { id: 'desporto',       nome: 'Desporto',       icone: 'sports_tennis', descricao: 'Ginásio, personal trainer, pilates e padel', livres: 6, total: 6 },
];

// map() transforma cada categoria num pedaço de HTML; join('') junta tudo numa string
document.getElementById('lista-categorias').innerHTML = CATEGORIAS.map(c => `
  <a class="card-categoria" href="categoria.html?cat=${c.id}"
     style="--cor-cat: var(--${c.id}); --cor-cat-suave: var(--${c.id}-suave)">
    <div class="card-topo">
      <div class="icone-caixa"><span class="icone">${c.icone}</span></div>
      <span class="icone">arrow_forward</span>
    </div>
    <div>
      <div class="card-nome">${escapar(c.nome)}</div>
      <div class="card-descricao">${escapar(c.descricao)}</div>
    </div>
    <div class="card-rodape">
      <i class="ponto-livre"></i>
      <b>${c.livres} livres agora</b>
      <span>de ${c.total}</span>
    </div>
  </a>
`).join('');

// ===== PRÓXIMAS RESERVAS (dados fictícios) =====
// Depois virão da API (GET /api/reservas), com datas reais em vez de texto pronto.
// "let" em vez de "const" porque vamos substituir a lista ao cancelar.
let reservas = [
  {id: 1, diaSemana: 'Hoje', dia: 22, nome: 'Sala Atlântico',    local: 'Coworking · Piso 2',      categoria: 'coworking',      icone: 'groups',        inicio: '11:00', fim: '12:00' },
  { id: 2, diaSemana: 'Sex',  dia: 23, nome: 'Vaga P-115',        local: 'Estacionamento · Piso -1', categoria: 'estacionamento', icone: 'ev_station',    inicio: '08:30', fim: '18:00' },
  { id: 3, diaSemana: 'Seg',  dia: 26, nome: 'Quadra de padel 2', local: 'Desporto · Exterior',      categoria: 'desporto',       icone: 'sports_tennis', inicio: '09:00', fim: '10:30' },
];

function renderizarReservas() {
  const lista = document.getElementById('lista-reservas');

  // Lista vazia: mostra a mensagem do design
  if (reservas.length === 0){
    lista.innerHTML = '<p class="painel-vazio">Sem reservas. Escolha uma categoria acima para começar.</p>';
    return;
  }

  lista.innerHTML = reservas.map(r => `
    <div class="reserva">
      <div class="reserva-data">
        <div class="reserva-dia-semana">${escapar(r.diaSemana)}</div>
        <div class="reserva-dia">${r.dia}</div>
      </div>
      <div class="reserva-icone" style="--cor-cat: var(--${r.categoria}); --cor-cat-suave: var(--${r.categoria}-suave)">
        <span class="icone">${r.icone}</span>
      </div>
      <div class="reserva-info">
        <div class="reserva-nome">${escapar(r.nome)}</div>
        <div class="reserva-local">${escapar(r.local)}</div>
      </div>
      <div class="reserva-hora">${r.inicio}–${r.fim}</div>
      <!-- data-id guarda o id da reserva no próprio botão -->
      <button class="botao-cancelar" data-id="${r.id}">Cancelar</button>
    </div>
  `).join('');
}

// Delegação de eventos: um único "ouvinte" na lista em vez de um por botão.
// Funciona mesmo depois de a lista ser redesenhada.
document.getElementById('lista-reservas').addEventListener('click', (evento) => {
  const botao = evento.target.closest('.botao-cancelar');
  if (!botao) return;
  const id = Number(botao.dataset.id);
  reservas = reservas.filter(r => r.id !== id);
  renderizarReservas();
});

renderizarReservas();

// ===== FILA DE ESPERA (dados fictícios) =====
// vagaAberta = true corresponde ao status HELD no backend
const fila = [
  { nome: 'Personal trainer · Rui', quando: 'Sex, 23 out · 08:00–09:00', posicao: 1, vagaAberta: true },
];

function renderizarFila() {
  const lista = document.getElementById('lista-fila');

  if (fila.length === 0) {
    lista.innerHTML = '<p class="painel-vazio">Não está em nenhuma fila. Quando um horário estiver ocupado, pode entrar na fila e avisamos por email.</p>';
  } else {
    lista.innerHTML = fila.map(f => `
      <div class="fila-item">
        <div class="fila-topo">
          <b>${escapar(f.nome)}</b>
          <span class="fila-estado">${f.vagaAberta ? 'Vaga aberta' : f.posicao + '.º na fila'}</span>
        </div>
        <div class="fila-quando">${escapar(f.quando)}</div>
      </div>
    `).join('');
  }

  // Badge do cabeçalho: número de filas; some quando é zero
  const badge = document.getElementById('badge-fila');
  badge.textContent = fila.length;
  badge.hidden = fila.length === 0;
}

renderizarFila();