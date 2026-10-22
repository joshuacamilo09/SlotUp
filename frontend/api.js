/* =====================================================================
   SlotUp – camada de acesso à API
   Todas as páginas falam com o backend através deste ficheiro.
   Para mudar o endereço do backend, altera só CONFIG.API_BASE.
   ===================================================================== */

const CONFIG = {
  // Em produção o Nginx faz proxy de /api para o FastAPI (ver README).
  // Em desenvolvimento local, sem Nginx, usa por exemplo "http://localhost:8000/api"
  // (e ativa o CORS no FastAPI).
  API_BASE: "/api",
};

// Modo de demonstração: ?mock=1 liga, ?mock=0 desliga (fica guardado no browser).
(function () {
  const p = new URLSearchParams(location.search).get("mock");
  try {
    if (p === "1") localStorage.setItem("slotup_mock", "1");
    if (p === "0") localStorage.removeItem("slotup_mock");
    CONFIG.USE_MOCK = localStorage.getItem("slotup_mock") === "1";
  } catch (e) {
    CONFIG.USE_MOCK = p === "1";
  }
})();

class ApiError extends Error {
  constructor(status, message, data) {
    super(message);
    this.status = status;
    this.data = data;
  }
}

/* ---------- Sessão ---------- */
const Auth = {
  getToken: () => localStorage.getItem("slotup_token"),
  getUser() {
    try { return JSON.parse(localStorage.getItem("slotup_user")); } catch (e) { return null; }
  },
  setSession(token, user) {
    localStorage.setItem("slotup_token", token);
    localStorage.setItem("slotup_user", JSON.stringify(user));
  },
  clear() {
    localStorage.removeItem("slotup_token");
    localStorage.removeItem("slotup_user");
  },
  logout() {
    Auth.clear();
    location.href = "login.html";
  },
};

/* ---------- Pedidos HTTP ---------- */
function parseDetail(data) {
  if (!data || !data.detail) return null;
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail)) {
    // erros de validação do FastAPI (422)
    return data.detail.map((d) => d.msg).join("; ");
  }
  return null;
}

async function request(method, path, body) {
  if (CONFIG.USE_MOCK) return window.mockRequest(method, path, body);

  const headers = { "Content-Type": "application/json" };
  const token = Auth.getToken();
  if (token) headers.Authorization = "Bearer " + token;

  let res;
  try {
    res = await fetch(CONFIG.API_BASE + path, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    throw new ApiError(0, "Não foi possível contactar o servidor.");
  }

  let data = null;
  try { data = await res.json(); } catch (e) { /* resposta sem corpo */ }

  if (res.status === 401 && token) {
    // token expirado ou inválido
    Auth.clear();
    location.href = "login.html";
  }
  if (!res.ok) {
    throw new ApiError(res.status, parseDetail(data) || "Erro " + res.status, data);
  }
  return data;
}

const api = {
  // Autenticação
  register: (nome, email, password) => request("POST", "/auth/register", { nome, email, password }),
  login: (email, password) => request("POST", "/auth/login", { email, password }),
  verify2fa: (temp_token, code) => request("POST", "/auth/2fa/verify", { temp_token, code }),
  me: () => request("GET", "/auth/me"),

  // Recursos
  categories: () => request("GET", "/categories"),
  resources: (categoryId) =>
    request("GET", "/resources" + (categoryId ? "?category_id=" + encodeURIComponent(categoryId) : "")),
  availability: (resourceId, date) =>
    request("GET", "/resources/" + resourceId + "/availability?date=" + encodeURIComponent(date)),

  // Reservas
  createBooking: (resource_id, start, end) => request("POST", "/bookings", { resource_id, start, end }),
  myBookings: () => request("GET", "/bookings/me"),
  cancelBooking: (id) => request("DELETE", "/bookings/" + id),
  joinWaitlist: (resource_id, start, end) => request("POST", "/waitlist", { resource_id, start, end }),
};

/* ---------- Utilitários de interface ---------- */
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function toISODate(d) {
  const p = (n) => String(n).padStart(2, "0");
  return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate());
}

function fmtDateTime(iso) {
  const d = new Date(iso);
  return d.toLocaleString("pt-PT", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function toast(msg, isError) {
  const el = document.createElement("div");
  el.className = "toast" + (isError ? " error" : "");
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

function showAlert(el, msg, kind) {
  el.textContent = msg;
  el.className = "alert " + (kind || "error");
}

function hideAlert(el) {
  el.className = "alert hidden";
  el.textContent = "";
}

/** Redireciona para o login se não houver sessão. Devolve o utilizador. */
function requireAuth() {
  if (!Auth.getToken()) {
    location.href = "login.html";
    return null;
  }
  return Auth.getUser();
}

/** Desenha a barra de navegação dentro de <div id="nav"></div>. */
function renderNav(active) {
  const user = Auth.getUser();
  const link = (href, label, key) =>
    '<a href="' + href + '"' + (active === key ? ' class="active"' : "") + ">" + label + "</a>";
  document.getElementById("nav").innerHTML =
    '<nav class="nav"><div class="nav-inner">' +
    '<a class="brand" href="resources.html">Slot<span>Up</span></a>' +
    '<div class="nav-links">' +
    link("resources.html", "Recursos", "resources") +
    link("bookings.html", "As minhas reservas", "bookings") +
    "</div>" +
    '<div class="nav-user">' +
    (user ? "<span>" + esc(user.nome || user.email) + "</span>" : "") +
    (CONFIG.USE_MOCK ? '<span class="badge concluida">demo</span>' : "") +
    '<button class="btn secondary small" id="logout-btn">Terminar sessão</button>' +
    "</div></div></nav>";
  document.getElementById("logout-btn").addEventListener("click", Auth.logout);
}
