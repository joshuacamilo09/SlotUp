/* =====================================================================
   SlotUp – backend simulado (só para demonstração do frontend)
   Ativa-se com ?mock=1 na URL. Não é carregado em produção se não for
   incluído nas páginas. Código 2FA aceite: 123456
   ===================================================================== */

(function () {
  const MOCK_CODE = "123456";
  const MOCK_SECRET = "JBSWY3DPEHPK3PXP";

  const categories = [
    { id: 1, nome: "Coworking" },
    { id: 2, nome: "Estacionamento" },
    { id: 3, nome: "Desporto" },
  ];

  const resources = [
    { id: 1, category_id: 1, nome: "Mesa 1", descricao: "Posto de trabalho individual" },
    { id: 2, category_id: 1, nome: "Mesa 2", descricao: "Posto de trabalho individual" },
    { id: 3, category_id: 1, nome: "Sala de reunião A", descricao: "Até 6 pessoas" },
    { id: 4, category_id: 1, nome: "Sala de reunião B", descricao: "Até 10 pessoas" },
    { id: 5, category_id: 2, nome: "Lugar P1", descricao: "Piso -1" },
    { id: 6, category_id: 2, nome: "Lugar P2", descricao: "Piso -1" },
    { id: 7, category_id: 2, nome: "Lugar P3", descricao: "Piso -2" },
    { id: 8, category_id: 3, nome: "Ginásio com personal trainer", descricao: "Sessão de 1 hora" },
    { id: 9, category_id: 3, nome: "Quadra de padel", descricao: "Quadra coberta" },
  ];

  const HOURS = [8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19];
  const KEY = "slotup_mock_bookings";

  const load = () => { try { return JSON.parse(localStorage.getItem(KEY)) || []; } catch (e) { return []; } };
  const save = (b) => localStorage.setItem(KEY, JSON.stringify(b));
  const pad = (n) => String(n).padStart(2, "0");
  const delay = (v) => new Promise((r) => setTimeout(() => r(v), 150));
  const fail = (status, detail) => Promise.reject(new ApiError(status, detail, { detail }));

  // Alguns horários aparecem sempre ocupados, para se poder testar a fila de espera.
  function busyByDefault(resourceId, date, hour) {
    const day = Number(date.slice(-2));
    return (resourceId * 7 + hour + day) % 6 === 0;
  }

  function slotTaken(bookings, resourceId, startIso) {
    return bookings.some((b) => b.resource_id === resourceId && b.status === "confirmada" && b.start.slice(0, 16) === startIso.slice(0, 16));
  }

  window.mockRequest = async function (method, fullPath, body) {
    const url = new URL(fullPath, "http://x");
    const path = url.pathname;
    const q = url.searchParams;

    // ----- Autenticação -----
    if (method === "POST" && path === "/auth/register") {
      return delay({
        temp_token: "mock-temp",
        totp_secret: MOCK_SECRET,
        totp_uri: "otpauth://totp/SlotUp:" + encodeURIComponent(body.email) + "?secret=" + MOCK_SECRET + "&issuer=SlotUp",
        nome: body.nome,
        email: body.email,
      });
    }
    if (method === "POST" && path === "/auth/login") {
      if (!body.email || !body.password) return fail(401, "Credenciais inválidas.");
      return delay({ requires_2fa: true, temp_token: "mock-temp:" + body.email });
    }
    if (method === "POST" && path === "/auth/2fa/verify") {
      if (body.code !== MOCK_CODE) return fail(401, "Código 2FA inválido (em modo demo usa 123456).");
      const email = (body.temp_token.split(":")[1]) || "demo@slotup.pt";
      return delay({
        access_token: "mock-token",
        token_type: "bearer",
        user: { id: 1, nome: email.split("@")[0], email, role: "user" },
      });
    }
    if (method === "GET" && path === "/auth/me") return delay(Auth.getUser());

    // Daqui para a frente é preciso sessão
    if (!Auth.getToken()) return fail(401, "Não autenticado.");

    // ----- Recursos -----
    if (method === "GET" && path === "/categories") return delay(categories);
    if (method === "GET" && path === "/resources") {
      const cat = q.get("category_id");
      return delay(cat ? resources.filter((r) => r.category_id === Number(cat)) : resources);
    }
    let m = path.match(/^\/resources\/(\d+)\/availability$/);
    if (method === "GET" && m) {
      const rid = Number(m[1]);
      const date = q.get("date");
      const bookings = load();
      const slots = HOURS.map((h) => {
        const start = date + "T" + pad(h) + ":00:00";
        return {
          start: pad(h) + ":00",
          end: pad(h + 1) + ":00",
          available: !busyByDefault(rid, date, h) && !slotTaken(bookings, rid, start),
        };
      });
      return delay(slots);
    }

    // ----- Reservas -----
    if (method === "POST" && path === "/bookings") {
      const bookings = load();
      const date = body.start.slice(0, 10);
      const hour = Number(body.start.slice(11, 13));
      if (busyByDefault(body.resource_id, date, hour) || slotTaken(bookings, body.resource_id, body.start)) {
        return fail(409, "Este recurso já está reservado nesse horário.");
      }
      const r = resources.find((x) => x.id === body.resource_id);
      const c = categories.find((x) => x.id === r.category_id);
      const booking = {
        id: Date.now(),
        resource_id: r.id,
        resource_nome: r.nome,
        category_nome: c.nome,
        start: body.start,
        end: body.end,
        status: "confirmada",
      };
      bookings.push(booking);
      save(bookings);
      return delay(booking);
    }
    if (method === "GET" && path === "/bookings/me") return delay(load());
    m = path.match(/^\/bookings\/(\d+)$/);
    if (method === "DELETE" && m) {
      const bookings = load();
      const b = bookings.find((x) => x.id === Number(m[1]));
      if (!b) return fail(404, "Reserva não encontrada.");
      b.status = "cancelada";
      save(bookings);
      return delay(b);
    }
    if (method === "POST" && path === "/waitlist") {
      return delay({ position: 1 });
    }

    return fail(404, "Endpoint não encontrado (mock): " + method + " " + path);
  };
})();
