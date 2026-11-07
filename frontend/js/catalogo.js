// ===== CATÁLOGO: como os códigos do backend aparecem na tela =====
// O backend guarda códigos ("sala", "vaga_carro", {"monitor": true}).
// Aqui ficam os textos e os ícones de cada código. Usado por várias páginas.

// Categorias: o backend devolve o nome ("Coworking"); o frontend usa um id curto
// ("coworking") para as cores do CSS (--coworking) e para os endereços (categoria.html?cat=coworking)
const CATEGORIAS_UI = {
  coworking:      { icon: "desk",          description: "Mesas individuais e salas de reunião" },
  estacionamento: { icon: "local_parking", description: "Vagas para carro e mota" },
  desporto:       { icon: "sports_tennis", description: "Padel e personal trainer" },
};

// Tipos de recurso (resource_type) de cada categoria: código → [texto, ícone]
const TIPOS_UI = {
  coworking:      { sala: ["Salas de reunião", "groups"], mesa: ["Mesas individuais", "desk"] },
  estacionamento: { vaga_carro: ["Carro", "directions_car"], vaga_mota: ["Mota", "two_wheeler"] },
  desporto:       { quadra: ["Padel", "sports_tennis"], personal: ["Personal trainer", "fitness_center"] },
};

// Atributos (attributes) de cada categoria: chave → [texto, ícone]
const ATRIBUTOS_UI = {
  coworking: {
    monitor: ["Monitor", "desktop_windows"], tem_projetor: ["Projetor", "slideshow"],
    videoconferencia: ["Videoconferência", "videocam"], quadro: ["Quadro", "edit_note"],
    janela: ["Janela", "window"], acessivel: ["Acessível", "accessible"],
  },
  estacionamento: {
    eletrico: ["Carregador EV", "ev_station"], coberta: ["Coberta", "roofing"],
    junto_elevador: ["Junto ao elevador", "elevator"], acessivel: ["Acessível", "accessible"],
  },
  desporto: {
    coberta: ["Coberta", "roofing"], iluminacao: ["Iluminação", "light_mode"],
    balneario: ["Balneário", "shower"], acessivel: ["Acessível", "accessible"],
  },
};

// "Coworking" → "coworking" (sem acentos, minúsculas). normalize("NFD") separa a letra do acento
function idCategoria(nome) {
  return nome.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}

// Texto e ícone de um tipo; se o código não estiver no dicionário, mostra o próprio código
function textoTipo(categoria, codigo) {
  return TIPOS_UI[categoria]?.[codigo]?.[0] ?? codigo;
}
function iconeTipo(categoria, codigo) {
  return TIPOS_UI[categoria]?.[codigo]?.[1] ?? CATEGORIAS_UI[categoria]?.icon ?? "category";
}

// {"monitor": true, "tem_projetor": false} → ["Monitor"] (só os atributos que estão a true)
function atributosEmTexto(categoria, atributos) {
  return Object.entries(atributos ?? {})
    .filter(([, valor]) => valor === true)
    .map(([chave]) => ATRIBUTOS_UI[categoria]?.[chave]?.[0] ?? chave);
}

// Capacidade em texto, como aparece nos cartões ("até 8 pessoas", "1 lugar"...)
function textoCapacidade(categoria, n) {
  if (categoria === "coworking") return n > 1 ? `até ${n} pessoas` : "1 pessoa";
  if (categoria === "estacionamento") return n > 1 ? `${n} lugares` : "1 lugar";
  return n > 1 ? `até ${n} participantes` : "1 participante";
}