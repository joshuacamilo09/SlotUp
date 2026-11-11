/* =====================================================================
   SlotUp – camada de acesso à API
   Todas as páginas falam com o backend por este arquivo.
   O Nginx encaminha /api/auth para o auth e /api/reservas para o booking.
   ===================================================================== */

const CONFIG = {
  API_BASE: "/api",   // mesmo endereço do site (via Nginx): não precisa de CORS
};

// Erro que guarda o código HTTP, para as telas reagirem (401, 409, 429...)
class ApiError extends Error {
  constructor(status, message, data) {
    super(message);
    this.status = status;
    this.data = data;
  }
}

/* ---------- Sessão: token de acesso + dados do utilizador ---------- */
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
// Lê a mensagem de erro do FastAPI: texto simples ou lista de erros de validação (422)
function parseDetail(data) {
  if (!data || !data.detail) return null;
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail)) return data.detail.map((d) => d.msg).join("; ");
  return null;
}

/**
 * Faz um pedido à API.
 * tokenTemporario: só no login (o pre_auth_token do 2FA).
 * Sem ele, usa o token de acesso guardado na sessão.
 */
async function request(method, path, body, tokenTemporario) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";  // só declara JSON quando há corpo
  const token = tokenTemporario || Auth.getToken();
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
  try { data = await res.json(); } catch (e) { /* resposta sem corpo (ex.: 204) */ }

  // Token de acesso expirado ou inválido: termina a sessão.
  // Não vale para o token temporário: aí um 401 significa só "código errado".
  if (res.status === 401 && !tokenTemporario && Auth.getToken()) {
    Auth.logout();
    throw new ApiError(401, "Sessão expirada.");
  }
  if (!res.ok) {
    throw new ApiError(res.status, parseDetail(data) || "Erro " + res.status, data);
  }
  return data;
}

const api = {
  // ----- Autenticação (auth-service) -----
  register:  (name, email, password) => request("POST", "/auth/register", { name, email, password }),
  login:     (email, password)       => request("POST", "/auth/login", { email, password }),
  setup2fa:  (preToken)              => request("POST", "/auth/2fa/setup", undefined, preToken),
  enable2fa: (preToken, code)        => request("POST", "/auth/2fa/enable", { code }, preToken),
  verify2fa: (preToken, code)        => request("POST", "/auth/2fa/verify", { code }, preToken),
  me:        ()                      => request("GET", "/auth/me"),

  // ----- Booking: categorias e recursos -----
  // includeInactive só funciona para o ADMIN (o backend devolve 403 aos outros)
  categories: (includeInactive) =>
    request("GET", "/reservas/categorias" + (includeInactive ? "?include_inactive=true" : "")),
  resources: ({ categoryId, includeInactive } = {}) => {
    const p = new URLSearchParams();                 // monta "?category_id=...&include_inactive=true"
    if (categoryId) p.set("category_id", categoryId);
    if (includeInactive) p.set("include_inactive", "true");
    const q = p.toString();
    return request("GET", "/reservas/recursos" + (q ? "?" + q : ""));
  },
  resource:       (id)        => request("GET", `/reservas/recursos/${id}`),
  createResource: (dados)     => request("POST", "/reservas/recursos", dados),
  updateResource: (id, dados) => request("PATCH", `/reservas/recursos/${id}`, dados),
  availability:   (id, dia)   => request("GET", `/reservas/recursos/${id}/disponibilidade?day=${dia}`),   // dia: "AAAA-MM-DD"

  // ----- Booking: reservas -----
  // start_at/end_at sem fuso ("2026-11-09T10:00") = hora local do complexo
  createReservation: (resource_id, start_at, end_at) =>
    request("POST", "/reservas/reservas", { resource_id, start_at, end_at }),
  // status opcional: "CONFIRMED", "HELD" ou "CANCELLED"
  myReservations: (periodo = "futuras", limit = 50, status) =>
    request("GET", `/reservas/reservas/minhas?periodo=${periodo}&limit=${limit}` + (status ? `&status=${status}` : "")),
  cancelReservation: (id) => request("POST", `/reservas/reservas/${id}/cancelar`),

  // ----- Booking: fila de espera -----
  joinWaitlist:  (resource_id, start_at, end_at) => request("POST", "/reservas/fila", { resource_id, start_at, end_at }),
  myWaitlist:    ()   => request("GET", "/reservas/fila/minhas"),
  acceptOffer:   (id) => request("POST", `/reservas/fila/${id}/aceitar`),
  leaveWaitlist: (id) => request("POST", `/reservas/fila/${id}/sair`),
};

/* ---------- Ajudantes do login ---------- */
/** Último passo do login: guarda o token, busca o perfil e vai para a home. */
async function concluirLogin(resposta) {
  Auth.setSession(resposta.access_token, null);   // o /me precisa do token já guardado
  const user = await api.me();
  Auth.setSession(resposta.access_token, user);
  location.href = "index.html";
}

/** Desenha o QR code do 2FA (biblioteca qrcode.js) dentro do elemento. */
function desenharQR(el, uri) {
  el.innerHTML = "";
  if (window.QRCode) new QRCode(el, { text: uri, width: 180, height: 180 });
  else el.textContent = "(QR indisponível – use a chave abaixo)";
}

async function comBotao(btn, alerta, acao) {
  hideAlert(alerta);
  btn.disabled = true;
  try {
    await acao();
  } catch (err) {
    showAlert(alerta, err.message);   // ex.: "Código inválido", "Demasiadas tentativas..."
  } finally {
    btn.disabled = false;
  }
}

/** Pede o segredo do 2FA e mostra o QR code e a chave (ids "qrcode" e "secret"). */
async function prepararSetup2fa(preToken) {
  const setup = await api.setup2fa(preToken);
  desenharQR(document.getElementById("qrcode"), setup.otpauth_uri);
  // Chave em grupos de 4 letras: mais fácil de copiar à mão
  document.getElementById("secret").textContent = setup.secret.match(/.{1,4}/g).join(" ");
}

/* ---------- Utilitários de interface ---------- */
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function toISODate(d) {
  const p = (n) => String(n).padStart(2, "0");
  return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate());
}

function fmtDateTime(iso) {
  return new Date(iso).toLocaleString("pt-PT", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
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

/** Manda para o login se não houver sessão. Devolve o utilizador. */
function requireAuth() {
  if (!Auth.getToken()) {
    location.href = "login.html";
    return null;
  }
  return Auth.getUser();
}