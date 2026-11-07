// ===== CABEÇALHO COMUM =====
// Desenha o cabeçalho dentro de <div id="cabecalho"></div> em todas as páginas.
// Precisa do js/api.js carregado ANTES (usa Auth, requireAuth e esc).

// Função que se executa logo: as variáveis daqui não "vazam" para o JS de cada página
(function () {
  const utilizador = requireAuth();
  if (!utilizador) return;   // sem sessão: o requireAuth já mandou para o login

  // Nome do arquivo da página atual ("index.html", "reservas.html"...). Em "/" vale index.html
  const pagina = location.pathname.split("/").pop() || "index.html";

  // Itens do menu e as páginas que pertencem a cada um (categoria e recurso fazem parte do "Início")
  const LINKS = [
    { href: "index.html",    texto: "Início",          paginas: ["index.html", "categoria.html", "recurso.html"] },
    { href: "reservas.html", texto: "Minhas reservas", paginas: ["reservas.html"], badge: true },
  ];
  if (utilizador.role === "ADMIN") {
    LINKS.push({ href: "admin.html", texto: "Administração", paginas: ["admin.html", "novo-recurso.html"] });
  }

  // Iniciais do avatar: primeira letra do primeiro e do último nome ("Marta Sousa" → "MS")
  const partes = (utilizador.name ?? "").trim().split(/\s+/);
  const iniciais = ((partes[0]?.[0] ?? "") + (partes.length > 1 ? partes.at(-1)[0] : "")).toUpperCase();

  // HTML dos links; "ativo" marca o item da página atual.
  // O badge começa escondido: cada página preenche o número (ex.: home.js com a fila de espera)
  const linksHtml = LINKS.map((l) => `
    <a href="${l.href}" class="nav-link${l.paginas.includes(pagina) ? " ativo" : ""}">
      ${l.texto}${l.badge ? '<span class="badge" id="badge-fila" hidden></span>' : ""}
    </a>`).join("");

  document.getElementById("cabecalho").innerHTML = `
    <header class="topbar">
      <a href="index.html" class="logo">
        <svg width="17" height="28" viewBox="0 0 24 40" aria-hidden="true">
          <rect x="2" y="2" width="20" height="36" rx="10" fill="none" stroke="currentColor" stroke-width="4"/>
          <circle cx="12" cy="12" r="5.5" fill="currentColor"/>
        </svg>
        SlotUp
      </a>

      <nav class="nav">${linksHtml}</nav>

      <div class="topbar-direita">
        <div class="perfil">
          <button class="avatar" id="avatar-btn" title="Perfil" aria-haspopup="true" aria-expanded="false">
            <span class="avatar-circulo">${esc(iniciais)}</span>
            <span class="icone">expand_more</span>
          </button>

          <div class="menu-perfil" id="menu-perfil" hidden>
            <div class="menu-perfil-topo">
              <span class="avatar-circulo">${esc(iniciais)}</span>
              <div class="menu-perfil-dados">
                <div class="menu-perfil-nome">${esc(utilizador.name)}</div>
                <div class="menu-perfil-email">${esc(utilizador.email)}</div>
              </div>
            </div>
            <!-- "Alterar palavra-passe" entra quando o auth tiver a rota (tarefa no ClickUp) -->
            <button class="menu-item perigo" id="sair-btn"><span class="icone">logout</span>Sair</button>
          </div>
        </div>
      </div>
    </header>`;

  // ----- Abrir e fechar o menu do perfil -----
  const botao = document.getElementById("avatar-btn");
  const menu = document.getElementById("menu-perfil");

  function abrirMenu(abrir) {
    menu.hidden = !abrir;
    botao.setAttribute("aria-expanded", abrir);   // acessibilidade: leitores de ecrã sabem se está aberto
  }

  botao.addEventListener("click", (e) => {
    e.stopPropagation();          // sem isto, o clique chegava ao "document" abaixo e fechava logo
    abrirMenu(menu.hidden);       // se está escondido abre, se está aberto fecha
  });
  document.addEventListener("click", (e) => {
    if (!menu.contains(e.target)) abrirMenu(false);   // clique fora do menu fecha
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") abrirMenu(false);         // Esc fecha
  });
  document.getElementById("sair-btn").addEventListener("click", Auth.logout);
})();