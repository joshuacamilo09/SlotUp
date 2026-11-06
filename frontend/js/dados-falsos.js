// ===== DADOS FICTÍCIOS (por agora) =====
// Tudo o que vai vir da API está neste objeto, para ser trocado depois por fetch.
// Os nomes dos campos são provisórios: vão ser alinhados com o booking-service.
// "ocupados" repete-se todos os dias; "dia" em minhas/fila = dias a partir de hoje (0 = hoje).
const DADOS_FALSOS = {
  categorias: {
    coworking:      { name: "Coworking",      icon: "desk",          description: "Mesas individuais e salas de reunião" },
    estacionamento: { name: "Estacionamento", icon: "local_parking", description: "Vagas nos pisos -1 e -2" },
    desporto:       { name: "Desporto",       icon: "sports_tennis", description: "Ginásio, personal trainer, pilates e padel" },
  },
  recursos: [
    { id: 1,  category: "coworking", type: "Salas de reunião",  icon: "groups", name: "Sala Atlântico",    location: "Piso 2", capacity: "até 8 pessoas",  tags: ["Ecrã", "Videoconferência"],       ocupados: [["09:00", "10:30"], ["13:00", "14:30"], ["18:00", "19:00"]] },
    { id: 2,  category: "coworking", type: "Salas de reunião",  icon: "groups", name: "Sala Índico",       location: "Piso 2", capacity: "até 8 pessoas",  tags: ["Videoconferência", "Quadro"],     ocupados: [["08:30", "10:00"], ["14:00", "16:00"]] },
    { id: 3,  category: "coworking", type: "Salas de reunião",  icon: "groups", name: "Sala Báltico",      location: "Piso 3", capacity: "até 6 pessoas",  tags: ["Ecrã"],                           ocupados: [["09:00", "12:00"], ["13:00", "17:30"]] },
    { id: 4,  category: "coworking", type: "Salas de reunião",  icon: "groups", name: "Sala Mediterrâneo", location: "Piso 3", capacity: "até 12 pessoas", tags: ["Ecrã duplo", "Videoconferência"], ocupados: [["15:00", "18:00"]] },
    { id: 5,  category: "coworking", type: "Salas de reunião",  icon: "groups", name: "Sala Cáspio",       location: "Piso 4", capacity: "até 10 pessoas", tags: ["Ecrã", "Videoconferência"],       ocupados: [["12:00", "13:00"]] },
    { id: 6,  category: "coworking", type: "Mesas individuais", icon: "desk",   name: "Mesa 2.14", location: "Piso 2 · open space",      capacity: "1 pessoa", tags: ["Monitor"],           ocupados: [["08:00", "13:00"]] },
    { id: 7,  category: "coworking", type: "Mesas individuais", icon: "desk",   name: "Mesa 2.15", location: "Piso 2 · open space",      capacity: "1 pessoa", tags: ["Monitor", "Janela"], ocupados: [["14:00", "18:00"]] },
    { id: 8,  category: "coworking", type: "Mesas individuais", icon: "desk",   name: "Mesa 3.01", location: "Piso 3 · zona silenciosa", capacity: "1 pessoa", tags: ["Monitor"],           ocupados: [] },

    { id: 9,  category: "estacionamento", type: "Piso -1", icon: "directions_car", name: "Vaga P-012", location: "Piso -1", capacity: "Ligeiro", tags: ["Junto ao elevador"], ocupados: [["08:00", "18:00"]] },
    { id: 10, category: "estacionamento", type: "Piso -1", icon: "directions_car", name: "Vaga P-114", location: "Piso -1", capacity: "Ligeiro", tags: [],                    ocupados: [["08:00", "12:00"]] },
    { id: 11, category: "estacionamento", type: "Piso -1", icon: "ev_station",     name: "Vaga P-115", location: "Piso -1", capacity: "Ligeiro", tags: ["Carregador EV"],     ocupados: [] },
    { id: 12, category: "estacionamento", type: "Piso -2", icon: "ev_station",     name: "Vaga P-203", location: "Piso -2", capacity: "Ligeiro", tags: ["Carregador EV"],     ocupados: [["09:00", "17:00"]] },
    { id: 13, category: "estacionamento", type: "Piso -2", icon: "two_wheeler",    name: "Vaga P-204", location: "Piso -2", capacity: "Mota",    tags: [],                    ocupados: [["13:00", "19:00"]] },

    { id: 14, category: "desporto", type: "Padel",   icon: "sports_tennis",    name: "Quadra de padel 1",       location: "Exterior",            capacity: "4 jogadores",       tags: ["Iluminação"],            ocupados: [["12:00", "13:00"], ["18:00", "20:00"]] },
    { id: 15, category: "desporto", type: "Padel",   icon: "sports_tennis",    name: "Quadra de padel 2",       location: "Exterior",            capacity: "4 jogadores",       tags: ["Iluminação", "Coberta"], ocupados: [["17:00", "18:30"]] },
    { id: 16, category: "desporto", type: "Ginásio", icon: "fitness_center",   name: "Personal trainer · Rui",  location: "Ginásio",             capacity: "Sessão individual", tags: ["Força", "Mobilidade"],   ocupados: [["08:00", "10:00"], ["17:00", "19:00"]] },
    { id: 17, category: "desporto", type: "Ginásio", icon: "fitness_center",   name: "Personal trainer · Inês", location: "Ginásio",             capacity: "Sessão individual", tags: ["Cardio"],                ocupados: [["12:00", "14:00"]] },
    { id: 18, category: "desporto", type: "Pilates", icon: "self_improvement", name: "Pilates · Sofia",         location: "Ginásio · estúdio 1", capacity: "Sessão individual", tags: ["Reformer"],              ocupados: [["09:00", "10:00"], ["18:00", "19:00"]] },
  ],
  minhas: [
    { resource_id: 1,  dia: 0, start: "11:00", end: "12:00" },
    { resource_id: 11, dia: 1, start: "08:30", end: "18:00" },
    { resource_id: 15, dia: 3, start: "09:00", end: "10:30" },
  ],
  fila: [
    { resource_id: 16, dia: 1, start: "08:00", end: "09:00" },
  ],
};